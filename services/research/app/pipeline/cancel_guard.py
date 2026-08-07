"""Pipeline 取消检查辅助 —— RESEARCH_PIPELINE §13.2。

取消接口只写 `research_tasks.cancel_requested_at`；Worker 应在以下安全检查点
检查取消请求，取消后不得继续外部调用、抓取剩余 URL 或发布新 Revision：

- 每次外部调用前后；
- 每个 Web URL 完成后；
- LLM 调用前后；
- Evidence Graph 持久化前；
- Report 发布事务前。

本模块提供对 task 的取消状态查询辅助，供 fetcher / renderer 等 pipeline
阶段在安全检查点复用。Agent Runtime 的迭代级检查见 `agent/loop.py`。
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_task import ResearchTask

logger = logging.getLogger(__name__)


async def is_task_canceled(session: AsyncSession, task_id: str) -> bool:
    """查询任务是否已请求取消（cancel_requested_at 非空）。

    Args:
        session: 当前 DB 会话。
        task_id: Research Task UUID。

    Returns:
        True 表示已请求取消，后续安全检查点应停止执行。
    """
    row = await session.execute(
        select(ResearchTask.cancel_requested_at).where(ResearchTask.id == task_id)
    )
    return row.scalar_one_or_none() is not None
