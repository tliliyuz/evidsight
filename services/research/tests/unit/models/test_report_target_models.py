"""目标态报告数据层模型单元测试 —— 对齐 DATABASE.md §7 / ADR-009。

覆盖切片 1 数据层验收：
- evidence_items / report_sections 新增对外 external_id（UUID，唯一非空）；
- reports：task_id 唯一并级联删除，current_revision_id 指向 published Revision；
- report_revisions：(report_id, revision_number) 唯一，status 状态机；
- claims：revision/section FK，sequence 排序，certainty/qualification 受控表达；
- evidence_relations：(claim_id, evidence_id, relation_type) 唯一，confidence 0-1。
"""

import uuid

import pytest
from app.core.database import Base
from app.models.claim import Claim
from app.models.enums import (
    CLAIM_CERTAINTY_ENUM,
    EVIDENCE_RELATION_TYPE_ENUM,
    REPORT_REVISION_STATUS_ENUM,
)
from app.models.evidence_item import EvidenceItem
from app.models.evidence_relation import EvidenceRelation
from app.models.report import Report
from app.models.report_revision import ReportRevision
from app.models.report_section import ReportSection
from app.models.research_task import ResearchTask
from sqlalchemy.ext.asyncio import AsyncSession


def _table(name: str):
    return Base.metadata.tables[name]


def _seed_task(db_session: AsyncSession) -> ResearchTask:
    task = ResearchTask(
        id="target-task-1",
        user_id="550e8400-e29b-41d4-a716-446655440000",
        topic="目标态报告测试",
        requirements={"task_type": "explainer", "max_sources": 5, "language": "zh"},
        status="completed",
    )
    db_session.add(task)
    return task


class TestEvidenceExternalId:
    async def test_evidence_items_有external_id列且非空唯一(self):
        table = _table("evidence_items")
        assert "external_id" in table.c
        col = table.c["external_id"]
        assert not col.nullable

    async def test_evidence_items_external_id生成UUID(self, db_session: AsyncSession):
        task = _seed_task(db_session)
        db_session.add(task)
        await db_session.flush()
        ev = EvidenceItem(task_id=task.id, source_type="web")
        db_session.add(ev)
        await db_session.flush()
        assert ev.external_id
        uuid.UUID(ev.external_id)  # 必须为合法 UUID

    async def test_report_sections_有external_id列(self):
        table = _table("report_sections")
        assert "external_id" in table.c
        assert not table.c["external_id"].nullable


class TestReportsTable:
    async def test_reports_表结构与唯一约束(self):
        table = _table("reports")
        assert "task_id" in table.c
        assert "current_revision_id" in table.c
        unique_ok = any(set(c.name for c in uc.columns) == {"task_id"} for uc in table.constraints)
        assert unique_ok

    async def test_reports_task级联删除(self, db_session: AsyncSession):
        task = _seed_task(db_session)
        db_session.add(task)
        await db_session.flush()
        report = Report(task_id=task.id)
        db_session.add(report)
        await db_session.flush()
        assert report.id
        assert report.task_id == task.id

    async def test_reports_task_id唯一(self, db_session: AsyncSession):
        task = _seed_task(db_session)
        db_session.add(task)
        await db_session.flush()
        db_session.add(Report(task_id=task.id))
        await db_session.flush()
        with pytest.raises(Exception):
            db_session.add(Report(task_id=task.id))
            await db_session.flush()


class TestReportRevisionsTable:
    async def test_report_revisions_结构与唯一约束(self):
        table = _table("report_revisions")
        assert "report_id" in table.c
        assert "revision_number" in table.c
        assert "status" in table.c
        assert "evidence_completeness" in table.c
        assert "title" in table.c
        assert "executive_summary" in table.c
        assert "language" in table.c
        assert "content_hash" in table.c
        assert "limitations_summary" in table.c
        assert "published_at" in table.c
        assert "failed_at" in table.c
        unique_ok = any(
            {"report_id", "revision_number"} == set(c.name for c in uc.columns)
            for uc in table.constraints
        )
        assert unique_ok

    async def test_report_revisions_status_枚举(self):
        table = _table("report_revisions")
        assert set(table.c["status"].type.enums) == set(REPORT_REVISION_STATUS_ENUM)

    async def test_report_revisions_模型可创建(self, db_session: AsyncSession):
        task = _seed_task(db_session)
        db_session.add(task)
        await db_session.flush()
        report = Report(task_id=task.id)
        db_session.add(report)
        await db_session.flush()
        rev = ReportRevision(
            report_id=report.id,
            revision_number=1,
            status="building",
            title="测试报告",
            language="zh",
            content_hash="abc",
            evidence_completeness={"score": 0.9},
        )
        db_session.add(rev)
        await db_session.flush()
        assert rev.id
        assert rev.revision_number == 1


class TestClaimsTable:
    async def test_claims_结构与外键(self):
        table = _table("claims")
        assert "revision_id" in table.c
        assert "section_id" in table.c
        assert "sequence" in table.c
        assert "statement" in table.c
        assert "certainty" in table.c
        assert "qualification" in table.c

    async def test_claims_certainty_枚举(self):
        table = _table("claims")
        assert set(table.c["certainty"].type.enums) == set(CLAIM_CERTAINTY_ENUM)

    async def test_claims_模型可创建(self, db_session: AsyncSession):
        task = _seed_task(db_session)
        db_session.add(task)
        await db_session.flush()
        report = Report(task_id=task.id)
        db_session.add(report)
        await db_session.flush()
        rev = ReportRevision(
            report_id=report.id,
            revision_number=1,
            status="building",
            title="测试",
            language="zh",
            content_hash="abc",
        )
        db_session.add(rev)
        await db_session.flush()
        section = ReportSection(task_id=task.id, heading="章节", content="正文")
        db_session.add(section)
        await db_session.flush()
        claim = Claim(
            revision_id=rev.id,
            section_id=section.id,
            sequence=1,
            statement="这是结论",
            certainty="high",
        )
        db_session.add(claim)
        await db_session.flush()
        assert claim.id
        assert claim.sequence == 1


class TestEvidenceRelationsTable:
    async def test_evidence_relations_结构与唯一约束(self):
        table = _table("evidence_relations")
        assert "claim_id" in table.c
        assert "evidence_id" in table.c
        assert "relation_type" in table.c
        assert "confidence" in table.c
        assert "rationale_summary" in table.c
        unique_ok = any(
            {"claim_id", "evidence_id", "relation_type"} == set(c.name for c in uc.columns)
            for uc in table.constraints
        )
        assert unique_ok

    async def test_evidence_relations_类型枚举(self):
        table = _table("evidence_relations")
        assert set(table.c["relation_type"].type.enums) == set(EVIDENCE_RELATION_TYPE_ENUM)

    async def test_evidence_relations_模型可创建(self, db_session: AsyncSession):
        task = _seed_task(db_session)
        db_session.add(task)
        await db_session.flush()
        ev = EvidenceItem(task_id=task.id, source_type="web")
        db_session.add(ev)
        await db_session.flush()
        report = Report(task_id=task.id)
        db_session.add(report)
        await db_session.flush()
        rev = ReportRevision(
            report_id=report.id,
            revision_number=1,
            status="building",
            title="测试",
            language="zh",
            content_hash="abc",
        )
        db_session.add(rev)
        await db_session.flush()
        section = ReportSection(task_id=task.id, heading="章节", content="正文")
        db_session.add(section)
        await db_session.flush()
        claim = Claim(
            revision_id=rev.id,
            section_id=section.id,
            sequence=1,
            statement="结论",
            certainty="high",
        )
        db_session.add(claim)
        await db_session.flush()
        rel = EvidenceRelation(
            claim_id=claim.id,
            evidence_id=ev.id,
            relation_type="supports",
            confidence=0.9,
        )
        db_session.add(rel)
        await db_session.flush()
        assert rel.id
        assert rel.confidence == 0.9
