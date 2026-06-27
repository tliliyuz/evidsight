"""离线评估报告聚合器

整合 Search / Fetch / Rerank 三阶段指标，生成单任务或多任务评估报告，
并与目标值对比得出 overall_pass。
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import TaskNotFoundException
from app.evaluation.constants import TARGETS
from app.evaluation.fetch_eval import evaluate_fetch
from app.evaluation.loader import (
    load_evidence_items,
    load_step_output,
    load_task,
)
from app.evaluation.models import (
    FetchMetrics,
    PipelineEvaluationReport,
    RerankMetrics,
    SearchMetrics,
    SystemReliabilityMetrics,
)
from app.evaluation.rerank_eval import evaluate_rerank
from app.evaluation.search_eval import evaluate_search


async def evaluate_task(
    session: AsyncSession,
    task_id: str,
    targets: dict[str, float] | None = None,
) -> PipelineEvaluationReport:
    """对单个已完成任务执行离线检索评估。

    Args:
        session: 异步数据库会话。
        task_id: 任务 UUID。
        targets: 自定义目标值字典，默认使用 constants.TARGETS。

    Returns:
        PipelineEvaluationReport。

    Raises:
        ResourceNotFoundException: 任务不存在。
        ValueError: 任务状态不是 completed / partially_completed，无法评估。
    """
    task = await load_task(session, task_id)
    if task is None:
        raise TaskNotFoundException(task_id=task_id)

    if task.status not in {"completed", "partially_completed"}:
        raise ValueError(f"任务状态为 {task.status}，仅 completed / partially_completed 可评估")

    effective_targets = dict(targets if targets is not None else TARGETS)

    search_output = await load_step_output(session, task_id, "search", output_key="sub_question_results")
    fetch_output = await load_step_output(session, task_id, "fetch", output_key="fetched")
    evidence_items = await load_evidence_items(session, task_id)

    search_metrics = evaluate_search(search_output) if search_output else None
    fetch_metrics = evaluate_fetch(fetch_output) if fetch_output else None
    rerank_metrics = evaluate_rerank(evidence_items) if evidence_items else None

    overall_pass = _check_targets(search_metrics, fetch_metrics, rerank_metrics, effective_targets)

    task_type = ""
    if isinstance(task.requirements, dict):
        task_type = task.requirements.get("task_type", "") or ""

    return PipelineEvaluationReport(
        task_id=task.id,
        topic=task.topic,
        status=task.status,
        task_type=task_type,
        evaluated_at=datetime.now(timezone.utc),
        search=search_metrics,
        fetch=fetch_metrics,
        rerank=rerank_metrics,
        targets=effective_targets,
        overall_pass=overall_pass,
    )


def _check_targets(
    search: SearchMetrics | None,
    fetch: FetchMetrics | None,
    rerank: RerankMetrics | None,
    targets: dict[str, float],
) -> bool:
    """将三阶段指标与目标值对比，全部达标返回 True。"""
    if not (search and fetch and rerank):
        return False

    checks = [
        search.coverage_rate >= targets.get("search_coverage_rate", 0.0),
        search.recall_at_k >= targets.get("search_recall_at_5", 0.0),
        fetch.success_rate > targets.get("fetch_success_rate", 0.0),
        rerank.mean_score >= targets.get("rerank_mean_score", 0.0),
        rerank.high_quality_ratio >= targets.get("rerank_high_quality_ratio", 0.0),
    ]
    return all(checks)


async def evaluate_tasks(
    session: AsyncSession,
    task_ids: list[str],
    targets: dict[str, float] | None = None,
) -> list[PipelineEvaluationReport]:
    """批量评估多个任务。"""
    reports: list[PipelineEvaluationReport] = []
    for task_id in task_ids:
        try:
            report = await evaluate_task(session, task_id, targets)
            reports.append(report)
        except (TaskNotFoundException, ValueError):
            # 跳过不存在或状态不可评估的任务
            continue
    return reports


def aggregate_reports(
    reports: list[PipelineEvaluationReport],
    system: SystemReliabilityMetrics | None = None,
) -> dict[str, Any]:
    """聚合多任务评估结果，计算平均指标与通过率。

    Args:
        reports: 单任务评估报告列表。
        system: 可选，系统级可靠性指标。传入后将纳入聚合输出。
    """
    if not reports:
        result: dict[str, Any] = {
            "task_count": 0,
            "search": {},
            "fetch": {},
            "rerank": {},
            "pass_rate": 0.0,
        }
        if system:
            result["system"] = system.to_dict()
        return result

    search_reports = [r.search for r in reports if r.search]
    fetch_reports = [r.fetch for r in reports if r.fetch]
    rerank_reports = [r.rerank for r in reports if r.rerank]
    passed_count = sum(1 for r in reports if r.overall_pass)

    def _mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    result = {
        "task_count": len(reports),
        "search": {
            "mean_coverage_rate": _mean([s.coverage_rate for s in search_reports]),
            "mean_recall_at_k": _mean([s.recall_at_k for s in search_reports]),
            "mean_avg_results_per_sub_question": _mean(
                [s.avg_results_per_sub_question for s in search_reports]
            ),
        },
        "fetch": {
            "mean_success_rate": _mean([f.success_rate for f in fetch_reports]),
        },
        "rerank": {
            "mean_mean_score": _mean([r.mean_score for r in rerank_reports]),
            "mean_median_score": _mean([r.median_score for r in rerank_reports]),
            "mean_high_quality_ratio": _mean(
                [r.high_quality_ratio for r in rerank_reports]
            ),
        },
        "pass_rate": passed_count / len(reports),
    }
    if system:
        result["system"] = system.to_dict()
    return result
