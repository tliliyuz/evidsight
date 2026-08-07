"""AgentRuntime 预算接入单元测试 —— RESEARCH_PIPELINE §14。

- Tool 执行前预留（reserve）失败时停止新调用；
- Tool 结果后结算（settle）用量；
- 预算停止触发 budget.stop agent_event。
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.agent.context import AgentContext
from app.agent.memory import WorkingMemory
from app.agent.runtime import AgentRuntime
from app.core.trace_recorder import TraceRecorder
from app.models.research_task import ResearchTask
from app.services.budget_service import freeze_budget
from app.tools.base import Tool, ToolCall, ToolContext


class OkTool(Tool):
    name = "ok_tool"
    description = "ok"
    mapped_phase = "search"
    parameters_schema = {"type": "object", "properties": {}}

    async def execute(self, ctx: ToolContext, **params):
        return type(
            "R",
            (),
            {
                "success": True,
                "output": {
                    "total_results": 5,
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "model": "test",
                },
                "observation": "ok",
                "error_message": None,
                "cost": None,
                "duration_ms": 10,
            },
        )()


@pytest.fixture
def budget_runtime(monkeypatch):
    task = ResearchTask(
        id="runtime-budget-task",
        user_id=1,
        topic="test",
        requirements={"task_type": "analysis", "max_sources": 10},
        source_strategy="web",
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    freeze_budget(task, task.requirements, task.source_strategy)

    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    monkeypatch.setattr(
        "app.agent.runtime.AgentEventRecorder",
        lambda *a, **k: AsyncMock(),
    )

    sse = AsyncMock()
    trace = TraceRecorder(task_id=task.id, user_id=task.user_id, topic=task.topic)
    runtime = AgentRuntime(
        task=task,
        session=session,
        sse_bridge=sse,
        trace_recorder=trace,
        tool_registry=MagicMock(),
    )
    runtime._agent_context = AgentContext(current_phase="search")
    runtime._working_memory = WorkingMemory()
    runtime._lock_handle.worker_id = "worker-1"
    runtime._lock_handle.lease_generation = 1
    monkeypatch.setattr(
        "app.agent.runtime.is_step_commit_allowed",
        AsyncMock(return_value=True),
    )
    return runtime


class TestRuntimeBudget:
    @pytest.mark.asyncio
    async def test_tool执行前预留_完成后结算(self, budget_runtime):
        # 本组用例聚焦预算预留/结算，不验证 Step 提交的 execution_context 细节
        budget_runtime._complete_step = AsyncMock()
        budget_runtime._fail_step = AsyncMock()

        tool = OkTool()
        tool_call = ToolCall(id="1", name="ok_tool", arguments={})

        exec_result = await budget_runtime._execute_tool(tool, tool_call)

        assert exec_result.result.success is True
        # 结算：provider_calls +1、llm_tokens 累加 150
        assert budget_runtime._task.budget_usage["provider_calls"] == 1
        assert budget_runtime._task.budget_usage["llm_tokens"] == 150

    @pytest.mark.asyncio
    async def test_预算用尽_预留失败_停止新调用(self, budget_runtime):
        # 预先把 provider_calls 打到上限，使 reserve 失败
        from app.services.budget_service import settle_budget

        settle_budget(budget_runtime._task, {"provider_calls": 60})

        # 直接调用预留检查：预算停止后不应再发起外部调用
        from app.services.budget_service import can_reserve

        assert can_reserve(budget_runtime._task) is False

    @pytest.mark.asyncio
    async def test_预算停止_记录budget_stop事件(self, budget_runtime):
        from app.services.agent_event_service import EVENT_TYPE_BUDGET_STOP

        recorder = AsyncMock()
        budget_runtime._recorder = recorder
        await budget_runtime._record_budget_stop()

        recorder.record.assert_awaited()
        kwargs = recorder.record.call_args.kwargs
        assert kwargs["event_type"] == EVENT_TYPE_BUDGET_STOP
