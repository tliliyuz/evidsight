"""离线 Pipeline 评估模块

提供 Search / Fetch / Rerank 三阶段的量化指标计算，以及单任务/多任务的
评估报告聚合。指标定义与目标值见 tests/TESTING_STRATEGY.md §11。
"""

from app.evaluation.aggregator import aggregate_reports, evaluate_task
from app.evaluation.fetch_eval import FetchMetrics, evaluate_fetch
from app.evaluation.models import PipelineEvaluationReport, SystemReliabilityMetrics
from app.evaluation.rerank_eval import RerankMetrics, evaluate_rerank
from app.evaluation.search_eval import SearchMetrics, evaluate_search
from app.evaluation.system_eval import check_system_targets, evaluate_system_reliability

__all__ = [
    "evaluate_fetch",
    "evaluate_rerank",
    "evaluate_search",
    "evaluate_task",
    "evaluate_system_reliability",
    "check_system_targets",
    "aggregate_reports",
    "FetchMetrics",
    "RerankMetrics",
    "SearchMetrics",
    "PipelineEvaluationReport",
    "SystemReliabilityMetrics",
]
