"""Fetch 离线评估单元测试"""

import pytest

from app.evaluation.fetch_eval import evaluate_fetch
from app.evaluation.models import FetchMetrics


class TestEvaluateFetch:
    """测试 Fetch Success Rate 与状态分布。"""

    def test_4成功1超时_成功率08(self):
        fetch_output = {
            "fetched": [
                {"url": "https://a.com", "status": "success"},
                {"url": "https://b.com", "status": "success"},
                {"url": "https://c.com", "status": "success"},
                {"url": "https://d.com", "status": "success"},
                {"url": "https://e.com", "status": "timeout"},
            ]
        }

        metrics = evaluate_fetch(fetch_output)

        assert metrics == FetchMetrics(
            successful=4,
            failed=1,
            skipped_safety=0,
            success_rate=0.8,
            status_distribution={
                "success": 4,
                "timeout": 1,
            },
        )

    def test_全部成功_成功率为1(self):
        fetch_output = {
            "fetched": [
                {"url": "https://a.com", "status": "success"},
                {"url": "https://b.com", "status": "success"},
            ]
        }

        metrics = evaluate_fetch(fetch_output)

        assert metrics.success_rate == 1.0
        assert metrics.successful == 2
        assert metrics.failed == 0

    def test_全部失败_成功率为0(self):
        fetch_output = {
            "fetched": [
                {"url": "https://a.com", "status": "blocked"},
                {"url": "https://b.com", "status": "dns_error"},
            ]
        }

        metrics = evaluate_fetch(fetch_output)

        assert metrics.success_rate == 0.0
        assert metrics.successful == 0
        assert metrics.failed == 2
        assert metrics.status_distribution == {"blocked": 1, "dns_error": 1}

    def test_仅安全拦截_分母为0成功率为0(self):
        fetch_output = {
            "fetched": [
                {"url": "http://127.0.0.1", "status": "safety_blocked"},
            ]
        }

        metrics = evaluate_fetch(fetch_output)

        assert metrics.success_rate == 0.0
        assert metrics.skipped_safety == 1
        assert metrics.successful == 0
        assert metrics.failed == 0

    def test_混合失败状态_统计正确(self):
        fetch_output = {
            "fetched": [
                {"url": "https://a.com", "status": "success"},
                {"url": "https://b.com", "status": "blocked"},
                {"url": "https://c.com", "status": "empty"},
                {"url": "https://d.com", "status": "dns_error"},
                {"url": "http://10.0.0.1", "status": "safety_blocked"},
            ]
        }

        metrics = evaluate_fetch(fetch_output)

        assert metrics.successful == 1
        assert metrics.failed == 3
        assert metrics.skipped_safety == 1
        assert metrics.success_rate == pytest.approx(0.25)
        assert metrics.status_distribution == {
            "success": 1,
            "blocked": 1,
            "empty": 1,
            "dns_error": 1,
            "safety_blocked": 1,
        }

    def test_空输入返回零值指标(self):
        metrics = evaluate_fetch(None)

        assert metrics == FetchMetrics()

    def test_空fetched列表返回零值指标(self):
        metrics = evaluate_fetch({"fetched": []})

        assert metrics == FetchMetrics()
