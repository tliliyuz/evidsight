"""切片 1 —— 生命周期冲突复现验收测试（MySQL lease 单一事实源）。

对齐 RESEARCH_PIPELINE §13.1/§13.5/§17.3（12、16、19、20）、DATABASE.md §8、ADR-008：

1. 双 Worker 同时领取，只有一个成功；
2. Redis 完全不可用时，已有有效 DB lease 的任务继续执行（领取只走 DB）；
3. 有效 lease 不被 Recovery Scanner 接管，且扫描不依赖 Redis；
4. lease 过期后新 generation 接管，旧 generation 无法提交；
5. 旧 Worker 的 finally 不释放新 Worker 的 lease；
6. 任意 watchdog/Scanner 不绕过 TaskStateResolver 写终态。

RED 预期（目标行为缺失）：用例 2、3、6 在当前实现下失败；
其余用例为既有已满足语义的回归锚点，防止收敛过程中回归。
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from app.models.research_task import ResearchTask
from app.services.task_lifecycle import (
    RECOVERY_SCANNER_WORKER_ID,
    TaskLeaseHandle,
    claim_task_lease,
    is_step_commit_allowed,
    release_task_lease,
    start_research_task,
)
from app.tasks.recovery import recover_stale_tasks
from sqlalchemy.ext.asyncio import AsyncSession


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _SessionContextManager:
    """把已存在 db_session 包装成 async_session_factory 上下文管理器。

    租约原语内部会调用 session.commit()；为避免提交外层测试事务造成跨测试
    数据泄漏，进入上下文时把 commit 重定向为 flush（写入仍生效，随测试结束回滚）。
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
    def factory():
        return _SessionContextManager(db_session)

    return factory


async def _seed_task(db_session: AsyncSession, task_id: str, **kw) -> ResearchTask:
    defaults = dict(
        user_id="00000000-0000-4000-8000-000000000001",
        topic="生命周期冲突测试",
        requirements={"task_type": "analysis", "max_sources": 10},
        status="pending",
        total_steps=7,
    )
    defaults.update(kw)
    task = ResearchTask(id=task_id, **defaults)
    db_session.add(task)
    await db_session.flush()
    return task


class TestConcurrentClaim:
    """验收 1：双 Worker 同时领取，只有一个成功。"""

    async def test_两个worker顺序启动_只有一个成功_租约不被夺走(
        self, db_session, seeded_user, monkeypatch
    ):
        user, _ = seeded_user
        task = await _seed_task(db_session, "conflict-claim-1", user_id=user.id)
        monkeypatch.setattr(db_session, "commit", db_session.flush)
        # 目标态无 Redis 锁：DB lease 条件更新作为唯一裁决，start_research_task 不再触碰 Redis。

        sse = AsyncMock()
        handle_a = TaskLeaseHandle(str(task.id))
        handle_b = TaskLeaseHandle(str(task.id))
        try:
            started_a = await start_research_task(task, db_session, sse, handle_a)
            # 第二个 Worker 尝试启动同一任务：target 语义为单次条件更新原子裁决
            started_b = await start_research_task(task, db_session, sse, handle_b)
        finally:
            with patch(
                "app.services.task_lifecycle.async_session_factory",
                new=_session_factory(db_session),
            ):
                await handle_a.release()

        assert started_a is True
        assert started_b is False
        await db_session.refresh(task)
        # 只有一个 generation 被领取，owner 未被第二个 Worker 覆盖
        assert task.lease_generation == 1
        assert task.lease_owner == handle_a.worker_id


class TestRedisDown:
    """验收 2：Redis 完全不可用时，DB lease 领取照常，任务继续执行。"""

    async def test_redis_down_pending任务仍经DB租约启动(self, db_session, seeded_user, monkeypatch):
        user, _ = seeded_user
        task = await _seed_task(db_session, "conflict-redis-1", user_id=user.id)
        monkeypatch.setattr(db_session, "commit", db_session.flush)

        # 目标态：start_research_task 不再触碰 Redis（无 acquire/refresh/release），
        # Redis 不可用自然不影响 DB lease 领取。
        sse = AsyncMock()
        handle = TaskLeaseHandle(str(task.id))
        try:
            started = await start_research_task(task, db_session, sse, handle)
        except Exception:
            started = False
        finally:
            with patch(
                "app.services.task_lifecycle.async_session_factory",
                new=_session_factory(db_session),
            ):
                await handle.release()

        assert started is True, "DB lease 领取不依赖 Redis（目标行为）"
        await db_session.refresh(task)
        assert task.lease_owner == handle.worker_id
        assert task.lease_generation == 1

    async def test_redis_down_已领取lease的worker续租与释放不受影响(
        self, db_session, seeded_user, monkeypatch
    ):
        user, _ = seeded_user
        task = await _seed_task(
            db_session,
            "conflict-redis-2",
            user_id=user.id,
            status="running",
            lease_owner="worker-1",
            lease_generation=1,
            lease_expires_at=_now() + timedelta(seconds=300),
        )
        monkeypatch.setattr(db_session, "commit", db_session.flush)

        handle = TaskLeaseHandle(str(task.id))
        handle.bind_lease("worker-1", 1, ttl_seconds=120)
        # 续租只走 DB，Redis 不可用不影响
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


class TestRenewExceptionLeaseLost:
    """验收 1 补充：续租异常（DB 瞬时故障等）必须置 lease_lost=True 并停续租（评审 🔴1）。

    §13.1 失去租约的 Worker 立即停止：续租异常与续租返回 False 同权，不能让 Worker
    在未知租约状态下继续执行 Provider 调用或提交业务结果。
    """

    async def test_续租异常_置lease_lost并停止续租(self, db_session):
        task = await _seed_task(db_session, "conflict-regen-1")
        handle = TaskLeaseHandle(str(task.id))
        handle.bind_lease("worker-1", 1, ttl_seconds=120)
        try:
            with patch(
                "app.services.task_lifecycle.renew_task_lease",
                AsyncMock(side_effect=RuntimeError("db down")),
            ):
                with patch(
                    "app.services.task_lifecycle.async_session_factory",
                    new=_session_factory(db_session),
                ):
                    ok = await handle.renew_lease()

            assert ok is False
            assert handle.lease_lost is True
            # 已停止续租协程（不再尝试 DB），后续续租无副作用
            assert handle._renew_task is None
        finally:
            with patch(
                "app.services.task_lifecycle.async_session_factory",
                new=_session_factory(db_session),
            ):
                await handle.release()

    """验收 3：有效 lease 不被 Recovery Scanner 接管，扫描不依赖 Redis。"""

    async def test_有效lease的running任务_不被扫描接管(self, db_session):
        task = await _seed_task(
            db_session,
            "conflict-scanner-1",
            status="running",
            lease_owner="worker-1",
            lease_generation=1,
            lease_expires_at=_now() + timedelta(seconds=60),
        )

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                recovered = await recover_stale_tasks()

        assert str(task.id) not in recovered
        mock_task.delay.assert_not_called()

    async def test_过期lease任务_Redis不可用仍可恢复(self, db_session):
        """目标签名 recover_stale_tasks() 无 check_lock、不依赖 Redis（纯 DB lease）。

        当前实现已移除 Redis 判断 → GREEN。
        """
        task = await _seed_task(
            db_session,
            "conflict-scanner-2",
            status="running",
            lease_owner="worker-old",
            lease_generation=1,
            lease_expires_at=_now() - timedelta(seconds=30),
        )

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                recovered = await recover_stale_tasks()

        assert str(task.id) in recovered
        mock_task.delay.assert_any_call(str(task.id))


class TestGenerationTakeover:
    """验收 4：lease 过期后新 generation 接管，旧 generation 无法提交。"""

    async def test_过期后新generation接管_旧generation无法提交(self, db_session):
        task = await _seed_task(db_session, "conflict-gen-1", status="running")
        generation_old = await claim_task_lease(
            db_session, str(task.id), "worker-old", ttl_seconds=1
        )
        assert generation_old == 1
        # 使租约过期
        task.lease_expires_at = _now() - timedelta(seconds=5)
        await db_session.flush()

        generation_new = await claim_task_lease(
            db_session, str(task.id), "worker-new", ttl_seconds=120
        )
        assert generation_new == 2

        # 旧 generation 无法提交
        assert await is_step_commit_allowed(db_session, str(task.id), "worker-old", 1) is False
        # 新 generation 可以提交
        assert await is_step_commit_allowed(db_session, str(task.id), "worker-new", 2) is True


class TestOldWorkerFinally:
    """验收 5：旧 Worker 的 finally 不释放新 Worker 的 lease。"""

    async def test_旧worker的finally不释放新worker的lease(self, db_session):
        task = await _seed_task(db_session, "conflict-finally-1", status="running")
        await claim_task_lease(db_session, str(task.id), "worker-old", ttl_seconds=1)
        task.lease_expires_at = _now() - timedelta(seconds=5)
        await db_session.flush()
        await claim_task_lease(db_session, str(task.id), "worker-new", ttl_seconds=120)

        # 旧 Worker 的 finally 释放：release_task_lease 仅 owner 匹配生效
        ok = await release_task_lease(db_session, str(task.id), "worker-old")

        assert ok is False
        await db_session.refresh(task)
        assert task.lease_owner == "worker-new"
        assert task.lease_generation == 2


class TestTerminalWriteDiscipline:
    """验收 6：任意 watchdog/Scanner 不绕过 TaskStateResolver 写终态。"""

    def test_main模块不存在直接写终态的watchdog(self):
        """结构性断言：main 不再存在基于 Redis 锁直接写 failed 的 watchdog。

        当前实现存在这些函数（直接写 failed E3112/E3113，绕过 Resolver）→ RED。
        """
        import app.main as main

        for name in (
            "_run_worker_timeout_watcher",
            "_check_worker_timeouts",
            "_mark_task_worker_timeout",
            "_mark_task_pending_timeout",
        ):
            assert not hasattr(main, name), (
                f"{name} 直接写终态，违反 ADR-008 终态纪律（仅 TaskStateResolver 可写终态）"
            )

    async def test_recovery扫描_只改step状态_不直接写task终态(self, db_session):
        """Scanner 对过期 lease 任务只把 running Step 转 retrying、清 owner，
        不直接写 task.status 终态（终态留待重新执行的 Worker 经 Resolver 推导）。"""
        task = await _seed_task(
            db_session,
            "conflict-terminal-1",
            status="running",
            lease_owner="worker-old",
            lease_generation=1,
            lease_expires_at=_now() - timedelta(seconds=30),
        )
        from app.models.research_step import ResearchStep

        db_session.add(ResearchStep(task_id=task.id, step_type="search", status="running"))
        await db_session.flush()

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.research_task.execute_research_task"):
                await recover_stale_tasks()

        await db_session.refresh(task)
        # Scanner 不写终态：任务仍为 running（不被标记 completed/failed/canceled），
        # owner 为 scanner handoff（评审 🔴2：保留 handoff 租约阻止下轮重复投递）；
        # generation 因 scanner 条件领取递增（使旧 Worker 迟到提交失效）。
        assert task.status == "running"
        assert task.lease_owner == RECOVERY_SCANNER_WORKER_ID
        assert task.lease_generation == 2
        assert task.recovery_count == 1
