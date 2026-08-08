"""Report Render 目标态原子发布单元测试 —— 对齐 DATABASE.md §7.6 / ADR-009 / 切片 4 单写。

断言 run_render 单写目标态 revision sections 并同步写 section_evidence：
- 创建 reports 根（task_id 唯一）；
- 创建 building→published ReportRevision（含完整度摘要、build_step_id）；
- report_sections 挂 revision_id，且同一事务写 section_evidence；
- claims 与 evidence_relations 落库，relation_type/confidence 正确；
- reports.current_revision_id 指向 published Revision；
- 二次渲染创建更高 revision_number，published Revision 不变。
"""

import json
from typing import cast
from unittest.mock import patch

from app.core.llm import LLMResult
from app.models.claim import Claim
from app.models.evidence_relation import EvidenceRelation
from app.models.report import Report
from app.models.report_revision import ReportRevision
from app.models.report_section import ReportSection
from app.models.section_evidence import SectionEvidence
from app.pipeline.renderer import run_render
from app.pipeline.sse_bridge import SSEBridge
from sqlalchemy import select

from .test_renderer import _seed_render_task, _valid_report_sections


def _mock_llm_report(sections: list[dict]) -> LLMResult:
    return LLMResult(
        content=json.dumps({"sections": sections}, ensure_ascii=False),
        reasoning_content="",
        prompt_tokens=2000,
        completion_tokens=1500,
        total_tokens=3500,
    )


class TestRenderTargetPublish:
    async def test_渲染后发布目标态reports与publishedRevision(self, db_session):
        task, render_step, evidence_items = await _seed_render_task(db_session, evidence_count=3)
        sse = _FakeSSE()

        # 给 graph 增加 claims
        from app.models.research_step import ResearchStep

        eg_step = (
            await db_session.execute(
                select(ResearchStep).where(
                    ResearchStep.task_id == task.id,
                    ResearchStep.step_type == "evidence_graph",
                )
            )
        ).scalar_one()
        eg_step.output["graph"]["claims"] = [
            {
                "statement": "量子计算对 RSA 构成实际威胁。",
                "critical": True,
                "certainty": "high",
                "qualification": "需要工程化验证。",
                "relations": [
                    {
                        "evidence_item_id": evidence_items[0].id,
                        "evidence_index": 0,
                        "relation_type": "supports",
                        "confidence": 0.9,
                    }
                ],
            },
            {
                "statement": "NIST 后量子标准化存在时间分歧。",
                "critical": False,
                "certainty": "medium",
                "relations": [],
            },
        ]

        with patch("app.pipeline.renderer.chat_completion") as mock_llm:
            mock_llm.return_value = _mock_llm_report(_valid_report_sections())
            await run_render(task, render_step, db_session, cast(SSEBridge, sse))

        # 目标态 reports 根存在
        report = (
            await db_session.execute(select(Report).where(Report.task_id == task.id))
        ).scalar_one()
        assert report is not None

        # published Revision
        rev = (
            await db_session.execute(
                select(ReportRevision).where(ReportRevision.report_id == report.id)
            )
        ).scalar_one()
        assert rev.status == "published"
        assert rev.published_at is not None
        assert rev.build_step_id == render_step.id
        assert rev.evidence_completeness is not None
        assert rev.evidence_completeness["score"] > 0
        assert report.current_revision_id == rev.id

        # sections 挂 revision_id（目标态单写）
        sections = (
            (
                await db_session.execute(
                    select(ReportSection).where(ReportSection.revision_id == rev.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(sections) == 2
        for s in sections:
            assert s.revision_id == rev.id

        # claims 落库（按 sequence 匹配，critical 为合成期标记不落库）
        claims = (
            (
                await db_session.execute(
                    select(Claim).where(Claim.revision_id == rev.id).order_by(Claim.sequence)
                )
            )
            .scalars()
            .all()
        )
        assert len(claims) == 2
        assert claims[0].statement == "量子计算对 RSA 构成实际威胁。"
        assert claims[0].certainty == "high"
        assert claims[0].qualification == "需要工程化验证。"
        assert claims[1].statement == "NIST 后量子标准化存在时间分歧。"
        assert claims[1].certainty == "medium"

        # evidence_relations 落库（关联 claim0，即 sequence=0 的 claim）
        rels = (
            (
                await db_session.execute(
                    select(EvidenceRelation).where(EvidenceRelation.claim_id == claims[0].id)
                )
            )
            .scalars()
            .all()
        )
        assert len(rels) == 1
        assert rels[0].relation_type == "supports"
        assert float(rels[0].confidence) == 0.9
        assert rels[0].evidence_id == evidence_items[0].id
        assert rels[0].created_by_step_id == render_step.id

    async def test_revision_sections同步写section_evidence(self, db_session):
        """切片 4 单写：revision sections 在同一事务同步写 section_evidence（AC-001 依赖）。"""
        task, render_step, evidence_items = await _seed_render_task(db_session, evidence_count=3)
        sse = _FakeSSE()

        with patch("app.pipeline.renderer.chat_completion") as mock_llm:
            mock_llm.return_value = _mock_llm_report(_valid_report_sections())
            await run_render(task, render_step, db_session, cast(SSEBridge, sse))

        report = (
            await db_session.execute(select(Report).where(Report.task_id == task.id))
        ).scalar_one()
        sections = (
            (
                await db_session.execute(
                    select(ReportSection).where(
                        ReportSection.revision_id == report.current_revision_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(sections) == 2
        assoc_count = (
            await db_session.execute(
                select(__import__("sqlalchemy").func.count())
                .select_from(SectionEvidence)
                .where(SectionEvidence.section_id.in_([s.id for s in sections]))
            )
        ).scalar()
        assert assoc_count == 4

    async def test_二次渲染_创建更高revision(self, db_session):
        task, render_step, evidence_items = await _seed_render_task(db_session, evidence_count=3)
        sse = _FakeSSE()

        with patch("app.pipeline.renderer.chat_completion") as mock_llm:
            mock_llm.return_value = _mock_llm_report(_valid_report_sections())
            await run_render(task, render_step, db_session, cast(SSEBridge, sse))
            await run_render(task, render_step, db_session, cast(SSEBridge, sse))

        report = (
            await db_session.execute(select(Report).where(Report.task_id == task.id))
        ).scalar_one()
        revisions = (
            (
                await db_session.execute(
                    select(ReportRevision)
                    .where(ReportRevision.report_id == report.id)
                    .order_by(ReportRevision.revision_number)
                )
            )
            .scalars()
            .all()
        )
        assert [r.revision_number for r in revisions] == [1, 2]
        assert [r.status for r in revisions] == ["published", "published"]
        assert report.current_revision_id == revisions[-1].id


class _FakeSSE:
    async def publish(self, event, data):
        pass
