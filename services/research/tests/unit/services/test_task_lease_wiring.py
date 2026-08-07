"""切片 E —— 租约接入（start_research_task 领取 + TaskLockHandle 绑定/释放）验收测试。

对齐 RESEARCH_PIPELINE §13.1 / DATABASE.md §8 / §17.12：
- Worker 启动（pending 正常路径与 running 恢复路径）领取租约并绑定到锁句柄；
- 领取失败（并发 Worker / 扫描器已持有）时放弃启动并释放锁；
- 锁句柄释放时清除 DB 租约；刷新循环续租 DB 租约。
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_task import ResearchTask
from app.services.task_lifecycle import TaskLockHandle, start_research_task


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _SessionContextManager:
    """把已存在的 db_session 包装成 async_session_factory 的上下文管理器。

    租约原语内部会调用 session.commit()；为避免提交外层测试事务造成跨测试数据泄漏，
    进入上下文时把 commit 重定向为 flush（写入仍生效，随测试结束统一回滚）。
    """

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
    """返回一个复用测试 db_session 的 session_factory。"""

    def factory():
        return _SessionContextManager(db_session)

    return factory


@pytest.fixture
def fake_locks(monkeypatch):
    """Mock Redis 任务锁函数，避免测试依赖 Redis。"""
    lock_state = {"locked": False}

    async def acquire(task_id, ttl=None):
        if not lock_state["locked"]:
            lock_state["locked"] = True
            return True
        return False

    async def release(task_id):
        lock_state["locked"] = False

    async def refresh(task_id, ttl=None):
        return lock_state["locked"]

    monkeypatch.setattr("app.services.task_lifecycle.acquire_task_lock_async", acquire)
    monkeypatch.setattr("app.services.task_lifecycle.release_task_lock_async", release)
    monkeypatch.setattr("app.services.task_lifecycle.refresh_task_lock_async", refresh)
    return lock_state


async def _seed_task(db_session: AsyncSession, task_id: str, **kw) -> ResearchTask:
    defaults = dict(
        user_id="00000000-0000-4000-8000-000000000001",
        topic="租约接入测试",
        requirements={"task_type": "analysis"},
        status="pending",
    )
    defaults.update(kw)
    task = ResearchTask(id=task_id, **defaults)
    db_session.add(task)
    await db_session.flush()
    return task


class TestStartClaimsLease:
    async def test_pending任务启动_领取租约并绑定到handle(
        self,
        db_session,
        seeded_user,
        fake_locks,
        monkeypatch,
    ):
        user, _ = seeded_user
        task = await _seed_task(
            db_session, "lease-wire-1", user_id=user.id, status="pending", total_steps=0
        )
        # 单元测试中避免真实 commit 破坏事务隔离：将 commit 重定向为 flush
        monkeypatch.setattr(db_session, "commit", db_session.flush)

        sse = AsyncMock()
        handle = TaskLockHandle("lease-wire-1")
        try:
            started = await start_research_task(task, db_session, sse, handle)

            assert started is True
            assert handle.lease_bound is True
            assert handle.lease_generation == 1
            await db_session.refresh(task)
            assert task.lease_owner == handle.worker_id
            assert task.lease_expires_at is not None
        finally:
            # release 会释放 DB 租约：复用测试会话，避免连接真实 MySQL
            with patch(
                "app.services.task_lifecycle.async_session_factory",
                new=_session_factory(db_session),
            ):
                await handle.release()

    async def test_running恢复路径_领取新generation(
        self,
        db_session,
        seeded_user,
        fake_locks,
        monkeypatch,
    ):
        user, _ = seeded_user
        task = await _seed_task(
            db_session,
            "lease-wire-2",
            user_id=user.id,
            status="running",
            lease_owner="worker-old",
            lease_expires_at=_now() - timedelta(seconds=30),
            lease_generation=1,
        )
        monkeypatch.setattr(db_session, "commit", db_session.flush)

        sse = AsyncMock()
        handle = TaskLockHandle("lease-wire-2")
        try:
            started = await start_research_task(task, db_session, sse, handle)

            assert started is True
            assert handle.lease_generation == 2
            await db_session.refresh(task)
            assert task.lease_generation == 2
            assert task.lease_owner == handle.worker_id
            assert task.lease_owner != "worker-old"
        finally:
            with patch(
                "app.services.task_lifecycle.async_session_factory",
                new=_session_factory(db_session),
            ):
                await handle.release()

    async def test_租约领取失败_放弃启动并释放锁(
        self,
        db_session,
        seeded_user,
        fake_locks,
        monkeypatch,
    ):
        user, _ = seeded_user
        task = await _seed_task(db_session, "lease-wire-3", user_id=user.id, status="pending")
        monkeypatch.setattr(db_session, "commit", db_session.flush)
        # 模拟并发 Worker / 扫描器已持有有效租约 → 领取失败
        monkeypatch.setattr(
            "app.services.task_lifecycle.claim_task_lease",
            AsyncMock(return_value=None),
        )

        sse = AsyncMock()
        handle = TaskLockHandle("lease-wire-3")
        started = await start_research_task(task, db_session, sse, handle)

        assert started is False
        assert handle.lease_bound is False
        assert fake_locks["locked"] is False


class TestHandleLeaseRelease:
    async def test_release_清除DB租约(self, db_session, seeded_user, fake_locks):
        user, _ = seeded_user
        task = await _seed_task(
            db_session,
            "lease-wire-4",
            user_id=user.id,
            status="running",
            lease_owner="worker-1",
            lease_expires_at=_now() + timedelta(seconds=300),
            lease_generation=1,
        )

        handle = TaskLockHandle("lease-wire-4")
        handle.bind_lease("worker-1", 1)
        with patch(
            "app.services.task_lifecycle.async_session_factory", new=_session_factory(db_session)
        ):
            await handle.release()

        await db_session.refresh(task)
        assert task.lease_owner is None
        assert task.lease_expires_at is None
        assert handle.lease_bound is False

    async def test_renew_续租DB租约(self, db_session, seeded_user, fake_locks):
        user, _ = seeded_user
        task = await _seed_task(
            db_session,
            "lease-wire-5",
            user_id=user.id,
            status="running",
            lease_owner="worker-1",
            lease_expires_at=_now() - timedelta(seconds=10),
            lease_generation=1,
        )

        handle = TaskLockHandle("lease-wire-5")
        handle.bind_lease("worker-1", 1, ttl_seconds=120)
        with patch(
            "app.services.task_lifecycle.async_session_factory", new=_session_factory(db_session)
        ):
            ok = await handle.renew_lease()

        assert ok is True
        await db_session.refresh(task)
        assert task.lease_expires_at > _now() + timedelta(seconds=100)
