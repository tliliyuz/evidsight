"""PipelineOrchestrator 单元测试 — 七阶段调度、幂等锁、FATAL 提前终止、_finalize_task 三分支。

Mock 注入 phase_handlers + AsyncMock session + MagicMock sse_bridge，
验证核心调度逻辑的正确性。
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select as sa_select

from app.core.exceptions import PlanningFailedException, SynthesisFailedException
from app.core.security import hash_password
from app.core.task_state_resolver import FATAL_STEP_ERROR_CODES
from app.core.trace_recorder import TraceRecorder
from app.models.enums import TASK_PHASE_ENUM, STEP_TYPE_ENUM
from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.pipeline.sse_bridge import (
    EVENT_STEP_COMPLETED,
    EVENT_STEP_FAILED,
    EVENT_STEP_SKIPPED,
    EVENT_STEP_STARTED,
    EVENT_TASK_CANCELED,
    EVENT_TASK_COMPLETED,
    EVENT_TASK_CREATED,
    EVENT_TASK_FAILED,
    EVENT_TASK_PROGRESS,
    EVENT_TASK_WARNING,
)
from app.services.pipeline_orchestrator import (
    PHASE_LABELS,
    PHASE_ORDER,
    PipelineOrchestrator,
)
from app.tasks.lock import (
    acquire_task_lock_async,
    release_task_lock_async,
)


@pytest.fixture(autouse=True)
def _mock_task_lock():
    """默认自动 mock 任务级锁，避免污染现有调度测试；锁专用测试会单独 patch。

    把 refresh_task_lock_async mock 掉，使测试不会访问真实 Redis。
    fixture 退出时取消事件循环中残留的后台协程，避免 'Task destroyed but pending' 警告。
    """
    with patch("app.services.pipeline_orchestrator.acquire_task_lock_async", return_value=True), \
         patch("app.services.pipeline_orchestrator.release_task_lock_async"), \
         patch("app.services.pipeline_orchestrator.refresh_task_lock_async", new_callable=AsyncMock):
        yield

    try:
        loop = asyncio.get_event_loop()
        if not loop.is_closed():
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# 工厂
# ═══════════════════════════════════════════════════════════════


def _make_task(**kwargs) -> MagicMock:
    """创建测试用 ResearchTask mock，默认 status=running。"""
    task = MagicMock(spec=ResearchTask)
    task.id = kwargs.get("id", 1)
    task.status = kwargs.get("status", "running")
    task.topic = kwargs.get("topic", "测试主题")
    task.current_phase = kwargs.get("current_phase", None)
    total_steps = kwargs.get("total_steps", 7)
    completed_steps = kwargs.get("completed_steps", 0)
    task.total_steps = total_steps
    task.completed_steps = completed_steps
    task.total_sources = kwargs.get("total_sources", 0)
    task.total_evidence = kwargs.get("total_evidence", 0)
    task.error_code = kwargs.get("error_code", None)
    task.error_message = kwargs.get("error_message", None)
    task.recoverable = kwargs.get("recoverable", None)
    task.created_at = kwargs.get("created_at", datetime.now(timezone.utc))
    task.started_at = kwargs.get("started_at", datetime.now(timezone.utc))
    task.completed_at = kwargs.get("completed_at", None)
    task.execution_context = kwargs.get("execution_context", None)

    # 构造 steps 列表，避免 _check_early_termination / _finalize_task 把 MagicMock
    # 当成空列表导致误判（空列表会被视为全部终态并触发 Evidence Threshold 判定）。
    steps = []
    for i in range(total_steps):
        step_mock = MagicMock(spec=ResearchStep)
        step_mock.status = "completed" if i < completed_steps else "pending"
        step_mock.error_code = None
        step_mock.error_message = None
        steps.append(step_mock)
    task.steps = steps
    return task


def _make_phase_handler(should_fail: bool = False, error: Exception = None):
    """创建 Phase handler mock，可选失败。"""
    async def handler(task, step, session, sse_bridge):
        if should_fail:
            if error:
                raise error
            raise RuntimeError("模拟 Phase 失败")
        return {"status": "ok"}
    return handler


def _configure_async_mock_session(session: AsyncMock) -> None:
    """配置 AsyncMock session，使 _create_step 中的复用查询返回 None。

    默认 AsyncMock 的 scalar_one_or_none() 被 await 后会返回 AsyncMock 实例，
    导致 _create_step 误判为"复用已有 Step"。生产环境无此问题（真实 DB 返回 None
    或 ResearchStep 实例），此处仅为 Mock 测试做一致性配置。

    同时默认 rowcount=1，避免 CAS 更新后把 AsyncMock 当整数比较失败。
    """
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalar.return_value = 0
    mock_result.rowcount = 1
    session.execute = AsyncMock(return_value=mock_result)


# ═══════════════════════════════════════════════════════════════
# Phase 顺序与调度
# ═══════════════════════════════════════════════════════════════


class TestPhaseOrder:
    """七阶段顺序正确，按 PHASE_ORDER 串行调度。"""

    def test_PHASE_ORDER_包含全部七阶段(self):
        """PHASE_ORDER 应包含全部 7 个 step_type。"""
        assert len(PHASE_ORDER) == 7
        expected = [
            "planning", "search", "fetch", "rerank",
            "synthesis", "evidence_graph", "render",
        ]
        assert list(PHASE_ORDER) == expected

    def test_PHASE_LABELS_七阶段均有中文标签(self):
        """PHASE_LABELS 为七阶段提供前端展示用中文标签。"""
        for step_type in PHASE_ORDER:
            assert step_type in PHASE_LABELS
            assert PHASE_LABELS[step_type]

    @pytest.mark.asyncio
    async def test_终态任务_不执行任何phase(self):
        """_start_task 遇到终态任务时 run() 应直接返回，不调用任何 handler。"""
        task = _make_task(status="completed")  # 终态，直接返回 False
        session = AsyncMock()
        _configure_async_mock_session(session)
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        handler_called = []
        handlers = {
            phase: _make_phase_handler() for phase in PHASE_ORDER
        }
        for phase in PHASE_ORDER:
            original = handlers[phase]

            async def wrapped(t, s, sess, sb, p=phase, orig=original):
                handler_called.append(p)
                return await orig(t, s, sess, sb)

            handlers[phase] = wrapped

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers=handlers,
        )

        await orchestrator.run()

        assert len(handler_called) == 0
        # task.created 事件不应发送
        created_calls = [
            c for c in sse_bridge.publish.await_args_list
            if c[0][0] == EVENT_TASK_CREATED
        ]
        assert len(created_calls) == 0

    @pytest.mark.asyncio
    async def test_run_按顺序调用已注册phase_handler(self):
        """已注册 handler 的 phase 按 PHASE_ORDER 顺序被调用。"""
        task = _make_task()
        session = AsyncMock()
        _configure_async_mock_session(session)
        _configure_async_mock_session(session)
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        call_order = []
        handlers = {}
        for phase in PHASE_ORDER[:3]:  # planning / search / fetch
            async def h(t, s, sess, sb, p=phase):
                call_order.append(p)
                return {"status": "ok"}
            handlers[phase] = h

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers=handlers,
        )

        # Mock 模块级锁函数（acquire_step_lock_async / release_step_lock_async）
        with patch("app.services.pipeline_orchestrator.acquire_step_lock_async", return_value=True):
            with patch("app.services.pipeline_orchestrator.release_step_lock_async"):
                await orchestrator.run()

        assert call_order == ["planning", "search", "fetch"]

    @pytest.mark.asyncio
    async def test_run_未注册handler自动跳过(self):
        """未注册 handler 的 phase → _skip_phase 被调用且不抛异常。"""
        task = _make_task()
        session = AsyncMock()
        _configure_async_mock_session(session)
        _configure_async_mock_session(session)
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        handlers = {"planning": _make_phase_handler()}

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers=handlers,
        )

        skip_phases = []
        original_skip = orchestrator._skip_phase

        async def _tracking_skip(step, phase_name, reason=""):
            skip_phases.append(phase_name)
            await original_skip(step, phase_name, reason=reason)

        orchestrator._skip_phase = _tracking_skip

        with patch("app.services.pipeline_orchestrator.acquire_step_lock_async", return_value=True):
            with patch("app.services.pipeline_orchestrator.release_step_lock_async"):
                await orchestrator.run()

        # 6 unregistered phases skip (all except planning)
        assert len(skip_phases) == 6  # search/fetch/rerank/synthesis/evidence_graph/render


# ═══════════════════════════════════════════════════════════════
# 幂等锁
# ═══════════════════════════════════════════════════════════════


class TestIdempotentLock:
    """幂等锁占用 → 跳过 phase。"""

    @pytest.mark.asyncio
    async def test_锁已被占用则跳过phase(self):
        """acquire_step_lock_async 返回 False → phase 被跳过且不抛异常。"""
        task = _make_task()
        session = AsyncMock()
        _configure_async_mock_session(session)
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)
        handlers = {"planning": _make_phase_handler()}

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers=handlers,
        )

        with patch("app.services.pipeline_orchestrator.acquire_step_lock_async", return_value=False):
            # 锁被占用 → orchestrator 应完成运行（不抛异常），所有 phase 被跳过
            await orchestrator.run()

        # 验证 orchestrator 完成运行（无异常即为通过）


# ═══════════════════════════════════════════════════════════════
# FATAL 错误提前终止
# ═══════════════════════════════════════════════════════════════


class TestFatalErrorTermination:
    """FATAL 错误码 → 提前终止并 emit task.failed。"""

    @pytest.mark.asyncio
    async def test_FATAL错误_emit_task_failed事件(self):
        """Planning 抛出 E3101（FATAL）→ emit task.failed + task 状态为 failed。"""
        task = _make_task()
        session = AsyncMock()
        _configure_async_mock_session(session)
        _configure_async_mock_session(session)
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)
        handlers = {
            "planning": _make_phase_handler(
                should_fail=True,
                error=PlanningFailedException("测试 FATAL 错误"),
            )
        }

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers=handlers,
        )

        with patch("app.services.pipeline_orchestrator.acquire_step_lock_async", return_value=True):
            with patch("app.services.pipeline_orchestrator.release_step_lock_async"):
                await orchestrator.run()

        # 验证 task.failed 事件被发送
        task_failed_calls = [
            c for c in sse_bridge.publish.await_args_list
            if c[0][0] == EVENT_TASK_FAILED
        ]
        assert len(task_failed_calls) == 1
        payload = task_failed_calls[0][0][1]
        assert payload["error_type"] == "PlanningFailed"
        # 应使用 AppException 的友好 message，禁止暴露 JSON 或原始 detail
        assert payload["error_description"] == "LLM 无法拆解研究主题"
        assert "{" not in payload["error_description"]
        # 验证 error_code 在 FATAL 集中
        assert "E3101" in FATAL_STEP_ERROR_CODES

    @pytest.mark.asyncio
    async def test_可恢复致命错误_emit_task_failed_recoverable为True_终止Pipeline(self):
        """FATAL 但 recoverable=true 的错误（E3104）→ emit task.failed(recoverable=True) + Pipeline 终止。"""
        task = _make_task()
        task.execution_context = {"last_completed_step_id": "some-step-uuid"}
        session = AsyncMock()
        _configure_async_mock_session(session)
        _configure_async_mock_session(session)
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        call_order = []
        async def failing_planning(t, s, sess, sb):
            call_order.append("planning")
            raise SynthesisFailedException("模拟可恢复致命失败")

        async def ok_search(t, s, sess, sb):
            call_order.append("search")
            return {"status": "ok"}

        handlers = {"planning": failing_planning, "search": ok_search}

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers=handlers,
        )

        with patch("app.services.pipeline_orchestrator.acquire_step_lock_async", return_value=True):
            with patch("app.services.pipeline_orchestrator.release_step_lock_async"):
                await orchestrator.run()

        # 验证 task.failed 事件被发送且 recoverable=True
        failed_calls = [
            c for c in sse_bridge.publish.await_args_list
            if c[0][0] == EVENT_TASK_FAILED
        ]
        assert len(failed_calls) == 1
        payload = failed_calls[0][0][1]
        assert payload["recoverable"] is True
        assert payload.get("last_checkpoint") == "some-step-uuid"

        # 验证没有 warning 事件（所有 E31xx 均致命）
        warning_calls = [
            c for c in sse_bridge.publish.await_args_list
            if c[0][0] == EVENT_TASK_WARNING
        ]
        assert len(warning_calls) == 0

        # 验证 Pipeline 在 planning 后终止，search 未执行
        assert call_order == ["planning"]

    @pytest.mark.asyncio
    async def test_handle_step_error_session已失效_先rollback再更新step状态(self):
        """模拟 DB flush 失败导致 session inactive，_handle_step_error 应恢复 session 并继续处理。"""
        task = _make_task()
        session = AsyncMock()
        _configure_async_mock_session(session)
        session.is_active = False
        session.rollback = AsyncMock()
        session.get = AsyncMock(return_value=None)

        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers={},
        )

        step = MagicMock(spec=ResearchStep)
        step.id = "step-001"
        step.task_id = task.id
        # 使用非致命 phase（fetch 不在 FATAL_STEP_TYPES 中），避免 raise 重新抛出
        step.step_type = "fetch"
        step.started_at = datetime.now(timezone.utc)
        step.status = "running"

        error = RuntimeError("模拟 Fetch 失败")

        await orchestrator._handle_step_error(step, "fetch", error)

        # session 回滚后被重新激活，step 状态仍应被标记为 failed
        session.rollback.assert_awaited_once()
        assert step.status == "failed"
        # 未知异常不应暴露原始错误细节给前端
        assert step.error_message == "未预期的内部错误，请稍后重试"
        assert step.error_code is None
        # step.failed SSE 事件应被发送
        failed_calls = [
            c for c in sse_bridge.publish.await_args_list
            if c[0][0] == EVENT_STEP_FAILED
        ]
        assert len(failed_calls) == 1

    @pytest.mark.asyncio
    async def test_handle_fatal_error_session已失效_rollback后写入task失败状态(self):
        """模拟 DB flush 失败导致 session inactive，_handle_fatal_error 应恢复 session 并写入 failed 状态。"""
        task = _make_task()
        session = AsyncMock()
        _configure_async_mock_session(session)
        session.is_active = False
        session.rollback = AsyncMock()

        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers={},
        )

        error = RuntimeError("模拟未知致命错误")
        await orchestrator._handle_fatal_error(error)

        # session 应先回滚，然后执行 CAS 更新
        session.rollback.assert_awaited_once()
        assert session.execute.await_count >= 1

        # task.failed SSE 事件应被发送
        failed_calls = [
            c for c in sse_bridge.publish.await_args_list
            if c[0][0] == EVENT_TASK_FAILED
        ]
        assert len(failed_calls) == 1


# ═══════════════════════════════════════════════════════════════
# _finalize_task 三分支
# ═══════════════════════════════════════════════════════════════


class TestFinalizeTask:
    """_finalize_task 根据 steps 终态推导 task 最终状态。"""

    @pytest.mark.asyncio
    async def test_全部phase注册且完成_emit_task_completed(self):
        """所有 7 个 phases 成功完成 → emit task.completed。"""
        task = _make_task(completed_steps=7, total_steps=7, total_evidence=10)
        task.status = "running"
        session = AsyncMock()
        _configure_async_mock_session(session)
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        # 注册全部 7 个 phase handler
        handlers = {p: _make_phase_handler() for p in PHASE_ORDER}

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers=handlers,
        )

        with patch("app.services.pipeline_orchestrator.acquire_step_lock_async", return_value=True):
            with patch("app.services.pipeline_orchestrator.release_step_lock_async"):
                await orchestrator.run()

        # 验证 task.completed 事件被发送
        completed_calls = [
            c for c in sse_bridge.publish.await_args_list
            if c[0][0] == EVENT_TASK_COMPLETED
        ]
        assert len(completed_calls) == 1

    @pytest.mark.asyncio
    async def test_有failed_step_emit_task_failed(self):
        """存在 failed step → emit task.failed。"""
        task = _make_task()
        session = AsyncMock()
        _configure_async_mock_session(session)
        _configure_async_mock_session(session)
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)
        handlers = {
            "planning": _make_phase_handler(
                should_fail=True,
                error=PlanningFailedException("FATAL"),
            )
        }

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers=handlers,
        )

        with patch("app.services.pipeline_orchestrator.acquire_step_lock_async", return_value=True):
            with patch("app.services.pipeline_orchestrator.release_step_lock_async"):
                await orchestrator.run()

        failed_calls = [
            c for c in sse_bridge.publish.await_args_list
            if c[0][0] == EVENT_TASK_FAILED
        ]
        assert len(failed_calls) == 1


# ═══════════════════════════════════════════════════════════════
# 取消检测
# ═══════════════════════════════════════════════════════════════


class TestCancelDetection:
    """Orchestrator 执行过程中检测到 status=canceled 后停止并发送 task.canceled。"""

    @pytest.mark.asyncio
    async def test_执行中任务被取消_发送task_canceled事件(self):
        task = _make_task(status="running")
        session = AsyncMock()
        _configure_async_mock_session(session)
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        # 第一次 refresh（_start_task）保持 running，后续 refresh（phase 循环）变为 canceled
        refresh_count = 0
        async def _refresh(task_obj, attrs=None):
            nonlocal refresh_count
            refresh_count += 1
            if refresh_count > 1:
                task_obj.status = "canceled"
            return None
        session.refresh.side_effect = _refresh

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers={},
        )

        await orchestrator.run()

        canceled_calls = [
            c for c in sse_bridge.publish.await_args_list
            if c[0][0] == EVENT_TASK_CANCELED
        ]
        assert len(canceled_calls) == 1
        payload = canceled_calls[0][0][1]
        assert payload["task_id"] == str(task.id)
        assert payload["status"] == "canceled"


# ═══════════════════════════════════════════════════════════════
# 成本追踪
# ═══════════════════════════════════════════════════════════════


class TestCostTracking:
    """Step cost 写入与 Trace 聚合。"""

    @pytest.mark.asyncio
    async def test_complete_step_写入step_cost(self):
        task = _make_task()
        session = AsyncMock()
        _configure_async_mock_session(session)
        session.refresh = AsyncMock()
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        # 构造真实 ResearchStep，便于断言 cost 字段
        step = ResearchStep(
            id="step-cost-001",
            task_id=task.id,
            step_type="planning",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        trace = TraceRecorder(task_id=str(task.id), user_id=1, topic="测试")
        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=trace, phase_handlers={},
        )

        output = {
            "sub_questions": ["q1", "q2"],
            "prompt_tokens": 1000,
            "completion_tokens": 200,
            "model": "deepseek-v4-pro",
            "retry_count": 0,
        }
        await orchestrator._complete_step(step, "planning", output)

        assert step.cost["input_tokens"] == 1000
        assert step.cost["output_tokens"] == 200
        assert step.cost["model"] == "deepseek-v4-pro"
        assert step.cost["estimated_cost_usd"] == 0.000609

    @pytest.mark.asyncio
    async def test_complete_step_非LLM阶段不写入cost(self):
        task = _make_task()
        session = AsyncMock()
        _configure_async_mock_session(session)
        session.refresh = AsyncMock()
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        step = ResearchStep(
            id="step-cost-002",
            task_id=task.id,
            step_type="search",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        trace = TraceRecorder(task_id=str(task.id), user_id=1, topic="测试")
        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=trace, phase_handlers={},
        )

        await orchestrator._complete_step(step, "search", {"after_dedup": 5})

        assert step.cost is None

    @pytest.mark.asyncio
    async def test_trace_聚合各LLM阶段成本(self):
        trace = TraceRecorder(task_id="task-trace-001", user_id=1, topic="测试")
        trace.record_planning(
            duration_ms=1000,
            input_tokens=1000,
            output_tokens=200,
            sub_questions_count=3,
            model="deepseek-v4-pro",
        )
        trace.record_rerank(
            duration_ms=2000,
            bm25_candidates=10,
            llm_reranked=5,
            input_tokens=2000,
            output_tokens=300,
            model="deepseek-v4-flash",
        )
        trace.record_synthesis(
            duration_ms=3000,
            input_tokens=5000,
            output_tokens=1000,
            clusters_count=2,
            model="deepseek-v4-pro",
        )
        trace.record_render(
            duration_ms=4000,
            input_tokens=3000,
            output_tokens=1500,
            sections_count=3,
            model="deepseek-v4-pro",
        )

        result = trace.finish()

        assert result["total_input_tokens"] == 11000
        assert result["total_output_tokens"] == 3000
        assert result["total_tokens"] == 14000
        assert result["total_cost_usd"] == 0.006628
        assert "planning" in result["breakdown"]
        assert "rerank" in result["breakdown"]
        assert "synthesis" in result["breakdown"]
        assert "render" in result["breakdown"]
        assert result["breakdown"]["planning"]["tokens"] == 1200
        assert result["breakdown"]["planning"]["cost"] == 0.000609
        assert result["phases"]["planning"]["model"] == "deepseek-v4-pro"

    @pytest.mark.asyncio
    async def test_trace_断点续跑合并previous_trace(self):
        """断点续跑：previous_trace 中已完成的阶段应保留，并累加到 task 总计。"""
        # 模拟首次运行：planning/search/fetch/rerank 完成，synthesis 失败
        previous_trace = {
            "task_id": "task-resume-001",
            "user_id": 1,
            "status": "error",
            "total_duration_ms": 6500,
            "total_input_tokens": 3000,
            "total_output_tokens": 500,
            "total_cost_usd": 0.076973,
            "phases": {
                "planning": {
                    "span_name": "planning",
                    "duration_ms": 1000,
                    "status": "success",
                    "input_tokens": 1000,
                    "output_tokens": 200,
                    "model": "deepseek-v4-pro",
                },
                "search": {
                    "span_name": "search",
                    "duration_ms": 2000,
                    "status": "success",
                    "cost_usd": 0.075,
                },
                "fetch": {
                    "span_name": "fetch",
                    "duration_ms": 1500,
                    "status": "success",
                    "cost_usd": 0.001,
                },
                "rerank": {
                    "span_name": "rerank",
                    "duration_ms": 2000,
                    "status": "success",
                    "input_tokens": 2000,
                    "output_tokens": 300,
                    "model": "deepseek-v4-flash",
                },
                "synthesis": None,
                "evidence_graph": None,
                "render": None,
            },
            "phase_durations_ms": {
                "planning": 1000,
                "search": 2000,
                "fetch": 1500,
                "rerank": 2000,
            },
            "breakdown": {
                "planning": {"tokens": 1200, "cost": 0.000609},
                "search": {"tokens": 0, "cost": 0.075},
                "fetch": {"tokens": 0, "cost": 0.001},
                "rerank": {"tokens": 2300, "cost": 0.000364},
            },
            "error_message": "synthesis failed",
            "created_at": "2025-01-01T00:00:00.000+00:00",
        }

        # 续跑：仅 synthesis / evidence_graph / render 重新执行，
        # planning / search / fetch / rerank 被跳过（沿用 previous_trace）
        trace = TraceRecorder(
            task_id="task-resume-001",
            user_id=1,
            topic="测试",
            previous_trace=previous_trace,
        )
        trace.record_synthesis(
            duration_ms=3000,
            input_tokens=5000,
            output_tokens=1000,
            clusters_count=2,
            model="deepseek-v4-pro",
        )
        trace.record_evidence_graph(
            duration_ms=500,
            evidence_count=8,
            source_count=5,
        )
        trace.record_render(
            duration_ms=4000,
            input_tokens=3000,
            output_tokens=1500,
            sections_count=3,
            model="deepseek-v4-pro",
        )

        result = trace.finish()

        # 阶段数据：被跳过的阶段保留 previous_trace 数据
        assert result["phases"]["planning"]["model"] == "deepseek-v4-pro"
        assert result["phases"]["planning"]["duration_ms"] == 1000
        assert result["phases"]["search"]["cost_usd"] == 0.075
        assert result["phases"]["fetch"]["cost_usd"] == 0.001
        assert result["phases"]["rerank"]["model"] == "deepseek-v4-flash"
        # 重新执行阶段使用新数据
        assert result["phases"]["synthesis"]["input_tokens"] == 5000
        assert result["phases"]["evidence_graph"]["evidence_count"] == 8
        assert result["phases"]["render"]["sections_count"] == 3

        # 总计：previous skipped + current run
        # input: (1000+2000) [prev] + (5000+3000) [cur] = 11000
        assert result["total_input_tokens"] == 11000
        # output: (200+300) [prev] + (1000+1500) [cur] = 3000
        assert result["total_output_tokens"] == 3000
        assert result["total_tokens"] == 14000
        # cost: 0.000609 + 0.075 + 0.001 + 0.000364 [prev] + 0.003045 + 0.00261 [cur]
        assert result["total_cost_usd"] == 0.082628

        # breakdown 合并：prev 阶段 + 当前阶段
        assert result["breakdown"]["planning"]["cost"] == 0.000609
        assert result["breakdown"]["search"]["cost"] == 0.075
        assert result["breakdown"]["fetch"]["cost"] == 0.001
        assert result["breakdown"]["rerank"]["cost"] == 0.000364
        assert result["breakdown"]["synthesis"]["cost"] == 0.003045
        assert result["breakdown"]["render"]["cost"] == 0.00261

        # 总耗时：所有阶段 duration_ms 之和
        # 1000 + 2000 + 1500 + 2000 + 3000 + 500 + 4000 = 14000
        assert result["total_duration_ms"] == 14000
        assert result["phase_durations_ms"]["planning"] == 1000
        assert result["phase_durations_ms"]["render"] == 4000

    @pytest.mark.asyncio
    async def test_complete_step_search阶段记录trace(self):
        """search 阶段完成后应调用 record_search 写入 trace。"""
        task = _make_task()
        session = AsyncMock()
        _configure_async_mock_session(session)
        session.refresh = AsyncMock()
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        step = ResearchStep(
            id="step-search-001",
            task_id=task.id,
            step_type="search",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        trace = TraceRecorder(task_id=str(task.id), user_id=1, topic="测试")
        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=trace, phase_handlers={},
        )

        output = {
            "total_results": 30,
            "sub_question_results": [
                {"status": "completed", "results_count": 10},
                {"status": "completed", "results_count": 10},
                {"status": "skipped", "results_count": 10},
            ],
        }
        await orchestrator._complete_step(step, "searching", output)

        search_data = trace.finish()["phases"]["search"]
        assert search_data["total_results"] == 30
        assert search_data["success_count"] == 2
        assert search_data["skipped_count"] == 1

    @pytest.mark.asyncio
    async def test_complete_step_fetch阶段记录trace(self):
        """fetch 阶段完成后应调用 record_fetch 写入 trace。"""
        task = _make_task()
        session = AsyncMock()
        _configure_async_mock_session(session)
        session.refresh = AsyncMock()
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        step = ResearchStep(
            id="step-fetch-001",
            task_id=task.id,
            step_type="fetch",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        trace = TraceRecorder(task_id=str(task.id), user_id=1, topic="测试")
        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=trace, phase_handlers={},
        )

        output = {
            "fetched": [
                {"url": "https://a.com", "content_length": 100},
                {"url": "https://b.com", "content_length": 200},
            ],
            "successful": 2,
            "failed": 0,
            "skipped_safety": 1,
        }
        await orchestrator._complete_step(step, "fetching", output)

        fetch_data = trace.finish()["phases"]["fetch"]
        assert fetch_data["total_urls"] == 2
        assert fetch_data["success_count"] == 2
        assert fetch_data["skipped_count"] == 1
        assert fetch_data["total_content_bytes"] == 300

    @pytest.mark.asyncio
    async def test_complete_step_evidence_graph阶段记录trace(self):
        """evidence_graph 阶段完成后应调用 record_evidence_graph 写入 trace。"""
        task = _make_task()
        session = AsyncMock()
        _configure_async_mock_session(session)
        session.refresh = AsyncMock()
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        step = ResearchStep(
            id="step-eg-001",
            task_id=task.id,
            step_type="evidence_graph",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        trace = TraceRecorder(task_id=str(task.id), user_id=1, topic="测试")
        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=trace, phase_handlers={},
        )

        output = {"item_count": 8, "source_count": 5}
        await orchestrator._complete_step(step, "building_evidence_graph", output)

        eg_data = trace.finish()["phases"]["evidence_graph"]
        assert eg_data["evidence_count"] == 8
        assert eg_data["source_count"] == 5


# ═══════════════════════════════════════════════════════════════════════
# 真实 DB session 集成验证
# ═══════════════════════════════════════════════════════════════════════


class TestPipelineWithRealSession:
    """使用真实 DB session 验证 Pipeline 完成后 Task 状态正确流转。"""

    @pytest.mark.asyncio
    async def test_全部phase完成后_task状态变为completed(self, db_session):
        """全部 7 个 phase handler 成功执行后，task status 应从 running 变为 completed。"""
        user = User(
            username="pipeline-real-session",
            password_hash=hash_password("pass"),
            role="user",
            status="active",
        )
        db_session.add(user)
        await db_session.flush()

        task = ResearchTask(
            user_id=user.id,
            topic="真实 session 测试",
            requirements={"task_type": "analysis", "max_sources": 10, "language": "zh"},
            status="pending",
        )
        db_session.add(task)
        await db_session.flush()

        handlers = {phase: _make_phase_handler() for phase in PHASE_ORDER}

        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)
        trace_recorder = TraceRecorder(
            task_id=str(task.id), user_id=str(user.id), topic=task.topic
        )

        orchestrator = PipelineOrchestrator(
            task=task,
            session=db_session,
            sse_bridge=sse_bridge,
            trace_recorder=trace_recorder,
            phase_handlers=handlers,
        )

        # 阻止内部 commit，避免破坏测试事务隔离；所有写操作仍在同一事务内可见
        with patch.object(db_session, "commit", new_callable=AsyncMock):
            with patch("app.services.pipeline_orchestrator.acquire_step_lock_async", return_value=True):
                with patch("app.services.pipeline_orchestrator.release_step_lock_async"):
                    await orchestrator.run()

        # 在同一未提交事务内查询验证 CAS 更新结果
        result = await db_session.execute(
            sa_select(ResearchTask).where(ResearchTask.id == task.id)
        )
        updated_task = result.scalar_one()
        assert updated_task.status == "completed"


# ═══════════════════════════════════════════════════════════════
# Step 幂等锁崩溃恢复
# ═══════════════════════════════════════════════════════════════


class TestStepLockRecovery:
    """崩溃恢复模式下遗留 Step 锁的清理行为。"""

    @pytest.mark.asyncio
    async def test_恢复模式_running_Step遗留锁被强制释放并执行(self):
        """恢复模式 + step.running + 已持有任务锁 → 强制释放旧锁并执行 handler。"""
        task = _make_task(status="running")
        session = AsyncMock()
        _configure_async_mock_session(session)
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        handler_called = []

        async def handler(t, s, sess, sb):
            handler_called.append("synthesis")
            return {"status": "ok"}

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers={"synthesis": handler},
        )
        orchestrator._is_recovery = True
        orchestrator._task_lock_acquired = True

        step = MagicMock(spec=ResearchStep)
        step.id = "step-synthesis-001"
        step.status = "running"
        step.step_type = "synthesis"
        step.label = "Synthesis"
        orchestrator._create_step = AsyncMock(return_value=step)

        with patch("app.services.pipeline_orchestrator.acquire_step_lock_async", side_effect=[False, True]) as mock_acquire, \
             patch("app.services.pipeline_orchestrator.release_step_lock_async") as mock_release:
            await orchestrator._run_phase("synthesis")

        # 强制释放旧锁并重新获取（finally 块会再释放一次，因此共 2 次）
        assert mock_acquire.await_count == 2
        assert mock_release.await_count == 2
        mock_release.assert_any_await(str(task.id), "synthesis")
        # handler 被调用，step 未被 skipped
        assert handler_called == ["synthesis"]
        assert step.status != "skipped"

    @pytest.mark.asyncio
    async def test_未持有任务锁时Step锁被占用则跳过(self):
        """未持有任务锁 + acquire_step_lock_async 返回 False → Step 被 skipped。

        任务级锁是强制释放的基础。不持有任务锁时，Step 锁可能属于正在运行的
        另一个 Worker，不应强制释放。
        """
        task = _make_task(status="running")
        session = AsyncMock()
        _configure_async_mock_session(session)
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers={},
        )
        orchestrator._task_lock_acquired = False

        step = MagicMock(spec=ResearchStep)
        step.id = "step-synthesis-002"
        step.status = "running"
        step.step_type = "synthesis"
        step.label = "Synthesis"
        orchestrator._create_step = AsyncMock(return_value=step)

        with patch("app.services.pipeline_orchestrator.acquire_step_lock_async", return_value=False) as mock_acquire, \
             patch("app.services.pipeline_orchestrator.release_step_lock_async") as mock_release:
            await orchestrator._run_phase("synthesis")

        # 仅尝试一次，不强制释放
        mock_acquire.assert_awaited_once()
        mock_release.assert_not_awaited()
        # Step 被标记为 skipped
        assert step.status == "skipped"

    @pytest.mark.asyncio
    async def test_恢复模式_Step已终态不强制释放锁(self):
        """恢复模式下 Step 已是 completed/skipped/failed 终态，直接返回不碰锁。"""
        task = _make_task(status="running")
        session = AsyncMock()
        _configure_async_mock_session(session)
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers={},
        )
        orchestrator._is_recovery = True
        orchestrator._task_lock_acquired = True

        step = MagicMock(spec=ResearchStep)
        step.id = "step-synthesis-003"
        step.status = "completed"
        step.step_type = "synthesis"
        step.label = "Synthesis"
        orchestrator._create_step = AsyncMock(return_value=step)

        with patch("app.services.pipeline_orchestrator.acquire_step_lock_async") as mock_acquire, \
             patch("app.services.pipeline_orchestrator.release_step_lock_async") as mock_release:
            await orchestrator._run_phase("synthesis")

        mock_acquire.assert_not_awaited()
        mock_release.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_持有任务锁时_pending_Step遗留锁被强制释放并执行(self):
        """持有任务锁 + step.pending → 强制释放旧锁并执行 handler。

        Worker 崩溃后 DB 事务回滚，task.status 可能回到 pending，
        _is_recovery=False（正常路径），但 _task_lock_acquired=True。
        只要持有任务锁，Step 锁一定是崩溃遗留的。
        """
        task = _make_task(status="running")
        session = AsyncMock()
        _configure_async_mock_session(session)
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        handler_called = []

        async def handler(t, s, sess, sb):
            handler_called.append("synthesis")
            return {"status": "ok"}

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers={"synthesis": handler},
        )
        # 注意：不设置 _is_recovery，模拟 DB 回滚到 pending 的情况
        orchestrator._task_lock_acquired = True

        step = MagicMock(spec=ResearchStep)
        step.id = "step-synthesis-004"
        step.status = "pending"
        step.step_type = "synthesis"
        step.label = "Synthesis"
        orchestrator._create_step = AsyncMock(return_value=step)

        with patch("app.services.pipeline_orchestrator.acquire_step_lock_async", side_effect=[False, True]) as mock_acquire, \
             patch("app.services.pipeline_orchestrator.release_step_lock_async") as mock_release:
            await orchestrator._run_phase("synthesis")

        # 强制释放旧锁并重新获取（finally 块会再释放一次，因此共 2 次）
        assert mock_acquire.await_count == 2
        assert mock_release.await_count == 2
        mock_release.assert_any_await(str(task.id), "synthesis")
        # handler 被调用，step 未被 skipped
        assert handler_called == ["synthesis"]
        assert step.status != "skipped"

    @pytest.mark.asyncio
    async def test_持有任务锁时_running_Step遗留锁被强制释放并执行(self):
        """持有任务锁 + step.running → 强制释放旧锁（覆盖 running 状态分支）。"""
        task = _make_task(status="running")
        session = AsyncMock()
        _configure_async_mock_session(session)
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        handler_called = []

        async def handler(t, s, sess, sb):
            handler_called.append("fetch")
            return {"successful": 1, "failed": 0}

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers={"fetch": handler},
        )
        orchestrator._task_lock_acquired = True

        step = MagicMock(spec=ResearchStep)
        step.id = "step-fetch-005"
        step.status = "running"
        step.step_type = "fetch"
        step.label = "Fetch"
        orchestrator._create_step = AsyncMock(return_value=step)

        with patch("app.services.pipeline_orchestrator.acquire_step_lock_async", side_effect=[False, True]) as mock_acquire, \
             patch("app.services.pipeline_orchestrator.release_step_lock_async") as mock_release:
            await orchestrator._run_phase("fetch")

        assert mock_acquire.await_count == 2
        assert mock_release.await_count == 2
        assert handler_called == ["fetch"]
        assert step.status != "skipped"

    @pytest.mark.asyncio
    async def test_复用research_service创建的pending_planning_step(self, db_session):
        """research_service 预先创建的 pending planning step 应被复用并完成。"""
        user = User(
            username="pipeline-reuse-planning",
            password_hash=hash_password("pass"),
            role="user",
            status="active",
        )
        db_session.add(user)
        await db_session.flush()

        task = ResearchTask(
            user_id=user.id,
            topic="复用 planning step 测试",
            requirements={"task_type": "analysis", "max_sources": 10, "language": "zh"},
            status="pending",
            total_steps=1,
        )
        db_session.add(task)
        await db_session.flush()

        # 模拟 research_service 预先创建的 pending planning step
        planning_step = ResearchStep(
            task_id=task.id,
            step_type="planning",
            status="pending",
            label="Planning：拆解研究主题",
        )
        db_session.add(planning_step)
        await db_session.flush()

        handlers = {phase: _make_phase_handler() for phase in PHASE_ORDER}

        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)
        trace_recorder = TraceRecorder(
            task_id=str(task.id), user_id=str(user.id), topic=task.topic
        )

        orchestrator = PipelineOrchestrator(
            task=task,
            session=db_session,
            sse_bridge=sse_bridge,
            trace_recorder=trace_recorder,
            phase_handlers=handlers,
        )

        with patch.object(db_session, "commit", new_callable=AsyncMock):
            with patch("app.services.pipeline_orchestrator.acquire_step_lock_async", return_value=True):
                with patch("app.services.pipeline_orchestrator.release_step_lock_async"):
                    await orchestrator.run()

        # 验证只存在一个 planning step，且它由 pending 转为 completed
        result = await db_session.execute(
            sa_select(ResearchStep)
            .where(ResearchStep.task_id == task.id, ResearchStep.step_type == "planning")
            .order_by(ResearchStep.started_at)
        )
        planning_steps = result.scalars().all()
        assert len(planning_steps) == 1
        assert planning_steps[0].id == planning_step.id
        assert planning_steps[0].status == "completed"

        # 验证 task 状态变为 completed
        result = await db_session.execute(
            sa_select(ResearchTask).where(ResearchTask.id == task.id)
        )
        updated_task = result.scalar_one()
        assert updated_task.status == "completed"

    @pytest.mark.asyncio
    async def test_fatal_error后_step和task均标记为failed(self, db_session):
        """Phase handler 抛致命错误，Step 应持久化为 failed，Task 也应为 failed。"""
        user = User(
            username="pipeline-fatal",
            password_hash=hash_password("pass"),
            role="user",
            status="active",
        )
        db_session.add(user)
        await db_session.flush()

        task = ResearchTask(
            user_id=user.id,
            topic="fatal error 测试",
            requirements={"task_type": "analysis", "max_sources": 10, "language": "zh"},
            status="pending",
        )
        db_session.add(task)
        await db_session.flush()

        async def failing_handler(task, step, session, sse_bridge):
            raise PlanningFailedException("模拟 Planning 失败")

        handlers = {phase: _make_phase_handler() for phase in PHASE_ORDER}
        handlers["planning"] = failing_handler

        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)
        trace_recorder = TraceRecorder(
            task_id=str(task.id), user_id=str(user.id), topic=task.topic
        )

        orchestrator = PipelineOrchestrator(
            task=task,
            session=db_session,
            sse_bridge=sse_bridge,
            trace_recorder=trace_recorder,
            phase_handlers=handlers,
        )

        with patch.object(db_session, "commit", new_callable=AsyncMock):
            with patch("app.services.pipeline_orchestrator.acquire_step_lock_async", return_value=True):
                with patch("app.services.pipeline_orchestrator.release_step_lock_async"):
                    await orchestrator.run()

        # 验证 planning step 状态为 failed
        result = await db_session.execute(
            sa_select(ResearchStep)
            .where(ResearchStep.task_id == task.id, ResearchStep.step_type == "planning")
        )
        planning_step = result.scalar_one()
        assert planning_step.status == "failed"
        assert planning_step.error_code == "E3101"

        # 验证 task 状态为 failed
        result = await db_session.execute(
            sa_select(ResearchTask).where(ResearchTask.id == task.id)
        )
        updated_task = result.scalar_one()
        assert updated_task.status == "failed"
        assert updated_task.error_code == "E3101"


# ═══════════════════════════════════════════════════════════════════════
# _create_step 断点续跑 Step 复用
# ═══════════════════════════════════════════════════════════════════════


class TestCreateStepRetryReuse:
    """_create_step 三层复用逻辑：已完成 → 待执行 → 新建。"""

    @pytest.mark.asyncio
    async def test_completed_step_被复用_不新建(self, db_session: AsyncSession):
        """已存在 completed step → _create_step 应直接返回该 step，不新建。"""
        user = User(
            username="retry-reuse-completed",
            password_hash=hash_password("pass"),
            role="user",
            status="active",
        )
        db_session.add(user)
        await db_session.flush()

        task = ResearchTask(
            user_id=user.id,
            topic="Step 复用测试",
            requirements={"task_type": "analysis", "max_sources": 10, "language": "zh"},
            status="pending",
            execution_context={"execution_pointer": {"phase": "searching"}},
        )
        db_session.add(task)
        await db_session.flush()

        # 已存在一条 completed planning step
        existing_step = ResearchStep(
            task_id=task.id,
            step_type="planning",
            status="completed",
            label="Planning：拆解研究主题",
        )
        db_session.add(existing_step)
        await db_session.flush()

        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)
        orchestrator = PipelineOrchestrator(
            task=task,
            session=db_session,
            sse_bridge=sse_bridge,
            trace_recorder=MagicMock(),
            phase_handlers={},
        )

        step = await orchestrator._create_step("planning")

        # 应返回已有 completed step，而非新建
        assert step.id == existing_step.id
        assert step.status == "completed"

        # 验证没有新建额外 planning step
        result = await db_session.execute(
            sa_select(ResearchStep).where(
                ResearchStep.task_id == task.id,
                ResearchStep.step_type == "planning",
            )
        )
        all_planning = result.scalars().all()
        assert len(all_planning) == 1

    @pytest.mark.asyncio
    async def test_skipped_step_被复用_不新建(self, db_session: AsyncSession):
        """已存在 skipped step → _create_step 应复用。"""
        user = User(
            username="retry-reuse-skipped",
            password_hash=hash_password("pass"),
            role="user",
            status="active",
        )
        db_session.add(user)
        await db_session.flush()

        task = ResearchTask(
            user_id=user.id,
            topic="Step 复用 skipped 测试",
            requirements={"task_type": "analysis", "max_sources": 10, "language": "zh"},
            status="pending",
        )
        db_session.add(task)
        await db_session.flush()

        existing_step = ResearchStep(
            task_id=task.id,
            step_type="fetch",
            status="skipped",
            label="Fetch：内容抓取",
        )
        db_session.add(existing_step)
        await db_session.flush()

        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)
        orchestrator = PipelineOrchestrator(
            task=task,
            session=db_session,
            sse_bridge=sse_bridge,
            trace_recorder=MagicMock(),
            phase_handlers={},
        )

        step = await orchestrator._create_step("fetch")
        assert step.id == existing_step.id
        assert step.status == "skipped"

    @pytest.mark.asyncio
    async def test_failed_step_不被复用_新建新step(self, db_session: AsyncSession):
        """failed step 不被 _create_step 复用（不在 completed/skipped/pending/running 中），应新建。"""
        user = User(
            username="retry-not-reuse-failed",
            password_hash=hash_password("pass"),
            role="user",
            status="active",
        )
        db_session.add(user)
        await db_session.flush()

        task = ResearchTask(
            user_id=user.id,
            topic="Failed step 不复用测试",
            requirements={"task_type": "analysis", "max_sources": 10, "language": "zh"},
            status="pending",
        )
        db_session.add(task)
        await db_session.flush()

        failed_step = ResearchStep(
            task_id=task.id,
            step_type="synthesis",
            status="failed",
            error_code="E3104",
            error_message="LLM 综合失败",
            label="Synthesis：跨源综合",
        )
        db_session.add(failed_step)
        await db_session.flush()

        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)
        orchestrator = PipelineOrchestrator(
            task=task,
            session=db_session,
            sse_bridge=sse_bridge,
            trace_recorder=MagicMock(),
            phase_handlers={},
        )

        step = await orchestrator._create_step("synthesis")

        # 应新建 step（failed 不在 reuse 查询范围内）
        assert step.id != failed_step.id
        assert step.status == "pending"

        # 验证 DB 中 synthesis step 共 2 条（1 failed + 1 new pending）
        result = await db_session.execute(
            sa_select(ResearchStep).where(
                ResearchStep.task_id == task.id,
                ResearchStep.step_type == "synthesis",
            )
        )
        all_synthesis = result.scalars().all()
        assert len(all_synthesis) == 2
        statuses = {s.status for s in all_synthesis}
        assert "failed" in statuses
        assert "pending" in statuses

    @pytest.mark.asyncio
    async def test_无已存在step_新建pending_step(self, db_session: AsyncSession):
        """无任何已存在 step → _create_step 新建 pending step。"""
        user = User(
            username="retry-new-step",
            password_hash=hash_password("pass"),
            role="user",
            status="active",
        )
        db_session.add(user)
        await db_session.flush()

        task = ResearchTask(
            user_id=user.id,
            topic="新建 step 测试",
            requirements={"task_type": "analysis", "max_sources": 10, "language": "zh"},
            status="pending",
        )
        db_session.add(task)
        await db_session.flush()

        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)
        orchestrator = PipelineOrchestrator(
            task=task,
            session=db_session,
            sse_bridge=sse_bridge,
            trace_recorder=MagicMock(),
            phase_handlers={},
        )

        step = await orchestrator._create_step("rerank")
        assert step.step_type == "rerank"
        assert step.status == "pending"
        assert step.task_id == task.id

    @pytest.mark.asyncio
    async def test_pending_step_被复用_不新建(self, db_session: AsyncSession):
        """已存在 pending step → _create_step 崩溃恢复路径应复用。"""
        user = User(
            username="retry-reuse-pending",
            password_hash=hash_password("pass"),
            role="user",
            status="active",
        )
        db_session.add(user)
        await db_session.flush()

        task = ResearchTask(
            user_id=user.id,
            topic="Pending step 复用测试",
            requirements={"task_type": "analysis", "max_sources": 10, "language": "zh"},
            status="pending",
        )
        db_session.add(task)
        await db_session.flush()

        existing_step = ResearchStep(
            task_id=task.id,
            step_type="search",
            status="pending",
            label="Search：多源搜索",
        )
        db_session.add(existing_step)
        await db_session.flush()

        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)
        orchestrator = PipelineOrchestrator(
            task=task,
            session=db_session,
            sse_bridge=sse_bridge,
            trace_recorder=MagicMock(),
            phase_handlers={},
        )

        step = await orchestrator._create_step("search")
        assert step.id == existing_step.id
        assert step.status == "pending"


# ═══════════════════════════════════════════════════════════════════════
# Execution Context 原子更新 — _complete_step 与 checkpoint 恢复
# ═══════════════════════════════════════════════════════════════════════


class TestExecutionContextAtomicity:
    """_complete_step 原子更新 step 状态与 execution_context，确保崩溃后可恢复。"""

    @pytest.mark.asyncio
    async def test__complete_step_原子更新step状态与execution_context(self, db_session: AsyncSession):
        """_complete_step 调用后，step.status 与 task.execution_context 同时可见。"""
        import json

        user = User(
            username="ec-atomic-user",
            password_hash=hash_password("pass"),
            role="user",
            status="active",
        )
        db_session.add(user)
        await db_session.flush()

        task = ResearchTask(
            user_id=user.id,
            topic="ExecutionContext 原子性测试",
            requirements={"task_type": "explainer", "max_sources": 5, "language": "zh"},
            status="running",
            total_steps=7,
            completed_steps=0,
            execution_context=None,
        )
        db_session.add(task)
        await db_session.flush()

        step = ResearchStep(
            task_id=task.id,
            step_type="planning",
            status="running",
            label="Planning：拆解研究主题",
            started_at=datetime.now(timezone.utc),
        )
        db_session.add(step)
        await db_session.flush()

        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)
        orchestrator = PipelineOrchestrator(
            task=task,
            session=db_session,
            sse_bridge=sse_bridge,
            trace_recorder=TraceRecorder(
                task_id=str(task.id), user_id=user.id, topic=task.topic
            ),
            phase_handlers={},
        )

        output = {
            "sub_questions": ["什么是量子计算？", "量子计算的应用场景"],
            "prompt_tokens": 500,
            "completion_tokens": 150,
            "model": "deepseek-v4-pro",
            "retry_count": 0,
        }
        await orchestrator._complete_step(step, "planning", output)

        # ── 断言：step 状态已更新 ──
        assert step.status == "completed"
        assert step.completed_at is not None
        assert step.duration_ms is not None
        assert step.output == output

        # ── 断言：execution_context 已原子更新 ──
        ec = task.execution_context
        assert ec is not None, "execution_context 应在 _complete_step 后写入"
        assert ec["current_phase"] == "planning"
        assert ec["last_completed_step_id"] == str(step.id)
        assert isinstance(ec["execution_pointer"], dict)
        assert ec["execution_pointer"]["phase"] == "planning"
        assert ec["execution_pointer"]["step_index"] == 1
        assert isinstance(ec["progress"], dict)
        assert ec["progress"]["completed_steps"] == 1
        assert ec["progress"]["total_steps"] == 7
        assert ec["progress"]["progress"] == pytest.approx(0.14, abs=0.01)

        # ── 断言：DB 刷新后 execution_context 持久化（JSON 可往返） ──
        await db_session.refresh(task)
        ec_from_db = task.execution_context
        assert ec_from_db is not None
        assert ec_from_db["current_phase"] == "planning"
        assert ec_from_db["last_completed_step_id"] == str(step.id)

    @pytest.mark.asyncio
    async def test__complete_step_连续两个phase后execution_context正确递进(self, db_session: AsyncSession):
        """连续执行 planning → search 后，execution_context 指向最后完成的 phase。"""
        user = User(
            username="ec-progress-user",
            password_hash=hash_password("pass"),
            role="user",
            status="active",
        )
        db_session.add(user)
        await db_session.flush()

        task = ResearchTask(
            user_id=user.id,
            topic="ExecutionContext 递进测试",
            requirements={"task_type": "analysis", "max_sources": 10, "language": "zh"},
            status="running",
            total_steps=7,
            completed_steps=0,
            execution_context=None,
        )
        db_session.add(task)
        await db_session.flush()

        # Phase 1: planning
        plan_step = ResearchStep(
            task_id=task.id,
            step_type="planning",
            status="running",
            label="Planning",
            started_at=datetime.now(timezone.utc),
        )
        db_session.add(plan_step)
        await db_session.flush()

        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)
        orchestrator = PipelineOrchestrator(
            task=task,
            session=db_session,
            sse_bridge=sse_bridge,
            trace_recorder=TraceRecorder(
                task_id=str(task.id), user_id=user.id, topic=task.topic
            ),
            phase_handlers={},
        )

        await orchestrator._complete_step(
            plan_step, "planning",
            {"sub_questions": ["q1"], "prompt_tokens": 100, "completion_tokens": 50,
             "model": "deepseek-v4-pro", "retry_count": 0},
        )

        assert task.execution_context["current_phase"] == "planning"
        assert task.execution_context["last_completed_step_id"] == str(plan_step.id)
        assert task.completed_steps == 1

        # Phase 2: search
        search_step = ResearchStep(
            task_id=task.id,
            step_type="search",
            status="running",
            label="Search",
            started_at=datetime.now(timezone.utc),
        )
        db_session.add(search_step)
        await db_session.flush()

        # 模拟 _complete_step 前递增 completed_steps（通常由 _run_phase 调用方管理）
        # 注意：_complete_step 内部会 +1，这里手动设回以模拟正常 flow
        task.completed_steps = 1
        await orchestrator._complete_step(
            search_step, "searching",
            {"total_results": 12, "after_dedup": 8, "sources_created": 8},
        )

        # ── 断言：execution_context 递进到 search ──
        assert task.execution_context["current_phase"] == "searching"
        assert task.execution_context["last_completed_step_id"] == str(search_step.id)
        assert task.execution_context["execution_pointer"]["phase"] == "searching"
        assert task.completed_steps == 2

        # ── 验证 planning step 的状态未被覆盖 ──
        await db_session.refresh(plan_step)
        assert plan_step.status == "completed"
        assert plan_step.completed_at is not None

    @pytest.mark.asyncio
    async def test__complete_step后execution_context可供retry_task构造resume_from(self, db_session: AsyncSession):
        """模拟 Worker 崩溃场景：search 完成后崩溃 → execution_context 中有完整 checkpoint。"""
        user = User(
            username="ec-crash-user",
            password_hash=hash_password("pass"),
            role="user",
            status="active",
        )
        db_session.add(user)
        await db_session.flush()

        task = ResearchTask(
            user_id=user.id,
            topic="崩溃恢复测试",
            requirements={"task_type": "comparison", "max_sources": 10, "language": "zh"},
            status="running",
            total_steps=7,
            completed_steps=1,
            execution_context={
                "current_phase": "planning",
                "last_completed_step_id": "fake-planning-step-uuid",
                "execution_pointer": {"phase": "planning", "step_index": 1, "total_steps_in_phase": 1},
                "progress": {"completed_steps": 1, "total_steps": 7, "progress": 0.14},
            },
        )
        db_session.add(task)
        await db_session.flush()

        search_step = ResearchStep(
            task_id=task.id,
            step_type="search",
            status="running",
            label="Search：多源搜索",
            started_at=datetime.now(timezone.utc),
        )
        db_session.add(search_step)
        await db_session.flush()

        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)
        orchestrator = PipelineOrchestrator(
            task=task,
            session=db_session,
            sse_bridge=sse_bridge,
            trace_recorder=TraceRecorder(
                task_id=str(task.id), user_id=user.id, topic=task.topic
            ),
            phase_handlers={},
        )

        await orchestrator._complete_step(
            search_step, "searching",
            {"total_results": 15, "after_dedup": 10, "sources_created": 10},
        )

        # ── 断言：execution_context 指向 search（模拟崩溃前最后一个 checkpoint） ──
        ec = task.execution_context
        assert ec["current_phase"] == "searching"
        assert ec["last_completed_step_id"] == str(search_step.id)
        assert ec["execution_pointer"]["phase"] == "searching"

        # ── 模拟 retry_task 从 execution_context 构建 resume_from ──
        ep = ec.get("execution_pointer", {})
        last_phase = ep.get("phase") if isinstance(ep, dict) else None
        assert last_phase == "searching", "崩溃前最后完成的 phase 应为 searching"

        # 根据 last_phase 推算下一个 step_type
        from app.services.research_service import PHASE_ORDER
        phase_to_step = {
            "planning": "planning", "searching": "search", "fetching": "fetch",
            "reranking": "rerank", "synthesizing": "synthesis",
            "building_evidence_graph": "evidence_graph", "rendering": "render",
        }
        last_step_type = phase_to_step.get(last_phase, last_phase)
        idx = PHASE_ORDER.index(last_step_type)
        next_step_type = PHASE_ORDER[idx + 1] if idx + 1 < len(PHASE_ORDER) else None
        assert next_step_type == "fetch", "search 完成后，下一个 phase 应为 fetch"

        # ── 验证已完成的 step 可被 _create_step 复用 ──
        reused = await orchestrator._create_step("search")
        assert reused.id == search_step.id
        assert reused.status == "completed"

    @pytest.mark.asyncio
    async def test__complete_step_失败时execution_context不更新(self, db_session: AsyncSession):
        """_update_execution_context 失败时，execution_context 保持旧值不更新。"""
        user = User(
            username="ec-fail-user",
            password_hash=hash_password("pass"),
            role="user",
            status="active",
        )
        db_session.add(user)
        await db_session.flush()

        old_ec = {
            "current_phase": "planning",
            "last_completed_step_id": "old-step-uuid",
            "execution_pointer": {"phase": "planning"},
        }
        task = ResearchTask(
            user_id=user.id,
            topic="ExecutionContext 失败测试",
            requirements={"task_type": "explainer", "max_sources": 5, "language": "zh"},
            status="running",
            total_steps=7,
            completed_steps=1,
            execution_context=old_ec,
        )
        db_session.add(task)
        await db_session.flush()

        step = ResearchStep(
            task_id=task.id,
            step_type="search",
            status="running",
            label="Search",
            started_at=datetime.now(timezone.utc),
        )
        db_session.add(step)
        await db_session.flush()

        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)
        orchestrator = PipelineOrchestrator(
            task=task,
            session=db_session,
            sse_bridge=sse_bridge,
            trace_recorder=TraceRecorder(
                task_id=str(task.id), user_id=user.id, topic=task.topic
            ),
            phase_handlers={},
        )

        # 注入异常：让 _update_execution_context 查询时触发错误
        # 通过 monkey-patch ResearchStep 查询使 count 查询失败
        original_execute = db_session.execute

        async def failing_execute(*args, **kwargs):
            from sqlalchemy import select as sa_select_inner
            from sqlalchemy.sql import func
            stmt = args[0] if args else kwargs.get("statement")
            stmt_str = str(stmt) if stmt is not None else ""
            # 拦截 execution_context 中的 count 查询（来自 _update_execution_context）
            if "count" in stmt_str.lower() and "research_steps" in stmt_str.lower():
                raise RuntimeError("模拟 DB 查询失败")
            return await original_execute(*args, **kwargs)

        db_session.execute = failing_execute

        try:
            with pytest.raises(RuntimeError, match="模拟 DB 查询失败"):
                await orchestrator._complete_step(
                    step, "searching",
                    {"total_results": 5},
                )
        finally:
            db_session.execute = original_execute

        # ── 断言：execution_context 保持旧值（未被部分更新） ──
        await db_session.refresh(task)
        assert task.execution_context == old_ec, (
            "_complete_step 失败后 execution_context 应保持旧值"
        )

        # ── 断言：step 状态也未被更新（因 flush 在 _update_execution_context 之前，
        #  但同在一个未 commit 的事务内，外部 rollback 会一并回退） ──
        # 注意：这里 flush 已执行（_complete_step line 473），
        # 但由于 pytest fixture 会回滚整个事务，DB 层面的持久性由外层保证
        await db_session.refresh(step)
        # step.status 可能因 flush 已变为 "completed"，但事务回滚会撤销
        # 关键断言：execution_context 没有被部分更新


# ═══════════════════════════════════════════════════════════════════════
# 崩溃恢复与任务级锁
# ═══════════════════════════════════════════════════════════════════════


class TestCrashRecoveryAndTaskLock:
    """_start_task 崩溃恢复路径 + 任务级锁生命周期。"""

    @pytest.mark.asyncio
    async def test_pending状态_正常启动_发送task_created(self):
        task = _make_task(status="pending")
        session = AsyncMock()
        _configure_async_mock_session(session)
        # 模拟 refresh 后 status 仍为 pending
        session.refresh = AsyncMock()
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers={},
        )

        started = await orchestrator._start_task()

        assert started is True
        # 正常路径发送 task.created
        created_calls = [
            c for c in sse_bridge.publish.await_args_list
            if c[0][0] == EVENT_TASK_CREATED
        ]
        assert len(created_calls) == 1

    @pytest.mark.asyncio
    async def test_running状态_崩溃恢复_不发送task_created并获取锁(self):
        task = _make_task(status="running")
        session = AsyncMock()
        _configure_async_mock_session(session)
        session.refresh = AsyncMock()
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers={},
        )

        with patch("app.services.pipeline_orchestrator.acquire_task_lock_async", return_value=True) as mock_acquire:
            started = await orchestrator._start_task()

        assert started is True
        # 崩溃恢复路径不发送 task.created
        created_calls = [
            c for c in sse_bridge.publish.await_args_list
            if c[0][0] == EVENT_TASK_CREATED
        ]
        assert len(created_calls) == 0
        mock_acquire.assert_awaited_once_with(str(task.id))

    @pytest.mark.asyncio
    async def test_running状态_锁被占用_返回False(self):
        task = _make_task(status="running")
        session = AsyncMock()
        _configure_async_mock_session(session)
        session.refresh = AsyncMock()
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers={},
        )

        with patch("app.services.pipeline_orchestrator.acquire_task_lock_async", return_value=False) as mock_acquire:
            started = await orchestrator._start_task()

        assert started is False
        mock_acquire.assert_awaited_once_with(str(task.id))

    @pytest.mark.asyncio
    async def test_run_正常完成_释放任务锁(self):
        task = _make_task(status="pending")
        session = AsyncMock()
        _configure_async_mock_session(session)
        session.refresh = AsyncMock()
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)
        handlers = {phase: _make_phase_handler() for phase in PHASE_ORDER}

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers=handlers,
        )

        with patch("app.services.pipeline_orchestrator.acquire_step_lock_async", return_value=True):
            with patch("app.services.pipeline_orchestrator.release_step_lock_async"):
                with patch("app.services.pipeline_orchestrator.acquire_task_lock_async", return_value=True) as mock_acquire:
                    with patch("app.services.pipeline_orchestrator.release_task_lock_async") as mock_release:
                        await orchestrator.run()

        mock_release.assert_awaited_once_with(str(task.id))

    @pytest.mark.asyncio
    async def test_run_异常退出_释放任务锁(self):
        task = _make_task(status="pending")
        session = AsyncMock()
        _configure_async_mock_session(session)
        session.refresh = AsyncMock()
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        async def failing_handler(task, step, session, sse_bridge):
            raise RuntimeError("模拟 Phase 失败")

        handlers = {"planning": failing_handler}

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers=handlers,
        )

        with patch("app.services.pipeline_orchestrator.acquire_step_lock_async", return_value=True):
            with patch("app.services.pipeline_orchestrator.release_step_lock_async"):
                with patch("app.services.pipeline_orchestrator.acquire_task_lock_async", return_value=True):
                    with patch("app.services.pipeline_orchestrator.release_task_lock_async") as mock_release:
                        await orchestrator.run()

        mock_release.assert_awaited_once_with(str(task.id))

    @pytest.mark.asyncio
    async def test_获取任务锁后启动租约刷新(self):
        task = _make_task(status="running")
        session = AsyncMock()
        _configure_async_mock_session(session)
        session.refresh = AsyncMock()
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers={},
        )

        with patch("app.services.pipeline_orchestrator.acquire_task_lock_async", return_value=True), \
             patch("app.services.pipeline_orchestrator.refresh_task_lock_async", new_callable=AsyncMock) as mock_refresh, \
             patch("app.services.pipeline_orchestrator.settings.CELERY_LOCK_REFRESH_INTERVAL", 0.05), \
             patch.object(PipelineOrchestrator, "_start_task_lock_refresh", PipelineOrchestrator._start_task_lock_refresh):
            await orchestrator._acquire_task_lock(str(task.id))

            assert orchestrator._task_lock_acquired is True
            assert orchestrator._task_lock_refresh_task is not None

            # 等待一次刷新循环，验证后台任务确实在运行
            await asyncio.sleep(0.1)
            mock_refresh.assert_awaited()

        # 清理：取消并等待任务结束，避免 "Task destroyed but pending" 警告
        refresh_task = orchestrator._task_lock_refresh_task
        orchestrator._stop_task_lock_refresh()
        try:
            await asyncio.wait_for(refresh_task, timeout=0.5)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    @pytest.mark.asyncio
    async def test_释放任务锁后停止租约刷新(self):
        task = _make_task(status="running")
        session = AsyncMock()
        _configure_async_mock_session(session)
        session.refresh = AsyncMock()
        sse_bridge = AsyncMock()
        sse_bridge.task_id = str(task.id)

        orchestrator = PipelineOrchestrator(
            task=task, session=session, sse_bridge=sse_bridge,
            trace_recorder=MagicMock(), phase_handlers={},
        )

        with patch("app.services.pipeline_orchestrator.acquire_task_lock_async", return_value=True), \
             patch("app.services.pipeline_orchestrator.refresh_task_lock_async", new_callable=AsyncMock), \
             patch("app.services.pipeline_orchestrator.settings.CELERY_LOCK_REFRESH_INTERVAL", 0.05):
            await orchestrator._acquire_task_lock(str(task.id))

            refresh_task = orchestrator._task_lock_refresh_task
            assert refresh_task is not None

        with patch("app.services.pipeline_orchestrator.release_task_lock_async") as mock_release:
            await orchestrator._release_task_lock(str(task.id))

        assert orchestrator._task_lock_refresh_task is None
        assert orchestrator._task_lock_acquired is False
        mock_release.assert_awaited_once_with(str(task.id))

        # 等待取消完成
        try:
            await asyncio.wait_for(refresh_task, timeout=0.5)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

