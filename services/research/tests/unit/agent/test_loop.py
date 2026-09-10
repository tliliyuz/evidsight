"""AgentLoop 单元测试。"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.agent.context import AgentContext
from app.agent.exceptions import AgentLoopExhaustedError
from app.agent.loop import AgentLoop, ToolExecutionResult
from app.agent.memory import WorkingMemory
from app.agent.state import PhaseController
from app.core.exceptions import LLMAuthFailedException, LLMUnknownException
from app.core.llm import LLMResult, ToolCall
from app.pipeline.sse_bridge import (
    EVENT_AGENT_ACTION,
    EVENT_AGENT_OBSERVATION,
    SSEBridge,
)
from app.tools.base import Tool, ToolContext, ToolResult
from app.tools.memory_tool import MemoryTool
from app.tools.registry import ToolRegistry


class DummyTool(Tool):
    def __init__(self, name: str, mapped_phase: str | None):
        self.name = name
        self.description = f"tool {name}"
        self.parameters_schema = {"type": "object", "properties": {}}
        self.mapped_phase = mapped_phase

    async def execute(self, ctx, **params):
        return ToolResult(success=True, output={"ok": True}, observation=f"obs {self.name}")


@pytest.fixture
def setup():
    reg = ToolRegistry()
    reg.register(DummyTool("plan_tool", "planning"))
    reg.register(DummyTool("search_tool", "search"))
    reg.register(MemoryTool())
    ctx = AgentContext(current_phase="planning")
    memory = WorkingMemory()
    sse = MagicMock(spec=SSEBridge)
    sse.publish = AsyncMock()
    controller = PhaseController(ctx, reg)
    loop = AgentLoop(controller, memory, sse, max_iterations=10)
    tool_ctx = MagicMock(spec=ToolContext)
    tool_ctx.agent_context = ctx
    return loop, tool_ctx, sse, reg, ctx


def _make_llm_result(tool_calls=None, reasoning="", content=""):
    return LLMResult(
        content=content,
        reasoning_content=reasoning,
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        tool_calls=tool_calls,
    )


def _callback_factory(agent_ctx):
    async def callback(tool, tool_call):
        if tool.name == "finish_tool":
            agent_ctx.finished = True
            return ToolExecutionResult(
                result=ToolResult(success=True, output={}, observation="finished"),
                step_id=None,
            )
        return ToolExecutionResult(
            result=ToolResult(success=True, output={"ok": True}, observation=f"obs {tool.name}"),
            step_id="step-1",
        )

    return callback


class TestAgentLoop:
    async def test_辅助tool无进展_下一轮强制当前phase主工具(self, setup, monkeypatch):
        loop, tool_ctx, sse, reg, agent_ctx = setup
        responses = [
            _make_llm_result(
                tool_calls=[
                    ToolCall(id="memory-1", name="memory_tool", arguments={"operation": "read"})
                ]
            ),
            _make_llm_result(tool_calls=[ToolCall(id="plan-1", name="plan_tool", arguments={})]),
            _make_llm_result(
                tool_calls=[ToolCall(id="finish-1", name="finish_tool", arguments={})]
            ),
        ]
        choices = []

        async def fake_chat(*args, **kwargs):
            choices.append(kwargs["tool_choice"])
            return responses.pop(0)

        monkeypatch.setattr("app.agent.loop.chat_completion", fake_chat)

        await loop.run(tool_ctx, _callback_factory(agent_ctx))

        assert choices == [
            "auto",
            {"type": "function", "function": {"name": "plan_tool"}},
            "auto",
        ]
        assert agent_ctx.completed_phases == {"planning"}
        assert agent_ctx.finished is True

    async def test_未返回Tool调用_下一轮强制当前phase主工具(self, setup, monkeypatch):
        loop, tool_ctx, sse, reg, agent_ctx = setup
        responses = [
            _make_llm_result(content="暂时没有可执行动作"),
            _make_llm_result(tool_calls=[ToolCall(id="plan-1", name="plan_tool", arguments={})]),
            _make_llm_result(
                tool_calls=[ToolCall(id="finish-1", name="finish_tool", arguments={})]
            ),
        ]
        choices = []

        async def fake_chat(*args, **kwargs):
            choices.append(kwargs["tool_choice"])
            return responses.pop(0)

        monkeypatch.setattr("app.agent.loop.chat_completion", fake_chat)

        await loop.run(tool_ctx, _callback_factory(agent_ctx))

        assert choices == [
            "auto",
            {"type": "function", "function": {"name": "plan_tool"}},
            "auto",
        ]
        assert agent_ctx.completed_phases == {"planning"}
        assert agent_ctx.finished is True

    async def test_强制主工具仍无进展_抛出受控LLM错误(self, setup, monkeypatch):
        loop, tool_ctx, sse, reg, agent_ctx = setup
        responses = [
            _make_llm_result(
                tool_calls=[
                    ToolCall(id="memory-1", name="memory_tool", arguments={"operation": "read"})
                ]
            ),
            _make_llm_result(
                tool_calls=[
                    ToolCall(id="memory-2", name="memory_tool", arguments={"operation": "read"})
                ]
            ),
        ]

        async def fake_chat(*args, **kwargs):
            return responses.pop(0)

        monkeypatch.setattr("app.agent.loop.chat_completion", fake_chat)

        with pytest.raises(LLMUnknownException) as exc_info:
            await loop.run(tool_ctx, _callback_factory(agent_ctx))

        assert exc_info.value.error_code == "E3111"
        assert agent_ctx.iteration_count == 2

    async def test_LLM认证失败_立即中断不重复调用(self, setup, monkeypatch):
        loop, tool_ctx, sse, reg, agent_ctx = setup
        chat_mock = AsyncMock(side_effect=LLMAuthFailedException("API Key 无效"))
        monkeypatch.setattr("app.agent.loop.chat_completion", chat_mock)

        with pytest.raises(LLMAuthFailedException):
            await loop.run(tool_ctx, _callback_factory(agent_ctx))

        chat_mock.assert_awaited_once()
        assert agent_ctx.finished is False

    async def test_finish_tool_结束循环(self, setup, monkeypatch):
        loop, tool_ctx, sse, reg, agent_ctx = setup

        async def fake_chat(*args, **kwargs):
            return _make_llm_result(
                reasoning="完成",
                tool_calls=[ToolCall(id="1", name="finish_tool", arguments={})],
            )

        monkeypatch.setattr("app.agent.loop.chat_completion", fake_chat)

        await loop.run(tool_ctx, _callback_factory(agent_ctx))

        assert agent_ctx.finished is True
        # §16 / §17.3-22：模型隐藏推理不得进入 SSE 用户可见字段
        for call in sse.publish.await_args_list:
            assert call.args[0] != "agent.thought"
        sse.publish.assert_any_call(
            EVENT_AGENT_ACTION,
            {
                "iteration": 1,
                "phase": "planning",
                "tool_call_id": "1",
                "tool_name": "finish_tool",
                "arguments": {},
            },
        )
        sse.publish.assert_any_call(
            EVENT_AGENT_OBSERVATION,
            {
                "iteration": 1,
                "phase": "planning",
                "tool_call_id": "1",
                "tool_name": "finish_tool",
                "observation": "finished",
                "success": True,
            },
        )

    async def test_非法tool返回失败observation(self, setup, monkeypatch):
        loop, tool_ctx, sse, reg, agent_ctx = setup

        responses = [
            _make_llm_result(tool_calls=[ToolCall(id="1", name="render_tool", arguments={})]),
            _make_llm_result(tool_calls=[ToolCall(id="2", name="finish_tool", arguments={})]),
        ]
        iter_resp = iter(responses)

        async def fake_chat(*args, **kwargs):
            return next(iter_resp)

        monkeypatch.setattr("app.agent.loop.chat_completion", fake_chat)
        callback = AsyncMock()

        await loop.run(tool_ctx, _callback_factory(agent_ctx))

        # render_tool 不在 planning phase，callback 不应被非法 tool 调用
        for call in callback.await_args_list:
            assert call.args[0].name != "render_tool"
        obs_call = [c for c in sse.publish.await_args_list if c.args[0] == EVENT_AGENT_OBSERVATION]
        assert obs_call
        assert "不可用" in obs_call[0].args[1]["observation"]

    async def test_达到最大迭代次数抛出异常(self, setup, monkeypatch):
        loop, tool_ctx, sse, reg, agent_ctx = setup
        loop._max_iterations = 2

        async def fake_chat(*args, **kwargs):
            return _make_llm_result(tool_calls=[ToolCall(id="1", name="plan_tool", arguments={})])

        monkeypatch.setattr("app.agent.loop.chat_completion", fake_chat)
        callback = AsyncMock(
            return_value=ToolExecutionResult(
                result=ToolResult(success=True, output={"ok": True}, observation="ok"),
                step_id="step-1",
            )
        )

        with pytest.raises(AgentLoopExhaustedError):
            await loop.run(tool_ctx, callback)

    async def test_primary_tool成功后推进phase(self, setup, monkeypatch):
        loop, tool_ctx, sse, reg, agent_ctx = setup

        responses = [
            _make_llm_result(tool_calls=[ToolCall(id="1", name="plan_tool", arguments={})]),
            _make_llm_result(tool_calls=[ToolCall(id="2", name="search_tool", arguments={})]),
            _make_llm_result(tool_calls=[ToolCall(id="3", name="finish_tool", arguments={})]),
        ]
        iter_resp = iter(responses)

        async def fake_chat(*args, **kwargs):
            return next(iter_resp)

        monkeypatch.setattr("app.agent.loop.chat_completion", fake_chat)

        await loop.run(tool_ctx, _callback_factory(agent_ctx))

        assert agent_ctx.finished is True
        assert "planning" in agent_ctx.completed_phases
        assert "search" in agent_ctx.completed_phases


class TestAgentLoopCancel:
    """取消检查回调测试。"""

    async def test_取消命中_不调用LLM直接退出(self, setup, monkeypatch):
        loop, tool_ctx, sse, reg, agent_ctx = setup
        chat_mock = AsyncMock()
        monkeypatch.setattr("app.agent.loop.chat_completion", chat_mock)
        callback = AsyncMock()

        async def cancel_check():
            return True

        await loop.run(tool_ctx, callback, cancel_check=cancel_check)

        assert agent_ctx.finished is True
        assert agent_ctx.finish_reason == "canceled"
        assert agent_ctx.iteration_count == 0
        chat_mock.assert_not_awaited()
        callback.assert_not_awaited()
        sse.publish.assert_not_awaited()

    async def test_第二轮命中取消_仅执行一轮(self, setup, monkeypatch):
        loop, tool_ctx, sse, reg, agent_ctx = setup

        async def fake_chat(*args, **kwargs):
            return _make_llm_result(tool_calls=[ToolCall(id="1", name="plan_tool", arguments={})])

        monkeypatch.setattr("app.agent.loop.chat_completion", fake_chat)

        calls = {"n": 0}

        async def cancel_check():
            # 第 1 次：第一轮迭代开头检查 → 放行；
            # 第 2 次：第一轮 tool 执行前检查 → 放行（同迭代内不应提前取消）；
            # 第 3 次：第二轮迭代开头检查 → 命中取消。
            calls["n"] += 1
            return calls["n"] >= 3

        await loop.run(tool_ctx, _callback_factory(agent_ctx), cancel_check=cancel_check)

        assert agent_ctx.finished is True
        assert agent_ctx.finish_reason == "canceled"
        assert agent_ctx.iteration_count == 1
        assert agent_ctx.completed_phases == {"planning"}

    async def test_未取消_循环正常结束不置canceled(self, setup, monkeypatch):
        loop, tool_ctx, sse, reg, agent_ctx = setup

        async def fake_chat(*args, **kwargs):
            return _make_llm_result(tool_calls=[ToolCall(id="1", name="finish_tool", arguments={})])

        monkeypatch.setattr("app.agent.loop.chat_completion", fake_chat)

        async def cancel_check():
            return False

        await loop.run(tool_ctx, _callback_factory(agent_ctx), cancel_check=cancel_check)

        assert agent_ctx.finished is True
        assert agent_ctx.finish_reason is None
        assert agent_ctx.iteration_count == 1


class TestAgentLoopSanitize:
    """SSE 参数脱敏测试。"""

    def test_memory_tool参数仅保留operation(self):
        assert AgentLoop._sanitize_arguments(
            "memory_tool",
            {
                "operation": "read",
                "limit": 5,
            },
        ) == {"operation": "read"}
        assert AgentLoop._sanitize_arguments(
            "memory_tool",
            {
                "operation": "append",
                "content": "# 抓取内容\n来源：光明网\n链接：http://example.com/secret",
            },
        ) == {"operation": "append"}
        assert AgentLoop._sanitize_arguments("memory_tool", {}) == {}

    def test_其他工具长字符串参数截断(self):
        long_text = "x" * 500
        result = AgentLoop._sanitize_arguments(
            "search_tool",
            {
                "query": long_text,
                "reason": "覆盖研究方向",
            },
        )
        assert result["reason"] == "覆盖研究方向"
        assert len(result["query"]) == 201
        assert result["query"].endswith("…")

    def test_非字典参数返回空(self):
        assert AgentLoop._sanitize_arguments("plan_tool", None) == {}  # type: ignore[arg-type]
        assert AgentLoop._sanitize_arguments("plan_tool", "not-dict") == {}  # type: ignore[arg-type]

    def test_memory_tool_observation仅返回执行状态(self):
        assert (
            AgentLoop._sanitize_observation(
                "memory_tool",
                "已返回最近 5 条记录（最近 phase=rerank）",
                True,
            )
            == "执行完成"
        )
        assert (
            AgentLoop._sanitize_observation(
                "memory_tool",
                "参数校验失败",
                False,
            )
            == "执行失败"
        )

    def test_非memory_tool保留原observation(self):
        assert (
            AgentLoop._sanitize_observation(
                "rerank_tool",
                "产出 8 个字段",
                True,
            )
            == "产出 8 个字段"
        )
        assert (
            AgentLoop._sanitize_observation(
                "plan_tool",
                "",
                False,
            )
            == "执行失败"
        )
