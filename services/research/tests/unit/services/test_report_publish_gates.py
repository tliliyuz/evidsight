"""Report 发布硬门槛验收测试 —— RESEARCH_PIPELINE §10.2 / §11 / 评审 🔴4。

- 门禁 3：每个 critical Claim 必须至少一条闭合的 supports Relation，否则发布失败；
- 门禁 4：所有引用（章节引用 / Claim 关系）必须闭合到当前 Task 的 Evidence，
  否则发布失败（§11 发布流程第 3 步「重新运行引用闭包」）；
- 真实口径唯一：planning_questions 缺失时不得使用 total_steps/total_evidence
  近似口径，发布失败（§10.1 分子/分母必须来自 Planning 稳定结构）。
"""

from types import SimpleNamespace

import pytest
from app.core.exceptions import ReportPublishFailedException
from app.models.evidence_item import EvidenceItem
from app.models.research_source import ResearchSource
from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask
from app.services.report_publisher import publish_report
from sqlalchemy.ext.asyncio import AsyncSession

PLANNING_QUESTIONS = [
    {"question_id": "q1", "text": "问题", "required": True, "planned_channels": ["web"]}
]


async def _seed_publish_task(db_session: AsyncSession):
    task = ResearchTask(
        id="task-gate-1",
        user_id="550e8400-e29b-41d4-a716-446655440000",
        topic="发布门槛测试",
        requirements={"task_type": "explainer", "max_sources": 3, "language": "zh"},
        status="running",
    )
    db_session.add(task)
    await db_session.flush()
    step = ResearchStep(id="step-gate-1", task_id=task.id, step_type="render", status="running")
    db_session.add(step)
    await db_session.flush()

    evidence_by_id: dict = {}
    for i in range(2):
        src = ResearchSource(
            task_id=task.id,
            url=f"https://g{i}.example.com",
            title=f"来源{i}",
            domain="example.com",
        )
        db_session.add(src)
        await db_session.flush()
        ev = EvidenceItem(
            task_id=task.id,
            source_type="web",
            source_id=src.id,
            canonical_url_snapshot=f"https://g{i}.example.com",
            display_title=f"来源{i}",
            relevance_score=0.9 - i * 0.1,
            question_id="q1",
        )
        db_session.add(ev)
        await db_session.flush()
        evidence_by_id[ev.id] = ev
    return task, step, evidence_by_id


def _supports_claim(evidence_id) -> dict:
    return {
        "statement": "关键结论。",
        "critical": True,
        "certainty": "high",
        "qualification": "待验证。",
        "relations": [
            {"evidence_item_id": evidence_id, "relation_type": "supports", "confidence": 0.9}
        ],
    }


class TestGate3CriticalClaimSupports:
    """§10.2 门禁 3：每个 critical Claim 必须至少一条 supports Relation。"""

    async def test_criticalClaim无supports_发布失败(self, db_session):
        task, step, evidence_by_id = await _seed_publish_task(db_session)
        ev_id = list(evidence_by_id.keys())[0]
        sections = [SimpleNamespace(heading="1. 概述", content="正文", sources=[])]

        with pytest.raises(ReportPublishFailedException):
            await publish_report(
                db_session,
                task=task,
                build_step_id=str(step.id),
                title="t",
                sections=sections,
                index_to_evidence_id={},
                claims_raw=[
                    {
                        "statement": "关键结论。",
                        "critical": True,
                        "certainty": "high",
                        "relations": [
                            {
                                "evidence_item_id": ev_id,
                                "relation_type": "context",
                                "confidence": 0.5,
                            }
                        ],
                    }
                ],
                evidence_by_id=evidence_by_id,
                planning_questions=PLANNING_QUESTIONS,
            )

    async def test_criticalClaim有supports_发布成功(self, db_session):
        task, step, evidence_by_id = await _seed_publish_task(db_session)
        ev_id = list(evidence_by_id.keys())[0]
        sections = [SimpleNamespace(heading="1. 概述", content="正文", sources=[])]

        revision = await publish_report(
            db_session,
            task=task,
            build_step_id=str(step.id),
            title="t",
            sections=sections,
            index_to_evidence_id={},
            claims_raw=[_supports_claim(ev_id)],
            evidence_by_id=evidence_by_id,
            planning_questions=PLANNING_QUESTIONS,
        )
        assert revision.status == "published"


class TestGate4ReferenceClosure:
    """§10.2 门禁 4：所有引用闭合到当前 Task 的 Evidence（§11 重跑引用闭包）。"""

    async def test_章节引用未知index_发布失败(self, db_session):
        task, step, evidence_by_id = await _seed_publish_task(db_session)
        ev_id = list(evidence_by_id.keys())[0]
        sections = [
            SimpleNamespace(
                heading="1. 概述",
                content="正文[来源999]。",
                sources=[{"evidence_index": 999}],
            )
        ]

        with pytest.raises(ReportPublishFailedException):
            await publish_report(
                db_session,
                task=task,
                build_step_id=str(step.id),
                title="t",
                sections=sections,
                index_to_evidence_id={},
                claims_raw=[_supports_claim(ev_id)],
                evidence_by_id=evidence_by_id,
                planning_questions=PLANNING_QUESTIONS,
            )

    async def test_Claim关系引用未知evidence_发布失败(self, db_session):
        task, step, evidence_by_id = await _seed_publish_task(db_session)
        sections = [SimpleNamespace(heading="1. 概述", content="正文", sources=[])]

        with pytest.raises(ReportPublishFailedException):
            await publish_report(
                db_session,
                task=task,
                build_step_id=str(step.id),
                title="t",
                sections=sections,
                index_to_evidence_id={},
                claims_raw=[
                    {
                        "statement": "关键结论。",
                        "critical": True,
                        "certainty": "high",
                        "relations": [
                            {
                                "evidence_item_id": "99999999-9999-4999-8999-999999999999",
                                "relation_type": "supports",
                                "confidence": 0.9,
                            }
                        ],
                    }
                ],
                evidence_by_id=evidence_by_id,
                planning_questions=PLANNING_QUESTIONS,
            )


class TestRealCompletenessOnly:
    """评审 🔴4：真实口径唯一，planning_questions 缺失时不得用近似口径。"""

    async def test_无planning_questions_发布失败(self, db_session):
        task, step, evidence_by_id = await _seed_publish_task(db_session)
        ev_id = list(evidence_by_id.keys())[0]
        sections = [SimpleNamespace(heading="1. 概述", content="正文", sources=[])]

        with pytest.raises(ReportPublishFailedException):
            await publish_report(
                db_session,
                task=task,
                build_step_id=str(step.id),
                title="t",
                sections=sections,
                index_to_evidence_id={},
                claims_raw=[_supports_claim(ev_id)],
                evidence_by_id=evidence_by_id,
            )
