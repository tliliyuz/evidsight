"""Research v1 字段级契约测试 — 真实路由响应逐字段对齐 docs/openapi/evidsight-v1.yaml。

对齐 TESTING.md §4 与 §131：External OpenAPI 的 Provider 契约测试必须验证
真实路由响应与 OpenAPI 组件 Schema 一致（不只声明 content schema）。本文件
用真实 db_session 播种 + 真实 FastAPI 路由 + `assert_data_matches_schema`，
覆盖：
- POST   /api/v1/research/tasks                → ResearchTaskCreateResponse
- GET    /api/v1/research/tasks                → ResearchTaskList / ResearchTaskListItem
- GET    /api/v1/research/tasks/{task_id}      → ResearchTask
- POST   /api/v1/research/tasks/{task_id}/cancel → ResearchCancelResponse
- POST   /api/v1/research/tasks/{task_id}/resume → ResearchRetryResponse / ResearchResumeFrom
- GET    /api/v1/research/tasks/{task_id}/state  → ResearchTaskState / ResearchTaskStateStep
- GET    /api/v1/research/tasks/{task_id}/report → ResearchTaskReportResponse / ResearchReport

嵌套对象在浅层断言之外显式做深层断言（steps / report.sections / sources），
防止 schema 漂移只发生在深层字段时漏检。
"""

from datetime import datetime, timezone
from unittest.mock import patch

from app.models.evidence_item import EvidenceItem
from app.models.report import Report
from app.models.report_revision import ReportRevision
from app.models.report_section import ReportSection
from app.models.research_source import ResearchSource
from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask
from app.models.section_evidence import SectionEvidence
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.contract.openapi_utils import assert_data_matches_schema, assert_data_matches_schema_deep

USER_ID = "550e8400-e29b-41d4-a716-446655440000"


async def _seed_pending_task(db: AsyncSession, topic: str = "字段契约任务") -> ResearchTask:
    task = ResearchTask(
        user_id=USER_ID,
        topic=topic,
        requirements={"task_type": "analysis"},
        status="pending",
    )
    db.add(task)
    await db.flush()
    return task


async def _seed_running_task_with_steps(db: AsyncSession) -> ResearchTask:
    """预置 running 任务 + 各类已完成/失败 Step，覆盖 ResearchTaskStateStep 深层字段。"""
    task = ResearchTask(
        user_id=USER_ID,
        topic="带步骤的任务",
        requirements={"task_type": "analysis"},
        status="running",
        total_steps=3,
        completed_steps=1,
    )
    db.add(task)
    await db.flush()

    db.add_all(
        [
            ResearchStep(
                task_id=task.id,
                step_type="planning",
                status="completed",
                label="规划拆解",
                output={"sub_questions": [{"q": "a"}, {"q": "b"}, {"q": "c"}]},
                started_at=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
                completed_at=datetime(2026, 1, 1, 0, 0, 2, tzinfo=timezone.utc),
                duration_ms=1000,
            ),
            ResearchStep(
                task_id=task.id,
                step_type="search",
                status="completed",
                label="来源检索",
                output={"results_found": 5, "after_dedup": 4, "sources_created": 3},
                duration_ms=800,
            ),
            ResearchStep(
                task_id=task.id,
                step_type="fetch",
                status="failed",
                label="正文抓取",
                error_code="E3106",
                error_message="瞬时故障",
                duration_ms=None,
            ),
        ]
    )
    await db.flush()
    return task


async def _seed_completed_task_with_report(db: AsyncSession) -> ResearchTask:
    """预置已完成任务 + published Revision 报告（对齐 get_report 读取路径）。"""
    task = ResearchTask(
        id="task-field-report-001",
        user_id=USER_ID,
        topic="量子计算威胁",
        requirements={"task_type": "analysis"},
        status="completed",
        completed_at=datetime(2026, 1, 1, 0, 0, 8, tzinfo=timezone.utc),
    )
    db.add(task)
    await db.flush()

    source = ResearchSource(
        task_id=task.id,
        url="https://example.com/qc",
        title="量子计算来源",
        domain="example.com",
        content="量子计算对 RSA 构成威胁。",
        fetch_status="success",
    )
    db.add(source)
    await db.flush()

    ev1 = EvidenceItem(
        task_id=task.id,
        source_type="web",
        source_id=source.id,
        canonical_url_snapshot=source.url,
        display_title=source.title,
        content=source.content,
        relevance_score=0.95,
    )
    db.add(ev1)
    await db.flush()

    graph_step = ResearchStep(
        task_id=task.id,
        step_type="evidence_graph",
        status="completed",
        label="来源图谱：结构化认知资产构建",
        output={
            "graph": {
                "task_id": task.id,
                "generated_at": "2026-01-01T00:00:10Z",
                "items": [
                    {
                        "index": 0,
                        "evidence_item_id": ev1.id,
                        "source_type": "web",
                        "source_id": source.id,
                        "source_url": source.url,
                        "source_title": source.title,
                        "domain": source.domain,
                        "content": ev1.content,
                        "relevance_score": 0.95,
                        "used_in_sections": ["1"],
                    }
                ],
                "clusters": [],
                "conflicts": [],
                "knowledge_gaps": [],
                "sources": [
                    {
                        "id": source.id,
                        "url": source.url,
                        "title": source.title,
                        "domain": source.domain,
                        "evidence_count": 1,
                    }
                ],
            }
        },
        started_at=datetime(2026, 1, 1, 0, 0, 6, tzinfo=timezone.utc),
        completed_at=datetime(2026, 1, 1, 0, 0, 7, tzinfo=timezone.utc),
        duration_ms=1000,
    )
    db.add(graph_step)

    report = Report(task_id=task.id)
    db.add(report)
    await db.flush()
    revision = ReportRevision(
        report_id=report.id,
        revision_number=1,
        status="published",
        title=task.topic,
        published_at=datetime(2026, 1, 1, 0, 0, 8, tzinfo=timezone.utc),
    )
    db.add(revision)
    await db.flush()
    report.current_revision_id = revision.id

    section = ReportSection(
        task_id=task.id,
        revision_id=revision.id,
        heading="1. 概述",
        content="量子计算威胁[来源0]。",
        sort_order=0,
    )
    db.add(section)
    await db.flush()
    db.add(SectionEvidence(section_id=section.id, evidence_id=ev1.id))
    await db.flush()
    return task


class TestCreateFieldContract:
    """POST /api/v1/research/tasks → ResearchTaskCreateResponse"""

    async def test_创建响应字段级契约(self, async_client: AsyncClient, auth_headers: dict):
        payload = {
            "topic": "量子计算对密码学的影响",
            "requirements": {"task_type": "analysis", "depth": "quick"},
            "source_strategy": "knowledge",
            "knowledge_base_ids": ["11111111-1111-4111-8111-111111111111"],
        }
        with patch("app.api.research_v1._execute_research_task.delay"):
            resp = await async_client.post(
                "/api/v1/research/tasks",
                json=payload,
                headers={**auth_headers, "Idempotency-Key": "field-contract-key"},
            )
        assert resp.status_code == 202, resp.text
        data = resp.json()
        assert_data_matches_schema("ResearchTaskCreateResponse", data)
        assert_data_matches_schema_deep("ResearchTaskCreateResponse", data)
        assert data["status"] in {
            "pending",
            "running",
            "completed",
            "partially_completed",
            "failed",
            "canceled",
            "paused",
        }


class TestListFieldContract:
    """GET /api/v1/research/tasks → ResearchTaskList"""

    async def test_列表响应字段级契约(
        self, async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        await _seed_pending_task(db_session, topic="列表契约")
        resp = await async_client.get("/api/v1/research/tasks", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert_data_matches_schema("ResearchTaskList", data)
        assert_data_matches_schema_deep("ResearchTaskList", data)
        for item in data["items"]:
            assert_data_matches_schema("ResearchTaskListItem", item)
            assert_data_matches_schema_deep("ResearchTaskListItem", item)


class TestDetailFieldContract:
    """GET /api/v1/research/tasks/{task_id} → ResearchTask"""

    async def test_详情响应字段级契约(
        self, async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        task = await _seed_pending_task(db_session)
        resp = await async_client.get(f"/api/v1/research/tasks/{task.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert_data_matches_schema("ResearchTask", data)
        assert_data_matches_schema_deep("ResearchTask", data)
        assert_data_matches_schema("ResearchRequirements", data["requirements"])
        assert_data_matches_schema("ResearchProgress", data["progress"])


class TestCancelFieldContract:
    """POST /api/v1/research/tasks/{task_id}/cancel → ResearchCancelResponse"""

    async def test_取消响应字段级契约(
        self, async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        task = await _seed_pending_task(db_session)
        resp = await async_client.post(
            f"/api/v1/research/tasks/{task.id}/cancel", headers=auth_headers
        )
        assert resp.status_code == 202
        data = resp.json()
        assert_data_matches_schema("ResearchCancelResponse", data)
        assert_data_matches_schema_deep("ResearchCancelResponse", data)


class TestResumeFieldContract:
    """POST /api/v1/research/tasks/{task_id}/resume → ResearchRetryResponse"""

    async def test_续跑响应字段级契约(
        self, async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        task = ResearchTask(
            user_id=USER_ID,
            topic="可续跑任务",
            requirements={"task_type": "analysis"},
            status="failed",
            recoverable=True,
            error_code="E3106",
            error_message="瞬时故障",
        )
        db_session.add(task)
        await db_session.flush()
        with patch("app.api.research_v1._execute_research_task.delay"):
            resp = await async_client.post(
                f"/api/v1/research/tasks/{task.id}/resume", headers=auth_headers
            )
        assert resp.status_code == 202
        data = resp.json()
        assert_data_matches_schema("ResearchRetryResponse", data)
        assert_data_matches_schema_deep("ResearchRetryResponse", data)
        assert_data_matches_schema("ResearchResumeFrom", data["resume_from"])


class TestStateFieldContract:
    """GET /api/v1/research/tasks/{task_id}/state → ResearchTaskState"""

    async def test_状态快照字段级契约含步骤深层断言(
        self, async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        task = await _seed_running_task_with_steps(db_session)
        resp = await async_client.get(
            f"/api/v1/research/tasks/{task.id}/state", headers=auth_headers
        )
        assert resp.status_code == 200
        snapshot = resp.json()
        assert_data_matches_schema("ResearchTaskState", snapshot)
        assert_data_matches_schema_deep("ResearchTaskState", snapshot)
        assert_data_matches_schema("ResearchProgress", snapshot["progress"])
        assert snapshot["stats"]["total_sources"] == 0
        assert snapshot["stats"]["total_evidence"] == 0
        # 步骤深层字段：completed/failed 各形态必须落在 ResearchTaskStateStep 契约内
        assert len(snapshot["steps"]) == 3
        by_type = {s["step_type"]: s for s in snapshot["steps"]}
        assert_data_matches_schema("ResearchTaskStateStep", by_type["planning"])
        assert by_type["planning"]["sub_questions_count"] == 3
        assert_data_matches_schema("ResearchTaskStateStep", by_type["search"])
        assert by_type["search"]["after_dedup"] == 4
        assert by_type["search"]["sources_created"] == 3
        assert by_type["search"]["progress_label"] == "5 条结果"
        assert_data_matches_schema("ResearchTaskStateStep", by_type["fetch"])
        assert by_type["fetch"]["error_code"] == "E3106"


class TestReportFieldContract:
    """GET /api/v1/research/tasks/{task_id}/report → ResearchTaskReportResponse"""

    async def test_报告响应字段级契约含章节深层断言(
        self, async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        task = await _seed_completed_task_with_report(db_session)
        resp = await async_client.get(
            f"/api/v1/research/tasks/{task.id}/report", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert_data_matches_schema("ResearchTaskReportResponse", data)
        assert_data_matches_schema_deep("ResearchTaskReportResponse", data)
        report = data["report"]
        assert_data_matches_schema("ResearchReport", report)
        assert len(report["sections"]) >= 1
        for section in report["sections"]:
            assert_data_matches_schema("ResearchReportSection", section)
            for src in section["sources"]:
                assert_data_matches_schema("ResearchReportSectionSource", src)
        for src in report["sources"]:
            assert_data_matches_schema("ResearchReportSource", src)
        assert report["sources"][0]["id"] >= 0
