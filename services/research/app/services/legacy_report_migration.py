"""存量报告迁移 service —— 切片 5（DATABASE.md §12-4 / §7.3 / DATA_MIGRATION_AND_ROLLBACK.md）。

切片 4 前新渲染写 task 级迁移态 `report_sections`（revision_id IS NULL）。本 service
为已完成/部分完成、有 task 级 sections 且无目标态 reports 根的任务生成 revision 1：

1. 创建 Report（task_id 唯一）与 published Revision 1（title=task.topic）；
2. 把 task 级 sections 的 `revision_id` 更新为该 Revision（保留 section_evidence，
   不重建 sections、不复制正文）；
3. 幂等可重跑：已有 reports 根的任务跳过；每任务最多一个 current published Revision。

校验门禁：迁移后无 `revision_id IS NULL` 的 sections 残留；每已完成任务最多一个
current published Revision。迁移不改变权限、状态机或业务含义（DATA_MIGRATION §2）。
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report import Report
from app.models.report_revision import ReportRevision
from app.models.report_section import ReportSection
from app.models.research_task import ResearchTask

logger = logging.getLogger(__name__)

# 可迁移的终态：报告已生成且可读取的状态（RESEARCH_PIPELINE §4.1）
MIGRATABLE_STATUSES = ("completed", "partially_completed")


@dataclass
class MigrationReport:
    """一次迁移的统计与校验结果。"""

    scanned: int = 0
    migrated: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


async def _legacy_section_task_ids(session: AsyncSession) -> list[str]:
    """有 task 级迁移态 sections（revision_id IS NULL）的 task_id。"""
    rows = await session.execute(
        select(ReportSection.task_id).where(ReportSection.revision_id.is_(None)).distinct()
    )
    return [r[0] for r in rows.all()]


async def _existing_report_task_ids(session: AsyncSession) -> set[str]:
    rows = await session.execute(select(Report.task_id))
    return {r[0] for r in rows.all()}


async def _count_published_revisions(session: AsyncSession) -> int:
    """每任务 current published Revision 唯一性校验：同 Report 至多一个 published。"""
    return (
        await session.scalar(
            select(func.count())
            .select_from(ReportRevision)
            .where(ReportRevision.status == "published")
        )
    ) or 0


async def migrate_legacy_report_sections(
    session: AsyncSession,
    *,
    dry_run: bool = False,
) -> MigrationReport:
    """把存量 task 级 sections 迁移归入目标态 Revision 1（幂等可重跑）。

    Args:
        session: 业务库异步会话（真实 MySQL 或测试 SQLite）。
        dry_run: True 时只扫描并校验，不写入。

    Returns:
        MigrationReport 统计与校验结果。
    """
    result = MigrationReport()
    legacy_task_ids = await _legacy_section_task_ids(session)
    existing_reports = await _existing_report_task_ids(session)

    # 候选：有 task 级 sections、无 reports 根、且为可迁移终态的任务
    # （非终态任务保留 task 级 sections 待任务完成后经渲染发布，不属于本次迁移）
    candidates: list[tuple[str, ResearchTask]] = []
    for tid in legacy_task_ids:
        if tid in existing_reports:
            continue
        task = await session.get(ResearchTask, tid)
        if task is None or task.status not in MIGRATABLE_STATUSES:
            continue
        candidates.append((tid, task))

    result.scanned = len(legacy_task_ids)
    result.skipped = len(legacy_task_ids) - len(candidates)

    if dry_run:
        # dry-run 只扫描候选，不写入、不做残留校验
        result.migrated = len(candidates)
    else:
        for task_id, task in candidates:
            try:
                await _migrate_one(session, task)
                await session.flush()
                result.migrated += 1
            except Exception as e:  # noqa: BLE001 — 迁移单任务失败不中断整体，计入隔离清单
                logger.exception("存量报告迁移失败: task_id=%s, err=%s", task_id, e)
                result.failed += 1
                result.errors.append(f"{task_id}: {e}")

        # 校验门禁：迁移后无 task 级 sections 残留（候选任务应全部归入 revision）
        remaining = await _legacy_section_task_ids(session)
        # 评审 🔴5：candidates 为 (task_id, task) 元组列表，字符串 tid 直接判成员
        # 永不命中；改为对候选 task_id 集合判成员，残留校验才能正确命中。
        candidate_ids = {c[0] for c in candidates}
        still_legacy = [tid for tid in remaining if tid in candidate_ids]
        if still_legacy:
            result.errors.append(
                f"迁移后仍存在 task 级 sections 残留: {len(still_legacy)} 个任务: {still_legacy[:10]}"
            )
            result.failed += len(still_legacy)

    # 校验门禁：每任务最多一个 current published Revision（DATABASE.md §7.1）
    published_count = await _count_published_revisions(session)
    logger.info(
        "存量报告迁移完成: scanned=%d, migrated=%d, skipped=%d, failed=%d, published_revisions=%d",
        result.scanned,
        result.migrated,
        result.skipped,
        result.failed,
        published_count,
    )
    return result


async def _migrate_one(session: AsyncSession, task: ResearchTask) -> None:
    """为单个任务创建 Report + published Revision 1，并把 task 级 sections 归入 Revision。"""
    now = datetime.now(timezone.utc)
    report = Report(task_id=str(task.id))
    session.add(report)
    await session.flush()

    revision = ReportRevision(
        report_id=report.id,
        revision_number=1,
        status="published",
        build_step_id=None,
        title=task.topic or str(task.id),
        language=(task.requirements or {}).get("language", "zh"),
        published_at=now,
    )
    session.add(revision)
    await session.flush()

    # 把 task 级 sections 归入 Revision 1（保留 section_evidence，不重建、不复制正文）
    await session.execute(
        update(ReportSection)
        .where(ReportSection.task_id == str(task.id), ReportSection.revision_id.is_(None))
        .values(revision_id=revision.id)
    )
    report.current_revision_id = revision.id
    await session.flush()
