"""Research API 共享辅助 —— v1 前缀与旧前缀薄适配器共用。

对齐 API.md §8（Research Task API）与 §13（Research SSE）：
- v1 前缀 `/api/v1/research` 为目标态（API.md §8 表）；
- 旧前缀 `/api/research` 收敛期间保持可用（§8.2），薄适配器复用本模块，
  避免两套前缀各自维护快照 / SSE / 取消事件逻辑（切片 8 收敛）。

信封沿用全平台既有 {"code","message","data"}（API.md §8.2 迁移态）。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import sanitize_error_message_for_client
from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask
from app.pipeline.sse_bridge import (
    EVENT_TASK_CANCELED,
    EVENT_TASK_STATUS_SNAPSHOT,
    SSEBridge,
    sse_event_stream,
)
from app.services.research_service import _published_report_id

logger = logging.getLogger(__name__)

# 任务终态集合：终态任务 SSE 只推送 snapshot 后关闭连接
TERMINAL_STATUSES = frozenset({"completed", "failed", "canceled", "partially_completed"})


def _canonical_event_name(event_name: str) -> str:
    if event_name == "task.status.snapshot":
        return "snapshot"
    if event_name.startswith("task."):
        return "task.updated"
    if event_name.startswith("phase."):
        return "phase.updated"
    if event_name.startswith(("step.", "checkpoint.", "agent.")):
        return "step.updated"
    return event_name


def canonicalize_sse_chunk(chunk: str) -> str:
    """只改写 v1 事件名；原 data 与持久游标原样保留。"""
    match = re.search(r"(?m)^event: ([^\n]+)$", chunk)
    if match is None:
        return chunk
    canonical = _canonical_event_name(match.group(1).strip())
    return chunk[: match.start(1)] + canonical + chunk[match.end(1) :]


def _ok(data: Any) -> dict:
    """标准成功信封（API.md §8.2 迁移态）。"""
    return {"code": "0", "message": "ok", "data": data}


def _parse_last_event_id(raw: str | None) -> int | None:
    """解析 SSE Last-Event-ID 为持久游标；无法解析时视为无游标。"""
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def build_task_snapshot(
    task: ResearchTask,
    db: AsyncSession,
) -> dict:
    """构建任务状态快照（SSE 和 REST 共用）。

    快照结构：
    - task_id, status, current_phase
    - progress（completed_steps / total_steps / progress）
    - steps：已完成 Step 摘要列表
    - error：错误信息（如果失败）
    - 时间戳
    """
    # 显式查询 steps，避免依赖 task.steps 懒加载（在 async 上下文中触发 MissingGreenlet）
    result = await db.execute(
        sa_select(ResearchStep)
        .where(ResearchStep.task_id == task.id)
        .order_by(ResearchStep.started_at)
    )
    steps: list[ResearchStep] = list(result.scalars().all())

    # 步骤摘要
    steps_summary = []
    for s in steps:
        summary = {
            "id": str(s.id),
            "step_type": s.step_type,
            "status": s.status,
            "label": s.label,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        }
        if s.status == "completed" and s.output:
            # 根据 step_type 提取关键摘要字段
            if s.step_type == "planning":
                summary["sub_questions_count"] = len(s.output.get("sub_questions", []))
            elif s.step_type == "search":
                summary["after_dedup"] = s.output.get("after_dedup")
                summary["sources_created"] = s.output.get("sources_created")
            elif s.step_type == "fetch":
                summary["successful"] = s.output.get("successful")
                summary["failed"] = s.output.get("failed")
        if s.status == "failed":
            summary["error_code"] = s.error_code
            summary["error_message"] = sanitize_error_message_for_client(s.error_message)
        if s.duration_ms is not None:
            summary["duration_ms"] = s.duration_ms

        # 步骤进度摘要（切页重连后恢复日志的细化内容）
        progress_label = _extract_progress_label(s)
        if progress_label:
            summary["progress_label"] = progress_label

        steps_summary.append(summary)

    # 进度
    total = task.total_steps or 0
    completed = task.completed_steps or 0
    progress = round(completed / total, 2) if total > 0 else 0.0

    snapshot: dict = {
        "task_id": str(task.id),
        "status": task.status,
        "current_phase": task.current_phase,
        "progress": {
            "completed_steps": completed,
            "total_steps": total,
            "progress": progress,
        },
        "steps": steps_summary,
        "topic": task.topic,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "report_id": await _published_report_id(db, task.id),
    }

    # 错误信息（如果存在）
    if task.error_code:
        snapshot["error"] = {
            "error_code": task.error_code,
            "error_message": sanitize_error_message_for_client(task.error_message),
            "recoverable": task.recoverable,
        }

    # 统计
    snapshot["stats"] = {
        "total_sources": task.total_sources or 0,
        "total_evidence": task.total_evidence or 0,
    }

    return snapshot


def build_task_events_response(
    request: Request,
    task: ResearchTask,
    db: AsyncSession,
    snapshot: dict,
    *,
    canonical: bool = False,
) -> StreamingResponse:
    """构建 SSE 事件流响应（API.md §13 / RESEARCH_PIPELINE §15）。

    连接时立即推送 task.status.snapshot（当前完整状态），重连携带 Last-Event-ID
    时先回放持久游标之后的 Agent Event（事件 ID 为 agent_events.sequence），
    事件缺口由快照收敛；终态任务只推送 snapshot 后关闭连接。
    """
    if task.status in TERMINAL_STATUSES:
        from app.core.sse import format_sse_event

        async def terminal_stream():
            event = format_sse_event(EVENT_TASK_STATUS_SNAPSHOT, snapshot)
            yield canonicalize_sse_chunk(event) if canonical else event
            if canonical:
                yield format_sse_event("stream.end", {"reason": "terminal_snapshot"})

        return StreamingResponse(
            terminal_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
            },
        )

    last_event_id = _parse_last_event_id(request.headers.get("Last-Event-ID"))
    from app.services.agent_event_service import list_events_after

    async def replay_loader(after_seq: int | None):
        return await list_events_after(db, str(task.id), last_sequence=after_seq)

    # 流式生成器
    async def event_stream():
        async for sse_text in sse_event_stream(
            str(task.id),
            snapshot,
            last_event_id=last_event_id,
            replay_loader=replay_loader,
        ):
            yield canonicalize_sse_chunk(sse_text) if canonical else sse_text
        if canonical:
            yield format_sse_event("stream.end", {"reason": "subscription_ended"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        },
    )


async def publish_cancel_requested(task: ResearchTask) -> None:
    """发布「已请求取消」SSE 事件（终态事件由 Worker/Resolver 安全停止后发布）。

    SSE 发布失败不影响取消请求本身（仅记录日志）。
    """
    sse = SSEBridge(task.id)
    try:
        await sse.publish(
            EVENT_TASK_CANCELED,
            {
                "task_id": str(task.id),
                "status": task.status,
                "cancel_requested": True,
            },
        )
    except Exception:
        logger.exception("取消任务后发送 SSE 事件失败: task_id=%s", task.id)


def _extract_progress_label(step: ResearchStep) -> str | None:
    """从 Step output 提取一个简短的进度摘要，供前端日志恢复时显示细化内容。"""
    output = step.output
    if not isinstance(output, dict):
        return None

    if step.step_type == "search":
        results_found = output.get("results_found")
        if results_found is not None:
            return f"{results_found} 条结果"

    if step.step_type == "fetch":
        status = output.get("status")
        if status == "success":
            content_length = output.get("content_length")
            if content_length:
                return f"正文 {content_length} 字符"
            return "抓取成功"
        error = output.get("error")
        if error:
            return error

    return None
