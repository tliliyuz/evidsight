"""切片 D —— Recovery Scanner 按租约扫描验收测试。

对齐 RESEARCH_PIPELINE §13.5 / DATABASE.md §8：
- Scanner 按 (status, lease_expires_at) 查找过期运行任务；
- 锁定后再次确认租约过期；
- 将遗留 running Step 置为 retrying 或按重试上限 failed；
- 清除旧 owner、递增恢复计数并重新投递到 research.execute。
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask
from app.tasks.recovery import recover_stale_tasks
from sqlalchemy.ext.asyncio import AsyncSession


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _SessionContextManager:
    def __init__(self, session):
        self._session = session
        self._original_commit = session.commit
        session.commit = session.flush

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        self._session.commit = self._original_commit
        return False


def _session_factory(db_session):
    def factory():
        return _SessionContextManager(db_session)

    return factory


async def _seed_user(db_session):
    return SimpleNamespace(id="00000000-0000-4000-8000-000000000001")


async def _seed_running_task(
    db_session: AsyncSession,
    task_id: str,
    lease_expires_at: datetime | None,
    recovery_count: int = 0,
    lease_owner: str | None = "worker-old",
    lease_generation: int = 1,
) -> ResearchTask:
    user = await _seed_user(db_session)
    task = ResearchTask(
        id=task_id,
        user_id=user.id,
        topic=f"恢复扫描 {task_id}",
        requirements={"task_type": "analysis", "max_sources": 10},
        status="running",
        lease_expires_at=lease_expires_at,
        lease_owner=lease_owner,
        lease_generation=lease_generation,
        recovery_count=recovery_count,
    )
    db_session.add(task)
    await db_session.flush()
    return task


class TestRecoverStaleTasksByLease:
    @pytest.mark.asyncio
    async def test_租约过期的running任务_重新投递(self, db_session):
        task = await _seed_running_task(
            db_session,
            "task-stale-1",
            lease_expires_at=_now() - timedelta(seconds=30),
        )

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.recovery.check_task_lock_async", return_value=False):
                with patch("app.tasks.research_task.execute_research_task") as mock_task:
                    recovered = await recover_stale_tasks(check_lock=True)

        assert str(task.id) in recovered
        mock_task.delay.assert_any_call(str(task.id))

    @pytest.mark.asyncio
    async def test_租约未过期的running任务_不投递(self, db_session):
        task = await _seed_running_task(
            db_session,
            "task-fresh-1",
            lease_expires_at=_now() + timedelta(seconds=60),
        )

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                recovered = await recover_stale_tasks(check_lock=False)

        assert str(task.id) not in recovered
        mock_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_租约过期_但锁存在_跳过(self, db_session):
        task = await _seed_running_task(
            db_session,
            "task-locked-1",
            lease_expires_at=_now() - timedelta(seconds=30),
        )

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.recovery.check_task_lock_async", return_value=True):
                with patch("app.tasks.research_task.execute_research_task") as mock_task:
                    recovered = await recover_stale_tasks(check_lock=True)

        assert str(task.id) not in recovered
        mock_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_恢复后_清除旧owner_递增恢复计数(self, db_session):
        task = await _seed_running_task(
            db_session,
            "task-owner-1",
            lease_expires_at=_now() - timedelta(seconds=30),
            recovery_count=2,
        )
        db_session.add(ResearchStep(task_id=task.id, step_type="planning", status="completed"))
        db_session.add(ResearchStep(task_id=task.id, step_type="search", status="running"))
        await db_session.flush()

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.recovery.check_task_lock_async", return_value=False):
                with patch("app.tasks.research_task.execute_research_task"):
                    await recover_stale_tasks(check_lock=True)

        await db_session.refresh(task)
        assert task.lease_owner is None
        assert task.recovery_count == 3

    @pytest.mark.asyncio
    async def test_恢复时_遗留runningStep置为retrying(self, db_session):
        task = await _seed_running_task(
            db_session,
            "task-steps-1",
            lease_expires_at=_now() - timedelta(seconds=30),
        )
        step = ResearchStep(task_id=task.id, step_type="search", status="running")
        db_session.add(step)
        await db_session.flush()

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.recovery.check_task_lock_async", return_value=False):
                with patch("app.tasks.research_task.execute_research_task"):
                    await recover_stale_tasks(check_lock=True)

        await db_session.refresh(step)
        assert step.status == "retrying"

    @pytest.mark.asyncio
    async def test_非running任务_不投递(self, db_session):
        user = await _seed_user(db_session)
        task = ResearchTask(
            id="task-completed-1",
            user_id=user.id,
            topic="已完成",
            requirements={"task_type": "analysis"},
            status="completed",
            lease_expires_at=_now() - timedelta(seconds=30),
        )
        db_session.add(task)
        await db_session.flush()

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                recovered = await recover_stale_tasks(check_lock=False)

        assert str(task.id) not in recovered
        mock_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_无租约的running任务_视为过期可恢复(self, db_session):
        task = await _seed_running_task(
            db_session,
            "task-nolease-1",
            lease_expires_at=None,
            lease_owner=None,
        )

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.recovery.check_task_lock_async", return_value=False):
                with patch("app.tasks.research_task.execute_research_task"):
                    recovered = await recover_stale_tasks(check_lock=True)

        assert str(task.id) in recovered
