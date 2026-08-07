"""Budget Service 单元测试 —— RESEARCH_PIPELINE §14 预算冻结/预留/结算。

服务端默认推导（用户确认方案）：客户端不传预算字段，服务端按
max_sources/来源策略/服务端常量推导冻结上限并存入 Task；零公共契约变更。

覆盖：
- derive_default_budget：服务端默认推导冻结上限（含 schema_version 与各维度上限）；
- freeze_budget：创建任务时写入 task.budget_frozen；
- reserve/settle 原语：外部调用前预留、完成后结算，超限标记预算停止；
- deadline 总时限超时判定；
- 预算停止后拒绝新调用。
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from app.models.research_task import ResearchTask


@pytest.fixture(autouse=True)
def _budget_settings(monkeypatch):
    """固定预算相关服务端常量，保证断言确定。"""
    from app.config import settings

    monkeypatch.setattr(settings, "BUDGET_MAX_SUB_QUESTIONS", 5)
    monkeypatch.setattr(settings, "BUDGET_MAX_LLM_TOKENS", 100_000)
    monkeypatch.setattr(settings, "BUDGET_MAX_PROVIDER_CALLS", 60)
    monkeypatch.setattr(settings, "BUDGET_MAX_COST_USD", 1.0)
    monkeypatch.setattr(settings, "BUDGET_DEADLINE_SECONDS", 3600)
    monkeypatch.setattr(settings, "MAX_AGENT_ITERATIONS", 30)
    monkeypatch.setattr(settings, "FETCH_MAX_URLS_PER_TASK", 15)
    monkeypatch.setattr(settings, "TAVILY_TOTAL_RESULTS_LIMIT", 25)


def _make_task(**kwargs) -> ResearchTask:
    defaults = {
        "id": "task-budget-001",
        "user_id": "u1",
        "topic": "test",
        "requirements": {"task_type": "analysis", "max_sources": 10},
        "source_strategy": "web",
        "status": "running",
        "started_at": datetime.now(timezone.utc),
        "budget_frozen": None,
        "budget_usage": None,
        "budget_stopped_at": None,
    }
    defaults.update(kwargs)
    return MagicMock(spec=ResearchTask, **{k: v for k, v in defaults.items()})


class TestDeriveDefaultBudget:
    def test_推导包含全部维度与schema_version(self):
        from app.services.budget_service import derive_default_budget

        budget = derive_default_budget({"max_sources": 10}, "web")

        assert budget["schema_version"] == 1
        assert budget["max_sub_questions"] == 5
        assert budget["max_search_results"] == 25
        assert budget["max_fetch"] == 15
        assert budget["max_llm_tokens"] == 100_000
        assert budget["max_provider_calls"] == 60
        assert budget["max_cost_usd"] == 1.0
        assert budget["max_agent_iterations"] == 30
        assert budget["deadline_seconds"] == 3600

    def test_knowledge策略_fetch上限为0(self):
        from app.services.budget_service import derive_default_budget

        budget = derive_default_budget({"max_sources": 10}, "knowledge")

        # knowledge 无 Web Fetch（RESEARCH_PIPELINE §17.1：knowledge 的 Fetch 明确为 skipped）
        assert budget["max_fetch"] == 0
        assert budget["max_search_results"] == 25

    def test_requirements缺省max_sources_使用默认值(self):
        from app.services.budget_service import derive_default_budget

        budget = derive_default_budget({}, "web")
        assert budget["max_search_results"] == 25


class TestFreezeBudget:
    def test_freeze写入冻结快照(self):
        from app.services.budget_service import freeze_budget

        task = _make_task()
        freeze_budget(task, {"max_sources": 10}, "web")

        assert task.budget_frozen is not None
        assert task.budget_frozen["schema_version"] == 1
        assert task.budget_frozen["max_provider_calls"] == 60

    def test_freeze同时初始化空用量(self):
        from app.services.budget_service import freeze_budget

        task = _make_task()
        freeze_budget(task, {"max_sources": 10}, "web")

        assert task.budget_usage is not None
        assert task.budget_usage["provider_calls"] == 0
        assert task.budget_usage["llm_tokens"] == 0
        assert task.budget_usage["cost_usd"] == 0.0


class TestReserveSettle:
    def test_初始预算可预留(self):
        from app.services.budget_service import can_reserve, freeze_budget

        task = _make_task()
        freeze_budget(task, {"max_sources": 10}, "web")
        assert can_reserve(task) is True

    def test_settle累加用量(self):
        from app.services.budget_service import freeze_budget, settle_budget

        task = _make_task()
        freeze_budget(task, {"max_sources": 10}, "web")

        stopped = settle_budget(task, {"provider_calls": 1, "llm_tokens": 500, "cost_usd": 0.01})
        assert stopped is False
        assert task.budget_usage["provider_calls"] == 1
        assert task.budget_usage["llm_tokens"] == 500

    def test_provider_calls超限_标记预算停止(self):
        from app.services.budget_service import freeze_budget, settle_budget

        task = _make_task()
        freeze_budget(task, {"max_sources": 10}, "web")

        stopped = settle_budget(task, {"provider_calls": 60})
        assert stopped is True
        assert task.budget_stopped_at is not None

    def test_llm_tokens超限_标记预算停止(self):
        from app.services.budget_service import freeze_budget, settle_budget

        task = _make_task()
        freeze_budget(task, {"max_sources": 10}, "web")

        stopped = settle_budget(task, {"llm_tokens": 100_000})
        assert stopped is True
        assert task.budget_stopped_at is not None

    def test_cost超限_标记预算停止(self):
        from app.services.budget_service import freeze_budget, settle_budget

        task = _make_task()
        freeze_budget(task, {"max_sources": 10}, "web")

        stopped = settle_budget(task, {"cost_usd": 1.0})
        assert stopped is True

    def test_预算停止后拒绝新调用(self):
        from app.services.budget_service import can_reserve, freeze_budget, settle_budget

        task = _make_task()
        freeze_budget(task, {"max_sources": 10}, "web")
        settle_budget(task, {"provider_calls": 60})

        assert task.budget_stopped_at is not None
        assert can_reserve(task) is False

    def test_未超限_不标记停止(self):
        from app.services.budget_service import can_reserve, freeze_budget, settle_budget

        task = _make_task()
        freeze_budget(task, {"max_sources": 10}, "web")

        stopped = settle_budget(task, {"provider_calls": 10, "llm_tokens": 5000, "cost_usd": 0.1})
        assert stopped is False
        assert task.budget_stopped_at is None
        assert can_reserve(task) is True


class TestDeadline:
    def test_超过总时限_拒绝预留(self):
        from app.services.budget_service import can_reserve, freeze_budget

        started = datetime.now(timezone.utc) - timedelta(seconds=4000)
        task = _make_task(started_at=started)
        freeze_budget(task, {"max_sources": 10}, "web")

        assert can_reserve(task) is False

    def test_时限内_可预留(self):
        from app.services.budget_service import can_reserve, freeze_budget

        started = datetime.now(timezone.utc) - timedelta(seconds=100)
        task = _make_task(started_at=started)
        freeze_budget(task, {"max_sources": 10}, "web")

        assert can_reserve(task) is True
