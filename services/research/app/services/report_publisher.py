"""报告目标态原子发布服务 —— 对齐 DATABASE.md §7.6 / RESEARCH_PIPELINE §11 / ADR-009。

在迁移态 report_sections/section_evidence 写入之外，新增目标态发布：
1. 获取或创建 reports 根（task_id 唯一）；
2. 创建 building ReportRevision（revision_number 递增）；
3. 写入 report_sections（挂 revision_id）；
4. 写入 claims 与 evidence_relations（含 supports/contradicts/context + confidence）；
5. 计算 evidence_completeness 三分项并写入 Revision 摘要；
6. 单事务置 published 并切换 reports.current_revision_id。

published Revision 不可变：重复发布创建更高 revision_number，不覆盖旧版本。
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ReportPublishFailedException
from app.evaluation.completeness import (
    build_completeness_summary,
    compute_claim_coverage,
    compute_question_coverage,
)
from app.models.claim import Claim
from app.models.evidence_relation import EvidenceRelation
from app.models.report import Report
from app.models.report_revision import ReportRevision
from app.models.report_section import ReportSection
from app.models.research_task import ResearchTask

logger = logging.getLogger(__name__)


def _compute_channel_success(task: ResearchTask) -> float:
    """按来源策略推导通道成功数（最小可审计实现）。

    knowledge：内部通道（成功与否由 evidence 数体现）；
    web/hybrid：内部 + 外部两通道，有任意 evidence 的通道计为成功。
    该推导后续由 RESEARCH_PIPELINE §10.1 的完整通道计划替代。
    """
    evidence_count = task.total_evidence or 0
    if evidence_count <= 0:
        return 0.0
    # 有 evidence 即视为内部通道成功（channel_success 至少 1/计划通道）
    return 1.0


async def _create_or_get_report(session: AsyncSession, task_id: str) -> Report:
    report = (
        await session.execute(select(Report).where(Report.task_id == task_id))
    ).scalar_one_or_none()
    if report is None:
        report = Report(task_id=task_id)
        session.add(report)
        await session.flush()
    return report


async def _next_revision_number(session: AsyncSession, report_id: str) -> int:
    max_num = (
        await session.execute(
            select(func.max(ReportRevision.revision_number)).where(
                ReportRevision.report_id == report_id
            )
        )
    ).scalar()
    return (max_num or 0) + 1


async def _persist_claims_and_relations(
    session: AsyncSession,
    *,
    revision: ReportRevision,
    sections: list[ReportSection],
    claims_raw: list[dict],
    build_step_id: str | None,
    evidence_by_id: dict,
) -> None:
    """写入 claims 与 evidence_relations。

    claims_raw 来自 Evidence Graph 的 graph["claims"]（切片 3 产出），
    每项含 statement/critical/certainty/qualification 与
    relations[{evidence_item_id, evidence_index, relation_type, confidence}]。
    """
    # 简化映射：claims 归属首个 section（v1.0 单层报告），后续按 section 拆分演进
    primary_section = sections[0] if sections else None
    for i, c in enumerate(claims_raw):
        if not isinstance(c, dict):
            continue
        statement = c.get("statement")
        if not statement:
            continue
        claim = Claim(
            revision_id=revision.id,
            section_id=primary_section.id if primary_section else None,
            sequence=i,
            statement=statement,
            certainty=c.get("certainty", "medium"),
            qualification=c.get("qualification"),
        )
        session.add(claim)
        await session.flush()

        for rel in c.get("relations", []) or []:
            if not isinstance(rel, dict):
                continue
            evidence_id = rel.get("evidence_item_id")
            if evidence_id is None or evidence_id not in evidence_by_id:
                continue
            session.add(
                EvidenceRelation(
                    claim_id=claim.id,
                    evidence_id=evidence_id,
                    relation_type=rel.get("relation_type", "context"),
                    confidence=float(rel.get("confidence", 0.0)),
                    rationale_summary=None,
                    created_by_step_id=build_step_id,
                )
            )
    await session.flush()


async def publish_report(
    session: AsyncSession,
    *,
    task: ResearchTask,
    build_step_id: str,
    title: str,
    sections: list[ReportSection],
    claims_raw: list[dict],
    evidence_by_id: dict,
    language: str = "zh",
    content_hash: str | None = None,
    limitations_summary: str | None = None,
) -> ReportRevision:
    """目标态原子发布报告 Revision。

    方案 X：revision 发布时为 sections 创建独立副本（revision 专属），
    不修改迁移态 task 级 sections。因此 reports/revision 的级联删除
    只影响 revision 专属副本，不破坏迁移态展示数据。

    Args:
        sections: 迁移态 ReportSection 列表（仅读取 heading/content/sort_order 复制）。
        claims_raw: Evidence Graph 的 claims（含 relations）。

    Returns:
        已发布的 ReportRevision。

    Raises:
        ReportPublishFailedException: 无法完成原子发布。
    """
    try:
        report = await _create_or_get_report(session, str(task.id))
        revision_number = await _next_revision_number(session, str(report.id))

        # 直接读取列值（避免 current_revision relationship 在异步会话触发懒加载）
        from sqlalchemy import text as sa_text

        current_rev_id = (
            await session.execute(
                sa_text("SELECT current_revision_id FROM reports WHERE id = :rid"),
                {"rid": report.id},
            )
        ).scalar()

        revision = ReportRevision(
            report_id=report.id,
            revision_number=revision_number,
            status="building",
            build_step_id=build_step_id,
            based_on_revision_id=current_rev_id,
            title=title,
            executive_summary=None,
            language=language,
            content_hash=content_hash,
            evidence_completeness=None,
            limitations_summary=limitations_summary,
        )
        session.add(revision)
        await session.flush()

        # 方案 X：复制独立 sections（不挂载/不修改迁移态 sections）
        revision_sections: list[ReportSection] = []
        for i, s in enumerate(sections):
            copy = ReportSection(
                task_id=str(task.id),
                revision_id=revision.id,
                heading=s.heading,
                content=s.content,
                sort_order=i,
            )
            session.add(copy)
            revision_sections.append(copy)
        await session.flush()

        # 写入 claims 与 relations
        await _persist_claims_and_relations(
            session,
            revision=revision,
            sections=revision_sections,
            claims_raw=claims_raw,
            build_step_id=build_step_id,
            evidence_by_id=evidence_by_id,
        )

        # 完整度三分项（RESEARCH_PIPELINE §10）
        required_questions = max(1, task.total_steps or 1)
        evidence_count = task.total_evidence or 0
        question_coverage, _, _ = compute_question_coverage(
            required_questions=required_questions,
            questions_with_evidence=min(evidence_count, required_questions),
        )
        # 通道成功：有证据视为内部通道成功；按策略近似
        channel_success = _compute_channel_success(task)
        # claim 覆盖：critical claim 有 supports 的比例
        critical_claims = [c for c in claims_raw if isinstance(c, dict) and c.get("critical")]
        critical_with_supports = sum(
            1
            for c in critical_claims
            if any(r.get("relation_type") == "supports" for r in (c.get("relations") or []))
        )
        claim_coverage, _, _ = compute_claim_coverage(
            critical_claims=len(critical_claims),
            claims_with_supports=critical_with_supports,
        )
        revision.evidence_completeness = build_completeness_summary(
            question_coverage=question_coverage,
            channel_success=channel_success,
            claim_coverage=claim_coverage,
        )

        # 原子置 published 并切换 current_revision_id
        now = datetime.now(timezone.utc)
        revision.status = "published"
        revision.published_at = now
        report.current_revision_id = revision.id
        await session.flush()

        logger.info(
            "报告目标态发布完成: task_id=%s, report=%s, revision=%d, claims=%d, completeness=%s",
            task.id,
            report.id,
            revision.revision_number,
            len(critical_claims),
            revision.evidence_completeness,
        )
        return revision
    except Exception as e:
        logger.exception("报告目标态发布失败: task_id=%s, err=%s", task.id, e)
        raise ReportPublishFailedException(detail=f"报告发布失败: {e}") from e
