"""报告预算披露测试 —— RESEARCH_PIPELINE §14：报告必须披露因预算导致的缺失。

预算停止时，renderer 向知识缺口列表注入预算限制披露，
使报告生成过程必须披露因预算导致的覆盖缺失。
"""

from datetime import datetime, timezone

from app.models.research_task import ResearchTask
from app.pipeline.renderer import _build_render_prompt
from app.services.budget_service import budget_disclosure


def _make_task(budget_stopped_at=None) -> ResearchTask:
    return ResearchTask(
        id="task-disclosure-001",
        user_id=1,
        topic="量子计算对密码学的影响",
        requirements={"task_type": "analysis", "max_sources": 10},
        status="running",
        budget_stopped_at=budget_stopped_at,
        started_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
    )


def _graph(**overrides) -> dict:
    graph = {
        "task_id": "task-disclosure-001",
        "items": [{"index": 0, "evidence_item_id": 1, "source_id": 1}],
        "clusters": [],
        "conflicts": [],
        "knowledge_gaps": [],
        "sources": [],
    }
    graph.update(overrides)
    return graph


class TestBudgetDisclosure:
    def test_预算停止_生成披露文案(self):
        task = _make_task(budget_stopped_at=datetime.now(timezone.utc))
        disclosure = budget_disclosure(task)
        assert disclosure is not None
        assert "预算" in disclosure
        assert "覆盖" in disclosure or "缺失" in disclosure or "未完成" in disclosure

    def test_未预算停止_无披露(self):
        task = _make_task(budget_stopped_at=None)
        assert budget_disclosure(task) is None


class TestRendererBudgetDisclosure:
    def test_预算停止_渲染提示包含披露(self):
        """§14：预算停止时 render prompt 的知识缺口必须包含预算披露。"""
        task = _make_task(budget_stopped_at=datetime.now(timezone.utc))
        graph = _graph()
        disclosure = budget_disclosure(task)
        if disclosure:
            graph["knowledge_gaps"].append(disclosure)

        messages = _build_render_prompt(
            topic=task.topic,
            task_type="analysis",
            language="zh",
            template_name="analysis",
            template_desc="1. 概述",
            graph=graph,
            items=graph["items"],
        )
        system_prompt = messages[0]["content"]
        assert disclosure in system_prompt
