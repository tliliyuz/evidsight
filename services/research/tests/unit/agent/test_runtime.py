"""AgentRuntime 单元测试。"""

from contextlib import nullcontext
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.agent.context import AgentContext
from app.agent.exceptions import AgentLoopExhaustedError
from app.agent.memory import WorkingMemory
from app.agent.runtime import AgentRuntime
from app.core.exceptions import LLMAuthFailedException, LLMUnknownException
from app.core.llm import LLMResult
from app.core.llm import ToolCall as LLMToolCall
from app.core.trace_recorder import TraceRecorder
from app.models.research_task import ResearchTask
from app.pipeline.sse_bridge import EVENT_TASK_FAILED
from app.tools.base import Tool, ToolCall, ToolContext
from app.tools.registry import ToolRegistry


class FailingTool(Tool):
    """用于测试执行失败的 Tool。"""

    name = "failing_tool"
    description = "总是失败的 tool"
    mapped_phase = "planning"
    parameters_schema = {"type": "object", "properties": {}}

    async def execute(self, ctx: ToolContext, **params):
        raise RuntimeError("内部原始异常：包含敏感堆栈/JSON 细节")


class FailClosedTool(Tool):
    """抛出 fail-closed 异常的 Tool（E3115 KB forbidden / E1010 用户禁用 / E3117 契约错误）。"""

    name = "fail_closed_tool"
    description = "总是 fail-closed 失败的 tool"
    mapped_phase = "search"
    parameters_schema = {"type": "object", "properties": {}}

    async def execute(self, ctx: ToolContext, **params):
        from app.core.exceptions import InternalKnowledgeForbiddenException

        raise InternalKnowledgeForbiddenException("KB 不可读，fail-closed")


@pytest.fixture
def runtime(monkeypatch):
    task = ResearchTask(
        id="runtime-test-task",
        user_id=1,
        topic="test",
        status="running",
    )
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    # 本组用例不验证 agent_events（切片 F）：mock recorder，避免 mock session 走真实 DB 逻辑
    monkeypatch.setattr(
        "app.agent.runtime.AgentEventRecorder",
        lambda *a, **k: AsyncMock(),
    )

    sse = AsyncMock()
    trace = TraceRecorder(task_id=task.id, user_id=task.user_id, topic=task.topic)
    registry = ToolRegistry()
    registry.register(FailingTool())

    runtime = AgentRuntime(
        task=task,
        session=session,
        sse_bridge=sse,
        trace_recorder=trace,
        tool_registry=registry,
    )
    runtime._agent_context = AgentContext(current_phase="planning")
    runtime._working_memory = WorkingMemory()
    # 绑定租约（切片 E）：本组用例不验证租约门禁，默认放行提交
    runtime._lease_handle.worker_id = "worker-1"
    runtime._lease_handle.lease_generation = 1
    monkeypatch.setattr(
        "app.agent.runtime.is_step_commit_allowed",
        AsyncMock(return_value=True),
    )
    return runtime


class TestExecuteTool:
    """_execute_tool 行为测试。"""

    @pytest.mark.asyncio
    async def test_tool执行失败_observation不暴露原始异常(self, runtime):
        tool = FailingTool()
        tool_call = ToolCall(id="1", name="failing_tool", arguments={})

        exec_result = await runtime._execute_tool(tool, tool_call)

        assert exec_result.result.success is False
        assert "内部原始异常" not in exec_result.result.observation
        assert "阶段执行失败" in exec_result.result.observation
        # error_message 仍保留原始信息供服务端日志/排查
        assert "内部原始异常" in exec_result.result.error_message


class TestExecuteToolFailClosed:
    """fail-closed 异常（E3115/E1010/E3117）必须立即中断，不得转 ToolResult 后继续循环。"""

    @pytest.mark.asyncio
    async def test_fail_closed异常_立即重抛不吞掉(self, runtime):
        tool = FailClosedTool()
        tool_call = ToolCall(id="1", name="fail_closed_tool", arguments={})
        runtime._session.refresh = AsyncMock()

        with pytest.raises(Exception) as excinfo:
            await runtime._execute_tool(tool, tool_call)

        assert getattr(excinfo.value, "error_code", None) == "E3115"

    @pytest.mark.asyncio
    async def test_fail_closed异常_不以successFalse继续循环(self, runtime):
        tool = FailClosedTool()
        tool_call = ToolCall(id="1", name="fail_closed_tool", arguments={})
        runtime._session.refresh = AsyncMock()

        with pytest.raises(Exception) as excinfo:
            await runtime._execute_tool(tool, tool_call)

        assert excinfo.value.__class__.__name__ == "InternalKnowledgeForbiddenException"


class TestRunCancel:
    """run() 取消中断行为测试。"""

    def _prepare_run(self, runtime, monkeypatch):
        """公共打桩：任务启动、记忆服务、任务锁、最终化。"""
        monkeypatch.setattr("app.agent.runtime.start_research_task", AsyncMock(return_value=True))
        monkeypatch.setattr(
            "app.agent.runtime.agent_memory_service.build_working_memory",
            AsyncMock(return_value=WorkingMemory()),
        )
        monkeypatch.setattr(
            "app.agent.runtime.agent_memory_service.persist_pending_entries",
            AsyncMock(),
        )
        runtime._lease_handle = AsyncMock()
        runtime._lease_handle.lease_lost = False
        runtime._finalize_task = AsyncMock()
        runtime._task.execution_context = None

    @pytest.mark.asyncio
    async def test_取消请求_停止循环并进入最终化(self, runtime, monkeypatch):
        self._prepare_run(runtime, monkeypatch)
        chat_mock = AsyncMock()
        monkeypatch.setattr("app.agent.loop.chat_completion", chat_mock)

        async def refresh_to_cancel(obj, attrs):
            obj.cancel_requested_at = datetime.now(timezone.utc)

        runtime._session.refresh = AsyncMock(side_effect=refresh_to_cancel)

        await runtime.run()

        assert runtime._task.cancel_requested_at is not None
        assert runtime._agent_context.finish_reason == "canceled"
        chat_mock.assert_not_awaited()
        # 取消只写 cancel_requested_at，安全停止后进入最终化，由 Resolver 推导终态
        runtime._finalize_task.assert_awaited_once()
        runtime._lease_handle.release.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_未取消_正常进入最终化(self, runtime, monkeypatch):
        self._prepare_run(runtime, monkeypatch)
        session_context = MagicMock(side_effect=lambda task_id: nullcontext())
        monkeypatch.setattr("app.agent.runtime.llm_session", session_context)

        async def fake_chat(*args, **kwargs):
            return LLMResult(
                content="",
                reasoning_content="",
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
                tool_calls=[LLMToolCall(id="1", name="finish_tool", arguments={})],
            )

        monkeypatch.setattr("app.agent.loop.chat_completion", fake_chat)
        # refresh 不修改状态，任务保持 running
        runtime._session.refresh = AsyncMock()

        await runtime.run()

        assert runtime._task.status == "running"
        assert runtime._agent_context.finish_reason == "finished_by_llm"
        runtime._finalize_task.assert_awaited_once()
        runtime._lease_handle.release.assert_awaited_once()
        session_context.assert_called_once_with("runtime-test-task")

    @pytest.mark.asyncio
    async def test_AgentLoop迭代耗尽_按预算停止并最终化(self, runtime, monkeypatch):
        self._prepare_run(runtime, monkeypatch)

        async def exhausted_loop(*args, **kwargs):
            raise AgentLoopExhaustedError(30)

        monkeypatch.setattr("app.agent.runtime.AgentLoop.run", exhausted_loop)
        runtime._record_budget_stop = AsyncMock()

        await runtime.run()

        runtime._record_budget_stop.assert_awaited_once()
        assert runtime._task.budget_stopped_at is not None
        runtime._finalize_task.assert_awaited_once()
        runtime._lease_handle.release.assert_awaited_once()


class TestFatalErrorResolution:
    """结构化致命错误必须先形成 Step 事实，再由 Resolver 收口。"""

    @pytest.mark.asyncio
    async def test_LLM认证失败_经失败Step与Resolver收口(self, runtime):
        record_step = AsyncMock()
        finalize = AsyncMock()
        runtime._record_fatal_step = record_step
        runtime._finalize_task = finalize

        await runtime._handle_fatal_error(LLMAuthFailedException("API Key 无效"))

        record_step.assert_awaited_once_with("E3110", "LLM 认证失败")
        finalize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_LLM循环无进展_经失败Step与Resolver收口(self, runtime):
        record_step = AsyncMock()
        finalize = AsyncMock()
        runtime._record_fatal_step = record_step
        runtime._finalize_task = finalize

        await runtime._handle_fatal_error(
            LLMUnknownException(detail="planning 阶段 Tool 选择未推进")
        )

        record_step.assert_awaited_once_with("E3111", "LLM 调用返回未预期错误")
        finalize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_失败Resolver终态_发布完整task_failed事件(self, runtime, monkeypatch):
        step = MagicMock(
            step_type="planning",
            status="failed",
            error_code="E3110",
            error_message="LLM 认证失败",
        )
        monkeypatch.setattr("app.agent.runtime.load_task_steps", AsyncMock(return_value=[step]))
        runtime._assert_ownership = AsyncMock()
        runtime._load_published_completeness = AsyncMock(return_value=None)
        runtime._session.execute = AsyncMock(return_value=MagicMock(rowcount=1))
        runtime._session.commit = AsyncMock()

        await runtime._finalize_task()

        failed_event = next(
            call.args[1]
            for call in runtime._sse.publish.await_args_list
            if call.args[0] == EVENT_TASK_FAILED
        )
        assert failed_event["status"] == "failed"
        assert failed_event["error_code"] == "E3110"
        assert failed_event["completed_at"]
