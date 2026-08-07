#!/usr/bin/env python3
"""AC-003 深度研究任务成功率验证入口。

对齐 TESTING.md §5（AC-003：冻结评估集的 Research Task 统计）、PRD §12
（深度研究任务成功率 ≥ 95%，排除用户主动取消）与 §7 发布记录模板：
对冻结评估集（JSON 任务清单）中已完成的研究任务统计终态分布，
成功率 = (completed + partially_completed) / (completed + partially_completed + failed)，
canceled（用户主动取消）不进入分母。

不伪造结果：评估集缺失/非法、指定任务不存在或非终态时逐条记录；
全部任务不可评估时直接报错退出。

用法:
  python scripts/verify_ac003_task_success.py --tasks tests/eval/research_eval_set.json
  python scripts/verify_ac003_task_success.py --tasks eval_set.json --require-status completed
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.database import async_session_factory  # noqa: E402
from app.evaluation.ac_metrics import compute_task_success_rate  # noqa: E402
from app.models.research_task import ResearchTask  # noqa: E402

THRESHOLD = 0.95
# 任务清单条目：{id, task_id} 或 {id, topic}；topic 匹配时按 user+topic 找最新任务
ALLOWED_STATUSES = {"completed", "partially_completed", "failed", "canceled"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AC-003 深度研究任务成功率验证")
    parser.add_argument("--tasks", required=True,
                        help="冻结评估集 JSON：[{id, task_id}] 或 [{id, topic}]")
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


async def _resolve_task(session, entry: dict) -> ResearchTask | None:
    """按 task_id 或 (topic) 解析任务；topic 命中取该用户最新一条。"""
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


async def run() -> int:
    args = _parse_args()
    eval_set = _load_eval_set(Path(args.tasks))
    print(f"[AC-003] 评估集: {args.tasks}（{len(eval_set)} 条）")

    status_counts: dict[str, int] = {
        "completed": 0,
        "partially_completed": 0,
        "failed": 0,
        "canceled": 0,
    }
    problems: list[str] = []

    async with async_session_factory() as session:
        for entry in eval_set:
            task = await _resolve_task(session, entry)
            label = f"#{entry.get('id')}"
            if task is None:
                problems.append(f"{label}: 任务不存在")
                continue
            status = task.status
            if status not in ALLOWED_STATUSES:
                problems.append(f"{label} ({task.id}): 非终态（{status}）")
                continue
            status_counts[status] += 1

    success, denominator, rate = compute_task_success_rate(status_counts)
    canceled = status_counts["canceled"]

    print(f"  任务数: {sum(status_counts.values())}，成功: {success}，"
          f"分母（排除取消）: {denominator}，canceled: {canceled}")
    print(f"  成功率: {rate:.2%}（门槛 ≥ {THRESHOLD:.0%}）")
    for p in problems:
        print(f"  - {p}")

    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True,
        ).strip()
    except Exception:  # noqa: BLE001
        commit = "unknown"
    print("\n===== 发布记录模板（TESTING.md §7）=====")
    print(f"候选版本/提交：{commit}")
    print(f"环境与资源：research_db")
    print(f"数据集版本：{args.tasks}")
    print(f"执行命令：{' '.join(sys.argv)}")
    verdict = "通过" if denominator > 0 and rate >= THRESHOLD else "未通过"
    print(f"通过/失败/跳过：{verdict}（成功率 {rate:.2%}）")
    print("已知偏差与批准人：")
    print("证据链接：")

    return 0 if denominator > 0 and rate >= THRESHOLD else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
