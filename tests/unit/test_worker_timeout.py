"""Worker 超时监察者单元测试。

覆盖 _check_worker_timeouts 与 _mark_task_worker_timeout 的核心路径：
- 锁存在 → 不标记失败
- 锁缺失超过阈值 → CAS 标记 failed（E3112，recoverable=True）
- 启动宽限期内锁缺失 → 不标记失败
- 非 running 状态 → 不扫描
- SSE 失败不阻断状态更新
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.database import async_session_factory
from app.models.research_task import ResearchTask
from app.pipeline.sse_bridge import EVENT_TASK_FAILED


@pytest.fixture(autouse=True)
def _reset_tracker():
    """每次测试前清空超时追踪器。"""
    from app import main as main_module

    main_module._worker_lock_missing_since.clear()
    yield
    main_module._worker_lock_missing_since.clear()


def _make_async_session_cm(session) -> AsyncMock:
    """构造可被 `async with` 使用的 session 上下文管理器 mock。"""
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _mock_session_factory(session) -> MagicMock:
    """将 async_session_factory 替换为返回指定 session 的 mock。"""
    factory = MagicMock()
    factory.return_value = _make_async_session_cm(session)
    return factory


def _running_task_row(task_id: str, started_seconds_ago: int = 60):
    """构造一个 running 任务查询结果行。"""
    started_at = datetime.now(timezone.utc) - timedelta(seconds=started_seconds_ago)
    return (task_id, started_at)


# ═══════════════════════════════════════════════════════════════
# _mark_task_worker_timeout
# ═══════════════════════════════════════════════════════════════


class TestMarkTaskWorkerTimeout:
    """Worker 超时后的失败标记与 SSE 推送。"""

    @pytest.mark.asyncio
    async def test_CAS更新失败状态_E3112_recoverable为True(self):
        """成功 CAS 时写入 failed / E3112 / recoverable=True。"""
        task_id = "task-001"
        session = AsyncMock()
        execute_result = MagicMock()
        execute_result.rowcount = 1
        session.execute.return_value = execute_result

        context_session = AsyncMock()
        context_result = MagicMock()
        context_result.scalar_one_or_none.return_value = {
            "last_completed_step_id": "step-abc"
        }
        context_session.execute.return_value = context_result

        def _session_factory():
            # 第一次用于 CAS 更新，第二次用于读取 execution_context
            calls = [session, context_session]
            idx = 0

            def _factory():
                nonlocal idx
                cm = _make_async_session_cm(calls[idx])
                idx += 1
                return cm

            return _factory

        sse_bridge = AsyncMock()

        with patch("app.main.async_session_factory", side_effect=_session_factory()), \
             patch("app.main.SSEBridge", return_value=sse_bridge):
            from app.main import _mark_task_worker_timeout

            await _mark_task_worker_timeout(task_id)

        # 验证 CAS 更新
        update_call = session.execute.await_args
        stmt = update_call[0][0]
        compiled = stmt.compile(compile_kwargs={"literal_binds": True})
        assert f"WHERE research_tasks.id = '{task_id}'" in str(compiled)
        assert "status = 'running'" in str(compiled)
        assert "status='failed'" in str(compiled)
        assert "E3112" in str(compiled)

        # 验证 SSE
        publish_calls = [c for c in sse_bridge.publish.await_args_list if c[0][0] == EVENT_TASK_FAILED]
        assert len(publish_calls) == 1
        payload = publish_calls[0][0][1]
        assert payload["task_id"] == task_id
        assert payload["error_type"] == "E3112"
        assert payload["recoverable"] is True
        assert payload["last_checkpoint"] == "step-abc"

    @pytest.mark.asyncio
    async def test_CAS未命中_不发送SSE(self):
        """任务已非 running 时 CAS 未命中，不推送 SSE。"""
        task_id = "task-002"
        session = AsyncMock()
        execute_result = MagicMock()
        execute_result.rowcount = 0
        session.execute.return_value = execute_result

        sse_bridge = AsyncMock()

        with patch("app.main.async_session_factory", return_value=_make_async_session_cm(session)), \
             patch("app.main.SSEBridge", return_value=sse_bridge):
            from app.main import _mark_task_worker_timeout

            await _mark_task_worker_timeout(task_id)

        sse_bridge.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_SSE推送失败_不阻断状态更新(self):
        """SSE 发布异常不应导致状态更新回滚或抛错。"""
        task_id = "task-003"
        session = AsyncMock()
        execute_result = MagicMock()
        execute_result.rowcount = 1
        session.execute.return_value = execute_result

        sse_bridge = AsyncMock()
        sse_bridge.publish.side_effect = RuntimeError("Redis 不可用")

        with patch("app.main.async_session_factory", return_value=_make_async_session_cm(session)), \
             patch("app.main.SSEBridge", return_value=sse_bridge):
            from app.main import _mark_task_worker_timeout

            # 不应抛异常
            await _mark_task_worker_timeout(task_id)

        # 状态更新已提交
        session.commit.assert_awaited()


# ═══════════════════════════════════════════════════════════════
# _check_worker_timeouts
# ═══════════════════════════════════════════════════════════════


class TestCheckWorkerTimeouts:
    """Worker 超时监察者扫描逻辑。"""

    @staticmethod
    def _setup_session_for_two_queries(running_rows, pending_rows=None):
        """构造 session mock：交替返回 running 和 pending 查询结果（支持多次调用）。"""
        session = AsyncMock()
        running_result = MagicMock()
        running_result.all.return_value = running_rows
        pending_result = MagicMock()
        pending_result.all.return_value = pending_rows if pending_rows is not None else []

        call_count = [0]

        async def _side_effect(*args, **kwargs):
            idx = call_count[0] % 2
            call_count[0] += 1
            return running_result if idx == 0 else pending_result

        session.execute = AsyncMock(side_effect=_side_effect)
        return session

    @pytest.mark.asyncio
    async def test_锁存在且任务running_不标记失败(self):
        """任务级锁存在 → 跳过，不调用 _mark_task_worker_timeout。"""
        task_id = "task-101"
        session = self._setup_session_for_two_queries([_running_task_row(task_id)])

        with patch("app.main.async_session_factory", return_value=_make_async_session_cm(session)), \
             patch("app.main.check_task_lock_async", new_callable=AsyncMock, return_value=True), \
             patch("app.main._mark_task_worker_timeout") as mark_failed, \
             patch("app.main._mark_task_pending_timeout") as mark_pending:
            from app.main import _check_worker_timeouts

            await _check_worker_timeouts()

            mark_failed.assert_not_awaited()
            mark_pending.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_锁缺失且running超过超时_调用标记失败(self):
        """锁缺失持续超时阈值后调用 _mark_task_worker_timeout。"""
        task_id = "task-102"
        session = self._setup_session_for_two_queries([_running_task_row(task_id)])

        with patch("app.main.async_session_factory", return_value=_make_async_session_cm(session)), \
             patch("app.main.check_task_lock_async", new_callable=AsyncMock, return_value=False), \
             patch("app.main._mark_task_worker_timeout") as mark_failed, \
             patch("app.main._mark_task_pending_timeout") as mark_pending, \
             patch("app.main.settings.WORKER_TIMEOUT_SECONDS", 0):
            from app.main import _check_worker_timeouts

            # 第一次：记录首次缺失时间
            await _check_worker_timeouts()
            mark_failed.assert_not_awaited()

            # 第二次：超过阈值（timeout=0）→ 标记失败
            await _check_worker_timeouts()
            mark_failed.assert_awaited_once_with(task_id)

    @pytest.mark.asyncio
    async def test_启动宽限期内锁缺失_不标记失败(self):
        """started_at 在宽限期内即使锁缺失也不标记失败。"""
        task_id = "task-103"
        started_at = datetime.now(timezone.utc) - timedelta(seconds=2)
        session = self._setup_session_for_two_queries([(task_id, started_at)])

        with patch("app.main.async_session_factory", return_value=_make_async_session_cm(session)), \
             patch("app.main.check_task_lock_async", new_callable=AsyncMock, return_value=False), \
             patch("app.main._mark_task_worker_timeout") as mark_failed, \
             patch("app.main._mark_task_pending_timeout") as mark_pending:
            from app.main import _check_worker_timeouts

            await _check_worker_timeouts()

            mark_failed.assert_not_awaited()
            mark_pending.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_非running状态_不扫描(self):
        """没有 running 任务时 _mark_task_worker_timeout 不被调用。"""
        session = self._setup_session_for_two_queries([])

        with patch("app.main.async_session_factory", return_value=_make_async_session_cm(session)), \
             patch("app.main._mark_task_worker_timeout") as mark_failed, \
             patch("app.main._mark_task_pending_timeout") as mark_pending:
            from app.main import _check_worker_timeouts

            await _check_worker_timeouts()

            mark_failed.assert_not_awaited()
            mark_pending.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_锁检查异常_不误判失败(self):
        """Redis 不可用时 check_task_lock_async 抛异常，不应标记任务失败。"""
        task_id = "task-104"
        session = self._setup_session_for_two_queries([_running_task_row(task_id)])

        with patch("app.main.async_session_factory", return_value=_make_async_session_cm(session)), \
             patch("app.main.check_task_lock_async", new_callable=AsyncMock, side_effect=RuntimeError("Redis 断开")), \
             patch("app.main._mark_task_worker_timeout") as mark_failed, \
             patch("app.main._mark_task_pending_timeout") as mark_pending:
            from app.main import _check_worker_timeouts

            await _check_worker_timeouts()

            mark_failed.assert_not_awaited()
            mark_pending.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_锁恢复后_清除追踪记录(self):
        """锁从缺失恢复到存在后，应清除对应追踪条目。"""
        task_id = "task-105"
        session = self._setup_session_for_two_queries([_running_task_row(task_id)])

        from app import main as main_module

        with patch("app.main.async_session_factory", return_value=_make_async_session_cm(session)), \
             patch("app.main.check_task_lock_async", new_callable=AsyncMock, return_value=False), \
             patch("app.main._mark_task_worker_timeout"), \
             patch("app.main._mark_task_pending_timeout"):
            from app.main import _check_worker_timeouts

            await _check_worker_timeouts()
            assert task_id in main_module._worker_lock_missing_since

        with patch("app.main.async_session_factory", return_value=_make_async_session_cm(session)), \
             patch("app.main.check_task_lock_async", new_callable=AsyncMock, return_value=True), \
             patch("app.main._mark_task_worker_timeout") as mark_failed, \
             patch("app.main._mark_task_pending_timeout") as mark_pending:
            from app.main import _check_worker_timeouts

            await _check_worker_timeouts()

            assert task_id not in main_module._worker_lock_missing_since
            mark_failed.assert_not_awaited()
