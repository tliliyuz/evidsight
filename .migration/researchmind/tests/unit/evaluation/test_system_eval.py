"""系统可靠性评估单元测试"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.evaluation.constants import TARGETS
from app.evaluation.models import SystemReliabilityMetrics
from app.evaluation.system_eval import check_system_targets, evaluate_system_reliability


class TestEvaluateSystemReliability:
    """测试系统可靠性指标计算。"""

    async def test_全部达标_返回对应指标值(self):
        mock_session = MagicMock()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "app.evaluation.system_eval.load_task_terminal_status_counts",
                AsyncMock(return_value={
                    "completed": 45,
                    "partially_completed": 5,
                    "failed": 3,
                    "canceled": 2,
                }),
            )
            mp.setattr(
                "app.evaluation.system_eval.load_llm_step_status_counts",
                AsyncMock(return_value={
                    "completed": 200,
                    "failed": 1,
                }),
            )

            metrics = await evaluate_system_reliability(mock_session)

        assert metrics.task_completed == 45
        assert metrics.task_partially_completed == 5
        assert metrics.task_failed == 3
        assert metrics.task_canceled == 2
        # Task Completion Rate = (45+5) / (45+5+3+2) = 50/55 ≈ 0.909
        assert metrics.task_completion_rate == pytest.approx(50 / 55)
        # LLM Call Success Rate = 200 / (200+1) = 200/201 ≈ 0.995
        assert metrics.llm_calls_completed == 200
        assert metrics.llm_calls_failed == 1
        assert metrics.llm_call_success_rate == pytest.approx(200 / 201)

    async def test_全部失败_task_completion_rate为0(self):
        mock_session = MagicMock()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "app.evaluation.system_eval.load_task_terminal_status_counts",
                AsyncMock(return_value={
                    "completed": 0,
                    "partially_completed": 0,
                    "failed": 10,
                    "canceled": 1,
                }),
            )
            mp.setattr(
                "app.evaluation.system_eval.load_llm_step_status_counts",
                AsyncMock(return_value={
                    "completed": 0,
                    "failed": 0,
                }),
            )

            metrics = await evaluate_system_reliability(mock_session)

        assert metrics.task_completion_rate == 0.0
        assert metrics.llm_call_success_rate == 0.0

    async def test_无终态任务_两个比率均为0(self):
        mock_session = MagicMock()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "app.evaluation.system_eval.load_task_terminal_status_counts",
                AsyncMock(return_value={
                    "completed": 0,
                    "partially_completed": 0,
                    "failed": 0,
                    "canceled": 0,
                }),
            )
            mp.setattr(
                "app.evaluation.system_eval.load_llm_step_status_counts",
                AsyncMock(return_value={
                    "completed": 0,
                    "failed": 0,
                }),
            )

            metrics = await evaluate_system_reliability(mock_session)

        assert metrics.task_completion_rate == 0.0
        assert metrics.llm_call_success_rate == 0.0


class TestCheckSystemTargets:
    """测试系统可靠性目标值对比。"""

    def test_两个指标均达标返回true(self):
        metrics = SystemReliabilityMetrics(
            task_completion_rate=0.95,
            llm_call_success_rate=0.995,
        )
        results = check_system_targets(metrics, targets=TARGETS)

        assert results["task_completion_rate"] is True
        assert results["llm_call_success_rate"] is True

    def test_task_completion_rate不达标返回false(self):
        metrics = SystemReliabilityMetrics(
            task_completion_rate=0.85,
            llm_call_success_rate=0.995,
        )
        results = check_system_targets(metrics, targets=TARGETS)

        assert results["task_completion_rate"] is False
        assert results["llm_call_success_rate"] is True

    def test_llm_call_success_rate不达标返回false(self):
        metrics = SystemReliabilityMetrics(
            task_completion_rate=0.95,
            llm_call_success_rate=0.98,
        )
        results = check_system_targets(metrics, targets=TARGETS)

        assert results["task_completion_rate"] is True
        assert results["llm_call_success_rate"] is False

    def test_恰好等于目标值不算达标_因为是严格大于(self):
        """两个指标目标都是 > 不是 >=，恰好等于目标值应返回 False。"""
        metrics = SystemReliabilityMetrics(
            task_completion_rate=0.90,
            llm_call_success_rate=0.99,
        )
        results = check_system_targets(metrics, targets=TARGETS)

        assert results["task_completion_rate"] is False
        assert results["llm_call_success_rate"] is False

    def test_自定义目标值生效(self):
        metrics = SystemReliabilityMetrics(
            task_completion_rate=0.80,
            llm_call_success_rate=0.95,
        )
        custom_targets = {
            "task_completion_rate": 0.75,
            "llm_call_success_rate": 0.90,
        }
        results = check_system_targets(metrics, targets=custom_targets)

        assert results["task_completion_rate"] is True
        assert results["llm_call_success_rate"] is True


class TestSystemReliabilityMetricsSerialize:
    """测试序列化。"""

    def test_to_dict所有字段正确输出(self):
        metrics = SystemReliabilityMetrics(
            task_completed=10,
            task_partially_completed=2,
            task_failed=1,
            task_canceled=1,
            task_completion_rate=0.857,
            llm_calls_completed=50,
            llm_calls_failed=0,
            llm_call_success_rate=1.0,
        )
        data = metrics.to_dict()

        assert data == {
            "task_completed": 10,
            "task_partially_completed": 2,
            "task_failed": 1,
            "task_canceled": 1,
            "task_completion_rate": 0.857,
            "llm_calls_completed": 50,
            "llm_calls_failed": 0,
            "llm_call_success_rate": 1.0,
        }
