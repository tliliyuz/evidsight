"""Research SSE 逐事件校验 — 对齐 TESTING.md §4/§131 与 API.md §13。

TESTING.md §131：Chat/Research SSE 除路径外还必须逐事件校验事件名、顺序与
每种 data Schema。事件名投影（task.*→task.updated 等）由
tests/unit/api/test_research_sse_canonical.py 覆盖，本文件补齐 data Schema
逐事件校验：
- 真实路由终态流：seed completed 任务 → GET /events → 帧序 [snapshot,
  stream.end]，每帧 data 用 `assert_sse_events` 对
  x-sse-data-schemas 映射做 jsonschema 校验；
- error 帧 data 必须符合 StreamErrorEventData（错误事件由 Redis 驱动，
  用构造帧做单元校验）。
"""

from datetime import datetime, timezone

from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.contract.openapi_utils import (
    assert_sse_events,
    load_sse_event_schemas,
)

USER_ID = "550e8400-e29b-41d4-a716-446655440000"
EVENTS_PATH = "/api/v1/research/tasks/{task_id}/events"


async def _seed_completed_task_with_steps(db: AsyncSession) -> ResearchTask:
    """预置已完成任务 + 多种 Step 形态，覆盖 ResearchTaskStateStep 深层字段。"""
    task = ResearchTask(
        user_id=USER_ID,
        topic="SSE 校验任务",
        requirements={"task_type": "analysis"},
        status="completed",
        total_steps=2,
        completed_steps=2,
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
                output={"sub_questions": [{"q": "a"}]},
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
        ]
    )
    await db.flush()
    return task


class TestTerminalStreamSchema:
    """GET /api/v1/research/tasks/{task_id}/events — 终态流逐事件校验"""

    async def test_终态流_帧序snapshot_stream_end_且data逐事件校验(
        self, async_client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        task = await _seed_completed_task_with_steps(db_session)
        resp = await async_client.get(EVENTS_PATH.format(task_id=task.id), headers=auth_headers)
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

        event_schemas = load_sse_event_schemas(EVENTS_PATH, "get")
        events = assert_sse_events(
            resp.text,
            event_schemas,
            first_event="snapshot",
            terminal_events=frozenset({"stream.end", "error"}),
        )
        assert [name for name, _ in events] == ["snapshot", "stream.end"]

        # 快照 data 深层字段（steps 引用 ResearchTaskStateStep）
        snapshot = events[0][1]
        assert snapshot["task_id"] == task.id
        assert snapshot["status"] == "completed"
        by_type = {s["step_type"]: s for s in snapshot["steps"]}
        assert by_type["planning"]["sub_questions_count"] == 1
        assert by_type["search"]["after_dedup"] == 4
        assert by_type["search"]["progress_label"] == "5 条结果"
        # 终态帧 payload
        assert events[1] == ("stream.end", {"reason": "terminal_snapshot"})

    async def test_终态流_无任务数据时报404(self, async_client: AsyncClient, auth_headers: dict):
        resp = await async_client.get(
            EVENTS_PATH.format(task_id="00000000-0000-0000-0000-000000000000"),
            headers=auth_headers,
        )
        assert resp.status_code == 404


class TestErrorFrameSchema:
    """error 事件 data 必须符合 StreamErrorEventData"""

    def test_error帧_data校验通过(self):
        event_schemas = load_sse_event_schemas(EVENTS_PATH, "get")
        events = assert_sse_events(
            'event: error\ndata: {"error_code":"E3106","message":"瞬时故障","retryable":false}\n\n',
            event_schemas,
        )
        assert events[0][1] == {
            "error_code": "E3106",
            "message": "瞬时故障",
            "retryable": False,
        }

    def test_error帧_缺少必填字段校验失败(self):
        from pytest import raises

        event_schemas = load_sse_event_schemas(EVENTS_PATH, "get")
        with raises(AssertionError):
            assert_sse_events('event: error\ndata: {"error_code":"E3106"}\n\n', event_schemas)
