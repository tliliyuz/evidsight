"""Research v1 API 测试 — 切片 8 收敛路由（list/get/cancel/resume/delete/events/state/report）。

对齐 API.md §8（Research Task API 目标态前缀）：
- GET    /api/v1/research/tasks — 列表（分页+状态筛选）
- GET    /api/v1/research/tasks/{task_id} — 详情（E2001/E2002）
- POST   /api/v1/research/tasks/{task_id}/cancel — 请求取消（§13.2）
- POST   /api/v1/research/tasks/{task_id}/resume — 断点续跑（旧 /retry 语义等价）
- DELETE /api/v1/research/tasks/{task_id} — 删除（204）
- GET    /api/v1/research/tasks/{task_id}/events — SSE 事件流
- GET    /api/v1/research/tasks/{task_id}/state — REST 状态快照
- GET    /api/v1/research/tasks/{task_id}/report — 完整研究报告

创建语义（POST /tasks 幂等）由 test_research_v1_create.py 覆盖，不在此重复。
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

USER_ID = "550e8400-e29b-41d4-a716-446655440000"


async def _seed_pending_task(db_session: AsyncSession, topic: str = "v1 任务") -> ResearchTask:
    task = ResearchTask(
        user_id=USER_ID,
        topic=topic,
        requirements={"task_type": "analysis"},
        status="pending",
    )
    db_session.add(task)
    await db_session.flush()
    return task


async def _seed_failed_task(db_session: AsyncSession, *, recoverable: bool = True) -> ResearchTask:
    task = ResearchTask(
        user_id=USER_ID,
        topic="可续跑任务",
        requirements={"task_type": "analysis"},
        status="failed",
        recoverable=recoverable,
        error_code="E3106",
        error_message="瞬时故障",
    )
    db_session.add(task)
    await db_session.flush()
    return task


async def _seed_completed_task_with_report(db_session: AsyncSession) -> ResearchTask:
    """预置已完成任务 + published Revision 报告（切片 4 单写目标态）。"""
    task = ResearchTask(
        id="task-v1-report-001",
        user_id=USER_ID,
        topic="量子计算威胁",
        requirements={"task_type": "analysis"},
        status="completed",
        completed_at=datetime(2026, 1, 1, 0, 0, 8, tzinfo=timezone.utc),
    )
    db_session.add(task)
    await db_session.flush()

    source = ResearchSource(
        task_id=task.id,
        url="https://example.com/qc",
        title="量子计算来源",
        domain="example.com",
        content="量子计算对 RSA 构成威胁。",
        fetch_status="success",
    )
    db_session.add(source)
    await db_session.flush()

    ev1 = EvidenceItem(
        task_id=task.id,
        source_type="web",
        source_id=source.id,
        canonical_url_snapshot=source.url,
        display_title=source.title,
        content=source.content,
        relevance_score=0.95,
    )
    db_session.add(ev1)
    await db_session.flush()

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
    db_session.add(graph_step)

    # 切片 4 单写：reports → revision → sections
    report = Report(task_id=task.id)
    db_session.add(report)
    await db_session.flush()
    revision = ReportRevision(
        report_id=report.id,
        revision_number=1,
        status="published",
        title=task.topic,
        published_at=datetime(2026, 1, 1, 0, 0, 8, tzinfo=timezone.utc),
    )
    db_session.add(revision)
    await db_session.flush()
    report.current_revision_id = revision.id

    section = ReportSection(
        task_id=task.id,
        revision_id=revision.id,
        heading="1. 概述",
        content="量子计算威胁[来源0]。",
        sort_order=0,
    )
    db_session.add(section)
    await db_session.flush()
    db_session.add(SectionEvidence(section_id=section.id, evidence_id=ev1.id))
    await db_session.flush()

    return task


class TestV1ListResearch:
    """GET /api/v1/research/tasks"""

    async def test_空列表_返回total为0(self, async_client: AsyncClient, auth_headers: dict):
        response = await async_client.get("/api/v1/research/tasks", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 0
        assert data["items"] == []

    async def test_有任务时_返回列表(
        self, async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        await _seed_pending_task(db_session, topic="v1 列表任务")
        response = await async_client.get("/api/v1/research/tasks", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["topic"] == "v1 列表任务"

    async def test_非法status_返回422(self, async_client: AsyncClient, auth_headers: dict):
        response = await async_client.get(
            "/api/v1/research/tasks?status=invalid", headers=auth_headers
        )
        assert response.status_code == 422


class TestV1DetailResearch:
    """GET /api/v1/research/tasks/{task_id}"""

    async def test_正常获取详情(
        self, async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        task = await _seed_pending_task(db_session, topic="v1 详情")
        response = await async_client.get(f"/api/v1/research/tasks/{task.id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["task_id"] == task.id
        assert data["topic"] == "v1 详情"
        assert data["status"] == "pending"
        assert "progress" in data

    async def test_任务不存在_返回404_E2001(self, async_client: AsyncClient, auth_headers: dict):
        response = await async_client.get(
            "/api/v1/research/tasks/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert response.status_code == 404
        assert response.json()["code"] == "E2001"

    async def test_无权访问他人任务_返回403_E2002(
        self, async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        task = ResearchTask(
            user_id="550e8400-e29b-41d4-a716-446655440999",
            topic="别人的任务",
            requirements={"task_type": "analysis"},
            status="pending",
        )
        db_session.add(task)
        await db_session.flush()
        response = await async_client.get(f"/api/v1/research/tasks/{task.id}", headers=auth_headers)
        assert response.status_code == 403
        assert response.json()["code"] == "E2002"


class TestV1CancelResearch:
    """POST /api/v1/research/tasks/{task_id}/cancel"""

    async def test_pending任务_取消请求_返回202(
        self, async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        task = await _seed_pending_task(db_session)
        response = await async_client.post(
            f"/api/v1/research/tasks/{task.id}/cancel", headers=auth_headers
        )
        assert response.status_code == 202
        body = response.json()
        assert body["code"] == "0"
        assert body["data"]["cancel_requested"] is True


class TestV1ResumeResearch:
    """POST /api/v1/research/tasks/{task_id}/resume"""

    async def test_failed可续跑任务_返回202(
        self, async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        task = await _seed_failed_task(db_session)
        with patch("app.api.research_v1._execute_research_task.delay") as mock_delay:
            response = await async_client.post(
                f"/api/v1/research/tasks/{task.id}/resume", headers=auth_headers
            )
        assert response.status_code == 202
        body = response.json()
        assert body["code"] == "0"
        assert body["data"]["status"] == "running"
        mock_delay.assert_called_once_with(str(task.id))

    async def test_不可续跑任务_返回409(
        self, async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        task = await _seed_failed_task(db_session, recoverable=False)
        response = await async_client.post(
            f"/api/v1/research/tasks/{task.id}/resume", headers=auth_headers
        )
        assert response.status_code == 409


class TestV1DeleteResearch:
    """DELETE /api/v1/research/tasks/{task_id}"""

    async def test_删除返回204(
        self, async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        task = await _seed_pending_task(db_session)
        response = await async_client.delete(
            f"/api/v1/research/tasks/{task.id}", headers=auth_headers
        )
        assert response.status_code == 204

        # 删除后查询返回 404
        detail = await async_client.get(f"/api/v1/research/tasks/{task.id}", headers=auth_headers)
        assert detail.status_code == 404


class TestV1StateResearch:
    """GET /api/v1/research/tasks/{task_id}/state"""

    async def test_返回REST状态快照(
        self, async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        task = await _seed_pending_task(db_session)
        response = await async_client.get(
            f"/api/v1/research/tasks/{task.id}/state", headers=auth_headers
        )
        assert response.status_code == 200
        snapshot = response.json()["data"]
        assert snapshot["task_id"] == task.id
        assert snapshot["status"] == "pending"
        assert "progress" in snapshot
        assert "steps" in snapshot


class TestV1EventsResearch:
    """GET /api/v1/research/tasks/{task_id}/events（SSE）"""

    async def test_终态任务_推送snapshot后关闭(
        self, async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        task = await _seed_completed_task_with_report(db_session)
        response = await async_client.get(
            f"/api/v1/research/tasks/{task.id}/events", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert "task.status.snapshot" in response.text


class TestV1ReportResearch:
    """GET /api/v1/research/tasks/{task_id}/report"""

    async def test_已完成任务返回完整报告JSON(
        self, async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        task = await _seed_completed_task_with_report(db_session)
        response = await async_client.get(
            f"/api/v1/research/tasks/{task.id}/report", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["task_id"] == task.id
        assert data["status"] == "completed"
        assert data["report"]["title"] == task.topic
        assert len(data["report"]["sections"]) == 1
        assert data["report"]["sections"][0]["heading"] == "1. 概述"
        assert len(data["report"]["sources"]) == 1
        assert "trace" in data

    async def test_任务不存在_返回404_E2001(self, async_client: AsyncClient, auth_headers: dict):
        response = await async_client.get(
            "/api/v1/research/tasks/00000000-0000-0000-0000-000000000000/report",
            headers=auth_headers,
        )
        assert response.status_code == 404
        assert response.json()["code"] == "E2001"
