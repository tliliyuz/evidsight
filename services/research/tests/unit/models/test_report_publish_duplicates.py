"""Report 目标态发布 —— 重复 evidence_relations 合并测试。

对齐 RESEARCH_PIPELINE §9 门禁 4 / DATABASE.md §7.5：
- (claim_id, evidence_id, relation_type) 唯一；
- 重复 (claim, evidence, relation_type) 合并，不能覆盖其他关系类型。
"""

from app.models.evidence_item import EvidenceItem
from app.models.evidence_relation import EvidenceRelation
from app.models.report import Report
from app.models.report_section import ReportSection
from app.models.research_source import ResearchSource
from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask
from app.services.report_publisher import publish_report
from sqlalchemy import select


async def _seed_publish_task(db_session, task_suffix="dup"):
    task = ResearchTask(
        id=f"task-pub-dup-{task_suffix}",
        user_id="550e8400-e29b-41d4-a716-446655440000",
        topic="重复关系合并测试",
        requirements={"task_type": "explainer", "max_sources": 3, "language": "zh"},
        status="running",
    )
    db_session.add(task)
    await db_session.flush()

    step = ResearchStep(
        id=f"step-pub-dup-{task_suffix}",
        task_id=task.id,
        step_type="render",
        status="running",
    )
    db_session.add(step)
    await db_session.flush()

    evidence_by_id: dict = {}
    for i in range(2):
        src = ResearchSource(
            task_id=task.id, url=f"https://d{i}.example.com", title=f"来源{i}", domain="example.com"
        )
        db_session.add(src)
        await db_session.flush()
        ev = EvidenceItem(
            task_id=task.id,
            source_type="web",
            source_id=src.id,
            canonical_url_snapshot=f"https://d{i}.example.com",
            display_title=f"来源{i}",
            relevance_score=0.9 - i * 0.1,
        )
        db_session.add(ev)
        await db_session.flush()
        evidence_by_id[ev.id] = ev
    return task, step, evidence_by_id


class TestDuplicateRelationMerge:
    async def test_重复claim_evidence_relation_type_合并为一条(self, db_session):
        """§9 门禁 4：同一 (claim, evidence, relation_type) 只落库一条，不重复 INSERT。"""
        task, step, evidence_by_id = await _seed_publish_task(db_session)
        ev_ids = list(evidence_by_id.keys())

        sections = [
            ReportSection(
                task_id=task.id,
                heading="1. 概述",
                content="正文",
                sort_order=0,
            )
        ]

        revision = await publish_report(
            db_session,
            task=task,
            build_step_id=str(step.id),
            title="重复关系合并",
            sections=sections,
            claims_raw=[
                {
                    "statement": "结论。",
                    "critical": True,
                    "certainty": "high",
                    "qualification": "待验证。",
                    "relations": [
                        {
                            "evidence_item_id": ev_ids[0],
                            "relation_type": "supports",
                            "confidence": 0.9,
                        },
                        {
                            "evidence_item_id": ev_ids[0],
                            "relation_type": "supports",
                            "confidence": 0.8,
                        },
                        {
                            "evidence_item_id": ev_ids[0],
                            "relation_type": "context",
                            "confidence": 0.5,
                        },
                    ],
                }
            ],
            evidence_by_id=evidence_by_id,
        )

        report = (
            await db_session.execute(select(Report).where(Report.task_id == task.id))
        ).scalar_one()
        assert report.current_revision_id == revision.id

        rels = (
            (
                await db_session.execute(
                    select(EvidenceRelation).where(EvidenceRelation.claim_id.is_not(None))
                )
            )
            .scalars()
            .all()
        )

        # (ev0, supports) 合并为一条；不同 relation_type（context）保留
        supports = [r for r in rels if r.relation_type == "supports"]
        context = [r for r in rels if r.relation_type == "context"]
        assert len(supports) == 1
        assert len(context) == 1
        # 合并后 confidence 取更高值
        assert float(supports[0].confidence) == 0.9
