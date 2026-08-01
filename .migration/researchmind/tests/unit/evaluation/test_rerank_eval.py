"""Rerank 离线评估单元测试"""

from decimal import Decimal

import pytest

from app.evaluation.models import RerankMetrics
from app.evaluation.rerank_eval import evaluate_rerank


class TestEvaluateRerank:
    """测试 Rerank 相关性指标计算。"""

    def test_四个证据_均值中位数高质量比正确(self):
        evidence_items = [
            {"relevance_score": Decimal("0.9")},
            {"relevance_score": Decimal("0.8")},
            {"relevance_score": Decimal("0.7")},
            {"relevance_score": Decimal("0.5")},
        ]

        metrics = evaluate_rerank(evidence_items)

        assert metrics.evidence_count == 4
        assert metrics.mean_score == pytest.approx(0.725)
        assert metrics.median_score == pytest.approx(0.75)
        assert metrics.min_score == pytest.approx(0.5)
        assert metrics.max_score == pytest.approx(0.9)
        assert metrics.high_quality_ratio == pytest.approx(0.75)

    def test_空列表返回零值指标(self):
        metrics = evaluate_rerank([])

        assert metrics == RerankMetrics()

    def test_单条证据_最小最大均值相等(self):
        evidence_items = [{"relevance_score": Decimal("0.65")}]

        metrics = evaluate_rerank(evidence_items)

        assert metrics.evidence_count == 1
        assert metrics.mean_score == pytest.approx(0.65)
        assert metrics.median_score == pytest.approx(0.65)
        assert metrics.min_score == pytest.approx(0.65)
        assert metrics.max_score == pytest.approx(0.65)
        assert metrics.high_quality_ratio == pytest.approx(1.0)

    def test_浮点与字符串分数兼容(self):
        evidence_items = [
            {"relevance_score": 0.9},
            {"relevance_score": "0.7"},
        ]

        metrics = evaluate_rerank(evidence_items)

        assert metrics.mean_score == pytest.approx(0.8)

    def test_分布分箱计数正确(self):
        evidence_items = [
            {"relevance_score": Decimal("0.10")},  # [0.00,0.20)
            {"relevance_score": Decimal("0.30")},  # [0.20,0.40)
            {"relevance_score": Decimal("0.50")},  # [0.40,0.60)
            {"relevance_score": Decimal("0.70")},  # [0.60,0.80)
            {"relevance_score": Decimal("0.90")},  # [0.80,1.00]
        ]

        metrics = evaluate_rerank(evidence_items)

        assert metrics.score_distribution == {
            "[0.00,0.20)": 1,
            "[0.20,0.40)": 1,
            "[0.40,0.60)": 1,
            "[0.60,0.80)": 1,
            "[0.80,1.00]": 1,
        }

    def test_边界0点60计入高质量(self):
        evidence_items = [
            {"relevance_score": Decimal("0.60")},
            {"relevance_score": Decimal("0.59")},
        ]

        metrics = evaluate_rerank(evidence_items)

        assert metrics.high_quality_ratio == pytest.approx(0.5)
