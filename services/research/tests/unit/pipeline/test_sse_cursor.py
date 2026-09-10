"""Research SSE 持久游标测试 —— RESEARCH_PIPELINE §15 / §17.3-11。

验收：
- 重连携带 Last-Event-ID 时，先发快照，再回放游标后的可用 Agent Event；
- 不带游标时回放全部已持久化事件（新订阅收敛）；
- 回放事件带持久 sequence 作为 event id；
- 不依赖 Redis 历史恢复业务事实（快照 + DB 游标）。
"""

import asyncio
import json
from typing import cast
from unittest.mock import AsyncMock

import pytest
from app.agent.event_recorder import AgentEventRecorder
from app.models.research_task import ResearchTask
from app.pipeline.sse_bridge import (
    EVENT_AGENT_ACTION,
    EVENT_AGENT_OBSERVATION,
    EVENT_PHASE_STARTED,
    EVENT_TASK_STATUS_SNAPSHOT,
    SSEBridge,
    sse_event_stream,
)
from app.services.agent_event_service import (
    EVENT_TYPE_PHASE_ENTER,
    EVENT_TYPE_TOOL_REQUEST,
    EVENT_TYPE_TOOL_RESULT,
    list_events_after,
)
from sqlalchemy.ext.asyncio import AsyncSession


class FakePubSub:
    def __init__(self, messages=None):
        self._messages = list(messages or [])
        self.closed = False

    async def subscribe(self, channel):
        return None

    async def unsubscribe(self, channel):
        return None

    async def close(self):
        self.closed = True

    async def get_message(self, ignore_subscribe_messages=True, timeout=1.0):
        if self._messages:
            return {"type": "message", "data": self._messages.pop(0)}
        return None


class FakeRedis:
    def __init__(self, pubsub=None):
        self._pubsub = pubsub or FakePubSub()

    def pubsub(self):
        return self._pubsub


class RecordingSSE:
    async def publish(self, event_type, data=None, event_id=None):
        return None


async def _collect(agen, count: int, timeout: float = 5.0) -> list[str]:
    items: list[str] = []

    async def _grab():
        async for item in agen:
            items.append(item)
            if len(items) >= count:
                return

    await asyncio.wait_for(_grab(), timeout)
    return items


async def _seed_events(db_session: AsyncSession) -> str:
    db_session.add(
        ResearchTask(
            id="cursor-task-1",
            user_id="user-1",
            topic="t",
            requirements={"max_sources": 10},
        )
    )
    await db_session.flush()
    recorder = AgentEventRecorder("cursor-task-1", db_session, cast(SSEBridge, RecordingSSE()))
    await recorder.record(
        event_type=EVENT_TYPE_PHASE_ENTER,
        sse_event=EVENT_PHASE_STARTED,
        data={"phase": "planning"},
        input_summary={"phase": "planning"},
    )
    await recorder.record(
        event_type=EVENT_TYPE_TOOL_REQUEST,
        sse_event=EVENT_AGENT_ACTION,
        data={"tool_name": "search_tool", "arguments": {}},
        tool_name="search_tool",
        input_summary={"tool_name": "search_tool", "arguments": {}},
    )
    await recorder.record(
        event_type=EVENT_TYPE_TOOL_RESULT,
        sse_event=EVENT_AGENT_OBSERVATION,
        data={"tool_name": "search_tool", "observation": "完成", "success": True},
        tool_name="search_tool",
        result_summary={"tool_name": "search_tool", "observation": "完成", "success": True},
    )
    return "cursor-task-1"


@pytest.fixture
def fake_redis(monkeypatch):
    pubsub = FakePubSub()
    redis = FakeRedis(pubsub=pubsub)
    monkeypatch.setattr("app.pipeline.sse_bridge.get_async_redis", AsyncMock(return_value=redis))
    return redis


class TestSSEPersistentCursor:
    async def test_重连带游标先快照再回放游标后事件(self, db_session, fake_redis):
        task_id = await _seed_events(db_session)

        async def loader(after):
            return await list_events_after(db_session, task_id, last_sequence=after)

        stream = sse_event_stream(
            task_id,
            initial_snapshot={"status": "running"},
            last_event_id=1,
            replay_loader=loader,
        )
        chunks = await _collect(stream, 3)  # snapshot + seq2 + seq3
        text = "\n".join(chunks)

        assert f"event: {EVENT_TASK_STATUS_SNAPSHOT}" in text
        assert "id: 2" in text
        assert "event: agent.action" in text
        assert "id: 3" in text
        assert "event: agent.observation" in text
        # seq 1 已消费，不回放
        assert "id: 1" not in text

    async def test_不带游标回放全部已持久化事件(self, db_session, fake_redis):
        task_id = await _seed_events(db_session)

        async def loader(after):
            return await list_events_after(db_session, task_id, last_sequence=after)

        stream = sse_event_stream(
            task_id,
            initial_snapshot={"status": "running"},
            last_event_id=None,
            replay_loader=loader,
        )
        chunks = await _collect(stream, 4)  # snapshot + seq1 + seq2 + seq3
        text = "\n".join(chunks)
        assert f"event: {EVENT_TASK_STATUS_SNAPSHOT}" in text
        assert "id: 1" in text
        assert "id: 2" in text
        assert "id: 3" in text

    async def test_游标已到末尾只发快照后进入live(self, db_session, fake_redis):
        task_id = await _seed_events(db_session)

        async def loader(after):
            return await list_events_after(db_session, task_id, last_sequence=after)

        stream = sse_event_stream(
            task_id,
            initial_snapshot={"status": "running"},
            last_event_id=3,
            replay_loader=loader,
        )
        chunks = await _collect(stream, 1)
        assert f"event: {EVENT_TASK_STATUS_SNAPSHOT}" in "\n".join(chunks)

    async def test_live消息事件id为持久sequence(self, db_session, fake_redis):
        task_id = await _seed_events(db_session)

        async def loader(after):
            return await list_events_after(db_session, task_id, last_sequence=after)

        fake_redis._pubsub._messages.append(
            json.dumps(
                {"event": "step.started", "data": {"step_id": "s1"}, "seq": 4},
                ensure_ascii=False,
            )
        )
        stream = sse_event_stream(
            task_id,
            initial_snapshot={"status": "running"},
            last_event_id=3,
            replay_loader=loader,
        )
        # 收集 snapshot 之后的一条 live 消息
        chunks = await _collect(stream, 2)
        text = "\n".join(chunks)
        assert "event: step.started" in text
        assert "id: 4" in text
