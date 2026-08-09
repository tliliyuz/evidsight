"""Evidence 与 Report 读取 API 单元测试 —— 对齐 API.md §9。

覆盖切片 5 验收（task READ 权限）：
- GET /api/v1/research/tasks/{task_id}/evidence：任务证据列表（internal/web 区分，内部无正文）；
- GET /api/v1/evidence/{evidence_id}：单条证据（按对外 UUID）；
- GET /api/v1/evidence/{evidence_id}/relations：supports/contradicts/context 关系；
- GET /api/v1/reports/{report_id}：报告（published Revision、章节、引用、完整度摘要）；
- GET /api/v1/reports/{report_id}/sections/{section_id}：单章节。
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.models.claim import Claim
from app.models.evidence_item import EvidenceItem
from app.models.evidence_relation import EvidenceRelation
from app.models.report import Report
from app.models.report_revision import ReportRevision
from app.models.report_section import ReportSection
from app.models.research_source import ResearchSource
from app.models.research_task import ResearchTask


async def _seed_task_with_data(
    db_session,
    task_suffix: str = "e001",
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


async def _login(async_client, user_id: str = "550e8400-e29b-41d4-a716-446655440000"):
    """注入用户身份到 request.state（async_client 覆盖 get_current_user）。"""
    from fastapi import Request

    async def override_get_current_user(request: Request) -> dict:
        return {
            "user_id": user_id,
            "username": "testuser",
            "role": "user",
        }

    from app.dependencies import get_current_user

    async_client.app.dependency_overrides[get_current_user] = override_get_current_user
    await async_client.app.router.startup() if hasattr(async_client.app.router, "startup") else None


class TestEvidenceListAPI:
    async def test_任务证据列表_区分internal与web(self, db_session, async_client, auth_headers):
        task, report, rev, ev1, section, claim = await _seed_task_with_data(db_session)
        resp = await async_client.get(
            f"/api/v1/research/tasks/{task.id}/evidence", headers=auth_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        items = body["items"]
        assert len(items) == 2
        web = next(i for i in items if i["source_type"] == "web")
        internal = next(i for i in items if i["source_type"] == "internal")
        # web 展示 URL 与获取时间
        assert web["url"] == "https://a.example.com"
        assert web["fetched_at"] is not None
        # internal 无正文，展示稳定身份与位置
        assert "content" not in internal or internal["content"] is None
        assert internal["knowledge_base_id"] == "kb-1"
        assert internal["location_summary"] == "§2.1"
        # 对外 UUID
        uuid.UUID(internal["evidence_id"])

    async def test_任务证据列表_无权限_403(self, db_session, async_client, valid_access_token):
        task, report, rev, ev1, section, claim = await _seed_task_with_data(db_session)
        # 其他用户 token：sub 为合法 UUID，与 seed user_id 不同
        from datetime import datetime, timedelta, timezone

        from app.config import settings
        from jose import jwt

        other_token = jwt.encode(
            {
                "iss": settings.EVIDSIGHT_PLATFORM_JWT_ISSUER,
                "aud": ["evidsight-knowledge", settings.EVIDSIGHT_RESEARCH_JWT_AUDIENCE],
                "sub": "11111111-2222-3333-4444-555555555555",
                "username": "other",
                "role": "user",
                "token_type": "access",
                "jti": "other-user-jti",
                "iat": datetime.now(timezone.utc),
                "nbf": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
            },
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        resp = await async_client.get(
            f"/api/v1/research/tasks/{task.id}/evidence",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert resp.status_code == 403


class TestEvidenceDetailAPI:
    async def test_单条证据_按对外UUID(self, db_session, async_client, auth_headers):
        task, report, rev, ev1, section, claim = await _seed_task_with_data(db_session)
        resp = await async_client.get(f"/api/v1/evidence/{ev1.external_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["evidence_id"] == ev1.external_id
        assert data["source_type"] == "web"

    async def test_单条证据_不存在_404(self, db_session, async_client, auth_headers):
        resp = await async_client.get(
            "/api/v1/evidence/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert resp.status_code in (403, 404)

    async def test_鉴权后证据被删除_返回404(self, db_session, async_client, auth_headers):
        """依赖鉴权完成后证据消失时，不得返回成功信封 data=null。"""
        task, report, rev, ev1, section, claim = await _seed_task_with_data(db_session, "e002")
        with patch(
            "app.api.research_evidence.report_reader.get_evidence_detail",
            new=AsyncMock(return_value=None),
        ):
            resp = await async_client.get(
                f"/api/v1/evidence/{ev1.external_id}", headers=auth_headers
            )
        assert resp.status_code == 404


class TestEvidenceRelationsAPI:
    async def test_证据关系列表(self, db_session, async_client, auth_headers):
        task, report, rev, ev1, section, claim = await _seed_task_with_data(db_session)
        resp = await async_client.get(
            f"/api/v1/evidence/{ev1.external_id}/relations", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["relation_type"] == "supports"
        assert float(data["items"][0]["confidence"]) == 0.9
        assert data["items"][0]["claim"]["statement"] == "这是结论。"

    async def test_鉴权后证据被删除_返回404(self, db_session, async_client, auth_headers):
        """关系查询重取不到证据时，不得返回成功信封 data=null。"""
        task, report, rev, ev1, section, claim = await _seed_task_with_data(db_session, "e003")
        with patch(
            "app.api.research_evidence.report_reader.list_evidence_relations",
            new=AsyncMock(return_value=None),
        ):
            resp = await async_client.get(
                f"/api/v1/evidence/{ev1.external_id}/relations", headers=auth_headers
            )
        assert resp.status_code == 404


class TestReportAPI:
    async def test_报告详情(self, db_session, async_client, auth_headers):
        task, report, rev, ev1, section, claim = await _seed_task_with_data(db_session)
        resp = await async_client.get(f"/api/v1/reports/{report.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["report_id"] == report.id
        assert data["task_id"] == task.id
        assert data["revision"] == 1
        assert data["status"] == "published"
        assert data["evidence_completeness"]["score"] == 1.0
        assert len(data["sections"]) == 1
        assert data["sections"][0]["heading"] == "1. 概述"

    async def test_报告单章节(self, db_session, async_client, auth_headers):
        task, report, rev, ev1, section, claim = await _seed_task_with_data(db_session)
        resp = await async_client.get(
            f"/api/v1/reports/{report.id}/sections/{section.external_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["section_id"] == section.external_id
        assert data["heading"] == "1. 概述"
