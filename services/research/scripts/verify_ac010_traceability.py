#!/usr/bin/env python3
"""AC-010 报告 Evidence 来源可追溯性验证入口。

对齐 TESTING.md §5（AC-010：报告 Evidence 自动检查）、PRD §12
（来源可追溯性 100%：展示来源类型；内部证据可定位文档位置，外部证据
展示 URL 与获取时间）与 §7 发布记录模板：
对已完成任务的 evidence_items 逐条校验：
- source_type 必须为 internal|web；
- internal：内部稳定 ID（KB/Document/Version/Segment）与 location_summary 均非空；
- web：canonical_url_snapshot 与 fetched_at_snapshot 均非空。

不伪造结果：任务不存在/非终态/无证据时逐条记录为失败；
全部任务不可评估时直接报错退出。

用法:
  python scripts/verify_ac010_traceability.py --task-id <task_id>
  python scripts/verify_ac010_traceability.py --all-completed --limit 20
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.database import async_session_factory  # noqa: E402
from app.evaluation.ac_metrics import check_evidence_traceability  # noqa: E402
from app.models.evidence_item import EvidenceItem  # noqa: E402
from app.models.research_source import ResearchSource  # noqa: E402
from app.models.research_task import ResearchTask  # noqa: E402

TERMINAL_STATUSES = {"completed", "partially_completed"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AC-010 Evidence 可追溯性验证")
    parser.add_argument("--task-id", help="单个任务 UUID")
    parser.add_argument("--all-completed", action="store_true", help="校验全部已发布报告的任务")
    parser.add_argument(
        "--limit", type=int, default=50, help="--all-completed 时最多任务数（默认 50）"
    )
    return parser.parse_args()


async def _load_source_map(session: AsyncSession, task_id: str) -> dict[int, dict]:
    """research_sources.id -> {url, fetched_at}（web Evidence 的迁移态来源快照）。"""
    result = await session.execute(select(ResearchSource).where(ResearchSource.task_id == task_id))
    sources = list(result.scalars().all())
    return {s.id: {"url": s.url, "fetched_at": s.fetched_at} for s in sources}


async def _load_evidence_dicts(session: AsyncSession, task_id: str) -> list[dict]:
    result = await session.execute(select(EvidenceItem).where(EvidenceItem.task_id == task_id))
    items = list(result.scalars().all())
    source_map = await _load_source_map(session, task_id)
    rows: list[dict] = []
    for it in items:
        row = {
            "id": it.id,
            "source_type": it.source_type,
            "knowledge_base_id": it.knowledge_base_id,
            "document_id": it.document_id,
            "document_version_id": it.document_version_id,
            "segment_id": it.segment_id,
            "location_summary": it.location_summary,
            "canonical_url_snapshot": it.canonical_url_snapshot,
            "fetched_at_snapshot": it.fetched_at_snapshot,
        }
        # 迁移态（DATABASE.md §6.2 / EvidenceItem 模型注释）：web 的 URL 与
        # 获取时间由 research_sources 持有，snapshot 列可空。PRD AC-010 要求
        # 外部证据展示 URL 与获取时间，因此按实际来源回填判定字段。
        if row["source_type"] == "web":
            source = source_map.get(it.source_id) or {}
            row["canonical_url_snapshot"] = row["canonical_url_snapshot"] or source.get("url")
            row["fetched_at_snapshot"] = row["fetched_at_snapshot"] or source.get("fetched_at")
        rows.append(row)
    return rows


async def _evaluate_task(session: AsyncSession, task_id: str) -> dict:
    task = await session.get(ResearchTask, task_id)
    if task is None:
        return {
            "task_id": task_id,
            "ok": False,
            "reason": "任务不存在",
            "traceable": 0,
            "total": 0,
            "rate": 0.0,
        }
    if task.status not in TERMINAL_STATUSES:
        return {
            "task_id": task_id,
            "ok": False,
            "reason": f"任务非终态（{task.status}）",
            "traceable": 0,
            "total": 0,
            "rate": 0.0,
        }

    evidence = await _load_evidence_dicts(session, task_id)
    traceable, total, problems = check_evidence_traceability(evidence)
    ok = total > 0 and traceable == total
    reason = "; ".join(problems) if not ok else ""
    return {
        "task_id": task_id,
        "ok": ok,
        "reason": reason,
        "traceable": traceable,
        "total": total,
        "rate": (traceable / total) if total else 0.0,
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
            print("错误：无可评估任务（全部缺失/非终态/无 Evidence）")
            for r in results:
                print(f"  - {r['task_id']}: {r['reason']}")
            return 2

        traceable = sum(r["traceable"] for r in evaluable)
        total = sum(r["total"] for r in evaluable)
        rate = traceable / total
        failed = [r for r in results if not r["ok"]]

    print(f"[AC-010] 任务数: {len(task_ids)}，可评估: {len(evaluable)}")
    print(f"  Evidence 总数: {total}，可追溯: {traceable}")
    print(f"  追溯率: {rate:.2%}（门槛 100%）")
    for r in failed:
        print(f"  - {r['task_id']}: {r['traceable']}/{r['total']} ({r['rate']:.2%}) {r['reason']}")

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
    verdict = "通过" if total > 0 and rate >= 1.0 else "未通过"
    print(f"通过/失败/跳过：{verdict}（追溯率 {rate:.2%}）")
    print("已知偏差与批准人：")
    print("证据链接：")

    return 0 if total > 0 and rate >= 1.0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
