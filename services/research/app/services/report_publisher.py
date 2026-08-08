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
    compute_channel_success,
    compute_claim_coverage,
    compute_question_coverage,
)
from app.models.claim import Claim
from app.models.evidence_item import EvidenceItem
from app.models.evidence_relation import EvidenceRelation
from app.models.report import Report
from app.models.report_revision import ReportRevision
from app.models.report_section import ReportSection
from app.models.research_task import ResearchTask
from app.models.section_evidence import SectionEvidence

logger = logging.getLogger(__name__)


# 受控通道 → EvidenceItem.source_type（RESEARCH_PIPELINE §6.1/§6.2）
_CHANNEL_SOURCE_TYPE = {"knowledge": "internal", "web": "web"}


async def _compute_real_coverage(
    session: AsyncSession,
    task: ResearchTask,
    planning_questions: list[dict] | None,
) -> tuple[tuple[float, int, int], tuple[float, int, int]]:
    """按 Planning questions 与 evidence 归属计算 question_coverage / channel_success。

    对齐 RESEARCH_PIPELINE §10.1（切片 6 真实口径）：
    - 只统计 required 子问题与计划通道；
    - question_coverage = 有至少一条 available Evidence 的 required 问题 / required 总数；
    - channel_success = 成功产出至少一条 available Evidence 的计划通道 / 计划通道总数。

    planning_questions 为空（旧 planning 无 questions 结构）时不得用近似口径：
    §10.1 分子/分母必须来自 Planning 稳定结构（评审 🔴4/🟡6），缺失即发布失败。
    """
    if not planning_questions:
        raise ReportPublishFailedException(
            "Planning 未产出 questions 稳定结构，无法计算真实完整度，报告不可发布（§10.1）"
        )
    required = [q for q in planning_questions if q.get("required")]
    required_questions = len(required)
    # §10.2：Planning 产生零个 required 子问题 → Schema 校验失败，不发布
    if required_questions == 0:
        raise ReportPublishFailedException("零 required 子问题，报告不可发布（§10.2）")
    required_qids = {q.get("question_id") for q in required if q.get("question_id")}
    if not required_qids:
        # 防御：questions 缺 question_id（不应发生，校验会派生）
        required_qids = {f"q{i}" for i in range(1, required_questions + 1)}

    covered_qids = set(
        (
            await session.execute(
                select(EvidenceItem.question_id).where(
                    EvidenceItem.task_id == task.id,
                    EvidenceItem.question_id.in_(required_qids),
                    EvidenceItem.validity == "available",
                )
            )
        ).scalars()
    )
    question_coverage = compute_question_coverage(required_questions, len(covered_qids))

    planned_channels = set()
    for q in required:
        planned_channels.update(q.get("planned_channels") or [])
    succeeded: set[str] = set()
    if planned_channels:
        source_types = set(
            (
                await session.execute(
                    select(EvidenceItem.source_type).where(
                        EvidenceItem.task_id == task.id,
                        EvidenceItem.question_id.in_(required_qids),
                        EvidenceItem.validity == "available",
                    )
                )
            ).scalars()
        )
        for ch in planned_channels:
            if _CHANNEL_SOURCE_TYPE.get(ch) in source_types:
                succeeded.add(ch)
    channel_success = compute_channel_success(len(planned_channels), len(succeeded))
    return question_coverage, channel_success


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
        critical = bool(c.get("critical"))

        # §10.2 门禁 4（§11 重跑引用闭包）：Claim 关系必须闭合到当前 Task 的
        # Evidence，未知/跨任务 evidence 一律发布失败，不静默忽略（评审 🔴4）。
        valid_relations: list[dict] = []
        for rel in c.get("relations", []) or []:
            if not isinstance(rel, dict):
                continue
            evidence_id = rel.get("evidence_item_id")
            if evidence_id is None or evidence_id not in evidence_by_id:
                raise ReportPublishFailedException(
                    detail=(
                        f"Claim 关系未闭合到当前 Task 的 Evidence（§10.2 门禁 4）: "
                        f"statement={statement[:40]!r}"
                    )
                )
            valid_relations.append(rel)

        # §10.2 门禁 3：每个 critical Claim 必须至少一条 supports Relation（评审 🔴4）
        if critical and not any(r.get("relation_type") == "supports" for r in valid_relations):
            raise ReportPublishFailedException(
                detail=(
                    f"critical Claim 缺少 supports 关系（§10.2 门禁 3）: "
                    f"statement={statement[:40]!r}"
                )
            )

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

        # §9 门禁 4：重复 (claim, evidence, relation_type) 合并，不能覆盖其他关系类型。
        # 同 key 去重并保留更高 confidence（DATABASE.md §7.5 (claim,evidence,relation_type) 唯一）。
        merged: dict[tuple[int, str], dict] = {}
        for rel in valid_relations:
            evidence_id = rel["evidence_item_id"]
            relation_type = rel.get("relation_type", "context")
            key = (evidence_id, relation_type)
            confidence = float(rel.get("confidence", 0.0))
            if key not in merged or confidence > merged[key]["confidence"]:
                merged[key] = {
                    "evidence_id": evidence_id,
                    "relation_type": relation_type,
                    "confidence": confidence,
                }

        for rel in merged.values():
            session.add(
                EvidenceRelation(
                    claim_id=claim.id,
                    evidence_id=rel["evidence_id"],
                    relation_type=rel["relation_type"],
                    confidence=rel["confidence"],
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
    sections: list,
    index_to_evidence_id: dict[int, int],
    claims_raw: list[dict],
    evidence_by_id: dict,
    planning_questions: list[dict] | None = None,
    language: str = "zh",
    content_hash: str | None = None,
    limitations_summary: str | None = None,
) -> ReportRevision:
    """目标态原子发布报告 Revision（切片 4 单写口径，RESEARCH_PIPELINE §11）。

    切片 4 起 Renderer 单写：revision 发布时直接据渲染 DTO 创建 revision 专属
    sections（revision_id 归属）并在同一事务同步写 `section_evidence`（证据引用
    经 `index_to_evidence_id` 解析、按 §9 门禁 1 闭合到当前 Task）。
    不再复制/挂载 task 级迁移态 sections。reports/revision 的级联删除只影响
    revision 专属副本。

    Args:
        sections: 渲染 DTO 列表（鸭子类型），每项需提供 `heading`、`content`
            与 `sources`（list[dict]，每项含 `evidence_index`）。
        index_to_evidence_id: evidence_index → evidence_item_id 映射。
        claims_raw: Evidence Graph 的 claims（含 relations）。
        planning_questions: Planning 稳定结构 questions（§5.1），用于完整度真实口径；
            为空时发布失败（真实口径唯一，评审 🔴4/🟡6）。

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

        # 切片 4 单写：直接据渲染 DTO 创建 revision 专属 sections，并同步写 section_evidence
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

        # §9 门禁 1 / §10.2 门禁 4（§11 重跑引用闭包）：章节引用必须闭合到当前
        # Task 的 Evidence；无法闭合的引用发布失败，不静默丢弃（评审 🔴4）。
        for rs, section in zip(revision_sections, sections):
            for src in section.sources or []:
                evidence_id = index_to_evidence_id.get(src["evidence_index"])
                if evidence_id is None or evidence_id not in evidence_by_id:
                    raise ReportPublishFailedException(
                        detail=(
                            f"章节引用未闭合到当前 Task 的 Evidence（§10.2 门禁 4）: "
                            f"section={section.heading!r}, evidence_index={src.get('evidence_index')!r}"
                        )
                    )
                session.add(SectionEvidence(section_id=rs.id, evidence_id=evidence_id))
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

        # 完整度三分项（切片 6 真实口径，RESEARCH_PIPELINE §10.1）
        critical_claims = [c for c in claims_raw if isinstance(c, dict) and c.get("critical")]
        if not critical_claims:
            # §10.2：Synthesis 产生零个 critical Claim，报告不可发布
            raise ReportPublishFailedException("零 critical Claim，报告不可发布（§10.2）")
        critical_with_supports = sum(
            1
            for c in critical_claims
            if any(r.get("relation_type") == "supports" for r in (c.get("relations") or []))
        )

        question_coverage, channel_success = await _compute_real_coverage(
            session, task, planning_questions
        )
        claim_coverage = compute_claim_coverage(
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
