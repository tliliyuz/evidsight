"""AgentRuntime 单元测试。"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.context import AgentContext
from app.agent.memory import WorkingMemory
from app.agent.runtime import AgentRuntime
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
