"""切片 4 —— Report Revision 单写与双 API 同源读取验收测试。

对齐 RESEARCH_PIPELINE §11（切片 4 收敛）/ DATABASE.md §7.3 / §17.2-11：

1. Renderer 不再写 task 级迁移态 sections（revision_id IS NULL）；
2. revision 专属 sections 在同一事务同步写 section_evidence；
3. 旧 API get_report 经 reports → current_revision_id → revision sections 同源读取，
   无 revision 时按「报告尚未生成」失败（与 v1 读取同源）。

RED 预期（目标行为缺失）：用例 1、2 在当前实现（renderer 仍写迁移态 sections、
publish_report 只复制 heading/content/sort_order 不写 revision section_evidence）下失败；
用例 3 在当前实现（get_report 读 task 级 sections）下失败。
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.core.exceptions import TaskStatusConflictException
from app.models.evidence_item import EvidenceItem
from app.models.report import Report
from app.models.report_revision import ReportRevision
from app.models.report_section import ReportSection
from app.models.research_source import ResearchSource
from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask
from app.models.section_evidence import SectionEvidence
from app.pipeline.renderer import run_render
from app.services.research_service import get_report
from sqlalchemy import func, select

from .test_renderer import _mock_llm_report, _seed_render_task, _valid_report_sections


class TestRevisionSingleWrite:
    """验收 1/2：渲染只写 revision sections，并同步写 section_evidence。"""

    async def test_渲染后不再写task级迁移态sections(self, db_session):
        task, render_step, evidence_items = await _seed_render_task(db_session, evidence_count=3)
        sse = AsyncMock()

        with patch("app.pipeline.renderer.chat_completion") as mock_llm:
            mock_llm.return_value = _mock_llm_report(_valid_report_sections())
            await run_render(task, render_step, db_session, sse)

        # 目标行为：无 task 级（revision_id IS NULL）迁移态 sections 写入
        legacy_count = (
            await db_session.execute(
                select(func.count())
                .select_from(ReportSection)
                .where(ReportSection.task_id == task.id, ReportSection.revision_id.is_(None))
            )
        ).scalar()
        assert legacy_count == 0, "Renderer 不应再写 task 级迁移态 sections（单写 revision）"

    async def test_revision_sections同步写section_evidence(self, db_session):
        task, render_step, evidence_items = await _seed_render_task(db_session, evidence_count=3)
        sse = AsyncMock()

        with patch("app.pipeline.renderer.chat_completion") as mock_llm:
            mock_llm.return_value = _mock_llm_report(_valid_report_sections())
            await run_render(task, render_step, db_session, sse)

        report = (
            await db_session.execute(select(Report).where(Report.task_id == task.id))
        ).scalar_one()
        rev = await db_session.get(ReportRevision, report.current_revision_id)
        assert rev is not None and rev.status == "published"

        sections = (
            (
                await db_session.execute(
                    select(ReportSection).where(ReportSection.revision_id == rev.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(sections) == 2
        assoc_count = (
            await db_session.execute(
                select(func.count())
                .select_from(SectionEvidence)
                .where(SectionEvidence.section_id.in_([s.id for s in sections]))
            )
        ).scalar()
        # 两章节引用 0,1 + 0,2 共 4 条引用（_valid_report_sections）
        assert assoc_count == 4, "revision sections 应同步写 section_evidence"


class TestGetReportSameSource:
    """验收 3：旧 API get_report 经 reports → current_revision_id 同源读取。"""

    async def _seed_revision_report(self, db_session, status: str = "completed"):
        """预置含 Evidence Graph 的目标态 reports/revision/sections，同时留一份 task 级迁移态 sections。

        两份 sections 内容可区分：revision 章节 heading 以「revision」结尾，task 级迁移态以「legacy」结尾。
        目标行为 get_report 只返回 revision 章节（同源），不返回迁移态章节。
        """
        task = ResearchTask(
            id="task-rev-same-source-001",
            user_id=1,
            topic="量子计算对密码学的影响",
            requirements={"task_type": "analysis", "max_sources": 10, "language": "zh"},
            status=status,
            total_steps=7,
            completed_steps=7,
            completed_at=datetime(2026, 1, 1, 0, 0, 10, tzinfo=timezone.utc),
        )
        db_session.add(task)
        await db_session.flush()

        source = ResearchSource(
            task_id=task.id,
            url="https://example.com/source-0",
            title="来源 0",
            domain="example.com",
            content="量子计算对 RSA 算法构成严重威胁。",
            fetch_status="success",
            fetched_at=datetime(2026, 1, 1, 0, 0, 3, tzinfo=timezone.utc),
        )
        db_session.add(source)
        await db_session.flush()
        ev = EvidenceItem(
            task_id=task.id,
            source_id=source.id,
            content="量子计算对 RSA 算法构成严重威胁。",
            relevance_score=0.95,
        )
        db_session.add(ev)
        await db_session.flush()

        eg_step = ResearchStep(
            id="step-eg-rev-same-source-001",
            task_id=task.id,
            step_type="evidence_graph",
            status="completed",
            output={
                "graph": {
                    "task_id": task.id,
                    "generated_at": datetime(2026, 1, 1, 0, 0, 7, tzinfo=timezone.utc).isoformat(),
                    "items": [
                        {
                            "index": 0,
                            "evidence_item_id": ev.id,
                            "source_id": source.id,
                            "source_url": source.url,
                            "source_title": source.title,
                            "domain": source.domain,
                            "content": ev.content,
                            "relevance_score": 0.95,
                            "used_in_sections": [],
                        }
                    ],
                    "clusters": [],
                    "conflicts": [],
                    "knowledge_gaps": [],
                    "sources": [
                        {
                            "id": source.id,
                            "url": source.url,
                            "title": source.title,
                            "domain": source.domain,
                            "evidence_count": 1,
                        }
                    ],
                }
            },
            started_at=datetime(2026, 1, 1, 0, 0, 6, tzinfo=timezone.utc),
            completed_at=datetime(2026, 1, 1, 0, 0, 7, tzinfo=timezone.utc),
            duration_ms=1000,
        )
        db_session.add(eg_step)

        report = Report(task_id=task.id)
        db_session.add(report)
        await db_session.flush()
        rev = ReportRevision(
            report_id=report.id,
            revision_number=1,
            status="published",
            title="量子计算对密码学的影响",
            published_at=datetime(2026, 1, 1, 0, 0, 8, tzinfo=timezone.utc),
        )
        db_session.add(rev)
        await db_session.flush()
        report.current_revision_id = rev.id

        section = ReportSection(
            task_id=task.id,
            revision_id=rev.id,
            heading="1. 概述（revision）",
            content="量子计算威胁[来源0]。",
            sort_order=0,
        )
        db_session.add(section)
        await db_session.flush()
        db_session.add(SectionEvidence(section_id=section.id, evidence_id=ev.id))
        await db_session.flush()

        # 额外 task 级迁移态 sections（目标行为不应被读取）
        legacy_section = ReportSection(
            task_id=task.id,
            revision_id=None,
            heading="1. 概述（legacy）",
            content="旧的迁移态正文[来源0]。",
            sort_order=0,
        )
        db_session.add(legacy_section)
        await db_session.flush()
        return task

    async def test_旧API读取revision同源(self, db_session):
        task = await self._seed_revision_report(db_session)

        result = await get_report(db_session, task)

        assert result.report.title == task.topic
        # 只返回 revision 章节，不含 task 级迁移态章节
        assert len(result.report.sections) == 1
        assert result.report.sections[0].heading == "1. 概述（revision）"
        assert len(result.report.sections[0].sources) == 1
        assert result.report.sections[0].sources[0].evidence_index == 0

    async def test_无revision_报告尚未生成(self, db_session):
        task = await self._seed_revision_report(db_session)
        # 删除 reports 根（级联删 revision），模拟只有 task 级迁移态 sections（无目标态发布）
        report = (
            await db_session.execute(select(Report).where(Report.task_id == task.id))
        ).scalar_one()
        await db_session.delete(report)
        await db_session.flush()

        try:
            await get_report(db_session, task)
        except TaskStatusConflictException as exc:
            assert exc.error_code == "E2003"
            inner = (exc.detail or {}).get("detail") or {}
            if isinstance(inner, dict):
                desc = inner.get("error_description") or ""
            else:
                desc = str(exc.detail)
            assert "报告尚未生成" in desc
            return
        raise AssertionError("无目标态 revision 时应抛「报告尚未生成」")
