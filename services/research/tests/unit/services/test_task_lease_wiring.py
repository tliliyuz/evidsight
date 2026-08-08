"""切片 E —— 租约接入（start_research_task 合并领取 + TaskLeaseHandle 绑定/释放）验收测试。

对齐 RESEARCH_PIPELINE §13.1 / DATABASE.md §8 / §17.12：
- Worker 启动（pending 正常路径与 running 恢复路径）经单条条件更新领取租约并绑定；
- 领取失败（并发 Worker / 扫描器已持有有效租约）时放弃启动，不执行业务步骤；
- 租约句柄释放时清除 DB 租约；续租只走 DB，不依赖 Redis。
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from app.models.research_task import ResearchTask
from app.services.task_lifecycle import TaskLeaseHandle, start_research_task
from sqlalchemy.ext.asyncio import AsyncSession


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


async def _seed_task(db_session: AsyncSession, task_id: str, **kw) -> ResearchTask:
    defaults = dict(
        user_id="00000000-0000-4000-8000-000000000001",
        topic="租约接入测试",
        requirements={"task_type": "analysis"},
        status="pending",
        total_steps=7,
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
        monkeypatch,
    ):
        user, _ = seeded_user
        task = await _seed_task(
            db_session, "lease-wire-1", user_id=user.id, status="pending", total_steps=0
        )
        # 单元测试中避免真实 commit 破坏事务隔离：将 commit 重定向为 flush
        monkeypatch.setattr(db_session, "commit", db_session.flush)

        sse = AsyncMock()
        handle = TaskLeaseHandle("lease-wire-1")
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
        handle = TaskLeaseHandle("lease-wire-2")
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

    async def test_有效租约已被持有_放弃启动(
        self,
        db_session,
        seeded_user,
        monkeypatch,
    ):
        user, _ = seeded_user
        task = await _seed_task(
            db_session,
            "lease-wire-3",
            user_id=user.id,
            status="running",
            lease_owner="worker-a",
            lease_expires_at=_now() + timedelta(seconds=300),
            lease_generation=1,
        )
        monkeypatch.setattr(db_session, "commit", db_session.flush)
        # 并发 Worker 已持有有效租约 → 合并条件更新不命中，立即放弃启动

        sse = AsyncMock()
        handle = TaskLeaseHandle("lease-wire-3")
        started = await start_research_task(task, db_session, sse, handle)

        assert started is False
        assert handle.lease_bound is False
        await db_session.refresh(task)
        assert task.lease_owner == "worker-a"
        assert task.lease_generation == 1


class TestHandleLeaseRelease:
    async def test_release_清除DB租约(self, db_session, seeded_user):
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

        handle = TaskLeaseHandle("lease-wire-4")
        handle.bind_lease("worker-1", 1)
        with patch(
            "app.services.task_lifecycle.async_session_factory", new=_session_factory(db_session)
        ):
            await handle.release()

        await db_session.refresh(task)
        assert task.lease_owner is None
        assert task.lease_expires_at is None
        assert handle.lease_bound is False

    async def test_renew_续租DB租约(self, db_session, seeded_user):
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

        handle = TaskLeaseHandle("lease-wire-5")
        handle.bind_lease("worker-1", 1, ttl_seconds=120)
        with patch(
            "app.services.task_lifecycle.async_session_factory", new=_session_factory(db_session)
        ):
            ok = await handle.renew_lease()

        assert ok is True
        await db_session.refresh(task)
        assert task.lease_expires_at > _now() + timedelta(seconds=100)

        with patch(
            "app.services.task_lifecycle.async_session_factory", new=_session_factory(db_session)
        ):
            await handle.release()
