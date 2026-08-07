"""切片 D —— 取消请求化验收测试。

对齐 RESEARCH_PIPELINE §13.2 / DATABASE.md §8 / ADR-008：
- 取消接口只持久化 cancel_requested_at，不直接改写 status；
- Worker 在安全检查点看到取消后停止；
- TaskStateResolver 在安全停止后推导 canceled / partially_completed 终态；
- 重复取消幂等返回当前终态。
"""

from datetime import datetime, timezone

import pytest
from app.models.research_task import ResearchTask
from app.services.research_service import TaskStatusConflictException, cancel_task
from sqlalchemy.ext.asyncio import AsyncSession


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _seed_task(db_session: AsyncSession, task_id: str, status: str, **kw) -> ResearchTask:
    task = ResearchTask(
        id=task_id,
        user_id="00000000-0000-4000-8000-000000000001",
        topic="取消请求化测试",
        requirements={"task_type": "analysis", "max_sources": 10},
        status=status,
        **kw,
    )
    db_session.add(task)
    await db_session.flush()
    return task


class TestCancelTaskRequest:
    async def test_running任务_只写cancel_requested_at不改status(self, db_session: AsyncSession):
        task = await _seed_task(db_session, "task-cancel-running", "running")

        resp = await cancel_task(db_session, task)

        assert resp.task_id == task.id
        assert task.cancel_requested_at is not None
        assert task.status == "running"  # 不直接改写终态
        assert task.completed_at is None

    async def test_pending任务_只写cancel_requested_at(self, db_session: AsyncSession):
        task = await _seed_task(db_session, "task-cancel-pending", "pending")

        resp = await cancel_task(db_session, task)

        assert resp.task_id == task.id
        assert task.cancel_requested_at is not None
        assert task.status == "pending"

    async def test_重复取消_幂等(self, db_session: AsyncSession):
        task = await _seed_task(db_session, "task-cancel-idem", "running")
        first = await cancel_task(db_session, task)
        first_requested_at = task.cancel_requested_at

        second = await cancel_task(db_session, task)

        assert first.task_id == second.task_id
        assert task.cancel_requested_at == first_requested_at  # 不重复覆盖

    async def test_终态任务_抛E2003(self, db_session: AsyncSession):
        for status in ["completed", "failed", "partially_completed", "canceled"]:
            task = await _seed_task(db_session, f"task-cancel-{status}", status)
            with pytest.raises(TaskStatusConflictException):
                await cancel_task(db_session, task)


class TestCanceledTerminalResolver:
    """取消安全停止后的终态推导（§13.2：Resolver 决定终态）。"""

    async def test_全部完成_返回completed(self, db_session: AsyncSession):
        from app.core.task_state_resolver import TaskStateResolver
        from app.models.research_step import ResearchStep

        task = await _seed_task(db_session, "task-res-completed", "running")
        task.cancel_requested_at = _now()
        await db_session.flush()
        steps = [
            ResearchStep(task_id=task.id, step_type=t, status="completed")
            for t in [
                "planning",
                "search",
                "fetch",
                "rerank",
                "synthesis",
                "evidence_graph",
                "render",
            ]
        ]
        db_session.add_all(steps)
        await db_session.flush()

        status, _ = TaskStateResolver().resolve(task, steps, evidence_count=10)

        assert status == "completed"

    async def test_取消后未完成_证据足够_返回partially_completed(self, db_session: AsyncSession):
        from app.core.task_state_resolver import TaskStateResolver
        from app.models.research_step import ResearchStep

        task = await _seed_task(db_session, "task-res-partial", "running")
        task.cancel_requested_at = _now()
        task.requirements = {"task_type": "analysis", "max_sources": 10}
        await db_session.flush()
        steps = [
            ResearchStep(task_id=task.id, step_type="planning", status="completed"),
            ResearchStep(task_id=task.id, step_type="search", status="completed"),
            ResearchStep(task_id=task.id, step_type="fetch", status="completed"),
            ResearchStep(task_id=task.id, step_type="rerank", status="completed"),
            ResearchStep(task_id=task.id, step_type="synthesis", status="completed"),
            ResearchStep(task_id=task.id, step_type="evidence_graph", status="completed"),
            ResearchStep(task_id=task.id, step_type="render", status="failed"),
        ]
        db_session.add_all(steps)
        await db_session.flush()

        status, _ = TaskStateResolver().resolve(task, steps, evidence_count=10)

        assert status == "partially_completed"

    async def test_取消后证据不足_返回canceled(self, db_session: AsyncSession):
        from app.core.task_state_resolver import TaskStateResolver
        from app.models.research_step import ResearchStep

        task = await _seed_task(db_session, "task-res-canceled", "running")
        task.cancel_requested_at = _now()
        task.requirements = {"task_type": "analysis", "max_sources": 10}
        await db_session.flush()
        steps = [
            ResearchStep(task_id=task.id, step_type="planning", status="completed"),
            ResearchStep(task_id=task.id, step_type="search", status="failed"),
        ]
        db_session.add_all(steps)
        await db_session.flush()

        status, _ = TaskStateResolver().resolve(task, steps, evidence_count=0)

        assert status == "canceled"
