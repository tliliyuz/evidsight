"""启动时 / Worker 就绪时过时任务恢复测试 — recover_stale_tasks。

覆盖场景：
- 无 running 任务
- 有过时任务且锁不存在（重新投递）
- 有过时任务但锁仍存在（跳过）
- 阈值内任务不过时
- 非 running 状态不投递
- 启动恢复被禁用
- 查询异常不阻塞
- 投递异常不阻塞后续任务
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from app.main import _recover_stale_tasks
from app.models.research_task import ResearchTask
from app.tasks.recovery import recover_stale_tasks


class _SessionContextManager:
    """把已存在的 db_session 包装成 async_session_factory 的上下文管理器。

    Recovery 内部会调用 session.commit()；为避免提交外层测试事务造成跨测试数据泄漏，
    进入上下文时把 commit 重定向为 flush（恢复逻辑写入仍生效，随测试结束统一回滚）。
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


async def _seed_user(db_session):
    """返回 Knowledge 用户 UUID，不在 Research 持久化。"""
    return SimpleNamespace(id="00000000-0000-4000-8000-000000000001")


class TestRecoverStaleTasks:
    """recover_stale_tasks 核心逻辑测试。"""

    @pytest.mark.asyncio
    async def test_无running任务_不投递(self, db_session):
        await _seed_user(db_session)

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                recovered = await recover_stale_tasks(check_lock=False)

        assert recovered == []
        mock_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_有过时running任务且锁不存在_重新投递(self, db_session):
        user = await _seed_user(db_session)
        task = ResearchTask(
            user_id=user.id,
            topic="过时任务",
            requirements={"task_type": "analysis"},
            status="running",
            started_at=datetime.now(timezone.utc) - timedelta(seconds=300),
        )
        db_session.add(task)
        await db_session.flush()

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.recovery.check_task_lock_async", return_value=False):
                with patch("app.tasks.research_task.execute_research_task") as mock_task:
                    recovered = await recover_stale_tasks(check_lock=True)

        assert recovered == [str(task.id)]
        mock_task.delay.assert_called_once_with(str(task.id))

    @pytest.mark.asyncio
    async def test_有过时running任务但锁存在_跳过(self, db_session):
        user = await _seed_user(db_session)
        task = ResearchTask(
            user_id=user.id,
            topic="锁仍存在",
            requirements={"task_type": "analysis"},
            status="running",
            started_at=datetime.now(timezone.utc) - timedelta(seconds=300),
        )
        db_session.add(task)
        await db_session.flush()

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.recovery.check_task_lock_async", return_value=True):
                with patch("app.tasks.research_task.execute_research_task") as mock_task:
                    recovered = await recover_stale_tasks(check_lock=True)

        assert recovered == []
        mock_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_lock为False时不检查锁_直接投递(self, db_session):
        user = await _seed_user(db_session)
        task = ResearchTask(
            user_id=user.id,
            topic="不检查锁",
            requirements={"task_type": "analysis"},
            status="running",
            started_at=datetime.now(timezone.utc) - timedelta(seconds=300),
        )
        db_session.add(task)
        await db_session.flush()

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.recovery.check_task_lock_async") as mock_check:
                with patch("app.tasks.research_task.execute_research_task") as mock_task:
                    recovered = await recover_stale_tasks(check_lock=False)

        assert recovered == [str(task.id)]
        mock_check.assert_not_called()
        mock_task.delay.assert_called_once_with(str(task.id))

    @pytest.mark.asyncio
    async def test_阈值内running任务_不过时不投递(self, db_session):
        user = await _seed_user(db_session)
        task = ResearchTask(
            user_id=user.id,
            topic="阈值内任务",
            requirements={"task_type": "analysis"},
            status="running",
            started_at=datetime.now(timezone.utc) - timedelta(seconds=10),
            # 租约未过期（§13.5：按 (status, lease_expires_at) 扫描，非 started_at）
            lease_owner="worker-1",
            lease_expires_at=datetime.now(timezone.utc) + timedelta(seconds=300),
            lease_generation=1,
        )
        db_session.add(task)
        await db_session.flush()

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                recovered = await recover_stale_tasks(check_lock=False)

        assert recovered == []
        mock_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_非running状态_不投递(self, db_session):
        user = await _seed_user(db_session)
        task = ResearchTask(
            user_id=user.id,
            topic="已完成任务",
            requirements={"task_type": "analysis"},
            status="completed",
            started_at=datetime.now(timezone.utc) - timedelta(seconds=300),
            lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=30),
        )
        db_session.add(task)
        await db_session.flush()

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                recovered = await recover_stale_tasks(check_lock=False)

        assert recovered == []
        mock_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_启动恢复被禁用_不查询不投递(self, db_session):
        user = await _seed_user(db_session)
        task = ResearchTask(
            user_id=user.id,
            topic="禁用恢复",
            requirements={"task_type": "analysis"},
            status="running",
            started_at=datetime.now(timezone.utc) - timedelta(seconds=300),
        )
        db_session.add(task)
        await db_session.flush()

        with patch("app.tasks.recovery.settings.STARTUP_RECOVERY_ENABLED", False):
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                recovered = await recover_stale_tasks(check_lock=False)

        assert recovered == []
        mock_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_查询异常_不阻塞不抛异常(self, db_session):
        with patch(
            "app.tasks.recovery.async_session_factory",
            side_effect=RuntimeError("DB 连接失败"),
        ):
            recovered = await recover_stale_tasks(check_lock=False)

        assert recovered == []

    @pytest.mark.asyncio
    async def test_投递异常_不阻塞后续任务(self, db_session):
        user = await _seed_user(db_session)
        task1 = ResearchTask(
            user_id=user.id,
            topic="任务1",
            requirements={"task_type": "analysis"},
            status="running",
            started_at=datetime.now(timezone.utc) - timedelta(seconds=300),
        )
        task2 = ResearchTask(
            user_id=user.id,
            topic="任务2",
            requirements={"task_type": "analysis"},
            status="running",
            started_at=datetime.now(timezone.utc) - timedelta(seconds=300),
        )
        db_session.add(task1)
        db_session.add(task2)
        await db_session.flush()

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                mock_task.delay.side_effect = [RuntimeError("投递失败"), None]
                recovered = await recover_stale_tasks(check_lock=False)

        assert mock_task.delay.call_count == 2
        assert recovered == [str(task2.id)]


class TestMainStartupRecovery:
    """app.main._recover_stale_tasks 包装器测试。"""

    @pytest.mark.asyncio
    async def test_main包装器调用recover_stale_tasks(self):
        with patch("app.main.recover_stale_tasks", return_value=["task-1"]) as mock_recover:
            await _recover_stale_tasks()

        mock_recover.assert_awaited_once_with(check_lock=False)
