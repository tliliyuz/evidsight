"""切片 5 —— 存量报告迁移验收测试（DATABASE.md §12-4 / §7.3）。

切片 4 前新渲染写 task 级迁移态 sections（revision_id IS NULL）。本测试验证迁移
service `migrate_legacy_report_sections`：

1. 为有 task 级 sections 且无 reports 根的终态任务创建 Report + published Revision 1；
2. 把 task 级 sections 归入 Revision（revision_id 更新），保留 section_evidence；
3. 幂等可重跑：第二次无候选可迁移；
4. 已有 reports 根的任务跳过；非终态任务跳过（保留 task 级 sections 待渲染发布）；
5. dry_run 只扫描不写入。
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.models.evidence_item import EvidenceItem
from app.models.report import Report
from app.models.report_revision import ReportRevision
from app.models.report_section import ReportSection
from app.models.research_source import ResearchSource
from app.models.research_task import ResearchTask
from app.models.section_evidence import SectionEvidence
from app.services import legacy_report_migration
from app.services.legacy_report_migration import migrate_legacy_report_sections
from sqlalchemy import func, select

USER_ID = "550e8400-e29b-41d4-a716-446655440000"


async def _seed_legacy_task(
    db_session,
    task_id: str,
    *,
    status: str = "completed",
    with_evidence: bool = True,
    section_count: int = 2,
):
    """预置含 task 级迁移态 sections（revision_id IS NULL）的任务。"""
    task = ResearchTask(
        id=task_id,
        user_id=USER_ID,
        topic=f"存量报告 {task_id}",
        requirements={"task_type": "analysis", "language": "zh"},
        status=status,
        total_steps=7,
        completed_steps=7,
        completed_at=datetime(2026, 1, 1, 0, 0, 10, tzinfo=timezone.utc),
    )
    db_session.add(task)
    await db_session.flush()

    evidence_ids: list[int] = []
    if with_evidence:
        src = ResearchSource(
            task_id=task.id,
            url=f"https://example.com/{task_id}",
            title="来源",
            domain="example.com",
            content="正文",
            fetch_status="success",
        )
        db_session.add(src)
        await db_session.flush()
        ev = EvidenceItem(
            task_id=task.id,
            source_id=src.id,
            content="正文",
            relevance_score=0.9,
        )
        db_session.add(ev)
        await db_session.flush()
        evidence_ids.append(ev.id)

    sections: list[ReportSection] = []
    for i in range(section_count):
        section = ReportSection(
            task_id=task.id,
            heading=f"章节 {i + 1}",
            content=f"正文 {i + 1}",
            sort_order=i,
        )
        db_session.add(section)
        await db_session.flush()
        sections.append(section)
        if evidence_ids:
            db_session.add(SectionEvidence(section_id=section.id, evidence_id=evidence_ids[0]))
    await db_session.flush()
    return task, sections, evidence_ids


class TestMigrateLegacySections:
    async def test_创建Report与Revision1并归入sections保留evidence(self, db_session):
        task, sections, evidence_ids = await _seed_legacy_task(db_session, "legacy-mig-1")

        result = await migrate_legacy_report_sections(db_session)

        assert result.failed == 0
        assert result.migrated == 1
        assert result.scanned == 1

        # Report + published Revision 1
        report = (
            await db_session.execute(select(Report).where(Report.task_id == task.id))
        ).scalar_one()
        rev = (
            await db_session.execute(
                select(ReportRevision).where(ReportRevision.report_id == report.id)
            )
        ).scalar_one()
        assert rev.status == "published"
        assert rev.revision_number == 1
        assert report.current_revision_id == rev.id

        # sections 归入 revision，保留 section_evidence
        await db_session.refresh(sections[0])
        await db_session.refresh(sections[1])
        assert sections[0].revision_id == rev.id
        assert sections[1].revision_id == rev.id
        if evidence_ids:
            se_count = (
                await db_session.execute(
                    select(func.count())
                    .select_from(SectionEvidence)
                    .where(
                        SectionEvidence.section_id.in_([s.id for s in sections]),
                        SectionEvidence.evidence_id == evidence_ids[0],
                    )
                )
            ).scalar()
            assert se_count == 2

        # 无 task 级 sections 残留
        remaining = (
            (
                await db_session.execute(
                    select(ReportSection).where(
                        ReportSection.task_id == task.id, ReportSection.revision_id.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(remaining) == 0

    async def test_幂等_二次迁移无候选(self, db_session):
        task, _, _ = await _seed_legacy_task(db_session, "legacy-mig-2")
        first = await migrate_legacy_report_sections(db_session)
        second = await migrate_legacy_report_sections(db_session)

        assert first.migrated == 1
        assert second.migrated == 0
        assert second.scanned == 0  # 无 task 级 sections 残留，无候选
        # 仍只有一个 published revision（不重复创建）
        rev_count = (
            await db_session.execute(select(func.count()).select_from(ReportRevision))
        ).scalar()
        assert rev_count == 1

    async def test_已有reports根的任务跳过(self, db_session):
        task, sections, _ = await _seed_legacy_task(db_session, "legacy-mig-3")
        # 预置 reports 根 + current_revision_id
        report = Report(task_id=task.id)
        db_session.add(report)
        await db_session.flush()
        rev = ReportRevision(
            report_id=report.id,
            revision_number=1,
            status="published",
            title=task.topic,
        )
        db_session.add(rev)
        await db_session.flush()
        report.current_revision_id = rev.id
        await db_session.flush()

        result = await migrate_legacy_report_sections(db_session)

        assert result.migrated == 0
        assert result.skipped == 1
        # 未创建第二个 report
        report_count = (await db_session.execute(select(func.count()).select_from(Report))).scalar()
        assert report_count == 1

    async def test_非终态任务跳过_保留task级sections(self, db_session):
        task, sections, _ = await _seed_legacy_task(db_session, "legacy-mig-4", status="running")

        result = await migrate_legacy_report_sections(db_session)

        assert result.migrated == 0
        assert result.skipped == 1
        # 无 reports 根，task 级 sections 保留（待任务完成后经渲染发布）
        report = (
            await db_session.execute(select(Report).where(Report.task_id == task.id))
        ).scalar_one_or_none()
        assert report is None
        await db_session.refresh(sections[0])
        assert sections[0].revision_id is None

    async def test_dry_run_只扫描不写入(self, db_session):
        task, _, _ = await _seed_legacy_task(db_session, "legacy-mig-5")

        result = await migrate_legacy_report_sections(db_session, dry_run=True)

        assert result.migrated == 1  # dry-run 也统计可迁移数
        report = (
            await db_session.execute(select(Report).where(Report.task_id == task.id))
        ).scalar_one_or_none()
        assert report is None, "dry-run 不应写入"


class _TrackingSessionContextManager:
    """包装测试 session 供脚本复用，保留真实 commit（用于断言脚本显式提交）。"""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TestScriptCommitsMigration:
    """评审 🔴5：迁移脚本非 dry-run 必须显式 session.commit()。

    否则退出 `async with async_session_factory()` 时未提交写入被回滚，
    脚本仍返回成功（迁移实际未落库）。
    """

    async def test_脚本非dryrun_显式提交迁移(self, db_session, monkeypatch):
        import scripts.migrate_legacy_report_sections as script

        task, _, _ = await _seed_legacy_task(db_session, "legacy-script-1")

        commit_spy = AsyncMock()
        monkeypatch.setattr(db_session, "commit", commit_spy)

        def _factory():
            return _TrackingSessionContextManager(db_session)

        monkeypatch.setattr(script, "async_session_factory", _factory)
        monkeypatch.setattr(script, "_parse_args", lambda: SimpleNamespace(dry_run=False))

        rc = await script.run()

        assert rc == 0
        assert commit_spy.await_count >= 1, "非 dry-run 必须显式提交迁移写入"

    async def test_脚本dryrun_不提交(self, db_session, monkeypatch):
        import scripts.migrate_legacy_report_sections as script

        await _seed_legacy_task(db_session, "legacy-script-2")

        commit_spy = AsyncMock()
        monkeypatch.setattr(db_session, "commit", commit_spy)

        def _factory():
            return _TrackingSessionContextManager(db_session)

        monkeypatch.setattr(script, "async_session_factory", _factory)
        monkeypatch.setattr(script, "_parse_args", lambda: SimpleNamespace(dry_run=True))

        rc = await script.run()

        assert rc == 0
        assert commit_spy.await_count == 0, "dry-run 只扫描不提交"


class TestResidualValidationMembership:
    """评审 🔴5：迁移后残留校验必须正确命中。

    candidates 为 (task_id, task) 元组列表；原先用字符串 tid 直接判成员
    永不命中，残留校验形同虚设。
    """

    async def test_迁移失败任务_残留校验命中(self, db_session):
        await _seed_legacy_task(db_session, "legacy-residual-1")
        await _seed_legacy_task(db_session, "legacy-residual-2")

        real = legacy_report_migration._migrate_one

        async def _fail_second(session, task):
            if task.id == "legacy-residual-2":
                raise RuntimeError("模拟迁移失败")
            await real(session, task)

        with patch.object(legacy_report_migration, "_migrate_one", side_effect=_fail_second):
            result = await migrate_legacy_report_sections(db_session)

        assert result.failed >= 1
        assert any("残留" in err for err in result.errors), "残留校验未命中失败任务"
