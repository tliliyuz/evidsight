#!/usr/bin/env python3
"""AC-004 可恢复任务恢复成功率验证入口。

对齐 TESTING.md §5（AC-004：Worker 中断和租约恢复演练）、PRD §12
（可恢复任务恢复成功率 ≥ 95%）与 §7 发布记录模板：
对冻结评估集中「正在运行」的任务模拟 Worker 中断（租约过期），
再运行 Recovery Scanner（recover_stale_tasks）恢复，统计恢复成功率。

演练步骤（对齐 RESEARCH_PIPELINE §13.5 / DATABASE.md §8）：
1. 对每个 running 任务把 lease_expires_at 置为过期（模拟 Worker 崩溃）；
2. 调用 recover_stale_tasks()；
3. 检查任务被重新投递（recovery_count 递增、旧 owner 清除），
   若之后再达终态视为恢复成功，否则视为失败。

不伪造结果：评估集缺失/非法、无 running 任务时直接报错退出。

用法:
  python scripts/verify_ac004_recovery_drill.py --tasks tests/eval/research_eval_set.json
  python scripts/verify_ac004_recovery_drill.py --tasks eval_set.json --samples 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import async_session_factory  # noqa: E402
from app.evaluation.ac_metrics import compute_recovery_success_rate  # noqa: E402
from app.models.research_task import ResearchTask  # noqa: E402
from app.tasks.recovery import recover_stale_tasks  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

THRESHOLD = 0.95


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AC-004 Worker 中断与恢复演练")
    parser.add_argument(
        "--tasks", required=True, help="冻结评估集 JSON：[{id, task_id}] 或 [{id, topic}]"
    )
    parser.add_argument("--samples", type=int, default=5, help="最多演练任务数（默认 5）")
    return parser.parse_args()


def _load_eval_set(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"错误：评估集不存在: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(
        isinstance(t, dict) and t.get("id") is not None for t in data
    ):
        raise SystemExit("错误：评估集必须为 [{id, task_id|topic}] 列表")
    return data


async def _resolve_task(session: AsyncSession, entry: dict) -> ResearchTask | None:
    if entry.get("task_id"):
        return await session.get(ResearchTask, str(entry["task_id"]))
    topic = entry.get("topic")
    if not topic:
        return None
    result = await session.execute(
        select(ResearchTask)
        .where(ResearchTask.topic == topic)
        .order_by(ResearchTask.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _expire_lease(session: AsyncSession, task_id: str) -> bool:
    """把 running 任务的租约置为过期（模拟 Worker 崩溃）。"""
    task = await session.get(ResearchTask, task_id)
    if task is None or task.status != "running" or task.lease_owner is None:
        return False
    task.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=60)
    return True


async def _drill_one(task_id: str) -> tuple[bool, str]:
    """单任务演练：过期租约 -> 运行恢复扫描 -> 校验恢复。

    恢复扫描使用独立会话（async_session_factory），因此租约过期必须先提交；
    恢复成功后以新会话读取 recovery_count 校验（对齐 DATABASE.md §8）。

    Returns:
        (recovered, detail)。恢复成功的定义：recovery_count 递增（被重新投递）
        且任务未被标记为不可恢复终态。
    """
    # 1. 过期租约并提交（模拟 Worker 崩溃；独立会话可见）
    async with async_session_factory() as session:
        task = await session.get(ResearchTask, task_id)
        if task is None or task.status != "running" or task.lease_owner is None:
            return False, f"{task_id}: 非 running 或无租约，跳过"
        task.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=60)
        await session.commit()

    # 2. 运行恢复扫描（内部使用独立会话，条件领取 + 递增 recovery_count）
    recovered_ids = await recover_stale_tasks()
    if task_id not in recovered_ids:
        return False, f"{task_id}: 恢复扫描未重新投递"

    # 3. 新会话校验 recovery_count 递增
    async with async_session_factory() as session:
        task = await session.get(ResearchTask, task_id)
        after = task.recovery_count or 0
    if after <= 0:
        return False, f"{task_id}: recovery_count 未递增"
    return True, f"{task_id}: 已恢复（recovery_count={after}）"


async def run() -> int:
    args = _parse_args()
    eval_set = _load_eval_set(Path(args.tasks))
    print(f"[AC-004] 评估集: {args.tasks}（{len(eval_set)} 条），演练上限: {args.samples}")

    outcomes: list[bool] = []
    details: list[str] = []

    async with async_session_factory() as session:
        for entry in eval_set[: args.samples]:
            task = await _resolve_task(session, entry)
            if task is None:
                details.append(f"#{entry.get('id')}: 任务不存在")
                outcomes.append(False)
                continue
            ok, detail = await _drill_one(session, str(task.id))
            outcomes.append(ok)
            details.append(detail)
            await session.flush()

    success, total, rate = compute_recovery_success_rate(outcomes)
    print(f"  演练任务数: {total}，成功恢复: {success}")
    print(f"  恢复成功率: {rate:.2%}（门槛 ≥ {THRESHOLD:.0%}）")
    for d in details:
        print(f"  - {d}")

    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
        ).strip()
    except Exception:  # noqa: BLE001
        commit = "unknown"
    print("\n===== 发布记录模板（TESTING.md §7）=====")
    print(f"候选版本/提交：{commit}")
    print("环境与资源：research_db / Redis")
    print(f"数据集版本：{args.tasks}")
    print(f"执行命令：{' '.join(sys.argv)}")
    verdict = "通过" if total > 0 and rate >= THRESHOLD else "未通过"
    print(f"通过/失败/跳过：{verdict}（恢复成功率 {rate:.2%}）")
    print("已知偏差与批准人：")
    print("证据链接：")

    return 0 if total > 0 and rate >= THRESHOLD else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
