"""M3 切片 C 下游验收测试 — Synthesis / Evidence Graph / Render 消费 internal 证据。

对齐 RESEARCH_PIPELINE.md §8.1/§9/§11、DATABASE.md §6.2、ADR-003/ADR-009：
- Synthesis：internal 证据经 resolve 重取当前正文（仅当前 Step 内存）构造工作集，
  prompt 区分「内部来源」与「来源标注」，输出 notes 不持久化正文；
- Evidence Graph：internal 条目无正文、携带 source_type/显示名/位置，
  来源聚合按 Document 身份而非 source_id；
- Render：报告 prompt 区分内部与外部证据，internal 引用不内嵌正文。

SDD 门禁：RED —— 目标行为（下游消费 internal 证据）当前缺失。
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.core.internal_retrieval_client import ResolvedReference
from app.models.evidence_item import EvidenceItem
from app.models.report_section import ReportSection
from app.models.research_source import ResearchSource
from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask

KB_A = "11111111-1111-4111-8111-111111111111"
DOC_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
VER_A = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
SEG_A = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
SEG_B = "ffffffff-ffff-4fff-8fff-ffffffffffff"


async def _make_task(db_session, task_id: str = "task-downstream-001") -> ResearchTask:
    task = ResearchTask(
        id=task_id,
        user_id="550e8400-e29b-41d4-a716-446655440001",
        topic="量子计算对密码学的影响",
        requirements={
            "task_type": "analysis",
            "depth": "quick",
            "max_sources": 10,
            "language": "zh",
        },
        source_strategy="hybrid",
        status="running",
        total_steps=7,
        completed_steps=4,
        total_sources=0,
        total_evidence=0,
    )
    db_session.add(task)
    await db_session.flush()

    planning_step = ResearchStep(
        id=f"step-plan-{task_id}",
        task_id=task.id,
        step_type="planning",
        status="completed",
        label="Planning",
        output={
            "sub_questions": ["量子计算威胁", "PQC 标准化进展"],
            "rationale": "两维度",
        },
        started_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
        duration_ms=1000,
    )
    db_session.add(planning_step)
    return task


async def _seed_evidence(
    db_session,
    task: ResearchTask,
) -> list[EvidenceItem]:
    """预置 1 条 internal + 1 条 web Evidence，及 graph/render 所需 steps。"""
    step = ResearchStep(
        id=f"step-ev-{task.id}",
        task_id=task.id,
        step_type="rerank",
        status="completed",
        label="Rerank",
        output={"evidence_count": 2},
        started_at=datetime(2026, 1, 1, 0, 0, 2, tzinfo=timezone.utc),
        completed_at=datetime(2026, 1, 1, 0, 0, 3, tzinfo=timezone.utc),
        duration_ms=1000,
    )
    db_session.add(step)

    web_source = ResearchSource(
        task_id=task.id,
        url="https://example.com/web-1",
        title="外部网页",
        domain="example.com",
        content="外部网页正文，NIST 后量子密码进展。",
        fetch_status="success",
    )
    db_session.add(web_source)
    await db_session.flush()

    internal_item = EvidenceItem(
        task_id=task.id,
        source_type="internal",
        source_id=None,
        step_id=step.id,
        content=None,
        relevance_score=0.95,
        knowledge_base_id=KB_A,
        document_id=DOC_A,
        document_version_id=VER_A,
        segment_id=SEG_A,
        document_display_name_snapshot="内部文档A",
        display_title="内部文档A",
        location_summary="第一章 > 1.1",
        source_observed_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        score_summary={"best_score": 0.9, "score_kind": "semantic", "rank": 1},
        validity="available",
    )
    web_item = EvidenceItem(
        task_id=task.id,
        source_type="web",
        source_id=web_source.id,
        step_id=step.id,
        content="外部网页正文片段。",
        relevance_score=0.8,
        display_title="外部网页",
        canonical_url_snapshot="https://example.com/web-1",
    )
    db_session.add(internal_item)
    db_session.add(web_item)
    await db_session.flush()
    task.total_evidence = 2
    return [internal_item, web_item]


class TestSynthesisInternalEvidence:
    """Synthesis 消费 internal 证据：resolve 重取正文、区分来源、不持久化。"""

    @pytest.mark.asyncio
    async def test_synthesis_内部证据_resolve重取并区分来源(self, db_session):
        """internal 证据经 resolve 重取正文进入 prompt，标注「内部来源」。"""
        import json

        from app.core.llm import LLMResult
        from app.pipeline.synthesizer import run_synthesis

        task = await _make_task(db_session)
        await _seed_evidence(db_session, task)

        synthesis_step = ResearchStep(
            id=f"step-syn-{task.id}",
            task_id=task.id,
            step_type="synthesis",
            status="running",
            label="Synthesis",
            started_at=datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc),
        )
        db_session.add(synthesis_step)
        await db_session.flush()

        resolved = [
            ResolvedReference(
                source_identity={
                    "knowledge_base_id": KB_A,
                    "document_id": DOC_A,
                    "document_version_id": VER_A,
                    "segment_id": SEG_A,
                },
                minimal_excerpt="Shor 算法可多项式时间分解大整数。",
                location={"page": 1, "section_path": ["第一章", "1.1"]},
                source_updated_at="2026-01-01T00:00:00Z",
            ),
        ]

        captured = {}

        async def _llm(*args, **kwargs):
            captured["messages"] = kwargs.get("messages") or args[0]
            notes = {
                "clusters": [
                    {
                        "theme": "量子计算威胁",
                        "summary": "量子计算对 RSA 构成威胁。",
                        "consensus_level": "strong",
                        "supporting_evidence_indices": [0, 1],
                        "conflicting_evidence_indices": [],
                    }
                ],
                "conflicts": [],
                "knowledge_gaps": ["量子计算机实际错误率"],
                "overall_assessment": "证据质量较高。",
            }
            return LLMResult(
                content=json.dumps(notes, ensure_ascii=False),
                reasoning_content="",
                prompt_tokens=1000,
                completion_tokens=500,
                total_tokens=1500,
            )

        sse = AsyncMock()
        with patch(
            "app.pipeline.synthesizer.resolve_retrieval", new=AsyncMock(return_value=resolved)
        ):
            with patch("app.pipeline.synthesizer.chat_completion", new=_llm):
                output = await run_synthesis(task, synthesis_step, db_session, sse)

        assert output["clusters_count"] == 1
        user_content = captured["messages"][-1]["content"]
        system_content = captured["messages"][0]["content"]
        # prompt 包含 internal 证据重取正文
        assert "Shor 算法可多项式时间分解大整数" in system_content
        # 区分内部与外部来源
        assert "内部来源" in system_content

        # 内部证据仍未持久化正文
        result = await db_session.execute(
            select(EvidenceItem).where(
                EvidenceItem.task_id == task.id,
                EvidenceItem.source_type == "internal",
            )
        )
        internal_item = result.scalar_one()
        assert internal_item.content is None


class TestEvidenceGraphInternalEvidence:
    """Evidence Graph 消费 internal 证据：无正文、携带 source_type。"""

    @pytest.mark.asyncio
    async def test_graph_内部证据_无正文带source_type(self, db_session):
        from app.pipeline.evidence_graph import run_evidence_graph

        task = await _make_task(db_session, task_id="task-graph-001")
        await _seed_evidence(db_session, task)

        graph_step = ResearchStep(
            id=f"step-graph-{task.id}",
            task_id=task.id,
            step_type="evidence_graph",
            status="running",
            label="Evidence Graph",
            started_at=datetime(2026, 1, 1, 0, 0, 6, tzinfo=timezone.utc),
        )
        db_session.add(graph_step)

        synthesis_step = ResearchStep(
            id=f"step-graph-syn-{task.id}",
            task_id=task.id,
            step_type="synthesis",
            status="completed",
            label="Synthesis",
            output={
                "clusters": [
                    {
                        "theme": "量子计算威胁",
                        "summary": "量子计算对 RSA 构成威胁。",
                        "consensus_level": "strong",
                        "supporting_evidence_indices": [0, 1],
                        "conflicting_evidence_indices": [],
                    }
                ],
                "conflicts": [],
                "knowledge_gaps": ["量子计算机实际错误率"],
                "overall_assessment": "证据质量较高。",
            },
            started_at=datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc),
            completed_at=datetime(2026, 1, 1, 0, 0, 6, tzinfo=timezone.utc),
            duration_ms=1000,
        )
        db_session.add(synthesis_step)
        await db_session.flush()

        sse = AsyncMock()
        output = await run_evidence_graph(task, graph_step, db_session, sse)

        graph = output["graph"]
        internal_items = [i for i in graph["items"] if i["source_type"] == "internal"]
        web_items = [i for i in graph["items"] if i["source_type"] == "web"]
        assert len(internal_items) == 1
        assert len(web_items) == 1
        assert internal_items[0]["content"] == ""
        assert internal_items[0]["source_title"] == "内部文档A"
        assert internal_items[0]["location_summary"] == "第一章 > 1.1"
        # 来源聚合区分内部（按 Document）与 web（按 source）
        internal_sources = [s for s in graph["sources"] if s.get("source_type") == "internal"]
        web_sources = [s for s in graph["sources"] if s.get("source_type") == "web"]
        assert len(internal_sources) == 1
        assert len(web_sources) == 1


class TestRenderInternalEvidence:
    """Render 消费 internal 证据：prompt 区分来源，不内嵌内部正文。"""

    @pytest.mark.asyncio
    async def test_render_内部证据_报告区分来源(self, db_session):
        import json

        from app.core.llm import LLMResult
        from app.pipeline.renderer import run_render

        task = await _make_task(db_session, task_id="task-render-001")
        await _seed_evidence(db_session, task)

        render_step = ResearchStep(
            id=f"step-render-{task.id}",
            task_id=task.id,
            step_type="render",
            status="running",
            label="Render",
            started_at=datetime(2026, 1, 1, 0, 0, 7, tzinfo=timezone.utc),
        )
        db_session.add(render_step)

        graph_step = ResearchStep(
            id=f"step-render-graph-{task.id}",
            task_id=task.id,
            step_type="evidence_graph",
            status="completed",
            label="Evidence Graph",
            output={
                "graph": {
                    "task_id": task.id,
                    "generated_at": "2026-01-01T00:00:10Z",
                    "items": [
                        {
                            "index": 0,
                            "evidence_item_id": 1,
                            "source_type": "internal",
                            "source_id": None,
                            "source_url": "",
                            "source_title": "内部文档A",
                            "domain": "internal",
                            "location_summary": "第一章 > 1.1",
                            "content": "",
                            "relevance_score": 0.95,
                            "cluster_theme": "量子计算威胁",
                            "consensus_level": "strong",
                            "used_in_sections": [],
                        },
                        {
                            "index": 1,
                            "evidence_item_id": 2,
                            "source_type": "web",
                            "source_id": 1,
                            "source_url": "https://example.com/web-1",
                            "source_title": "外部网页",
                            "domain": "example.com",
                            "location_summary": "",
                            "content": "外部网页正文片段。",
                            "relevance_score": 0.8,
                            "cluster_theme": "量子计算威胁",
                            "consensus_level": "strong",
                            "used_in_sections": [],
                        },
                    ],
                    "clusters": [
                        {
                            "theme": "量子计算威胁",
                            "summary": "量子计算对 RSA 构成威胁。",
                            "consensus_level": "strong",
                            "evidence_indices": [0, 1],
                        }
                    ],
                    "conflicts": [],
                    "knowledge_gaps": [],
                    "sources": [],
                },
                "item_count": 2,
                "cluster_count": 1,
                "conflict_count": 0,
                "source_count": 0,
                "duration_ms": 0,
            },
            started_at=datetime(2026, 1, 1, 0, 0, 6, tzinfo=timezone.utc),
            completed_at=datetime(2026, 1, 1, 0, 0, 7, tzinfo=timezone.utc),
            duration_ms=1000,
        )
        db_session.add(graph_step)

        captured = {}

        async def _llm(*args, **kwargs):
            captured["messages"] = kwargs.get("messages") or args[0]
            sections = [
                {"heading": "1. 概述", "content": "量子计算威胁。[来源0] 外部进展。[来源1]"}
            ]
            return LLMResult(
                content=json.dumps({"sections": sections}, ensure_ascii=False),
                reasoning_content="",
                prompt_tokens=2000,
                completion_tokens=1000,
                total_tokens=3000,
            )

        sse = AsyncMock()
        with patch("app.pipeline.renderer.chat_completion", new=_llm):
            output = await run_render(task, render_step, db_session, sse)

        assert output["sections_count"] == 1
        system_content = captured["messages"][0]["content"]
        # prompt 区分内部来源标注
        assert "内部来源标注" in system_content
        assert "来源标注" in system_content
        # internal 证据不把正文塞进报告 prompt
        assert "Shor" not in system_content

        # 报告 Section 已持久化
        result = await db_session.execute(
            select(ReportSection).where(ReportSection.task_id == task.id)
        )
        sections = list(result.scalars().all())
        assert len(sections) == 1
