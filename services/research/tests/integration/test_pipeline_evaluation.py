"""Pipeline 离线评估集成测试

复用 test_pipeline_full.py 的全链路 Mock（AgentRuntime 驱动，切片 7：
原 PipelineOrchestrator 已删除，收敛至 AgentRuntime），在 Pipeline 完成后
调用 evaluate_task，验证 Search / Fetch / Rerank 指标与 overall_pass 计算。
"""

import json
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest
from app.agent.runtime import AgentRuntime
from app.core.llm import LLMResult, ToolCall
from app.core.trace_recorder import TraceRecorder
from app.evaluation.aggregator import evaluate_task
from app.models.research_source import ResearchSource
from app.models.research_task import ResearchTask
from app.pipeline.reranker import Evidence
from app.pipeline.sse_bridge import SSEBridge
from app.pipeline.synthesizer import (
    ClaimEvidenceRelation,
    ConflictPosition,
    SynthesisClaim,
    SynthesisCluster,
    SynthesisConflict,
    SynthesisNotes,
)
from app.tools.registry import build_default_tool_registry
from sqlalchemy import select

# ═══════════════════════════════════════════════════════════════
# 辅助工厂（与 test_pipeline_full.py 保持一致）
# ═══════════════════════════════════════════════════════════════


def _make_llm_result(
    content: str, prompt_tokens: int = 100, completion_tokens: int = 50
) -> LLMResult:
    """构造 LLMResult。"""
    return LLMResult(
        content=content,
        reasoning_content="",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )


def _make_llm_tool_result(tool_name: str) -> LLMResult:
    """构造携带单个 Tool Call 的 LLMResult。"""
    return LLMResult(
        content="",
        reasoning_content=f"调用 {tool_name}",
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        tool_calls=[ToolCall(id=tool_name, name=tool_name, arguments={})],
    )


def _valid_planning_json() -> str:
    """返回有效的 Planning 输出 JSON。"""
    return json.dumps(
        {
            "sub_questions": [
                "量子计算对 RSA/ECC 的具体威胁",
                "NIST 后量子密码标准化最新进展",
                "中国在量子安全通信领域的政策与布局",
            ],
            "rationale": "从技术威胁、标准应对、政策布局三维度拆解",
        },
        ensure_ascii=False,
    )


async def _seed_task(db_session) -> ResearchTask:
    """在测试数据库中预置一个待执行全链路的任务。"""
    task = ResearchTask(
        id="task-eval-001",
        user_id=1,
        topic="量子计算对网络安全的威胁与应对策略",
        requirements={
            "task_type": "analysis",
            "depth": "quick",
            "max_sources": 5,
            "language": "zh",
        },
        status="pending",
        total_steps=7,
        completed_steps=0,
        total_sources=0,
        total_evidence=0,
    )
    db_session.add(task)
    await db_session.flush()

    return task


def _build_tavily_side_effect():
    """构造 Search 阶段 Tavily Mock side_effect。"""

    async def _side_effect(query: str, api_key: str) -> dict:
        prefix = "threat" if "RSA" in query or "ECC" in query else "standard"
        return {
            "results": [
                {
                    "url": f"https://example.com/{prefix}-article{i}",
                    "title": f"{prefix.title()} Article {i}",
                    "score": 0.95 - i * 0.05,
                }
                for i in range(1, 6)
            ],
        }

    return _side_effect


def _build_fetch_side_effect(failing_url: str | None = None):
    """构造 Fetch 阶段 HTTP Mock side_effect。

    Args:
        failing_url: 指定一个 URL 返回 timeout，其余返回 success。
    """

    async def _side_effect(url: str) -> dict:
        if failing_url and url == failing_url:
            return {"status": "timeout", "content": None, "content_length": 0}
        return {
            "status": "success",
            "content": f"# {url.split('/')[-1]} 标题\n\n这是关于 {url} 的正文，"
            f"包含量子计算和网络安全相关信息，用于测试报告生成。",
            "content_length": 180,
        }

    return _side_effect


def _build_rerank_side_effect(db_session, task_id: str):
    """构造 Rerank 阶段 Mock side_effect。"""

    async def _side_effect(topic: str, task_type: str, sub_questions: list[str], candidates: list):
        result = await db_session.execute(
            select(ResearchSource).where(
                ResearchSource.task_id == task_id,
                ResearchSource.fetch_status == "success",
            )
        )
        sources = list(result.scalars().all())
        evidence_list = []
        for i, source in enumerate(sources):
            evidence_list.append(
                Evidence(
                    source_id=source.id,
                    url=source.url,
                    title=source.title or "",
                    domain=source.domain or "",
                    content=source.content or "",
                    relevance_score=round(0.9 - i * 0.05, 3),
                    bm25_score=1.0,
                    sub_question_index=0,
                    word_count=len(source.content or ""),
                    rationale="与问题高度相关",
                )
            )
        evidence_list.sort(key=lambda e: e.relevance_score, reverse=True)
        return evidence_list, 500, 200, 0

    return _side_effect


def _build_synthesis_side_effect():
    """构造 Synthesis 阶段 Mock side_effect（含 critical Claim，满足 §10.2 发布门禁）。"""

    async def _side_effect(
        topic: str, task_type: str, evidence_items_formatted: str, evidence_count: int
    ):
        notes = SynthesisNotes(
            clusters=[
                SynthesisCluster(
                    theme="量子计算威胁",
                    summary="量子计算对 RSA 和 ECC 构成实际威胁。",
                    consensus_level="strong",
                    supporting_evidence_indices=[0, 1],
                    conflicting_evidence_indices=[],
                ),
            ],
            conflicts=[
                SynthesisConflict(
                    topic="标准化时间表分歧",
                    position_a=ConflictPosition("NIST 2024 年发布最终标准", [0]),
                    position_b=ConflictPosition("业界认为需更长时间验证", [1]),
                ),
            ],
            knowledge_gaps=["量子计算机实际错误率数据"],
            overall_assessment="证据质量较高。",
            claims=[
                SynthesisClaim(
                    statement="量子计算对现有公钥密码体系构成实际威胁。",
                    critical=True,
                    certainty="high",
                    qualification="需工程化验证。",
                    evidence_relations=[
                        ClaimEvidenceRelation(
                            evidence_index=0,
                            relation_type="supports",
                            confidence=0.9,
                        )
                    ],
                ),
            ],
        )
        return notes, 1000, 500, 0

    return _side_effect


def _build_render_side_effect():
    """构造 Render 阶段 Mock side_effect。"""

    async def _side_effect(messages: list[dict[str, str]]) -> tuple[str, LLMResult, int]:
        raw_text = json.dumps(
            {
                "sections": [
                    {
                        "heading": "1. 概述",
                        "content": "量子计算对 RSA 构成威胁[来源0]，NIST 推进后量子密码标准化[来源1]。",
                    },
                ],
            },
            ensure_ascii=False,
        )
        return raw_text, _make_llm_result(raw_text, prompt_tokens=2000, completion_tokens=1500), 0

    return _side_effect


def _build_agent_llm():
    """构造 Agent Loop LLM Mock：按当前 phase 返回对应 Tool Call（真实 Phase Handler 执行）。"""

    async def _agent_llm(messages=None, tools=None, tool_choice=None, **kwargs):
        for t in tools or []:
            name = t.get("function", {}).get("name", "")
            if name.endswith("_tool") and name not in ("finish_tool", "memory_tool"):
                return _make_llm_tool_result(name)
        return _make_llm_tool_result("finish_tool")

    return _agent_llm


async def _run_pipeline(db_session, task: ResearchTask, failing_url: str | None = None):
    """使用全 Mock 外部依赖经 AgentRuntime 跑通 Pipeline。"""
    task_id = task.id
    sse_bridge = SSEBridge(task_id)
    sse_bridge.publish = AsyncMock()
    trace = TraceRecorder(task_id=task_id, user_id=1, topic=task.topic)

    # searcher §6.1 预检查：web 策略要求 TAVILY_API_KEY 非空（E3102 门禁）。
    # 测试全程 mock `_call_tavily`，这里只为通过预检查，不产生真实调用。
    patches = [
        patch("app.config.settings.TAVILY_API_KEY", "test-tavily-key"),
        patch(
            "app.pipeline.planner.chat_completion",
            return_value=_make_llm_result(_valid_planning_json()),
        ),
        patch("app.pipeline.searcher._call_tavily", side_effect=_build_tavily_side_effect()),
        patch(
            "app.pipeline.fetcher._fetch_one_url", side_effect=_build_fetch_side_effect(failing_url)
        ),
        patch(
            "app.pipeline.reranker._llm_rerank",
            side_effect=_build_rerank_side_effect(db_session, task_id),
        ),
        patch(
            "app.pipeline.synthesizer._llm_synthesize", side_effect=_build_synthesis_side_effect()
        ),
        patch("app.pipeline.renderer._call_llm_render", side_effect=_build_render_side_effect()),
        patch("app.agent.loop.chat_completion", side_effect=_build_agent_llm()),
    ]

    original_commit = db_session.commit

    async def _commit_to_flush():
        await db_session.flush()

    db_session.commit = _commit_to_flush
    try:
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            runtime = AgentRuntime(
                task=task,
                session=db_session,
                sse_bridge=sse_bridge,
                trace_recorder=trace,
                tool_registry=build_default_tool_registry(),
                max_iterations=20,
            )
            await runtime.run()
    finally:
        db_session.commit = original_commit


# ═══════════════════════════════════════════════════════════════
# 集成测试
# ═══════════════════════════════════════════════════════════════


class TestPipelineEvaluation:
    """Pipeline 离线评估集成测试。"""

    @pytest.mark.asyncio
    async def test_全链路完成后_评估指标全部通过(self, db_session):
        """全链路 Mock 跑通后，evaluate_task 应返回 overall_pass=true。"""
        task = await _seed_task(db_session)
        await _run_pipeline(db_session, task)

        report = await evaluate_task(db_session, task.id)

        assert report.task_id == task.id
        assert report.status == "completed"
        assert report.task_type == "analysis"
        assert report.search is not None
        assert report.fetch is not None
        assert report.rerank is not None
        assert report.search.coverage_rate == 1.0
        assert report.search.recall_at_k == 1.0
        assert report.search.sub_question_count == 3
        assert report.fetch.success_rate == 1.0
        assert report.fetch.successful == 10  # 3 子问题去重后共 10 个唯一 URL
        assert report.rerank.evidence_count == 5
        assert report.rerank.mean_score >= 0.65
        assert report.rerank.high_quality_ratio >= 0.60
        assert report.overall_pass is True

    @pytest.mark.asyncio
    async def test_单个URL抓取失败_成功率下降_评估可能不通过(self, db_session):
        """模拟一个 URL timeout，验证 fetch success_rate 下降。"""
        task = await _seed_task(db_session)
        failing_url = "https://example.com/threat-article1"
        await _run_pipeline(db_session, task, failing_url=failing_url)

        report = await evaluate_task(db_session, task.id)

        assert report.fetch.successful == 9
        assert report.fetch.failed == 1
        assert report.fetch.success_rate == pytest.approx(0.9)
        # 90% > 70%，仍应通过
        assert report.overall_pass is True

    @pytest.mark.asyncio
    async def test_评估非终态任务抛出异常(self, db_session):
        """对 pending 状态任务调用 evaluate_task 应抛出 ValueError。"""
        task = await _seed_task(db_session)

        with pytest.raises(ValueError) as exc_info:
            await evaluate_task(db_session, task.id)

        assert "pending" in str(exc_info.value)
