"""AgentEventRecorder —— 业务事件落库并带持久 sequence 发布 SSE。

对齐 RESEARCH_PIPELINE §15 / DATABASE.md §5.4：
- agent_events 是 SSE 持久游标的追加式事实来源；
- record() 先追加事件到 DB（与 Step 同事务，随业务提交持久化），再把持久
  sequence 作为 SSE event id 发布，保证客户端收到的事件在重连时可通过游标回放；
- 发布载荷与落库摘要统一走安全剥离，禁止 thought/reasoning/完整 Prompt 等字段。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.pipeline.sse_bridge import SSEBridge
from app.services.agent_event_service import (
    _strip_forbidden_keys,
    append_event,
)


class AgentEventRecorder:
    """把 Agent 业务事件同时投影到 agent_events 表与 Redis SSE。"""

    def __init__(
        self,
        task_id: str,
        session: AsyncSession,
        sse_bridge: SSEBridge,
        request_id: str | None = None,
        trace_id: str | None = None,
    ):
        self._task_id = task_id
        self._session = session
        self._sse = sse_bridge
        self._request_id = request_id
        self._trace_id = trace_id

    async def record(
        self,
        *,
        event_type: str,
        sse_event: str,
        data: dict[str, Any] | None = None,
        step_id: str | None = None,
        tool_name: str | None = None,
        provider_name: str | None = None,
        input_summary: dict[str, Any] | None = None,
        result_summary: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        cost_summary: dict[str, Any] | None = None,
    ) -> int:
        """追加一条 agent_event 并发布 SSE。

        Args:
            event_type: agent_events 白名单类型（EVENT_TYPE_*）。
            sse_event: 对应发布的 SSE 事件名（EVENT_*）。
            data: SSE 载荷（安全摘要，禁止字段会被剥离）。
            input_summary / result_summary: 落库安全摘要。

        Returns:
            持久 sequence（SSE event id）。
        """
        event = await append_event(
            self._session,
            self._task_id,
            event_type=event_type,
            step_id=step_id,
            tool_name=tool_name,
            provider_name=provider_name,
            input_summary=input_summary,
            result_summary=result_summary,
            request_id=self._request_id,
            trace_id=self._trace_id,
            duration_ms=duration_ms,
            cost_summary=cost_summary,
        )
        safe_data = _strip_forbidden_keys(data or {})
        await self._sse.publish(sse_event, safe_data, event_id=event.sequence)
        return event.sequence
