"""Evidence 与 Report 读取服务 —— 对齐 API.md §9 / DATABASE.md §7。

提供 task READ 权限下的只读查询：
- list_task_evidence：任务证据列表（internal/web 区分，内部无正文）；
- get_evidence_by_external_id：单条证据（按对外 UUID）；
- list_evidence_relations：证据的 supports/contradicts/context 关系；
- get_report_detail：报告（published Revision、章节、引用、完整度摘要）；
- get_report_section：单章节（按 section 对外 UUID）。

内部证据不返回正文（ADR-003）；web 证据返回 URL 与获取时间快照。
"""

import logging
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import TaskNotFoundException
from app.models.evidence_item import EvidenceItem
from app.models.evidence_relation import EvidenceRelation
from app.models.report import Report
from app.models.report_revision import ReportRevision
from app.models.report_section import ReportSection
from app.models.research_task import ResearchTask

logger = logging.getLogger(__name__)


def _iso(value) -> str | None:
    """datetime → ISO 8601（UTC aware），naive 视为 UTC。"""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _evidence_to_dict(ev: EvidenceItem) -> dict:
    """EvidenceItem → 公开 DTO（内部无正文，web 含 URL/获取时间快照）。"""
    dto: dict = {
        "evidence_id": ev.external_id,
        "task_id": ev.task_id,
        "source_type": ev.source_type,
        "display_title": ev.display_title,
        "location_summary": ev.location_summary,
        "source_observed_at": _iso(ev.source_observed_at),
        "score_summary": ev.score_summary,
        "validity": ev.validity,
        "relevance_score": float(ev.relevance_score) if ev.relevance_score is not None else None,
        "used_in_sections": ev.used_in_sections or [],
    }
    if ev.source_type == "internal":
        dto.update(
            {
                "knowledge_base_id": ev.knowledge_base_id,
                "document_id": ev.document_id,
                "document_version_id": ev.document_version_id,
                "segment_id": ev.segment_id,
                "document_display_name_snapshot": ev.document_display_name_snapshot,
                # 内部 Evidence 不含正文（ADR-003）
                "content": None,
            }
        )
    else:
        dto.update(
            {
                "url": ev.canonical_url_snapshot,
                "fetched_at": _iso(ev.fetched_at_snapshot),
                "content": ev.content,
            }
        )
    return dto


async def _get_task_owned(db: AsyncSession, task_id: str) -> ResearchTask:
    task = await db.get(ResearchTask, task_id)
    if task is None:
        raise TaskNotFoundException(task_id)
    return task


async def list_task_evidence(db: AsyncSession, task: ResearchTask) -> dict:
    """任务证据列表（按 relevance_score 降序）。"""
    stmt = (
        select(EvidenceItem)
        .where(EvidenceItem.task_id == task.id)
        .order_by(EvidenceItem.relevance_score.desc())
    )
    result = await db.execute(stmt)
    items = [_evidence_to_dict(ev) for ev in result.scalars().all()]
    return {"items": items, "total": len(items)}


async def _load_evidence_by_external_id(db: AsyncSession, evidence_id: str) -> EvidenceItem | None:
    stmt = select(EvidenceItem).where(EvidenceItem.external_id == evidence_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_evidence_detail(db: AsyncSession, evidence_id: str) -> dict | None:
    """单条证据（按对外 UUID）。调用方需先完成 task READ 权限校验。"""
    ev = await _load_evidence_by_external_id(db, evidence_id)
    if ev is None:
        return None
    return _evidence_to_dict(ev)


async def list_evidence_relations(db: AsyncSession, evidence_id: str) -> dict | None:
    """证据的 supports/contradicts/context 关系（含关联 Claim 摘要）。"""
    ev = await _load_evidence_by_external_id(db, evidence_id)
    if ev is None:
        return None
    stmt = (
        select(EvidenceRelation)
        .options(selectinload(EvidenceRelation.claim))
        .where(EvidenceRelation.evidence_id == ev.id)
        .order_by(EvidenceRelation.relation_type)
    )
    result = await db.execute(stmt)
    items = []
    for rel in result.scalars().all():
        claim = rel.claim
        items.append(
            {
                "relation_id": rel.id,
                "relation_type": rel.relation_type,
                "confidence": float(rel.confidence),
                "rationale_summary": rel.rationale_summary,
                "claim": {
                    "claim_id": claim.id if claim else None,
                    "statement": claim.statement if claim else None,
                    "certainty": claim.certainty if claim else None,
                    "qualification": claim.qualification if claim else None,
                },
            }
        )
    return {"items": items, "total": len(items)}


def _section_to_dict(section: ReportSection, evidence_refs: list[dict]) -> dict:
    return {
        "section_id": section.external_id,
        "heading": section.heading,
        "content": section.content,
        "sequence": section.sort_order,
        "evidence": evidence_refs,
    }


async def get_report_detail(db: AsyncSession, report_id: str) -> dict | None:
    """报告详情（published Revision、章节、引用与完整度摘要）。"""
    report = await db.get(Report, report_id)
    if report is None:
        return None
    rev = (
        await db.get(ReportRevision, report.current_revision_id)
        if report.current_revision_id
        else None
    )
    if rev is None or rev.status != "published":
        return None

    stmt = (
        select(ReportSection)
        .where(ReportSection.revision_id == rev.id)
        .order_by(ReportSection.sort_order)
    )
    result = await db.execute(stmt)
    sections = list(result.scalars().all())

    # 章节引用：按 section_evidence 关联证据（外部 UUID + 来源类型）
    from app.models.section_evidence import SectionEvidence

    section_ids = [s.id for s in sections]
    ref_map: dict[int, list[dict]] = {sid: [] for sid in section_ids}
    if section_ids:
        assoc = await db.execute(
            select(SectionEvidence.section_id, SectionEvidence.evidence_id).where(
                SectionEvidence.section_id.in_(section_ids)
            )
        )
        assoc_rows = list(assoc.all())
        evidence_ids = list({eid for _, eid in assoc_rows})
        ev_map: dict[int, EvidenceItem] = {}
        if evidence_ids:
            evs = await db.execute(select(EvidenceItem).where(EvidenceItem.id.in_(evidence_ids)))
            ev_map = {ev.id: ev for ev in evs.scalars().all()}
        for sid, eid in assoc_rows:
            ev = ev_map.get(eid)
            if ev is None:
                continue
            ref_map.setdefault(sid, []).append(
                {
                    "evidence_id": ev.external_id,
                    "source_type": ev.source_type,
                    "url": ev.canonical_url_snapshot if ev.source_type == "web" else None,
                    "fetched_at": _iso(ev.fetched_at_snapshot) if ev.source_type == "web" else None,
                }
            )

    return {
        "report_id": report.id,
        "task_id": report.task_id,
        "revision": rev.revision_number,
        "status": rev.status,
        "title": rev.title,
        "language": rev.language,
        "evidence_completeness": rev.evidence_completeness,
        "limitations_summary": rev.limitations_summary,
        "published_at": _iso(rev.published_at),
        "sections": [_section_to_dict(s, ref_map.get(s.id, [])) for s in sections],
    }


async def get_report_section(
    db: AsyncSession, report_id: str, section_external_id: str
) -> dict | None:
    """报告单章节（按 section 对外 UUID，且属于该报告当前 published Revision）。"""
    report = await db.get(Report, report_id)
    if report is None or not report.current_revision_id:
        return None
    stmt = select(ReportSection).where(
        ReportSection.external_id == section_external_id,
        ReportSection.revision_id == report.current_revision_id,
    )
    result = await db.execute(stmt)
    section = result.scalar_one_or_none()
    if section is None:
        return None
    return _section_to_dict(section, [])
