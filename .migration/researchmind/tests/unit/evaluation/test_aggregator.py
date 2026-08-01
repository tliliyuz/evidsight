"""评估聚合器单元测试"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.evaluation.aggregator import aggregate_reports, evaluate_task
from app.evaluation.constants import TARGETS
from app.evaluation.models import (
    FetchMetrics,
    PipelineEvaluationReport,
    RerankMetrics,
    SearchMetrics,
    SystemReliabilityMetrics,
)


class TestEvaluateTask:
    """测试单任务评估聚合。"""

    @pytest.fixture
    def mock_task(self):
        task = MagicMock()
        task.id = "task-uuid-1"
        task.topic = "测试主题"
        task.status = "completed"
        task.requirements = {"task_type": "analysis"}
        return task

    async def test_全部指标达标_overall_pass为true(self, mock_task):
        with patch("app.evaluation.aggregator.load_task", new=AsyncMock(return_value=mock_task)):
            with patch(
                "app.evaluation.aggregator.load_step_output",
                new=AsyncMock(side_effect=[
                    {
                        "sub_question_results": [
                            {"sub_question": "Q1", "results_count": 5},
                            {"sub_question": "Q2", "results_count": 5},
                            {"sub_question": "Q3", "results_count": 5},
                        ]
                    },
                    {
                        "fetched": [
                            {"url": "https://a.com", "status": "success"},
                            {"url": "https://b.com", "status": "success"},
                        ]
                    },
                ]),
            ):
                with patch(
                    "app.evaluation.aggregator.load_evidence_items",
                    new=AsyncMock(return_value=[
                        {"relevance_score": Decimal("0.8")},
                        {"relevance_score": Decimal("0.7")},
                    ]),
                ):
                    session = MagicMock()
                    report = await evaluate_task(session, "task-uuid-1", targets=TARGETS)

        assert report.task_id == "task-uuid-1"
        assert report.status == "completed"
        assert report.task_type == "analysis"
        assert report.overall_pass is True
        assert report.search.coverage_rate == 1.0
        assert report.fetch.success_rate == 1.0
        assert report.rerank.mean_score == pytest.approx(0.75)

    async def test_一个指标未达标_overall_pass为false(self, mock_task):
        with patch("app.evaluation.aggregator.load_task", new=AsyncMock(return_value=mock_task)):
            with patch(
                "app.evaluation.aggregator.load_step_output",
                new=AsyncMock(side_effect=[
                    {
                        "sub_question_results": [
                            {"sub_question": "Q1", "results_count": 5},
                            {"sub_question": "Q2", "results_count": 0},
                            {"sub_question": "Q3", "results_count": 0},
                        ]
                    },
                    {
                        "fetched": [
                            {"url": "https://a.com", "status": "success"},
                        ]
                    },
                ]),
            ):
                with patch(
                    "app.evaluation.aggregator.load_evidence_items",
                    new=AsyncMock(return_value=[{"relevance_score": Decimal("0.8")}]),
                ):
                    session = MagicMock()
                    report = await evaluate_task(session, "task-uuid-1", targets=TARGETS)

        assert report.overall_pass is False
        assert report.search.coverage_rate == pytest.approx(1 / 3)

    async def test_任务不存在抛出异常(self):
        with patch("app.evaluation.aggregator.load_task", new=AsyncMock(return_value=None)):
            from app.core.exceptions import TaskNotFoundException

            session = MagicMock()
            with pytest.raises(TaskNotFoundException) as exc_info:
                await evaluate_task(session, "missing-uuid")

            assert exc_info.value.error_code == "E2001"

    async def test_任务状态不可评估抛出异常(self, mock_task):
        mock_task.status = "running"
        with patch("app.evaluation.aggregator.load_task", new=AsyncMock(return_value=mock_task)):
            session = MagicMock()
            with pytest.raises(ValueError) as exc_info:
                await evaluate_task(session, "task-uuid-1")

            assert "running" in str(exc_info.value)


class TestAggregateReports:
    """测试多任务报告聚合。"""

    def test_两个任务聚合_均值与通过率正确(self):
        reports = [
            PipelineEvaluationReport(
                task_id="t1",
                topic="T1",
                status="completed",
                task_type="analysis",
                evaluated_at=datetime.now(timezone.utc),
                search=SearchMetrics(
                    sub_question_count=2,
                    total_results=10,
                    avg_results_per_sub_question=5.0,
                    coverage_rate=1.0,
                    recall_at_k=1.0,
                ),
                fetch=FetchMetrics(successful=4, failed=1, success_rate=0.8),
                rerank=RerankMetrics(
                    evidence_count=2,
                    mean_score=0.8,
                    median_score=0.8,
                    min_score=0.8,
                    max_score=0.8,
                    high_quality_ratio=1.0,
                ),
                overall_pass=True,
            ),
            PipelineEvaluationReport(
                task_id="t2",
                topic="T2",
                status="completed",
                task_type="comparison",
                evaluated_at=datetime.now(timezone.utc),
                search=SearchMetrics(
                    sub_question_count=2,
                    total_results=6,
                    avg_results_per_sub_question=3.0,
                    coverage_rate=0.5,
                    recall_at_k=0.6,
                ),
                fetch=FetchMetrics(successful=1, failed=1, success_rate=0.5),
                rerank=RerankMetrics(
                    evidence_count=1,
                    mean_score=0.6,
                    median_score=0.6,
                    min_score=0.6,
                    max_score=0.6,
                    high_quality_ratio=1.0,
                ),
                overall_pass=False,
            ),
        ]

        aggregate = aggregate_reports(reports)

        assert aggregate["task_count"] == 2
        assert aggregate["pass_rate"] == pytest.approx(0.5)
        assert aggregate["search"]["mean_coverage_rate"] == pytest.approx(0.75)
        assert aggregate["search"]["mean_recall_at_k"] == pytest.approx(0.8)
        assert aggregate["fetch"]["mean_success_rate"] == pytest.approx(0.65)
        assert aggregate["rerank"]["mean_mean_score"] == pytest.approx(0.7)

    def test_空列表聚合返回零值(self):
        aggregate = aggregate_reports([])

        assert aggregate["task_count"] == 0
        assert aggregate["pass_rate"] == 0.0
        assert aggregate["search"] == {}
        assert aggregate["fetch"] == {}
        assert aggregate["rerank"] == {}

    def test_传入system指标_聚合结果包含system字段(self):
        system = SystemReliabilityMetrics(
            task_completed=10,
            task_partially_completed=2,
            task_failed=1,
            task_canceled=1,
            task_completion_rate=0.857,
            llm_calls_completed=50,
            llm_calls_failed=0,
            llm_call_success_rate=1.0,
        )
        reports = [
            PipelineEvaluationReport(
                task_id="t1",
                topic="T1",
                status="completed",
                task_type="analysis",
                evaluated_at=datetime.now(timezone.utc),
                search=SearchMetrics(sub_question_count=2, total_results=10,
                                     avg_results_per_sub_question=5.0,
                                     coverage_rate=1.0, recall_at_k=1.0),
                fetch=FetchMetrics(successful=4, failed=1, success_rate=0.8),
                rerank=RerankMetrics(evidence_count=2, mean_score=0.8,
                                     median_score=0.8, min_score=0.8,
                                     max_score=0.8, high_quality_ratio=1.0),
                overall_pass=True,
            ),
        ]

        aggregate = aggregate_reports(reports, system=system)

        assert aggregate["task_count"] == 1
        assert "system" in aggregate
        assert aggregate["system"]["task_completion_rate"] == 0.857
        assert aggregate["system"]["llm_call_success_rate"] == 1.0

    def test_空列表但传入system_聚合结果仍包含system字段(self):
        system = SystemReliabilityMetrics()
        aggregate = aggregate_reports([], system=system)

        assert aggregate["task_count"] == 0
        assert "system" in aggregate
