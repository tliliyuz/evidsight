"""Rerank 内部候选接入 + Evidence 分型验收测试（M3 切片 C）。

对齐 RESEARCH_PIPELINE.md §7、DATABASE.md §6.2、ADR-003/ADR-009/ADR-010：
- `knowledge` 策略：Search 产出 `internal_candidates`（无正文，存于 search step.output），
  Rerank 经 `resolve_retrieval` 重取当前正文（仅当前 Step 内存）参与 BM25+LLM 精排，
  产出 `source_type='internal'` 的 EvidenceItem —— content 为 NULL、source_id 为 NULL、
  内部稳定 ID（KB/Document/Version/Segment）完整；
- `hybrid` 策略：内部候选与 Web 候选（research_sources）统一精排，产出 internal+web 两类证据；
- fail-closed：resolve 返回 KB_FORBIDDEN / 契约错误 / 瞬时不可用重试耗尽时，
  `knowledge` 任务失败关闭，不得降级为 Web；
- 内部证据持久化不包含 minimal_excerpt 或任何等价正文。

SDD 门禁：RED —— 目标行为（Rerank 消费内部候选 + 分型持久化）当前缺失。
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.core.exceptions import (
    InternalKnowledgeForbiddenException,
    RerankFailedException,
)
from app.core.internal_retrieval_client import ResolvedReference
from app.models.evidence_item import EvidenceItem
from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask

KB_A = "11111111-1111-4111-8111-111111111111"
KB_B = "22222222-2222-4222-8222-222222222222"

DOC_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
DOC_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
VER_A = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
VER_B = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
SEG_A = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
SEG_B = "ffffffff-ffff-4fff-8fff-ffffffffffff"


def _internal_candidate(
    *,
    kb: str = KB_A,
    doc: str = DOC_A,
    version: str = VER_A,
    segment: str = SEG_A,
    display_name: str = "内部文档A",
    title: str | None = "第一章",
    sq_index: int = 1,
    scores: list[dict] | None = None,
) -> dict:
    """构造 search step.output 中 internal_candidates 的安全 dict（无 minimal_excerpt）。"""
    return {
        "hit_id": f"hit-{segment}",
        "knowledge_base_id": kb,
        "document_id": doc,
        "document_version_id": version,
        "segment_id": segment,
        "document_display_name": display_name,
        "section_title": title,
        "location": {"page": 1, "section_path": ["第一章"]},
        "scores": scores or [{"score_kind": "semantic", "score": 0.9, "rank": 1}],
        "source_updated_at": "2026-01-01T00:00:00Z",
        "retrieved_at": "2026-01-01T00:00:00Z",
        "access_scope": "internal",
        "sub_question_index": sq_index,
    }


def _resolved_reference(candidate: dict, excerpt: str) -> ResolvedReference:
    """构造 resolve_retrieval 返回的 ResolvedReference。"""
    return ResolvedReference(
        source_identity={
            "knowledge_base_id": candidate["knowledge_base_id"],
            "document_id": candidate["document_id"],
            "document_version_id": candidate["document_version_id"],
            "segment_id": candidate["segment_id"],
        },
        minimal_excerpt=excerpt,
        location=candidate.get("location") or {},
        source_updated_at=candidate.get("source_updated_at") or "",
    )


def _make_llm_result() -> object:
    """构造 Rerank LLM 返回结果（ratings 数量与候选一致）。"""
    import json

    from app.core.llm import LLMResult

    async def _build(*args, **kwargs) -> LLMResult:
        messages = kwargs.get("messages") or args[0]
        user_content = messages[-1]["content"] if messages else ""
        # 从待评分片段数推断 ratings 数量
        count = user_content.count("[片段 ")
        ratings = [
            {"segment_index": i, "score": 8.0 - i * 0.5, "rationale": f"理由{i}"}
            for i in range(count)
        ]
        return LLMResult(
            content=json.dumps({"ratings": ratings}, ensure_ascii=False),
            reasoning_content="",
            prompt_tokens=300,
            completion_tokens=100,
            total_tokens=400,
        )

    return _build


def _make_task(*, strategy: str = "knowledge", task_id: str = "task-internal-001") -> ResearchTask:
    return ResearchTask(
        id=task_id,
        user_id="550e8400-e29b-41d4-a716-446655440001",
        topic="量子计算对密码学的影响",
        requirements={
            "task_type": "analysis",
            "depth": "quick",
            "max_sources": 5,
            "language": "zh",
        },
        source_strategy=strategy,
        status="running",
        total_steps=7,
        completed_steps=2,
        total_sources=0,
        total_evidence=0,
    )


async def _seed_task_with_search_output(
    db_session,
    task: ResearchTask,
    internal_candidates: list[dict],
) -> ResearchStep:
    """预置任务 + planning/search/rerank steps，search step.output 含 internal_candidates。"""
    db_session.add(task)
    await db_session.flush()

    planning_step = ResearchStep(
        id=f"step-plan-{task.id}",
        task_id=task.id,
        step_type="planning",
        status="completed",
        label="Planning",
        output={
            "sub_questions": ["量子计算对RSA的威胁", "NIST后量子密码进展"],
            "rationale": "两维度",
        },
        started_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
        duration_ms=1000,
    )
    db_session.add(planning_step)

    search_step = ResearchStep(
        id=f"step-search-{task.id}",
        task_id=task.id,
        step_type="search",
        status="completed",
        label="Search",
        output={
            "strategy": task.source_strategy,
            "total_internal_hits": len(internal_candidates),
            "internal_candidates": internal_candidates,
            "sub_question_results": [],
        },
        started_at=datetime(2026, 1, 1, 0, 0, 2, tzinfo=timezone.utc),
        completed_at=datetime(2026, 1, 1, 0, 0, 3, tzinfo=timezone.utc),
        duration_ms=1000,
    )
    db_session.add(search_step)

    rerank_step = ResearchStep(
        id=f"step-rerank-{task.id}",
        task_id=task.id,
        step_type="rerank",
        status="running",
        label="Rerank",
        started_at=datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc),
    )
    db_session.add(rerank_step)
    await db_session.flush()
    return rerank_step


class TestRerankKnowledgeInternal:
    """knowledge 策略：Rerank 消费内部候选并产出 internal Evidence。"""

    @pytest.mark.asyncio
    async def test_knowledge_内部候选_产出internal证据无正文(self, db_session):
        """knowledge 策略：无 Web 来源时，Rerank 消费内部候选，产出 internal Evidence。"""
        from app.pipeline.reranker import run_rerank

        task = _make_task(strategy="knowledge")
        candidates = [
            _internal_candidate(
                kb=KB_A,
                doc=DOC_A,
                version=VER_A,
                segment=SEG_A,
                display_name="内部文档A",
                sq_index=1,
            ),
            _internal_candidate(
                kb=KB_A,
                doc=DOC_A,
                version=VER_A,
                segment=SEG_B,
                display_name="内部文档A",
                sq_index=1,
            ),
            _internal_candidate(
                kb=KB_B,
                doc=DOC_B,
                version=VER_B,
                segment=SEG_B,
                display_name="内部文档B",
                sq_index=2,
            ),
        ]
        rerank_step = await _seed_task_with_search_output(db_session, task, candidates)

        resolved = [_resolved_reference(c, f"内部正文{c['segment_id'][:8]}") for c in candidates]

        sse = AsyncMock()
        with (
            patch(
                "app.pipeline.reranker.resolve_retrieval",
                new=AsyncMock(return_value=resolved),
            ),
            patch("app.pipeline.reranker.chat_completion", new=_make_llm_result()),
        ):
            output = await run_rerank(task, rerank_step, db_session, sse)

        assert output["evidence_count"] == 3

        result = await db_session.execute(
            select(EvidenceItem).where(EvidenceItem.task_id == task.id)
        )
        items = list(result.scalars().all())
        assert len(items) == 3

        for item in items:
            assert item.source_type == "internal"
            assert item.content is None
            assert item.source_id is None
            assert item.knowledge_base_id in {KB_A, KB_B}
            assert item.document_id is not None
            assert item.document_version_id is not None
            assert item.segment_id is not None
            assert item.document_display_name_snapshot in {"内部文档A", "内部文档B"}

        # task.total_evidence 更新
        assert task.total_evidence == 3

    @pytest.mark.asyncio
    async def test_knowledge_全部子问题无候选_失败关闭(self, db_session):
        """knowledge 策略：Search 无内部候选时 Rerank 失败关闭（E3105 语义），不降级 Web。"""
        from app.pipeline.reranker import run_rerank

        task = _make_task(strategy="knowledge", task_id="task-internal-empty")
        candidates: list[dict] = []
        rerank_step = await _seed_task_with_search_output(db_session, task, candidates)

        sse = AsyncMock()
        with pytest.raises(RerankFailedException) as exc_info:
            with patch("app.pipeline.reranker.chat_completion", new=_make_llm_result()):
                await run_rerank(task, rerank_step, db_session, sse)

        assert exc_info.value.error_code == "E3105"

    @pytest.mark.asyncio
    async def test_knowledge_resolve失败_failClosed不降级Web(self, db_session):
        """knowledge 策略：resolve 返回 KB_FORBIDDEN → fail-closed，整次失败。"""
        from app.pipeline.reranker import run_rerank

        task = _make_task(strategy="knowledge", task_id="task-internal-failclosed")
        candidates = [_internal_candidate(kb=KB_A, doc=DOC_A, version=VER_A, segment=SEG_A)]
        rerank_step = await _seed_task_with_search_output(db_session, task, candidates)

        sse = AsyncMock()
        with (
            patch(
                "app.pipeline.reranker.resolve_retrieval",
                new=AsyncMock(side_effect=InternalKnowledgeForbiddenException("无权访问")),
            ),
        ):
            with pytest.raises(InternalKnowledgeForbiddenException):
                await run_rerank(task, rerank_step, db_session, sse)

        # 不产出任何 Evidence（含 web 降级路径）
        result = await db_session.execute(
            select(EvidenceItem).where(EvidenceItem.task_id == task.id)
        )
        assert len(list(result.scalars().all())) == 0


class TestRerankHybridInternal:
    """hybrid 策略：内部候选与 Web 候选统一精排。"""

    @pytest.mark.asyncio
    async def test_hybrid_内部与Web候选统一精排_产出两类证据(self, db_session):
        """hybrid 策略：Rerank 合并内部候选与 Web 抓取文档，产出 internal+web 两类 Evidence。"""
        from sqlalchemy import select as sa_select

        from app.models.research_source import ResearchSource
        from app.pipeline.reranker import run_rerank

        task = _make_task(strategy="hybrid", task_id="task-hybrid-001")
        internal = [
            _internal_candidate(
                kb=KB_A,
                doc=DOC_A,
                version=VER_A,
                segment=SEG_A,
                display_name="内部文档A",
                sq_index=1,
            ),
        ]
        rerank_step = await _seed_task_with_search_output(db_session, task, internal)

        # Web 来源（fetch 成功）
        db_session.add(
            ResearchSource(
                task_id=task.id,
                url="https://example.com/web-1",
                title="外部网页",
                domain="example.com",
                content="外部网页正文，NIST 后量子密码进展。",
                fetch_status="success",
                fetched_at=datetime(2026, 1, 1, 0, 0, 4, tzinfo=timezone.utc),
            )
        )
        await db_session.flush()

        resolved = [_resolved_reference(internal[0], "内部正文ABCDEFGH")]
        sse = AsyncMock()
        with (
            patch(
                "app.pipeline.reranker.resolve_retrieval",
                new=AsyncMock(return_value=resolved),
            ),
            patch("app.pipeline.reranker.chat_completion", new=_make_llm_result()),
        ):
            output = await run_rerank(task, rerank_step, db_session, sse)

        result = await db_session.execute(
            sa_select(EvidenceItem).where(EvidenceItem.task_id == task.id)
        )
        items = list(result.scalars().all())

        internal_items = [i for i in items if i.source_type == "internal"]
        web_items = [i for i in items if i.source_type == "web"]

        assert len(internal_items) >= 1
        assert len(web_items) >= 1
        assert all(i.content is None and i.source_id is None for i in internal_items)
        assert all(i.content is not None and i.source_id is not None for i in web_items)
        assert output["evidence_count"] == len(items)


class TestEvidenceTypingModel:
    """数据层分型：evidence_items 支持 source_type 与内部稳定 ID 列。"""

    @pytest.mark.asyncio
    async def test_模型_支持source_type与内部稳定ID(self, db_session):
        """EvidenceItem 模型包含 source_type / 内部稳定 ID / 显示快照字段。"""
        task = _make_task(strategy="knowledge", task_id="task-typing-001")
        db_session.add(task)
        await db_session.flush()

        item = EvidenceItem(
            task_id="task-typing-001",
            step_id=None,
            source_type="internal",
            knowledge_base_id=KB_A,
            document_id=DOC_A,
            document_version_id=VER_A,
            segment_id=SEG_A,
            document_display_name_snapshot="内部文档A",
            location_summary="第一章 / 第1页",
            source_observed_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            score_summary={"best_score": 0.9, "score_kind": "semantic", "rank": 1},
            validity="available",
            content=None,
            source_id=None,
        )
        db_session.add(item)
        await db_session.flush()

        result = await db_session.execute(
            select(EvidenceItem).where(EvidenceItem.task_id == "task-typing-001")
        )
        saved = result.scalar_one()
        assert saved.source_type == "internal"
        assert saved.knowledge_base_id == KB_A
        assert saved.segment_id == SEG_A
        assert saved.validity == "available"
