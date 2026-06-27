"""离线评估 CLI 实现

通过 argparse 提供单任务/批量任务的离线检索评估入口。
"""

import argparse
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.evaluation.aggregator import aggregate_reports, evaluate_task, evaluate_tasks
from app.evaluation.constants import TARGETS
from app.evaluation.manual import (
    aggregate_manual_records,
    load_all_manual_rounds,
    load_manual_records,
)
from app.evaluation.system_eval import check_system_targets, evaluate_system_reliability
from app.models.research_task import ResearchTask


def _build_parser() -> argparse.ArgumentParser:
    """构建 argparse 解析器。"""
    parser = argparse.ArgumentParser(
        prog="eval_offline",
        description="ResearchMind 离线 Pipeline 检索评估",
    )
    parser.add_argument(
        "--task-id",
        type=str,
        help="单个任务 UUID",
    )
    parser.add_argument(
        "--all-completed",
        action="store_true",
        help="评估所有 completed / partially_completed 任务",
    )
    parser.add_argument(
        "--system",
        action="store_true",
        help="同时评估系统级可靠性指标（Task Completion Rate + LLM Call Success Rate），可与 --all-completed 联用",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="批量评估时的最大任务数（默认 50）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式输出报告",
    )
    parser.add_argument(
        "--manual-round",
        dest="manual_round",
        type=str,
        help="人工评估轮次目录（如 eval/manual/round1），加载并聚合该目录下 JSON 记录",
    )
    parser.add_argument(
        "--manual-all-rounds",
        dest="manual_all_rounds",
        action="store_true",
        help="聚合 eval/manual/round* 下所有轮次的人工评估记录",
    )
    return parser


async def _load_completed_task_ids(session: AsyncSession, limit: int) -> list[str]:
    """加载最近完成的任务的 ID 列表。"""
    result = await session.execute(
        select(ResearchTask.id)
        .where(ResearchTask.status.in_(["completed", "partially_completed"]))
        .order_by(ResearchTask.completed_at.desc())
        .limit(limit)
    )
    return [row[0] for row in result.all()]


def _render_report(report: Any) -> str:
    """将单任务报告渲染为人类可读文本。"""
    data = report.to_dict() if hasattr(report, "to_dict") else report
    lines = [
        f"任务 ID: {data['task_id']}",
        f"主题: {data['topic']}",
        f"状态: {data['status']}",
        f"任务类型: {data['task_type']}",
        "",
        "--- Search ---",
    ]
    search = data.get("search") or {}
    lines.extend(
        [
            f"  子问题数: {search.get('sub_question_count', 0)}",
            f"  总结果数: {search.get('total_results', 0)}",
            f"  Coverage Rate: {search.get('coverage_rate', 0.0):.2%}",
            f"  Recall@5: {search.get('recall_at_k', 0.0):.2%}",
        ]
    )

    fetch = data.get("fetch") or {}
    lines.extend(
        [
            "",
            "--- Fetch ---",
            f"  成功: {fetch.get('successful', 0)}",
            f"  失败: {fetch.get('failed', 0)}",
            f"  安全拦截: {fetch.get('skipped_safety', 0)}",
            f"  Success Rate: {fetch.get('success_rate', 0.0):.2%}",
        ]
    )

    rerank = data.get("rerank") or {}
    lines.extend(
        [
            "",
            "--- Rerank ---",
            f"  Evidence 数: {rerank.get('evidence_count', 0)}",
            f"  平均分: {rerank.get('mean_score', 0.0):.3f}",
            f"  中位数: {rerank.get('median_score', 0.0):.3f}",
            f"  高质量占比: {rerank.get('high_quality_ratio', 0.0):.2%}",
        ]
    )

    lines.extend(
        [
            "",
            f"整体通过: {'✅' if data.get('overall_pass') else '❌'}",
        ]
    )
    return "\n".join(lines)


def _render_aggregate(aggregate: dict[str, Any]) -> str:
    """将聚合报告渲染为人类可读文本。"""
    lines = [
        f"任务数: {aggregate['task_count']}",
        f"通过率: {aggregate.get('pass_rate', 0.0):.2%}",
        "",
        "--- Search 平均 ---",
    ]
    search = aggregate.get("search") or {}
    lines.extend(
        [
            f"  Coverage Rate: {search.get('mean_coverage_rate', 0.0):.2%}",
            f"  Recall@5: {search.get('mean_recall_at_k', 0.0):.2%}",
        ]
    )

    fetch = aggregate.get("fetch") or {}
    lines.extend(
        [
            "",
            "--- Fetch 平均 ---",
            f"  Success Rate: {fetch.get('mean_success_rate', 0.0):.2%}",
        ]
    )

    rerank = aggregate.get("rerank") or {}
    lines.extend(
        [
            "",
            "--- Rerank 平均 ---",
            f"  平均分: {rerank.get('mean_mean_score', 0.0):.3f}",
            f"  中位数: {rerank.get('mean_median_score', 0.0):.3f}",
            f"  高质量占比: {rerank.get('mean_high_quality_ratio', 0.0):.2%}",
        ]
    )

    system = aggregate.get("system")
    if system:
        lines.append("")
        lines.append(_render_system_block(system))

    return "\n".join(lines)


def _render_system_block(system: dict[str, Any]) -> str:
    """渲染系统可靠性指标块。"""
    targets = TARGETS
    tc_target = targets.get("task_completion_rate", 0.0)
    llm_target = targets.get("llm_call_success_rate", 0.0)

    tc_pass = system["task_completion_rate"] > tc_target
    llm_pass = system["llm_call_success_rate"] > llm_target

    lines = [
        "--- 系统可靠性 ---",
        f"  Task Completion Rate: {system['task_completion_rate']:.2%} "
        f"({'✅' if tc_pass else '❌'} 目标 > {tc_target:.0%})",
        f"    completed={system['task_completed']} partially_completed={system['task_partially_completed']} "
        f"failed={system['task_failed']} canceled={system['task_canceled']}",
        f"  LLM Call Success Rate: {system['llm_call_success_rate']:.2%} "
        f"({'✅' if llm_pass else '❌'} 目标 > {llm_target:.0%})",
        f"    completed={system['llm_calls_completed']} failed={system['llm_calls_failed']}",
    ]
    return "\n".join(lines)


def _render_manual_aggregate(aggregate: dict[str, Any]) -> str:
    """将人工评估聚合结果渲染为人类可读文本。"""
    lines = [
        f"记录数: {aggregate['record_count']}",
        f"总体平均分: {aggregate['overall_mean']:.2f}",
        "",
        "--- 维度平均分 ---",
    ]
    for dimension, mean_score in aggregate.get("dimension_means", {}).items():
        lines.append(f"  {dimension}: {mean_score:.2f}")

    task_type_means = aggregate.get("task_type_means") or {}
    if task_type_means:
        lines.extend(["", "--- task_type 平均分 ---"])
        for task_type, mean_score in task_type_means.items():
            lines.append(f"  {task_type}: {mean_score:.2f}")

    round_means = aggregate.get("round_means") or {}
    if round_means:
        lines.extend(["", "--- 轮次平均分 ---"])
        for round_key, mean_score in round_means.items():
            lines.append(f"  第 {round_key} 轮: {mean_score:.2f}")

    lines.extend(
        [
            "",
            f"最低维度: {aggregate['min_dimension']} ({aggregate['min_dimension_mean']:.2f})",
        ]
    )
    return "\n".join(lines)


async def run_cli(argv: list[str] | None = None) -> int:
    """CLI 主入口。

    Returns:
        退出码：0 表示成功，1 表示评估未通过或参数错误。
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if (
        not args.task_id
        and not args.all_completed
        and not args.manual_round
        and not args.manual_all_rounds
    ):
        parser.error("请提供 --task-id、--all-completed、--manual-round 或 --manual-all-rounds")

    if args.manual_round and args.manual_all_rounds:
        parser.error("--manual-round 与 --manual-all-rounds 不能同时使用")

    if args.manual_round:
        records = load_manual_records(args.manual_round)
        aggregate = aggregate_manual_records(records)
        data = aggregate.to_dict()
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(_render_manual_aggregate(data))
        return 0

    if args.manual_all_rounds:
        records = load_all_manual_rounds()
        aggregate = aggregate_manual_records(records)
        data = aggregate.to_dict()
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(_render_manual_aggregate(data))
        return 0

    async with async_session_factory() as session:
        if args.task_id:
            report = await evaluate_task(session, args.task_id, targets=TARGETS)
            if args.system:
                system = await evaluate_system_reliability(session, targets=TARGETS)
                data = report.to_dict()
                data["system"] = system.to_dict()
                if args.json:
                    print(json.dumps(data, ensure_ascii=False, indent=2))
                else:
                    print(_render_report(report))
                    print()
                    print(_render_system_block(system.to_dict()))
            elif args.json:
                print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
            else:
                print(_render_report(report))
            return 0 if report.overall_pass else 1

        task_ids = await _load_completed_task_ids(session, args.limit)
        reports = await evaluate_tasks(session, task_ids, targets=TARGETS)
        system = await evaluate_system_reliability(session, targets=TARGETS) if args.system else None
        aggregate = aggregate_reports(reports, system=system)
        if args.json:
            print(json.dumps(aggregate, ensure_ascii=False, indent=2))
        else:
            print(_render_aggregate(aggregate))
        return 0
