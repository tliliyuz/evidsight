"""agent_event_service 单元测试 —— DATABASE.md §5.4 / §9、RESEARCH_PIPELINE §15。

验收：
- sequence 为 Task 内单调序号，(task_id, sequence) 唯一；
- event_type 白名单枚举，非法类型被拒绝；
- 事件只含安全业务摘要，禁止 thought/reasoning/完整 Prompt/正文/凭证等字段；
- list_events_after 作为 SSE 持久游标回放。
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_task import ResearchTask
from app.services.agent_event_service import (
    EVENT_TYPE_PHASE_ENTER,
    EVENT_TYPE_TOOL_REQUEST,
    EVENT_TYPE_TOOL_RESULT,
    append_event,
    list_events_after,
)


async def _make_task(db: AsyncSession) -> str:
    task = ResearchTask(id="evt-task-1", user_id="user-1", topic="t", requirements={"max_sources": 10})
    db.add(task)
    await db.flush()
    return str(task.id)


class TestAppendEvent:
    async def test_事件sequence单调递增(self, db_session):
        task_id = await _make_task(db_session)
        ev1 = await append_event(db_session, task_id, event_type=EVENT_TYPE_PHASE_ENTER)
        ev2 = await append_event(db_session, task_id, event_type=EVENT_TYPE_TOOL_REQUEST)
        ev3 = await append_event(db_session, task_id, event_type=EVENT_TYPE_TOOL_RESULT)
        assert [ev1.sequence, ev2.sequence, ev3.sequence] == [1, 2, 3]

    async def test_不同任务各自独立序号(self, db_session):
        task_id = await _make_task(db_session)
        db_session.add(ResearchTask(id="evt-task-2", user_id="user-1", topic="t2", requirements={"max_sources": 10}))
        await db_session.flush()
        ev1 = await append_event(db_session, task_id, event_type=EVENT_TYPE_PHASE_ENTER)
        ev2 = await append_event(db_session, "evt-task-2", event_type=EVENT_TYPE_PHASE_ENTER)
        assert ev1.sequence == 1
        assert ev2.sequence == 1

    async def test_非法event_type被拒绝(self, db_session):
        task_id = await _make_task(db_session)
        with pytest.raises(ValueError):
            await append_event(db_session, task_id, event_type="thought")

    async def test_事件摘要剥离禁止字段(self, db_session):
        task_id = await _make_task(db_session)
        ev = await append_event(
            db_session, task_id,
            event_type=EVENT_TYPE_TOOL_REQUEST,
            input_summary={
                "tool_name": "plan_tool",
                "thought": "秘密推理",
                "reasoning_content": "Chain of Thought",
                "prompt": "完整提示词",
                "count": 3,
            },
            result_summary={"reasoning": "隐藏推理"},
        )
        assert ev.input_summary == {"tool_name": "plan_tool", "count": 3}
        assert ev.result_summary == {}


class TestListEventsAfter:
    async def _seed(self, db_session) -> str:
        task_id = await _make_task(db_session)
        await append_event(db_session, task_id, event_type=EVENT_TYPE_PHASE_ENTER)
        await append_event(db_session, task_id, event_type=EVENT_TYPE_TOOL_REQUEST)
        await append_event(db_session, task_id, event_type=EVENT_TYPE_TOOL_RESULT)
        return task_id

    async def test_无游标返回全部按序(self, db_session):
        task_id = await self._seed(db_session)
        rows = await list_events_after(db_session, task_id, last_sequence=None)
        assert [r.sequence for r in rows] == [1, 2, 3]
        assert [r.event_type for r in rows] == [
            EVENT_TYPE_PHASE_ENTER, EVENT_TYPE_TOOL_REQUEST, EVENT_TYPE_TOOL_RESULT,
        ]

    async def test_游标后事件(self, db_session):
        task_id = await self._seed(db_session)
        rows = await list_events_after(db_session, task_id, last_sequence=1)
        assert [r.sequence for r in rows] == [2, 3]

    async def test_游标已到末尾返回空(self, db_session):
        task_id = await self._seed(db_session)
        rows = await list_events_after(db_session, task_id, last_sequence=3)
        assert rows == []

    async def test_不同任务互不干扰(self, db_session):
        task_id = await self._seed(db_session)
        db_session.add(ResearchTask(id="evt-task-9", user_id="user-1", topic="t9", requirements={"max_sources": 10}))
        await db_session.flush()
        other = await append_event(db_session, "evt-task-9", event_type=EVENT_TYPE_PHASE_ENTER)
        rows = await list_events_after(db_session, task_id, last_sequence=None)
        assert len(rows) == 3
        assert other.task_id == "evt-task-9"
