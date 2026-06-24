"""Searcher 单元测试 — Tavily API 调用、子 step 管理、URL 去重、失败重试。"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import SearchFailedException
from app.models.research_task import ResearchTask
from app.models.research_step import ResearchStep
from app.models.research_source import ResearchSource
from app.pipeline.searcher import (
    run_search,
    _extract_domain,
    _get_sub_questions_from_planning,
)


# ═══════════════════════════════════════════════════════════════
# 工具函数测试
# ═══════════════════════════════════════════════════════════════


class TestExtractDomain:
    """域名提取。"""

    def test_标准URL提取域名(self):
        assert _extract_domain("https://example.com/page") == "example.com"

    def test_含端口URL(self):
        assert _extract_domain("http://localhost:8080/path") == "localhost:8080"

    def test_无效URL返回原文(self):
        assert _extract_domain("not-a-url") == "not-a-url"


class TestGetSubQuestionsFromPlanning:
    """从 Planning 输出中提取 sub_questions。"""

    def test_正常提取(self):
        parent = MagicMock(spec=ResearchStep)
        parent.output = {"sub_questions": ["q1", "q2", "q3"]}
        step = MagicMock(spec=ResearchStep)
        step.parent_step = parent

        result = _get_sub_questions_from_planning(step)
        assert result == ["q1", "q2", "q3"]

    def test_parent不存在(self):
        step = MagicMock(spec=ResearchStep)
        step.parent_step = None
        result = _get_sub_questions_from_planning(step)
        assert result == []

    def test_parent_output为None(self):
        parent = MagicMock(spec=ResearchStep)
        parent.output = None
        step = MagicMock(spec=ResearchStep)
        step.parent_step = parent
        result = _get_sub_questions_from_planning(step)
        assert result == []

    def test_parent_output无sub_questions(self):
        parent = MagicMock(spec=ResearchStep)
        parent.output = {"other": "data"}
        step = MagicMock(spec=ResearchStep)
        step.parent_step = parent
        result = _get_sub_questions_from_planning(step)
        assert result == []


# ═══════════════════════════════════════════════════════════════
# 辅助工厂
# ═══════════════════════════════════════════════════════════════


def _make_task(**overrides) -> MagicMock:
    """创建模拟 ResearchTask（MagicMock），避免 ORM backref 问题。"""
    defaults = {
        "id": "task-uuid-001",
        "user_id": 1,
        "topic": "量子计算",
        "requirements": {"task_type": "analysis", "max_sources": 10},
        "status": "running",
        "current_phase": "searching",
        "total_steps": 2,
        "completed_steps": 1,
        "total_sources": 0,
        "total_evidence": 0,
    }
    defaults.update(overrides)
    task = MagicMock()
    for k, v in defaults.items():
        setattr(task, k, v)
    return task


def _make_step(**overrides) -> MagicMock:
    """创建模拟 ResearchStep（MagicMock），避免 ORM backref 问题。"""
    defaults = {
        "id": "step-uuid-search-root",
        "task_id": "task-uuid-001",
        "step_type": "search",
        "status": "running",
        "label": "Search：多子问题搜索",
    }
    defaults.update(overrides)
    step = MagicMock(spec=ResearchStep)
    for k, v in defaults.items():
        setattr(step, k, v)

    # 模拟 parent_step（Planning 输出）
    parent = MagicMock(spec=ResearchStep)
    parent.output = {
        "sub_questions": [
            "量子计算对密码学的威胁",
            "后量子密码标准化进展",
            "NIST后量子密码竞赛结果",
        ],
    }
    step.parent_step = parent
    return step


def _make_tavily_response(urls: list[str]) -> dict:
    """构建模拟 Tavily API 返回（包装在 dict 中）。"""
    return {
        "results": [
            {
                "url": url,
                "title": f"Title for {url}",
                "content": f"Content snippet for {url}",
                "score": 0.9 - i * 0.05,
            }
            for i, url in enumerate(urls)
        ],
        "query": "test query",
    }


# ═══════════════════════════════════════════════════════════════
# run_search 正常流程
# ═══════════════════════════════════════════════════════════════


class TestRunSearchSuccess:
    """正常搜索流程。"""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.task = _make_task()
        self.step = _make_step()
        self.sse_bridge = MagicMock()
        self.db_session = AsyncMock()

    @pytest.mark.asyncio
    async def test_正常搜索_返回去重结果(self):
        with patch("app.pipeline.searcher._call_tavily") as mock_tavily:
            # 每个子问题返回2条结果
            mock_tavily.side_effect = [
                _make_tavily_response(["https://a.com/1", "https://a.com/2"]),
                _make_tavily_response(["https://b.com/1", "https://b.com/2"]),
                _make_tavily_response(["https://c.com/1", "https://c.com/2"]),
            ]

            output = await run_search(
                self.task, self.step, self.db_session, self.sse_bridge,
            )

            assert output["after_dedup"] == 6
            assert output["sources_created"] == 6
            assert mock_tavily.call_count == 3

    @pytest.mark.asyncio
    async def test_跨子问题URL去重(self):
        with patch("app.pipeline.searcher._call_tavily") as mock_tavily:
            mock_tavily.side_effect = [
                _make_tavily_response(["https://a.com/1", "https://shared.com/page"]),
                _make_tavily_response(["https://shared.com/page", "https://b.com/1"]),
                _make_tavily_response(["https://c.com/1"]),
            ]

            output = await run_search(
                self.task, self.step, self.db_session, self.sse_bridge,
            )

            # shared.com/page 被去重，所以只有 4 条唯一 URL
            assert output["after_dedup"] == 4

    @pytest.mark.asyncio
    async def test_搜索后创建_ResearchSource_行(self):
        with patch("app.pipeline.searcher._call_tavily") as mock_tavily:
            mock_tavily.return_value = _make_tavily_response(["https://example.com/article"])

            await run_search(
                self.task, self.step, self.db_session, self.sse_bridge,
            )

            # 验证 session.add 被调用（创建 ResearchSource）
            add_calls = [
                c for c in self.db_session.add.call_args_list
                if isinstance(c[0][0], ResearchSource)
            ]
            assert len(add_calls) == 1  # 每个 URL 一个 source

    @pytest.mark.asyncio
    async def test_子_step_SSE_事件已发射(self):
        with patch("app.pipeline.searcher._call_tavily") as mock_tavily:
            mock_tavily.return_value = _make_tavily_response(["https://example.com/1"])

            await run_search(
                self.task, self.step, self.db_session, self.sse_bridge,
            )

            # 验证发射了 step.started / step.progress / step.completed
            event_types = [
                c[0][0] for c in self.sse_bridge.publish.call_args_list
            ]
            assert "step.started" in event_types
            assert "step.progress" in event_types
            assert "step.completed" in event_types

    @pytest.mark.asyncio
    async def test_无子问题输入_返回空结果(self):
        # 无 Planning parent 输出
        self.step.parent_step = None

        output = await run_search(
            self.task, self.step, self.db_session, self.sse_bridge,
        )

        assert output["total_results"] == 0
        assert "无子问题输入" in output["message"]


class TestRunSearchFailure:
    """失败策略：单子问题降级 / 全失败 E3102。"""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.task = _make_task()
        self.step = _make_step()
        self.sse_bridge = MagicMock()
        self.db_session = AsyncMock()

    @pytest.mark.asyncio
    async def test_单子问题0结果_子step_SKIPPED(self):
        with patch("app.pipeline.searcher._call_tavily") as mock_tavily:
            mock_tavily.side_effect = [
                {"results": []},  # 子问题1: 0结果
                _make_tavily_response(["https://b.com/1"]),  # 子问题2
                _make_tavily_response(["https://c.com/1"]),  # 子问题3
            ]

            output = await run_search(
                self.task, self.step, self.db_session, self.sse_bridge,
            )

            # 子问题1 应标记为 skipped
            sq1_result = output["sub_question_results"][0]
            assert sq1_result["status"] == "skipped"
            assert output["after_dedup"] == 2  # 去重后结果数

    @pytest.mark.asyncio
    async def test_全部子问题失败_抛出E3102(self):
        with patch("app.pipeline.searcher._call_tavily") as mock_tavily:
            # 全部失败
            mock_tavily.side_effect = RuntimeError("API不可用")

            with pytest.raises(SearchFailedException) as exc_info:
                await run_search(
                    self.task, self.step, self.db_session, self.sse_bridge,
                )

            assert exc_info.value.error_code == "E3102"

    @pytest.mark.asyncio
    async def test_子问题失败后重试(self):
        with patch("app.pipeline.searcher._call_tavily") as mock_tavily:
            mock_tavily.side_effect = [
                RuntimeError("第一次失败"),
                _make_tavily_response(["https://recovered.com/1"]),  # 重试成功
            ]
            # 只保留1个子问题来测试重试
            self.step.parent_step.output = {
                "sub_questions": ["单个子问题"],
            }

            output = await run_search(
                self.task, self.step, self.db_session, self.sse_bridge,
            )

            assert mock_tavily.call_count == 2  # 原始 + 1次重试
            assert output["after_dedup"] == 1
