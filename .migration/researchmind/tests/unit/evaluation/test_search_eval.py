"""Search 离线评估单元测试"""

import pytest

from app.evaluation.models import SearchMetrics
from app.evaluation.search_eval import evaluate_search


class TestEvaluateSearch:
    """测试 Search Coverage Rate 与 Recall@K 计算。"""

    def test_三个子问题各返回5条_覆盖率与recall均为1(self):
        search_output = {
            "sub_question_results": [
                {"sub_question": "Q1", "results_count": 5},
                {"sub_question": "Q2", "results_count": 5},
                {"sub_question": "Q3", "results_count": 5},
            ]
        }

        metrics = evaluate_search(search_output, k=5)

        assert metrics == SearchMetrics(
            sub_question_count=3,
            total_results=15,
            avg_results_per_sub_question=5.0,
            coverage_rate=1.0,
            recall_at_k=1.0,
            k=5,
        )

    def test_一个子问题0结果_覆盖率变为三分之二(self):
        search_output = {
            "sub_question_results": [
                {"sub_question": "Q1", "results_count": 5},
                {"sub_question": "Q2", "results_count": 0},
                {"sub_question": "Q3", "results_count": 5},
            ]
        }

        metrics = evaluate_search(search_output, k=5)

        assert metrics.sub_question_count == 3
        assert metrics.total_results == 10
        assert metrics.coverage_rate == pytest.approx(2 / 3)
        assert metrics.recall_at_k == pytest.approx((1.0 + 0.0 + 1.0) / 3)

    def test_全部子问题0结果_覆盖率与recall均为0(self):
        search_output = {
            "sub_question_results": [
                {"sub_question": "Q1", "results_count": 0},
                {"sub_question": "Q2", "results_count": 0},
            ]
        }

        metrics = evaluate_search(search_output, k=5)

        assert metrics.coverage_rate == 0.0
        assert metrics.recall_at_k == 0.0
        assert metrics.total_results == 0

    def test_结果数超过k_recall按k截断(self):
        search_output = {
            "sub_question_results": [
                {"sub_question": "Q1", "results_count": 7},
                {"sub_question": "Q2", "results_count": 5},
            ]
        }

        metrics = evaluate_search(search_output, k=5)

        assert metrics.recall_at_k == pytest.approx((1.0 + 1.0) / 2)
        assert metrics.total_results == 12

    def test_自定义k为3_recall按3计算(self):
        search_output = {
            "sub_question_results": [
                {"sub_question": "Q1", "results_count": 2},
                {"sub_question": "Q2", "results_count": 3},
            ]
        }

        metrics = evaluate_search(search_output, k=3)

        assert metrics.k == 3
        assert metrics.recall_at_k == pytest.approx((2 / 3 + 1.0) / 2)

    def test_空输入返回零值指标(self):
        metrics = evaluate_search(None, k=5)

        assert metrics == SearchMetrics(k=5)

    def test_缺少sub_question_results返回零值指标(self):
        metrics = evaluate_search({"total_results": 10}, k=5)

        assert metrics == SearchMetrics(k=5)
