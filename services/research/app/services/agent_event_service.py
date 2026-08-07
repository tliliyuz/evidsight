"""Agent Event Service —— agent_events 追加与 SSE 持久游标查询。

对齐 DATABASE.md §5.4 / §9 与 RESEARCH_PIPELINE §15：
- event_type 白名单枚举：阶段进入 / Tool 请求 / Tool 结果 / 重试 / 预算停止 / 恢复；
- sequence 为 Task 内单调序号，`(task_id, sequence)` 唯一，作为 SSE 持久游标；
- 事件只含安全业务摘要，禁止 thought/reasoning/完整 Prompt/内部正文/凭证与堆栈。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_event import AgentEvent

# ── event_type 白名单枚举（DATABASE.md §5.4）────────────────────
EVENT_TYPE_PHASE_ENTER = "phase.enter"
EVENT_TYPE_TOOL_REQUEST = "tool.request"
EVENT_TYPE_TOOL_RESULT = "tool.result"
EVENT_TYPE_RETRY = "retry"
EVENT_TYPE_BUDGET_STOP = "budget.stop"
EVENT_TYPE_RECOVERY = "recovery"

EVENT_TYPE_WHITELIST = frozenset(
    {
        EVENT_TYPE_PHASE_ENTER,
        EVENT_TYPE_TOOL_REQUEST,
        EVENT_TYPE_TOOL_RESULT,
        EVENT_TYPE_RETRY,
        EVENT_TYPE_BUDGET_STOP,
        EVENT_TYPE_RECOVERY,
    }
)

# ── 禁止进入用户可见字段的键（§16 / §17.3-22 防御性剥离）────────
_FORBIDDEN_KEYS = frozenset(
    {
        "thought",
        "reasoning",
        "reasoning_content",
        "prompt",
        "prompt_text",
        "excerpt",
        "minimal_excerpt",
        "content",
        "password",
        "token",
        "secret",
        "cookie",
        "authorization",
        "stack",
    }
)


def _strip_forbidden_keys(summary: dict[str, Any] | None) -> dict[str, Any]:
    """递归剥离禁止字段，保证事件摘要只含安全业务信息。"""
    if not isinstance(summary, dict):
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in summary.items():
        if key in _FORBIDDEN_KEYS:
            continue
        if isinstance(value, dict):
            cleaned[key] = _strip_forbidden_keys(value)
        else:
            cleaned[key] = value
    return cleaned


async def _next_sequence(session: AsyncSession, task_id: str) -> int:
    result = await session.execute(
        sa_select(func.max(AgentEvent.sequence)).where(AgentEvent.task_id == task_id)
    )
    max_sequence = result.scalar()
    return (max_sequence or 0) + 1


async def append_event(
    session: AsyncSession,
    task_id: str,
    *,
    event_type: str,
    step_id: str | None = None,
    tool_name: str | None = None,
    provider_name: str | None = None,
    input_summary: dict[str, Any] | None = None,
    result_summary: dict[str, Any] | None = None,
    request_id: str | None = None,
    trace_id: str | None = None,
    duration_ms: int | None = None,
    cost_summary: dict[str, Any] | None = None,
) -> AgentEvent:
    """追加一条 agent_event（sequence 单调递增），事件摘要经安全剥离。

    Args:
        session: 与业务提交共用的事务会话（随 Step 提交持久化）。
        task_id: 任务 ID。
        event_type: 必须位于 EVENT_TYPE_WHITELIST。
        input_summary / result_summary: Schema 化安全摘要；禁止字段会被剥离。

    Returns:
        已 flush 的 AgentEvent（携带 sequence）。
    """
    if event_type not in EVENT_TYPE_WHITELIST:
        raise ValueError(f"非法 agent event 类型: {event_type}")

    sequence = await _next_sequence(session, task_id)
    event = AgentEvent(
        task_id=task_id,
        step_id=step_id,
        sequence=sequence,
        event_type=event_type,
        tool_name=tool_name,
        provider_name=provider_name,
        input_summary=_strip_forbidden_keys(input_summary),
        result_summary=_strip_forbidden_keys(result_summary),
        request_id=request_id,
        trace_id=trace_id,
        duration_ms=duration_ms,
        cost_summary=cost_summary,
    )
    session.add(event)
    await session.flush()
    return event


async def list_events_after(
    session: AsyncSession,
    task_id: str,
    last_sequence: int | None,
    limit: int = 500,
) -> list[AgentEvent]:
    """按持久游标读取 Task 的 agent_events（SSE 重连回放）。

    Args:
        task_id: 任务 ID。
        last_sequence: 持久游标；None 表示回放全部（新订阅收敛）。

    Returns:
        按 sequence 升序的 AgentEvent 列表。
    """
    stmt = sa_select(AgentEvent).where(AgentEvent.task_id == task_id)
    if last_sequence is not None:
        stmt = stmt.where(AgentEvent.sequence > last_sequence)
    stmt = stmt.order_by(AgentEvent.sequence).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())
