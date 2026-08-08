"""切片 6 —— 完整度真实口径验收测试（RESEARCH_PIPELINE §5.1/§10.1/§10.2）。

1. Planning 稳定结构 questions[{question_id, required, planned_channels}]：LLM 缺失时派生；
2. publish_report 用 Planning questions + evidence question_id 计算真实分子/分母；
3. 零 required 子问题、零 critical Claim 发布失败（§10.2）；
4. Revision 摘要持久化 numerator/denominator/ratio/score/rule_version。
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from app.core.exceptions import ReportPublishFailedException
from app.core.llm import LLMResult
from app.evaluation.completeness import build_completeness_summary
from app.models.evidence_item import EvidenceItem
from app.models.research_source import ResearchSource
from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask
from app.pipeline.planner import _derive_questions, _validate_questions, run_planning
from app.services.report_publisher import publish_report

USER_ID = "550e8400-e29b-41d4-a716-446655440000"


class TestBuildSummaryNumeratorDenominator:
    def test_三分项分子分母与score(self):
        summary = build_completeness_summary(
            question_coverage=(0.75, 3, 4),
            channel_success=(0.5, 1, 2),
            claim_coverage=(0.5, 1, 2),
        )
        assert summary["question_coverage"] == {
            "numerator": 3,
            "denominator": 4,
            "ratio": 0.75,
        }
        assert summary["channel_success"] == {"numerator": 1, "denominator": 2, "ratio": 0.5}
        assert summary["claim_coverage"] == {"numerator": 1, "denominator": 2, "ratio": 0.5}
        assert summary["score"] == 0.625  # 0.5*0.75 + 0.25*0.5 + 0.25*0.5
        assert summary["rule_version"] == 1


class TestPlannerQuestions:
    async def test_LLM无questions时按策略派生(self, db_session):
        task = ResearchTask(
            id="task-plan-q-1",
            user_id=USER_ID,
            topic="量子计算",
            requirements={"task_type": "analysis", "language": "zh"},
            source_strategy="hybrid",
            status="running",
        )
        db_session.add(task)
        await db_session.flush()
        step = ResearchStep(
            id="step-plan-q-1", task_id=task.id, step_type="planning", status="running"
        )
        db_session.add(step)
        await db_session.flush()
        sse = AsyncMock()

        llm_content = json.dumps(
            {
                "sub_questions": [
                    "量子计算对 RSA 加密的威胁分析",
                    "后量子密码学标准化进展评估",
                    "各国量子安全迁移策略对比",
                ],
                "rationale": "拆解",
            },
            ensure_ascii=False,
        )
        with patch("app.pipeline.planner.chat_completion") as mock_llm:
            mock_llm.return_value = LLMResult(
                content=llm_content,
                reasoning_content="",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            )
            output = await run_planning(task, step, db_session, sse)

        questions = output["questions"]
        assert len(questions) == 3
        for i, q in enumerate(questions, start=1):
            assert q["question_id"] == f"q{i}"
            assert q["required"] is True
            assert q["planned_channels"] == ["knowledge", "web"]  # hybrid 策略

    async def test_LLM输出questions被接受(self, db_session):
        task = ResearchTask(
            id="task-plan-q-2",
            user_id=USER_ID,
            topic="量子计算",
            requirements={"task_type": "analysis", "language": "zh"},
            source_strategy="web",
            status="running",
        )
        db_session.add(task)
        await db_session.flush()
        step = ResearchStep(
            id="step-plan-q-2", task_id=task.id, step_type="planning", status="running"
        )
        db_session.add(step)
        await db_session.flush()
        sse = AsyncMock()

        llm_content = json.dumps(
            {
                "sub_questions": [
                    "量子计算对 RSA 加密的威胁分析",
                    "后量子密码学标准化进展评估",
                    "各国量子安全迁移策略对比",
                ],
                "questions": [
                    {
                        "question_id": "q1",
                        "text": "量子计算对 RSA 加密的威胁分析",
                        "required": True,
                        "planned_channels": ["web"],
                    },
                    {
                        "question_id": "q2",
                        "text": "后量子密码学标准化进展评估",
                        "required": False,
                        "planned_channels": ["web"],
                    },
                    {
                        "question_id": "q3",
                        "text": "各国量子安全迁移策略对比",
                        "required": True,
                        "planned_channels": ["web"],
                    },
                ],
                "rationale": "拆解",
            },
            ensure_ascii=False,
        )
        with patch("app.pipeline.planner.chat_completion") as mock_llm:
            mock_llm.return_value = LLMResult(
                content=llm_content,
                reasoning_content="",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            )
            output = await run_planning(task, step, db_session, sse)

        required = [q for q in output["questions"] if q["required"]]
        assert len(required) == 2

    def test_validate_questions_非法通道报错(self):
        errors = _validate_questions(
            [
                {
                    "question_id": "q1",
                    "text": "a",
                    "required": True,
                    "planned_channels": ["chromadb"],
                },
                {"question_id": "q2", "text": "b", "required": True, "planned_channels": ["web"]},
            ],
            ["a", "b"],
        )
        assert any("非法通道" in e for e in errors)

    def test_derive_questions_全required(self):
        questions = _derive_questions(["a", "b", "c"], "knowledge")
        assert all(q["required"] for q in questions)
        assert questions[0]["planned_channels"] == ["knowledge"]


async def _seed_publish_task(db_session, *, planning_questions, evidence_question_map):
    """预置 task + planning questions + evidence（带 question_id）的任务。

    evidence_question_map: list[(question_id, source_type)]，可含同 question 多通道。
    """
    task = ResearchTask(
        id="task-real-001",
        user_id=USER_ID,
        topic="真实完整度测试",
        requirements={"task_type": "analysis", "language": "zh"},
        source_strategy="hybrid",
        status="running",
        total_steps=7,
        total_evidence=3,
    )
    db_session.add(task)
    await db_session.flush()

    plan_step = ResearchStep(
        id="step-plan-real-001",
        task_id=task.id,
        step_type="planning",
        status="completed",
        output={"sub_questions": ["q1", "q2", "q3"], "questions": planning_questions},
    )
    db_session.add(plan_step)
    await db_session.flush()

    render_step = ResearchStep(
        id="step-render-real-001",
        task_id=task.id,
        step_type="render",
        status="running",
    )
    db_session.add(render_step)
    await db_session.flush()

    evidence_by_id: dict = {}
    for i, (qid, source_type) in enumerate(evidence_question_map):
        src = ResearchSource(
            task_id=task.id,
            url=f"https://real-{i}.example.com",
            title=f"来源{i}",
            domain="example.com",
        )
        db_session.add(src)
        await db_session.flush()
        ev = EvidenceItem(
            task_id=task.id,
            source_type=source_type,
            source_id=src.id,
            question_id=qid,
            validity="available",
            relevance_score=0.9,
        )
        db_session.add(ev)
        await db_session.flush()
        evidence_by_id[ev.id] = ev
    return task, render_step, evidence_by_id


def _one_critical_claim(evidence_id):
    return [
        {
            "statement": "关键结论。",
            "critical": True,
            "certainty": "high",
            "qualification": None,
            "relations": [
                {"evidence_item_id": evidence_id, "relation_type": "supports", "confidence": 0.9}
            ],
        }
    ]


class TestPublishRealCompleteness:
    async def test_真实分子分母(self, db_session):
        planning_questions = [
            {"question_id": "q1", "text": "q1", "required": True, "planned_channels": ["web"]},
            {
                "question_id": "q2",
                "text": "q2",
                "required": True,
                "planned_channels": ["knowledge", "web"],
            },
            {"question_id": "q3", "text": "q3", "required": False, "planned_channels": ["web"]},
        ]
        # q1→web evidence，q2→knowledge + web evidence
        task, render_step, evidence_by_id = await _seed_publish_task(
            db_session,
            planning_questions=planning_questions,
            evidence_question_map=[("q1", "web"), ("q2", "internal"), ("q2", "web")],
        )
        ev_ids = list(evidence_by_id.keys())
        sections = [SimpleNamespace(heading="1", content="正文", sources=[])]

        rev = await publish_report(
            db_session,
            task=task,
            build_step_id=str(render_step.id),
            title="真实完整度",
            sections=sections,
            index_to_evidence_id={},
            claims_raw=_one_critical_claim(ev_ids[0]),
            evidence_by_id=evidence_by_id,
            planning_questions=planning_questions,
        )

        summary = rev.evidence_completeness
        # required = q1, q2（2 个）；covered = q1, q2（2 个）→ 2/2
        assert summary["question_coverage"]["numerator"] == 2
        assert summary["question_coverage"]["denominator"] == 2
        assert summary["question_coverage"]["ratio"] == 1.0
        # 通道 = {web, knowledge}（2）；web/internal 各成功 → 2/2
        assert summary["channel_success"]["numerator"] == 2
        assert summary["channel_success"]["denominator"] == 2
        # claim = 1 critical with supports → 1/1
        assert summary["claim_coverage"]["numerator"] == 1
        assert summary["claim_coverage"]["denominator"] == 1
        assert summary["score"] == 1.0
        assert summary["rule_version"] == 1

    async def test_零required_发布失败(self, db_session):
        planning_questions = [
            {"question_id": "q1", "text": "q1", "required": False, "planned_channels": ["web"]},
            {"question_id": "q2", "text": "q2", "required": False, "planned_channels": ["web"]},
        ]
        task, render_step, evidence_by_id = await _seed_publish_task(
            db_session,
            planning_questions=planning_questions,
            evidence_question_map=[("q1", "web")],
        )
        ev_ids = list(evidence_by_id.keys())
        sections = [SimpleNamespace(heading="1", content="正文", sources=[])]

        with pytest.raises(ReportPublishFailedException) as exc_info:
            await publish_report(
                db_session,
                task=task,
                build_step_id=str(render_step.id),
                title="零required",
                sections=sections,
                index_to_evidence_id={},
                claims_raw=_one_critical_claim(ev_ids[0]),
                evidence_by_id=evidence_by_id,
                planning_questions=planning_questions,
            )
        assert "零 required 子问题" in str(exc_info.value.detail)

    async def test_零critical_发布失败(self, db_session):
        planning_questions = [
            {"question_id": "q1", "text": "q1", "required": True, "planned_channels": ["web"]},
        ]
        task, render_step, evidence_by_id = await _seed_publish_task(
            db_session,
            planning_questions=planning_questions,
            evidence_question_map=[("q1", "web")],
        )
        sections = [SimpleNamespace(heading="1", content="正文", sources=[])]

        with pytest.raises(ReportPublishFailedException) as exc_info:
            await publish_report(
                db_session,
                task=task,
                build_step_id=str(render_step.id),
                title="零critical",
                sections=sections,
                index_to_evidence_id={},
                claims_raw=[
                    {"statement": "非关键", "critical": False, "certainty": "low", "relations": []}
                ],
                evidence_by_id=evidence_by_id,
                planning_questions=planning_questions,
            )
        assert "零 critical Claim" in str(exc_info.value.detail)
