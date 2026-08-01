"""离线评估数据加载器

从数据库加载 Task、Step output 与 EvidenceItem，为 aggregator 提供输入。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence_item import EvidenceItem
from app.models.research_source import ResearchSource
from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask


async def load_task(session: AsyncSession, task_id: str) -> ResearchTask | None:
    """按 task_id 加载 ResearchTask。"""
    result = await session.execute(select(ResearchTask).where(ResearchTask.id == task_id))
    return result.scalar_one_or_none()


async def load_step_output(
    session: AsyncSession,
    task_id: str,
    step_type: str,
    output_key: str | None = None,
) -> dict | None:
    """加载指定任务、指定类型的最新已完成父 Step 的 output。

    由于 Search / Fetch 等阶段会创建子 Step（每个子问题 / URL 一个），
    父 Step 与子 Step 的 `step_type` 相同。通过 `output_key` 可筛选包含该 key 的 Step，
    从而定位父 Step 的聚合 output。

    Args:
        output_key: 用于区分父 Step 的 output key，例如 "sub_question_results" / "fetched"。
            为 None 时返回最新完成的同类型 Step。
    """
    stmt = (
        select(ResearchStep)
        .where(
            ResearchStep.task_id == task_id,
            ResearchStep.step_type == step_type,
            ResearchStep.status == "completed",
        )
        .order_by(ResearchStep.completed_at.desc())
    )
    result = await session.execute(stmt)
    steps = list(result.scalars().all())

    if output_key:
        for step in steps:
            if step.output and output_key in step.output:
                return step.output
        return None

    if steps:
        return steps[0].output
    return None


async def load_evidence_items(session: AsyncSession, task_id: str) -> list[EvidenceItem]:
    """加载指定任务的全部 EvidenceItem，按 relevance_score 降序排列。"""
    result = await session.execute(
        select(EvidenceItem)
        .where(EvidenceItem.task_id == task_id)
        .order_by(EvidenceItem.relevance_score.desc())
    )
    return list(result.scalars().all())


async def load_sources_by_fetch_status(
    session: AsyncSession,
    task_id: str,
) -> list[ResearchSource]:
    """加载指定任务的全部 ResearchSource。"""
    result = await session.execute(
        select(ResearchSource).where(ResearchSource.task_id == task_id)
    )
    return list(result.scalars().all())


async def load_task_terminal_status_counts(
    session: AsyncSession,
) -> dict[str, int]:
    """统计全部已终结任务（终态）的各状态数量。

    Returns:
        形如 {"completed": 10, "partially_completed": 2, "failed": 1, "canceled": 1}。
    """
    from sqlalchemy import func

    result = await session.execute(
        select(ResearchTask.status, func.count(ResearchTask.id))
        .where(
            ResearchTask.status.in_(
                ["completed", "partially_completed", "failed", "canceled"]
            )
        )
        .group_by(ResearchTask.status)
    )
    counts: dict[str, int] = {
        "completed": 0,
        "partially_completed": 0,
        "failed": 0,
        "canceled": 0,
    }
    for row in result.all():
        status, count = row
        if status in counts:
            counts[status] = count
    return counts


async def load_llm_step_status_counts(
    session: AsyncSession,
) -> dict[str, int]:
    """统计全部 LLM 类 Step 的成功/失败数量。

    LLM 类 Step 类型由 constants.LLM_STEP_TYPES 定义。
    只统计已终态的 Step（completed / failed），pending / running / skipped / retrying 不纳入。

    Returns:
        形如 {"completed": 120, "failed": 3}。
    """
    from sqlalchemy import func

    from app.evaluation.constants import LLM_STEP_TYPES

    result = await session.execute(
        select(ResearchStep.status, func.count(ResearchStep.id))
        .where(
            ResearchStep.step_type.in_(LLM_STEP_TYPES),
            ResearchStep.status.in_(["completed", "failed"]),
        )
        .group_by(ResearchStep.status)
    )
    counts: dict[str, int] = {"completed": 0, "failed": 0}
    for row in result.all():
        status, count = row
        if status in counts:
            counts[status] = count
    return counts
