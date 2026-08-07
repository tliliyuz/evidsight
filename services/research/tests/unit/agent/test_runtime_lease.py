"""切片 E —— AgentRuntime 租约门禁验收测试。

对齐 RESEARCH_PIPELINE §13.1 / §17.12：
- Step 提交前校验租约：owner/generation 匹配才允许提交业务结果；
- 失去租约的 Worker 立即停止，不提交业务结果，也不写终态（交给 Recovery Scanner）；
- 终态推导前校验所有权（取消安全停止后仍允许 Resolver 推导 canceled）；
- 取消请求在迭代检查点生效，安全停止后进入最终化推导终态。
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.context import AgentContext
from app.agent.exceptions import LeaseLostError
from app.agent.memory import WorkingMemory
from app.agent.runtime import AgentRuntime
from app.core.llm import LLMResult, ToolCall as LLMToolCall
from app.core.trace_recorder import TraceRecorder
from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask
from app.tools.base import Tool, ToolCall, ToolContext, ToolResult
from app.tools.registry import ToolRegistry


class FailingTool(Tool):
    """用于测试执行失败的 Tool。"""

    name = "failing_tool"
    description = "总是失败的 tool"
    mapped_phase = "planning"
    parameters_schema = {"type": "object", "properties": {}}

    async def execute(self, ctx: ToolContext, **params):
        raise RuntimeError("内部原始异常")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def runtime(monkeypatch):
    task = ResearchTask(
        id="lease-runtime",
        user_id="00000000-0000-4000-8000-000000000001",
        topic="test",
        status="running",
    )
    session = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
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
    # 绑定租约：worker-1 / generation 1（模拟 start_research_task 领取后的状态）
    runtime._lock_handle = SimpleNamespace(
        worker_id="worker-1",
        lease_generation=1,
        release=AsyncMock(),
    )
    runtime._agent_context = AgentContext(current_phase="planning")
    runtime._working_memory = WorkingMemory()
    return runtime


class TestStepCommitLeaseGate:
    async def test_租约匹配_允许提交(self, runtime, monkeypatch):
        step = ResearchStep(task_id=runtime._task.id, step_type="planning", status="running")
        result = ToolResult(success=True, output={"ok": True}, observation="ok")
        runtime._record_phase_trace = AsyncMock()
        runtime._update_execution_context = AsyncMock()
        monkeypatch.setattr(
            "app.agent.runtime.is_step_commit_allowed",
            AsyncMock(return_value=True),
        )

        await runtime._complete_step(step, result)

        assert step.status == "completed"
        runtime._session.commit.assert_awaited_once()

    async def test_租约丢失_拒绝提交并抛LeaseLostError(self, runtime, monkeypatch):
        step = ResearchStep(task_id=runtime._task.id, step_type="planning", status="running")
        result = ToolResult(success=True, output={"ok": True}, observation="ok")
        monkeypatch.setattr(
            "app.agent.runtime.is_step_commit_allowed",
            AsyncMock(return_value=False),
        )

        with pytest.raises(LeaseLostError):
            await runtime._complete_step(step, result)

        assert step.status == "running"
        runtime._session.commit.assert_not_awaited()

    async def test_失败Step_租约丢失_拒绝写入(self, runtime, monkeypatch):
        step = ResearchStep(task_id=runtime._task.id, step_type="planning", status="running")
        result = ToolResult(success=False, output={}, observation="fail", error_message="boom")
        monkeypatch.setattr(
            "app.agent.runtime.is_step_commit_allowed",
            AsyncMock(return_value=False),
        )

        with pytest.raises(LeaseLostError):
            await runtime._fail_step(step, result)

        assert step.status == "running"
        runtime._session.flush.assert_not_awaited()


class TestFatalErrorLeaseLost:
    async def test_LeaseLostError_不写failed终态(self, runtime):
        with patch("app.agent.runtime.emit_task_status_transition") as mock_emit:
            await runtime._handle_fatal_error(LeaseLostError("租约丢失"))

        mock_emit.assert_not_called()
        runtime._session.execute.assert_not_awaited()
        runtime._sse.publish.assert_not_awaited()


class TestRunCancelCheckpoint:
    """取消请求在迭代检查点生效，安全停止后进入最终化推导终态（§13.2）。"""

    def _prepare_run(self, runtime, monkeypatch):
        monkeypatch.setattr("app.agent.runtime.start_research_task", AsyncMock(return_value=True))
        monkeypatch.setattr(
            "app.agent.runtime.agent_memory_service.build_working_memory",
            AsyncMock(return_value=WorkingMemory()),
        )
        monkeypatch.setattr(
            "app.agent.runtime.agent_memory_service.persist_pending_entries",
            AsyncMock(),
        )
        runtime._finalize_task = AsyncMock()
        runtime._task.execution_context = None

    async def test_取消请求_停止循环并进入最终化(self, runtime, monkeypatch):
        self._prepare_run(runtime, monkeypatch)
        chat_mock = AsyncMock()
        monkeypatch.setattr("app.agent.loop.chat_completion", chat_mock)

        async def refresh_to_cancel(obj, attrs):
            obj.cancel_requested_at = _now()

        runtime._session.refresh = AsyncMock(side_effect=refresh_to_cancel)

        await runtime.run()

        assert runtime._task.cancel_requested_at is not None
        assert runtime._agent_context.finish_reason == "canceled"
        chat_mock.assert_not_awaited()
        runtime._finalize_task.assert_awaited_once()
        runtime._lock_handle.release.assert_awaited_once()

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
        runtime._session.refresh = AsyncMock()

        await runtime.run()

        assert runtime._agent_context.finish_reason == "finished_by_llm"
        runtime._finalize_task.assert_awaited_once()
        runtime._lock_handle.release.assert_awaited_once()
