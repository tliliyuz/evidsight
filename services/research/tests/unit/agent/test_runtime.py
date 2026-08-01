"""AgentRuntime 单元测试。"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.context import AgentContext
from app.agent.memory import WorkingMemory
from app.agent.runtime import AgentRuntime
from app.core.llm import LLMResult, ToolCall as LLMToolCall
from app.core.trace_recorder import TraceRecorder
from app.models.research_task import ResearchTask
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


@pytest.fixture
def runtime():
    task = ResearchTask(
        id="runtime-test-task",
        user_id=1,
        topic="test",
        status="running",
    )
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

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


class TestRunCancel:
    """run() 取消中断行为测试。"""

    def _prepare_run(self, runtime, monkeypatch):
        """公共打桩：任务启动、记忆服务、任务锁、最终化。"""
        monkeypatch.setattr(
            "app.agent.runtime.start_research_task", AsyncMock(return_value=True)
        )
        monkeypatch.setattr(
            "app.agent.runtime.agent_memory_service.build_working_memory",
            AsyncMock(return_value=WorkingMemory()),
        )
        monkeypatch.setattr(
            "app.agent.runtime.agent_memory_service.persist_pending_entries",
            AsyncMock(),
        )
        runtime._lock_handle = AsyncMock()
        runtime._finalize_task = AsyncMock()
        runtime._task.execution_context = None

    @pytest.mark.asyncio
    async def test_运行中被取消_跳过最终化且不再调用LLM(self, runtime, monkeypatch):
        self._prepare_run(runtime, monkeypatch)
        chat_mock = AsyncMock()
        monkeypatch.setattr("app.agent.loop.chat_completion", chat_mock)

        async def refresh_to_canceled(obj, attrs):
            obj.status = "canceled"

        runtime._session.refresh = AsyncMock(side_effect=refresh_to_canceled)

        await runtime.run()

        assert runtime._task.status == "canceled"
        assert runtime._agent_context.finish_reason == "canceled"
        runtime._finalize_task.assert_not_awaited()
        chat_mock.assert_not_awaited()
        runtime._lock_handle.release.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_未取消_正常进入最终化(self, runtime, monkeypatch):
        self._prepare_run(runtime, monkeypatch)

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
        runtime._lock_handle.release.assert_awaited_once()
