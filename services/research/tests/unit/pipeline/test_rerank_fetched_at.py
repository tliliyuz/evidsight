"""Web Evidence 获取时间快照持久化测试。

对齐 DATABASE.md §6.2（Web 来源字段 fetched_at_snapshot）与 PRD AC-010
（外部证据展示 URL 与获取时间）：web EvidenceItem 持久化时必须写入
fetched_at_snapshot（来自 research_sources.fetched_at）。
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.core.llm import LLMResult
from app.models.evidence_item import EvidenceItem
from app.models.research_source import ResearchSource
from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask
from app.pipeline.reranker import run_rerank


def _make_llm_result(ratings: list[dict]) -> LLMResult:
    return LLMResult(
        content=json.dumps({"ratings": ratings}, ensure_ascii=False),
        reasoning_content="",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
    )


def _valid_ratings(count: int) -> list[dict]:
    return [
        {"segment_index": i, "score": 8.0, "rationale": "ok"}
        for i in range(count)
    ]


async def _seed_task(db_session) -> tuple[ResearchTask, ResearchStep]:
    task = ResearchTask(
        id="task-fetched-at-001",
        user_id=1,
        topic="话题",
        requirements={"task_type": "explainer", "max_sources": 2, "language": "zh"},
        status="running",
        total_steps=2,
        completed_steps=1,
    )
    db_session.add(task)
    await db_session.flush()

    planning = ResearchStep(
        id="step-fetched-plan",
        task_id=task.id,
        step_type="planning",
        status="completed",
        output={"sub_questions": ["问题一"]},
        completed_at=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
    )
    db_session.add(planning)

    rerank_step = ResearchStep(
        id="step-fetched-rerank",
        task_id=task.id,
        step_type="rerank",
        status="running",
    )
    db_session.add(rerank_step)
    await db_session.flush()
    return task, rerank_step


class TestWebEvidenceFetchedAt:
    """web EvidenceItem 持久化 fetched_at_snapshot。"""

    @pytest.mark.asyncio
    async def test_webEvidence_持久化fetched_at快照(self, db_session):
        """Rerank 后 web Evidence 的 fetched_at_snapshot 等于 research_sources.fetched_at。"""
        task, rerank_step = await _seed_task(db_session)
        fetch_time = datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc)
        db_session.add(ResearchSource(
            task_id=task.id,
            url="https://example.com/a",
            title="外部网页A",
            domain="example.com",
            content="正文内容只有一段，用于单候选精排。",
            fetch_status="success",
            fetched_at=fetch_time,
        ))
        await db_session.flush()

        sse = AsyncMock()
        with patch("app.pipeline.reranker.chat_completion",
                   return_value=_make_llm_result(_valid_ratings(1))):
            await run_rerank(task, rerank_step, db_session, sse)

        result = await db_session.execute(
            select(EvidenceItem).where(EvidenceItem.task_id == task.id)
        )
        items = list(result.scalars().all())
        assert len(items) >= 1
        web_items = [i for i in items if i.source_type == "web"]
        assert len(web_items) >= 1
        # PRD AC-010：外部证据展示 URL 与获取时间
        for item in web_items:
            assert item.canonical_url_snapshot == "https://example.com/a"
            assert item.fetched_at_snapshot == fetch_time
