"""策略感知 Search 阶段验收测试 — knowledge/web/hybrid 分流与查询域隔离。

对齐 RESEARCH_PIPELINE.md §3/§5.3/§6.1、ADR-010 与 API.md §8.1：
- `knowledge` 策略：只走 Internal Retrieval，绝不调用 Tavily，不创建 Web ResearchSource；
- `web` 策略：走既有 Tavily 路径（回归）；
- `hybrid` 策略：内部检索 + Web 搜索，Web Query 只来自原始 Topic / 公开子问题，
  绝不包含内部 excerpt、内部文档标题或内部命名；
- KB_FORBIDDEN / 用户禁用 → fail-closed，不得降级为 Web。

SDD 门禁：RED —— 目标行为（策略感知检索）当前缺失。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.core.exceptions import (
    InternalKnowledgeForbiddenException,
)
from app.models.research_step import ResearchStep
from app.pipeline.searcher import run_search

KB_A = "11111111-1111-4111-8111-111111111111"
KB_B = "22222222-2222-4222-8222-222222222222"


def _make_task(**overrides) -> MagicMock:
    """创建模拟 ResearchTask。"""
    defaults = {
        "id": "task-uuid-001",
        "user_id": "550e8400-e29b-41d4-a716-446655440001",
        "topic": "量子计算对密码学的影响",
        "requirements": {"task_type": "analysis", "max_sources": 10, "language": "zh"},
        "source_strategy": "web",
        "status": "running",
        "current_phase": "searching",
        "total_steps": 7,
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
    return step


def _make_planning_step(sub_questions: list[str]) -> MagicMock:
    step = MagicMock(spec=ResearchStep)
    step.output = {"sub_questions": sub_questions}
    step.status = "completed"
    step.completed_at = None
    return step


def _hit(hit_id: str, doc_id: str, excerpt: str = "内部正文片段") -> dict:
    return {
        "hit_id": hit_id,
        "knowledge_base_id": KB_A,
        "document_id": doc_id,
        "document_version_id": "550e8400-e29b-41d4-a716-446655440031",
        "segment_id": f"{doc_id}-seg1",
        "document_display_name": "内部权限设计文档",
        "section_title": "权限矩阵",
        "location": {"page_number": 3},
        "minimal_excerpt": excerpt,
        "scores": [{"score_kind": "vector", "value": 0.87, "rank": 0}],
        "source_updated_at": "2026-08-03T09:00:00Z",
        "retrieved_at": "2026-08-04T12:00:00Z",
        "access_scope": "internal",
    }


def _retrieval_response(hits: list[dict]):
    from app.core.internal_retrieval_client import RetrievalHit, RetrievalSearchResult

    return RetrievalSearchResult(
        contract_version="1.0.0",
        request_id="req-1",
        results=[
            RetrievalHit(
                hit_id=str(h["hit_id"]),
                knowledge_base_id=str(h["knowledge_base_id"]),
                document_id=str(h["document_id"]),
                document_version_id=str(h["document_version_id"]),
                segment_id=str(h["segment_id"]),
                document_display_name=str(h.get("document_display_name") or ""),
                section_title=h.get("section_title"),
                location=h.get("location") or {},
                minimal_excerpt=str(h.get("minimal_excerpt") or ""),
                scores=h.get("scores") or [],
                source_updated_at=str(h.get("source_updated_at") or ""),
                retrieved_at=str(h.get("retrieved_at") or ""),
                access_scope=str(h.get("access_scope") or "internal"),
            )
            for h in hits
        ],
        returned_count=len(hits),
        has_more=False,
    )


def _mock_planning_in_session(session: AsyncMock, sub_questions: list[str]) -> None:
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = _make_planning_step(sub_questions)
    session.execute.return_value = result_mock


def _setup_search_session(
    session: AsyncMock,
    sub_questions: list[str],
    kb_ids: list[str],
    *,
    existing_urls: list[str] | None = None,
) -> None:
    """配置 session.execute 依次返回 planning → KB 选择行 → planning → 既有 URL。

    execute 调用顺序（实现既定）：
    knowledge/hybrid：`_load_sub_questions`（planning）→ `_load_kb_ids`（KB 行）；
    web（含 hybrid）：`_load_sub_questions`（planning）→ 既有 URL 查询。
    """
    planning_result = MagicMock()
    planning_result.scalar_one_or_none.return_value = _make_planning_step(sub_questions)

    kb_result = MagicMock()
    kb_result.all.return_value = [(kb_id,) for kb_id in kb_ids]

    existing_result = MagicMock()
    existing_result.all.return_value = [(url,) for url in (existing_urls or [])]

    session.execute.side_effect = [
        planning_result,  # knowledge 通道：_load_sub_questions
        kb_result,  # knowledge 通道：_load_kb_ids
        planning_result,  # web 通道：_load_sub_questions（hybrid）
        existing_result,  # web 通道：既有 URL 查询（hybrid）
    ]


DEFAULT_SUB_QUESTIONS = [
    "量子计算对 RSA 的威胁程度",
    "后量子密码标准化进展",
    "NIST 后量子密码竞赛结果",
]


class TestKnowledgeStrategySearch:
    """knowledge 策略：只走 Internal Retrieval，不调用 Tavily，产出内部候选。"""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.task = _make_task(source_strategy="knowledge", knowledge_base_ids=[KB_A])
        self.step = _make_step()
        self.sse_bridge = AsyncMock()
        self.db_session = AsyncMock()
        _setup_search_session(self.db_session, DEFAULT_SUB_QUESTIONS, [KB_A])

    @pytest.mark.asyncio
    async def test_knowledge_策略_调用InternalRetrieval且不调用Tavily(self):
        mock_retrieval = AsyncMock(return_value=_retrieval_response([_hit("h1", "doc-1")]))
        with (
            patch(
                "app.pipeline.searcher.internal_retrieval_client.search_retrieval",
                mock_retrieval,
            ),
            patch(
                "app.pipeline.searcher._call_tavily",
                AsyncMock(side_effect=AssertionError("knowledge 策略不得调用 Tavily")),
            ) as mock_tavily,
        ):
            output = await run_search(
                self.task,
                self.step,
                self.db_session,
                self.sse_bridge,
            )

        assert output["strategy"] == "knowledge"
        assert output["total_internal_hits"] == 3
        assert "internal_candidates" in output
        # 每个子问题一次 Internal Retrieval
        assert mock_retrieval.await_count == 3
        # Tavily 从未被调用
        assert mock_tavily.await_count == 0

    @pytest.mark.asyncio
    async def test_knowledge_策略_候选含稳定身份且不含excerpt持久化(self):
        mock_retrieval = AsyncMock(return_value=_retrieval_response([_hit("h1", "doc-1")]))
        with (
            patch(
                "app.pipeline.searcher.internal_retrieval_client.search_retrieval",
                mock_retrieval,
            ),
            patch(
                "app.pipeline.searcher._call_tavily",
                AsyncMock(),
            ),
        ):
            output = await run_search(
                self.task,
                self.step,
                self.db_session,
                self.sse_bridge,
            )

        candidate = output["internal_candidates"][0]
        # 稳定身份齐全
        assert candidate["knowledge_base_id"] == KB_A
        assert candidate["document_id"] == "doc-1"
        assert candidate["document_version_id"]
        assert candidate["segment_id"]
        assert candidate["location"] == {"page_number": 3}
        assert candidate["scores"]
        # 持久化输出禁止携带内部正文/excerpt
        assert "minimal_excerpt" not in candidate
        assert "content" not in candidate and "text" not in candidate

    @pytest.mark.asyncio
    async def test_knowledge_策略_KB_FORBIDDEN_fail_closed不降级Web(self):
        mock_retrieval = AsyncMock(side_effect=InternalKnowledgeForbiddenException("KB 无权"))
        with (
            patch(
                "app.pipeline.searcher.internal_retrieval_client.search_retrieval",
                mock_retrieval,
            ),
            patch(
                "app.pipeline.searcher._call_tavily",
                AsyncMock(),
            ) as mock_tavily,
        ):
            with pytest.raises(InternalKnowledgeForbiddenException):
                await run_search(
                    self.task,
                    self.step,
                    self.db_session,
                    self.sse_bridge,
                )

        # 授权失败关闭：绝不降级调用 Web
        assert mock_tavily.await_count == 0

    @pytest.mark.asyncio
    async def test_knowledge_策略_不创建WebResearchSource(self):
        mock_retrieval = AsyncMock(return_value=_retrieval_response([_hit("h1", "doc-1")]))
        with (
            patch(
                "app.pipeline.searcher.internal_retrieval_client.search_retrieval",
                mock_retrieval,
            ),
            patch(
                "app.pipeline.searcher._call_tavily",
                AsyncMock(),
            ),
        ):
            await run_search(
                self.task,
                self.step,
                self.db_session,
                self.sse_bridge,
            )

        from app.models.research_source import ResearchSource

        add_calls = [
            c for c in self.db_session.add.call_args_list if isinstance(c[0][0], ResearchSource)
        ]
        assert add_calls == []


class TestWebStrategySearch:
    """web 策略：既有 Tavily 路径回归。"""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.task = _make_task(source_strategy="web")
        self.step = _make_step()
        self.sse_bridge = AsyncMock()
        self.db_session = AsyncMock()
        _mock_planning_in_session(self.db_session, DEFAULT_SUB_QUESTIONS)

    @pytest.mark.asyncio
    async def test_web_策略_调用Tavily不调用InternalRetrieval(self):
        async def _fake_tavily(query: str, api_key: str):
            return {
                "results": [
                    {
                        "url": f"https://a.com/{len(query)}",
                        "title": "t",
                        "score": 0.9,
                    }
                ]
            }

        with (
            patch(
                "app.pipeline.searcher._call_tavily",
                AsyncMock(side_effect=_fake_tavily),
            ) as mock_tavily,
            patch(
                "app.pipeline.searcher.internal_retrieval_client.search_retrieval",
                AsyncMock(),
            ) as mock_retrieval,
        ):
            output = await run_search(
                self.task,
                self.step,
                self.db_session,
                self.sse_bridge,
            )

        assert mock_tavily.await_count == 3
        assert mock_retrieval.await_count == 0
        assert output["after_dedup"] == 3


class TestHybridStrategySearch:
    """hybrid 策略：内部检索 + Web 搜索，Web Query 域隔离（ADR-010）。"""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.task = _make_task(source_strategy="hybrid", knowledge_base_ids=[KB_A])
        self.step = _make_step()
        self.sse_bridge = AsyncMock()
        self.db_session = AsyncMock()
        _setup_search_session(self.db_session, DEFAULT_SUB_QUESTIONS, [KB_A])

    @pytest.mark.asyncio
    async def test_hybrid_策略_同时调用内部检索与Web搜索(self):
        mock_retrieval = AsyncMock(return_value=_retrieval_response([_hit("h1", "doc-1")]))

        async def _fake_tavily(query: str, api_key: str):
            return {
                "results": [
                    {
                        "url": f"https://a.com/{len(query)}",
                        "title": "t",
                        "score": 0.9,
                    }
                ]
            }

        with (
            patch(
                "app.pipeline.searcher.internal_retrieval_client.search_retrieval",
                mock_retrieval,
            ),
            patch(
                "app.pipeline.searcher._call_tavily",
                AsyncMock(side_effect=_fake_tavily),
            ) as mock_tavily,
        ):
            output = await run_search(
                self.task,
                self.step,
                self.db_session,
                self.sse_bridge,
            )

        assert output["strategy"] == "hybrid"
        assert mock_retrieval.await_count == 3  # 每子问题一次内部检索
        assert mock_tavily.await_count == 3  # 每子问题一次 Web 搜索
        assert len(output["internal_candidates"]) == 3
        assert output["after_dedup"] == 3

    @pytest.mark.asyncio
    async def test_hybrid_WebQuery_不含内部excerpt与内部文档标题(self):
        captured_queries: list[str] = []

        async def _fake_tavily(query: str, api_key: str):
            captured_queries.append(query)
            return {"results": [{"url": "https://a.com/1", "title": "t", "score": 0.9}]}

        mock_retrieval = AsyncMock(
            return_value=_retrieval_response(
                [_hit("h1", "doc-1", excerpt="内部权限设计文档决定 READ 判定")]
            )
        )
        with (
            patch(
                "app.pipeline.searcher.internal_retrieval_client.search_retrieval",
                mock_retrieval,
            ),
            patch(
                "app.pipeline.searcher._call_tavily",
                AsyncMock(side_effect=_fake_tavily),
            ),
        ):
            await run_search(
                self.task,
                self.step,
                self.db_session,
                self.sse_bridge,
            )

        # Web Query 必须只来自公开子问题（与内部结果同源于规划阶段），
        # 不得携带内部文档标题「内部权限设计文档」或内部 excerpt 片段
        for q in captured_queries:
            assert "内部权限设计文档" not in q
            assert "READ 判定" not in q
            assert q in DEFAULT_SUB_QUESTIONS

    @pytest.mark.asyncio
    async def test_hybrid_KB_FORBIDDEN_fail_closed_不降级为纯Web(self):
        mock_retrieval = AsyncMock(side_effect=InternalKnowledgeForbiddenException("KB 无权"))
        with (
            patch(
                "app.pipeline.searcher.internal_retrieval_client.search_retrieval",
                mock_retrieval,
            ),
            patch(
                "app.pipeline.searcher._call_tavily",
                AsyncMock(),
            ) as mock_tavily,
        ):
            with pytest.raises(InternalKnowledgeForbiddenException):
                await run_search(
                    self.task,
                    self.step,
                    self.db_session,
                    self.sse_bridge,
                )

        # 授权失败关闭：不允许 Web 掩盖授权问题
        assert mock_tavily.await_count == 0
