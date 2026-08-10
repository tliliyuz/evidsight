"""Evidence / Report 字段级契约测试 — 真实路由响应逐字段对齐 docs/openapi/evidsight-v1.yaml。

对齐 TESTING.md §4：External OpenAPI 的 Provider 契约测试必须验证真实路由响应
与 OpenAPI 组件 Schema 一致。本文件覆盖：
- GET /api/v1/research/tasks/{task_id}/evidence   → EvidenceList / Evidence
- GET /api/v1/evidence/{evidence_id}              → Evidence
- GET /api/v1/evidence/{evidence_id}/relations    → EvidenceRelationList / EvidenceRelation
- GET /api/v1/reports/{report_id}                 → Report / ReportSection / ReportEvidenceReference
- GET /api/v1/reports/{report_id}/sections/{section_id} → ReportSection

Evidence/Report 响应由 report_reader 手拼 dict，字段级校验可捕获实现与
OpenAPI 的值级漂移（如字段类型/嵌套结构不一致）。
"""

from datetime import datetime, timezone

from app.models.claim import Claim
from app.models.evidence_item import EvidenceItem
from app.models.evidence_relation import EvidenceRelation
from app.models.report import Report
from app.models.report_revision import ReportRevision
from app.models.report_section import ReportSection
from app.models.research_source import ResearchSource
from app.models.research_task import ResearchTask
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.contract.openapi_utils import assert_data_matches_schema, assert_data_matches_schema_deep


async def _seed_task_with_data(
    db_session: AsyncSession,
    task_suffix: str = "f001",
) -> tuple[ResearchTask, Report, ReportRevision, EvidenceItem, ReportSection, Claim]:
    task = ResearchTask(
        id=f"task-ev-{task_suffix}",
        user_id="550e8400-e29b-41d4-a716-446655440000",
        topic="API 测试主题",
        requirements={"task_type": "explainer", "max_sources": 5, "language": "zh"},
        status="completed",
        source_strategy="web",
        total_evidence=2,
    )
    db_session.add(task)
    await db_session.flush()

    src = ResearchSource(
        task_id=task.id, url="https://a.example.com", title="来源A", domain="example.com"
    )
    db_session.add(src)
    await db_session.flush()

    ev1 = EvidenceItem(
        task_id=task.id,
        source_type="web",
        source_id=src.id,
        canonical_url_snapshot="https://a.example.com",
        fetched_at_snapshot=datetime(2026, 1, 1, tzinfo=timezone.utc),
        display_title="来源A",
        location_summary="page 1",
        relevance_score=0.9,
    )
    db_session.add(ev1)
    await db_session.flush()
    ev2 = EvidenceItem(
        task_id=task.id,
        source_type="internal",
        knowledge_base_id="kb-1",
        document_id="doc-1",
        document_version_id="ver-1",
        segment_id="seg-1",
        document_display_name_snapshot="内部文档",
        display_title="内部文档",
        location_summary="§2.1",
        relevance_score=0.8,
    )
    db_session.add(ev2)
    await db_session.flush()

    report = Report(task_id=task.id)
    db_session.add(report)
    await db_session.flush()

    rev = ReportRevision(
        report_id=report.id,
        revision_number=1,
        status="published",
        title="API 测试报告",
        language="zh",
        content_hash="hash1",
        evidence_completeness={
            "question_coverage": 1.0,
            "channel_success": 1.0,
            "claim_coverage": 1.0,
            "score": 1.0,
            "rule_version": 1,
        },
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    db_session.add(rev)
    await db_session.flush()
    report.current_revision_id = rev.id

    section = ReportSection(
        task_id=task.id,
        revision_id=rev.id,
        heading="1. 概述",
        content="正文引用[来源0]",
        sort_order=0,
    )
    db_session.add(section)
    await db_session.flush()

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
        evidence_id=ev1.id,
        relation_type="supports",
        confidence=0.9,
    )
    db_session.add(rel)

    await db_session.flush()
    return task, report, rev, ev1, section, claim


class TestEvidenceListFieldContract:
    """GET /api/v1/research/tasks/{task_id}/evidence → EvidenceList"""

    async def test_任务证据列表字段级契约(
        self, async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        task, *_ = await _seed_task_with_data(db_session)
        resp = await async_client.get(
            f"/api/v1/research/tasks/{task.id}/evidence", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert_data_matches_schema("EvidenceList", data)
        assert_data_matches_schema_deep("EvidenceList", data)
        for item in data["items"]:
            assert_data_matches_schema("Evidence", item)
            assert_data_matches_schema_deep("Evidence", item)


class TestEvidenceDetailFieldContract:
    """GET /api/v1/evidence/{evidence_id} → Evidence"""

    async def test_单条证据字段级契约(
        self, async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        task, report, rev, ev1, section, claim = await _seed_task_with_data(db_session)
        resp = await async_client.get(f"/api/v1/evidence/{ev1.external_id}", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert_data_matches_schema("Evidence", data)
        assert_data_matches_schema_deep("Evidence", data)


class TestEvidenceRelationsFieldContract:
    """GET /api/v1/evidence/{evidence_id}/relations → EvidenceRelationList"""

    async def test_证据关系字段级契约(
        self, async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        task, report, rev, ev1, section, claim = await _seed_task_with_data(db_session)
        resp = await async_client.get(
            f"/api/v1/evidence/{ev1.external_id}/relations", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert_data_matches_schema("EvidenceRelationList", data)
        assert_data_matches_schema_deep("EvidenceRelationList", data)
        for item in data["items"]:
            assert_data_matches_schema("EvidenceRelation", item)
            assert_data_matches_schema_deep("EvidenceRelation", item)


class TestReportFieldContract:
    """GET /api/v1/reports/{report_id} → Report"""

    async def test_报告详情字段级契约(
        self, async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        task, report, rev, ev1, section, claim = await _seed_task_with_data(db_session)
        resp = await async_client.get(f"/api/v1/reports/{report.id}", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert_data_matches_schema("Report", data)
        assert_data_matches_schema_deep("Report", data)
        for section_data in data["sections"]:
            assert_data_matches_schema("ReportSection", section_data)
            assert_data_matches_schema_deep("ReportSection", section_data)
            for ref in section_data["evidence"]:
                assert_data_matches_schema("ReportEvidenceReference", ref)


class TestReportSectionFieldContract:
    """GET /api/v1/reports/{report_id}/sections/{section_id} → ReportSection"""

    async def test_报告单章节字段级契约(
        self, async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        task, report, rev, ev1, section, claim = await _seed_task_with_data(db_session)
        resp = await async_client.get(
            f"/api/v1/reports/{report.id}/sections/{section.external_id}", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert_data_matches_schema("ReportSection", data)
        assert_data_matches_schema_deep("ReportSection", data)
