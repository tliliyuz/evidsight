"""切片 D/3 —— Recovery Scanner 按租约扫描（纯 DB）验收测试。

对齐 RESEARCH_PIPELINE §13.5/§13.6 / DATABASE.md §8：
- Scanner 按 (status, lease_expires_at) 查找过期运行任务，不依赖 Redis；
- 锁定后再次确认租约过期；
- 将遗留 running Step 置为 retrying 或按重试上限 failed；
- 清除旧 owner、递增恢复计数并重新投递到 research.execute；
- 两个 Scanner 并发只恢复一次；
- pending 任务超过阈值且无有效租约 → 重投；超过上限 → 受控失败事实由 Resolver 推导。
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from app.config import settings
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
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                recovered = await recover_stale_tasks()

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
                recovered = await recover_stale_tasks()

        assert str(task.id) not in recovered
        mock_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_恢复后_保留scanner租约_递增恢复计数(self, db_session):
        """§13.5 评审 🔴2：恢复成功后保留 scanner handoff 租约（不立即清空），
        使下一轮扫描条件不命中 → 只恢复一次；恢复计数递增。"""
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
            with patch("app.tasks.research_task.execute_research_task"):
                await recover_stale_tasks()

        await db_session.refresh(task)
        assert task.lease_owner == "recovery-scanner"
        assert task.lease_expires_at is not None  # handoff 租约仍在未来
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
            with patch("app.tasks.research_task.execute_research_task"):
                await recover_stale_tasks()

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
                recovered = await recover_stale_tasks()

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
            with patch("app.tasks.research_task.execute_research_task"):
                recovered = await recover_stale_tasks()

        assert str(task.id) in recovered

    @pytest.mark.asyncio
    async def test_scanner条件领取_并发第二scanner不重复claim(self, db_session):
        """两个 Scanner 并发只恢复一次：条件领取把 lease_expires_at 推到未来，
        并发 Scanner 的 WHERE（租约已过期）不命中，不会重复 claim。"""
        from app.tasks.recovery import _claim_expired_lease

        task = await _seed_running_task(
            db_session,
            "task-concurrent-1",
            lease_expires_at=_now() - timedelta(seconds=30),
            recovery_count=0,
        )

        claimed_a = await _claim_expired_lease(db_session, str(task.id), "scanner-a")
        assert claimed_a is True
        await db_session.flush()

        # 第二个 Scanner 在同一窗口内 claim → 租约已在未来，不命中
        claimed_b = await _claim_expired_lease(db_session, str(task.id), "scanner-b")
        assert claimed_b is False

        await db_session.refresh(task)
        assert task.lease_owner == "scanner-a"

    @pytest.mark.asyncio
    async def test_两轮扫描_只恢复一次(self, db_session):
        """§13.5/评审 🔴2：Beat 重复扫描只投递一次。

        恢复成功后保留 scanner handoff 租约，第二轮扫描条件（租约为空/已过期）
        不命中 → 不再重复投递，也不重复完成 Step/Evidence/Revision。
        """
        task = await _seed_running_task(
            db_session,
            "task-twice-1",
            lease_expires_at=_now() - timedelta(seconds=30),
            recovery_count=0,
        )
        step = ResearchStep(task_id=task.id, step_type="planning", status="completed")
        db_session.add(step)
        await db_session.flush()

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                await recover_stale_tasks()
                await recover_stale_tasks()

        # 两轮只投递一次（handoff 租约阻断重复扫描）
        assert mock_task.delay.call_count == 1
        await db_session.refresh(task)
        assert task.recovery_count == 1
        assert task.lease_owner == "recovery-scanner"
        await db_session.refresh(step)
        assert step.status == "completed"  # 已 completed 的 Step 不被 Scanner 改动

    @pytest.mark.asyncio
    async def test_投递失败_清除scanner租约_下轮可再发现(self, db_session):
        """§13.5：投递失败（broker 不可用）时清除 scanner handoff 租约，
        任务保持可再次被扫描发现，不留 scanner owner 永久占用。"""
        task = await _seed_running_task(
            db_session,
            "task-dispatch-fail-1",
            lease_expires_at=_now() - timedelta(seconds=30),
            recovery_count=0,
        )

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                mock_task.delay.side_effect = RuntimeError("broker down")
                recovered = await recover_stale_tasks()

        assert str(task.id) not in recovered
        await db_session.refresh(task)
        assert task.lease_owner is None
        assert task.lease_expires_at is None


class TestPendingRedelivery:
    @pytest.mark.asyncio
    async def test_pending超过阈值_无有效租约_重投并递增计数(self, db_session):
        user = await _seed_user(db_session)
        task = ResearchTask(
            id="task-pending-1",
            user_id=user.id,
            topic="pending 重投",
            requirements={"task_type": "analysis"},
            status="pending",
            started_at=_now()
            - timedelta(seconds=settings.PENDING_REDELIVERY_THRESHOLD_SECONDS + 10),
            redelivery_count=0,
        )
        db_session.add(task)
        await db_session.flush()

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                recovered = await recover_stale_tasks()

        assert str(task.id) in recovered
        mock_task.delay.assert_any_call(str(task.id))
        await db_session.refresh(task)
        assert task.redelivery_count == 1
        assert task.status == "pending"  # 重投不改变状态，由 Worker 领取后转 running

    @pytest.mark.asyncio
    async def test_pending未超阈值_不重投(self, db_session):
        user = await _seed_user(db_session)
        task = ResearchTask(
            id="task-pending-fresh",
            user_id=user.id,
            topic="fresh",
            requirements={"task_type": "analysis"},
            status="pending",
            started_at=_now(),
            redelivery_count=0,
        )
        db_session.add(task)
        await db_session.flush()

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                recovered = await recover_stale_tasks()

        assert str(task.id) not in recovered
        mock_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_pending超上限_创建受控失败事实_Resolver推导failed(self, db_session):
        user = await _seed_user(db_session)
        task = ResearchTask(
            id="task-pending-exhausted",
            user_id=user.id,
            topic="exhausted",
            requirements={"task_type": "analysis"},
            status="pending",
            started_at=_now()
            - timedelta(seconds=settings.PENDING_REDELIVERY_THRESHOLD_SECONDS + 10),
            redelivery_count=settings.PENDING_REDELIVERY_MAX_RETRIES,
        )
        db_session.add(task)
        await db_session.flush()

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                recovered = await recover_stale_tasks()

        assert str(task.id) not in recovered  # 不再投递
        mock_task.delay.assert_not_called()
        await db_session.refresh(task)
        assert task.status == "failed"  # 由 Resolver 依据 E3118 failed Step 推导
        assert task.error_code == "E3118"

        # 受控失败事实已落库
        from sqlalchemy import select as sa_select

        step = (
            await db_session.execute(
                sa_select(ResearchStep).where(
                    ResearchStep.task_id == task.id,
                    ResearchStep.error_code == "E3118",
                )
            )
        ).scalar_one_or_none()
        assert step is not None
        assert step.status == "failed"
        assert step.step_type == "planning"

    @pytest.mark.asyncio
    async def test_pending已有有效租约_跳过(self, db_session):
        user = await _seed_user(db_session)
        task = ResearchTask(
            id="task-pending-leased",
            user_id=user.id,
            topic="leased",
            requirements={"task_type": "analysis"},
            status="pending",
            started_at=_now()
            - timedelta(seconds=settings.PENDING_REDELIVERY_THRESHOLD_SECONDS + 10),
            lease_owner="worker-1",
            lease_expires_at=_now() + timedelta(seconds=60),
            redelivery_count=0,
        )
        db_session.add(task)
        await db_session.flush()

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                recovered = await recover_stale_tasks()

        assert str(task.id) not in recovered
        mock_task.delay.assert_not_called()
        await db_session.refresh(task)
        assert task.redelivery_count == 0
