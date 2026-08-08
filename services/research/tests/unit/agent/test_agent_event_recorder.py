"""AgentEventRecorder 单元测试 —— 事件落库并带持久 sequence 发布 SSE。

对齐 RESEARCH_PIPELINE §15 / §17.3-22：
- record 追加事件到 agent_events（随 Step 事务提交），sequence 单调；
- SSE 发布携带持久 sequence 作为 event id，重连可通过游标回放；
- 事件与 SSE 载荷不暴露模型隐藏推理。
"""

from typing import cast

from app.agent.event_recorder import AgentEventRecorder
from app.models.research_task import ResearchTask
from app.pipeline.sse_bridge import (
    EVENT_AGENT_ACTION,
    EVENT_AGENT_OBSERVATION,
    EVENT_PHASE_STARTED,
    SSEBridge,
)
from app.services.agent_event_service import (
    EVENT_TYPE_PHASE_ENTER,
    EVENT_TYPE_TOOL_REQUEST,
    EVENT_TYPE_TOOL_RESULT,
    list_events_after,
)
from sqlalchemy.ext.asyncio import AsyncSession


class RecordingSSE:
    def __init__(self):
        self.published: list[tuple[str, dict, int | None]] = []

    async def publish(self, event_type, data=None, event_id=None):
        self.published.append((event_type, data or {}, event_id))


async def _make_task(db: AsyncSession) -> str:
    db.add(
        ResearchTask(id="rec-task-1", user_id="user-1", topic="t", requirements={"max_sources": 10})
    )
    await db.flush()
    return "rec-task-1"


class TestAgentEventRecorder:
    async def test_record_持久化并带sequence发布SSE(self, db_session):
        task_id = await _make_task(db_session)
        sse = RecordingSSE()
        recorder = AgentEventRecorder(task_id, db_session, cast(SSEBridge, sse))

        seq1 = await recorder.record(
            event_type=EVENT_TYPE_PHASE_ENTER,
            sse_event=EVENT_PHASE_STARTED,
            data={"phase": "planning"},
            input_summary={"phase": "planning"},
        )
        seq2 = await recorder.record(
            event_type=EVENT_TYPE_TOOL_REQUEST,
            sse_event=EVENT_AGENT_ACTION,
            data={"tool_name": "search_tool", "arguments": {}},
            tool_name="search_tool",
            input_summary={"tool_name": "search_tool", "arguments": {}},
        )

        assert (seq1, seq2) == (1, 2)
        assert sse.published == [
            (EVENT_PHASE_STARTED, {"phase": "planning"}, 1),
            (EVENT_AGENT_ACTION, {"tool_name": "search_tool", "arguments": {}}, 2),
        ]

        rows = await list_events_after(db_session, task_id, last_sequence=None)
        assert [r.sequence for r in rows] == [1, 2]
        assert [r.event_type for r in rows] == [EVENT_TYPE_PHASE_ENTER, EVENT_TYPE_TOOL_REQUEST]

    async def test_record_不发布也不落库隐藏推理(self, db_session):
        task_id = await _make_task(db_session)
        sse = RecordingSSE()
        recorder = AgentEventRecorder(task_id, db_session, cast(SSEBridge, sse))

        await recorder.record(
            event_type=EVENT_TYPE_TOOL_RESULT,
            sse_event=EVENT_AGENT_OBSERVATION,
            data={
                "tool_name": "plan_tool",
                "observation": "完成",
                "success": True,
                "reasoning": "隐藏推理",
            },
            tool_name="plan_tool",
            result_summary={
                "tool_name": "plan_tool",
                "observation": "完成",
                "success": True,
                "reasoning": "隐藏推理",
            },
        )

        assert len(sse.published) == 1
        assert "reasoning" not in sse.published[0][1]

        rows = await list_events_after(db_session, task_id, last_sequence=None)
        assert len(rows) == 1
        assert "reasoning" not in (rows[0].result_summary or {})
        assert rows[0].result_summary.get("observation") == "完成"

    async def test_record_支持duration与cost观测字段(self, db_session):
        task_id = await _make_task(db_session)
        recorder = AgentEventRecorder(task_id, db_session, cast(SSEBridge, RecordingSSE()))
        await recorder.record(
            event_type=EVENT_TYPE_TOOL_RESULT,
            sse_event=EVENT_AGENT_OBSERVATION,
            data={"tool_name": "plan_tool", "success": True},
            tool_name="plan_tool",
            duration_ms=120,
            cost_summary={"estimated_cost_usd": 0.001},
        )
        rows = await list_events_after(db_session, task_id, last_sequence=None)
        assert rows[0].duration_ms == 120
        assert rows[0].cost_summary == {"estimated_cost_usd": 0.001}
