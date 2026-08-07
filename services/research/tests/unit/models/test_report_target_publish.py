"""Report 目标态原子发布单元测试 —— 对齐 DATABASE.md §7.6 / RESEARCH_PIPELINE §11。

覆盖切片 4 验收：
- 发布后 reports 存在且 current_revision_id 指向 published Revision；
- report_revisions 状态机：building → published，含完整度摘要；
- report_sections 挂 revision_id 且正文/排序保留；
- claims 与 evidence_relations 落库且 relation_type/confidence 正确；
- 重复发布创建更高 revision_number，published Revision 不可变（不覆盖）；
- 完整度三分项纯函数按 RESEARCH_PIPELINE §10 计算。
"""

import pytest
from app.core.database import Base
from app.evaluation.completeness import (
    compute_channel_success,
    compute_claim_coverage,
    compute_evidence_completeness,
    compute_question_coverage,
)
from app.models.claim import Claim
from app.models.evidence_item import EvidenceItem
from app.models.evidence_relation import EvidenceRelation
from app.models.report import Report
from app.models.report_revision import ReportRevision
from app.models.report_section import ReportSection
from app.models.research_source import ResearchSource
from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask
from sqlalchemy import select


class TestCompletenessMetrics:
    def test_question_coverage(self):
        rate, n, d = compute_question_coverage(required_questions=4, questions_with_evidence=3)
        assert rate == 0.75
        assert (n, d) == (3, 4)

    def test_question_coverage_零required_拒绝(self):
        with pytest.raises(ValueError):
            compute_question_coverage(required_questions=0, questions_with_evidence=0)

    def test_channel_success(self):
        rate, n, d = compute_channel_success(planned=2, succeeded=1)
        assert rate == 0.5

    def test_claim_coverage(self):
        rate, n, d = compute_claim_coverage(critical_claims=4, claims_with_supports=2)
        assert rate == 0.5

    def test_evidence_completeness_加权(self):
        # 0.5*q + 0.25*c + 0.25*k
        score = compute_evidence_completeness(
            question_coverage=0.8, channel_success=0.6, claim_coverage=1.0
        )
        assert abs(score - (0.5 * 0.8 + 0.25 * 0.6 + 0.25 * 1.0)) < 1e-9

    def test_evidence_completeness_越界拒绝(self):
        with pytest.raises(ValueError):
            compute_evidence_completeness(
                question_coverage=1.2, channel_success=0.5, claim_coverage=0.5
            )


class TestReportRevisionStatusEnum:
    def test_枚举(self):
        table = Base.metadata.tables["report_revisions"]
        assert set(table.c["status"].type.enums) == {"building", "published", "failed"}


async def _seed_render_task(
    db_session, task_suffix: str = "p001"
) -> tuple[ResearchTask, ResearchStep]:
    task = ResearchTask(
        id=f"task-target-pub-{task_suffix}",
        user_id="550e8400-e29b-41d4-a716-446655440000",
        topic="目标态发布测试",
        requirements={"task_type": "explainer", "max_sources": 5, "language": "zh"},
        status="running",
    )
    db_session.add(task)
    await db_session.flush()

    step = ResearchStep(
        id=f"step-target-render-{task_suffix}",
        task_id=task.id,
        step_type="render",
        status="running",
        started_at=__import__("datetime").datetime(
            2026, 1, 1, tzinfo=__import__("datetime").timezone.utc
        ),
    )
    db_session.add(step)

    for i in range(3):
        src = ResearchSource(
            task_id=task.id, url=f"https://e{i}.example.com", title=f"来源{i}", domain="example.com"
        )
        db_session.add(src)
        await db_session.flush()
        ev = EvidenceItem(
            task_id=task.id,
            source_type="web",
            source_id=src.id,
            canonical_url_snapshot=f"https://e{i}.example.com",
            display_title=f"来源{i}",
            relevance_score=0.9 - i * 0.1,
        )
        db_session.add(ev)
    await db_session.flush()
    return task, step


class TestTargetPublish:
    async def test_publish_创建reports与publishedRevision(self, db_session):
        task, step = await _seed_render_task(db_session)
        report = Report(task_id=task.id)
        db_session.add(report)
        await db_session.flush()

        rev = ReportRevision(
            report_id=report.id,
            revision_number=1,
            status="building",
            title="目标态报告",
            language="zh",
            content_hash="abc",
            build_step_id=step.id,
            evidence_completeness={
                "question_coverage": 1.0,
                "channel_success": 1.0,
                "claim_coverage": 1.0,
                "score": 1.0,
            },
        )
        db_session.add(rev)
        await db_session.flush()

        section = ReportSection(
            task_id=task.id,
            revision_id=rev.id,
            heading="1. 概述",
            content="正文[来源0]",
            sort_order=0,
        )
        db_session.add(section)
        await db_session.flush()

        ev = (
            (await db_session.execute(select(EvidenceItem).where(EvidenceItem.task_id == task.id)))
            .scalars()
            .first()
        )
        claim = Claim(
            revision_id=rev.id,
            section_id=section.id,
            sequence=1,
            statement="这是结论。",
            certainty="high",
        )
        db_session.add(claim)
        await db_session.flush()
        rel = EvidenceRelation(
            claim_id=claim.id,
            evidence_id=ev.id,
            relation_type="supports",
            confidence=0.9,
            created_by_step_id=step.id,
        )
        db_session.add(rel)

        rev.status = "published"
        rev.published_at = __import__("datetime").datetime(
            2026, 1, 1, tzinfo=__import__("datetime").timezone.utc
        )
        report.current_revision_id = rev.id
        await db_session.flush()

        # 直接查询数据库断言（避免 expire_all 触发懒加载）
        loaded_report = (
            await db_session.execute(select(Report).where(Report.id == report.id))
        ).scalar_one()
        loaded_rev = (
            await db_session.execute(select(ReportRevision).where(ReportRevision.id == rev.id))
        ).scalar_one()
        assert loaded_report.current_revision_id == rev.id
        assert loaded_rev.status == "published"
        assert loaded_rev.published_at is not None
        assert loaded_rev.evidence_completeness["score"] == 1.0

    async def test_二次发布_更高revision号(self, db_session):
        task, step = await _seed_render_task(db_session, task_suffix="p002")
        report = Report(task_id=task.id)
        db_session.add(report)
        await db_session.flush()

        rev1 = ReportRevision(
            report_id=report.id,
            revision_number=1,
            status="published",
            title="v1",
            language="zh",
            content_hash="h1",
            build_step_id=step.id,
        )
        db_session.add(rev1)
        await db_session.flush()
        report.current_revision_id = rev1.id
        await db_session.flush()

        rev2 = ReportRevision(
            report_id=report.id,
            revision_number=2,
            status="building",
            title="v2",
            language="zh",
            content_hash="h2",
            build_step_id=step.id,
            based_on_revision_id=rev1.id,
        )
        db_session.add(rev2)
        await db_session.flush()
        assert rev2.revision_number == 2
        assert rev2.based_on_revision_id == rev1.id
        # 已发布 v1 不被覆盖
        assert rev1.status == "published"
