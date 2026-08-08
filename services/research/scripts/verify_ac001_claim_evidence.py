#!/usr/bin/env python3
"""AC-001 关键结论有效引用率验证入口。

对齐 TESTING.md §5（AC-001：Claim—Evidence 关系自动检查 + 试点评审）、
PRD §12（关键结论有效引用率 ≥ 90%）与 §7 发布记录模板：
对已完成 Research Task 的每一份报告章节，解析正文中的 [来源N] 引用，
校验每个引用是否闭合到该章节实际关联且存在于 Evidence Graph 的 Evidence；
有效引用率 = 有效引用数 / 总引用数。

范围说明：本脚本只覆盖 AC-001 的「自动检查」部分（引用闭合率）。
「试点评审」（对评估集逐条人工核验结论与证据关系，PRD §12）由发布评审
另行执行，不在本脚本范围内；不得将本脚本结果单独视为 AC-001 的完整通过证据。

不伪造结果：任务不存在、状态非终态或报告缺失时逐条记录为失败；
指定任务均不可评估时直接报错退出（不返回通过）。

用法:
  python scripts/verify_ac001_claim_evidence.py --task-id <task_id>
  python scripts/verify_ac001_claim_evidence.py --all-completed --limit 20
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import async_session_factory  # noqa: E402
from app.evaluation.ac_metrics import evaluate_citation_validity  # noqa: E402
from app.models.report import Report  # noqa: E402
from app.models.report_section import ReportSection  # noqa: E402
from app.models.research_step import ResearchStep  # noqa: E402
from app.models.research_task import ResearchTask  # noqa: E402
from app.models.section_evidence import SectionEvidence  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

TERMINAL_STATUSES = {"completed", "partially_completed"}
THRESHOLD = 0.90


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AC-001 关键结论有效引用率验证")
    parser.add_argument("--task-id", help="单个任务 UUID")
    parser.add_argument("--all-completed", action="store_true", help="评估全部已发布报告的任务")
    parser.add_argument(
        "--limit", type=int, default=50, help="--all-completed 时最多评估任务数（默认 50）"
    )
    return parser.parse_args()


async def _load_sections(session: AsyncSession, task_id: str) -> list[ReportSection]:
    """切片 4 单写同源：经 reports → current_revision_id → revision sections 读取。"""
    report = (
        await session.execute(select(Report).where(Report.task_id == task_id))
    ).scalar_one_or_none()
    if report is None or not report.current_revision_id:
        return []
    result = await session.execute(
        select(ReportSection)
        .where(ReportSection.revision_id == report.current_revision_id)
        .order_by(ReportSection.sort_order)
    )
    return list(result.scalars().all())


async def _load_section_evidence(
    session: AsyncSession, section_ids: list[int]
) -> dict[int, list[int]]:
    mapping: dict[int, list[int]] = {}
    if not section_ids:
        return mapping
    result = await session.execute(
        select(SectionEvidence.section_id, SectionEvidence.evidence_id).where(
            SectionEvidence.section_id.in_(section_ids)
        )
    )
    for section_id, evidence_id in result.all():
        mapping.setdefault(section_id, []).append(evidence_id)
    return mapping


async def _load_evidence_index(session: AsyncSession, task_id: str) -> dict[int, int]:
    """evidence_item_id -> Evidence Graph index（来自 evidence_graph step output）。"""
    stmt = (
        select(ResearchStep)
        .where(
            ResearchStep.task_id == task_id,
            ResearchStep.step_type == "evidence_graph",
            ResearchStep.status == "completed",
        )
        .order_by(ResearchStep.completed_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    eg_step: ResearchStep | None = result.scalar_one_or_none()
    if eg_step is None or not isinstance(eg_step.output, dict):
        return {}
    items = (eg_step.output.get("graph") or {}).get("items") or []
    index: dict[int, int] = {}
    for item in items:
        if isinstance(item, dict) and "evidence_item_id" in item and "index" in item:
            index[int(item["evidence_item_id"])] = int(item["index"])
    return index


async def _evaluate_task(session: AsyncSession, task_id: str) -> dict:
    """评估单个任务的引用闭合率。"""
    task = await session.get(ResearchTask, task_id)
    if task is None:
        return {
            "task_id": task_id,
            "ok": False,
            "reason": "任务不存在",
            "valid": 0,
            "total": 0,
            "rate": 0.0,
        }
    if task.status not in TERMINAL_STATUSES:
        return {
            "task_id": task_id,
            "ok": False,
            "reason": f"任务非终态（{task.status}）",
            "valid": 0,
            "total": 0,
            "rate": 0.0,
        }

    sections = await _load_sections(session, task_id)
    if not sections:
        return {
            "task_id": task_id,
            "ok": False,
            "reason": "无报告章节",
            "valid": 0,
            "total": 0,
            "rate": 0.0,
        }

    section_evidence = await _load_section_evidence(session, [s.id for s in sections])
    evidence_index = await _load_evidence_index(session, task_id)

    section_dicts = [{"id": s.id, "content": s.content} for s in sections]
    valid, total, rate = evaluate_citation_validity(section_dicts, section_evidence, evidence_index)
    ok = total > 0 and rate >= THRESHOLD
    reason = "" if ok else "引用闭合率低于门槛或无可评估引用"
    return {
        "task_id": task_id,
        "ok": ok,
        "reason": reason,
        "valid": valid,
        "total": total,
        "rate": rate,
    }


async def _collect_task_ids(session: AsyncSession, args: argparse.Namespace) -> list[str]:
    if args.task_id:
        return [args.task_id]
    result = await session.execute(
        select(ResearchTask.id)
        .where(ResearchTask.status.in_(TERMINAL_STATUSES))
        .order_by(ResearchTask.completed_at.desc())
        .limit(args.limit)
    )
    return [str(row[0]) for row in result.all()]


async def run() -> int:
    args = _parse_args()
    async with async_session_factory() as session:
        task_ids = await _collect_task_ids(session, args)
        if not task_ids:
            print("错误：未找到可评估任务（--task-id 或 --all-completed 为空）")
            return 2

        results = [await _evaluate_task(session, tid) for tid in task_ids]
        evaluable = [r for r in results if r["total"] > 0]
        if not evaluable:
            print("错误：无可评估任务（全部缺失/非终态/无报告）")
            for r in results:
                print(f"  - {r['task_id']}: {r['reason']}")
            return 2

        valid = sum(r["valid"] for r in evaluable)
        total = sum(r["total"] for r in evaluable)
        rate = valid / total
        failed = [r for r in results if not r["ok"]]

    print(f"[AC-001] 任务数: {len(task_ids)}，可评估: {len(evaluable)}")
    print(f"  引用总数: {total}，有效引用: {valid}")
    print(f"  有效引用率: {rate:.2%}（门槛 ≥ {THRESHOLD:.0%}）")
    for r in failed:
        print(f"  - {r['task_id']}: 引用 {r['valid']}/{r['total']} ({r['rate']:.2%}) {r['reason']}")

    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
        ).strip()
    except Exception:  # noqa: BLE001
        commit = "unknown"
    print("\n===== 发布记录模板（TESTING.md §7）=====")
    print(f"候选版本/提交：{commit}")
    print(f"环境与资源：research_db（{', '.join(sys.argv)}）")
    print(f"数据集版本：{' '.join(sys.argv)}")
    print(f"执行命令：{' '.join(sys.argv)}")
    verdict = "通过" if total > 0 and rate >= THRESHOLD else "未通过"
    print(f"通过/失败/跳过：{verdict}（有效引用率 {rate:.2%}）")
    print("已知偏差与批准人：")
    print("证据链接：")

    return 0 if total > 0 and rate >= THRESHOLD else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
