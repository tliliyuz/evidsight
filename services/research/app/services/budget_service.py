"""Budget Service —— RESEARCH_PIPELINE §14 预算冻结/预留/结算。

服务端默认推导（负责人确认方案，零公共契约变更）：客户端不传预算字段，
服务端按 max_sources/来源策略/服务端常量推导冻结上限并存入 Task。

语义对齐 §14：
- Task 创建时冻结最大子问题数、搜索结果数、Fetch 数、LLM Token、Provider
  调用、估算成本、Agent 迭代和总时限；
- 每次外部调用前预留（can_reserve），完成后结算实际用量（settle_budget）；
  无法预留则停止新调用；
- 预算停止不是自动成功：已有 Evidence 仍需通过完整度硬门槛，终态由
  TaskStateResolver 按 §14 推导 partial/failed。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import settings

BUDGET_SCHEMA_VERSION = 1

# ── 预算维度常量（budget_frozen 键）────────────────────────────
KEY_MAX_SUB_QUESTIONS = "max_sub_questions"
KEY_MAX_SEARCH_RESULTS = "max_search_results"
KEY_MAX_FETCH = "max_fetch"
KEY_MAX_LLM_TOKENS = "max_llm_tokens"
KEY_MAX_PROVIDER_CALLS = "max_provider_calls"
KEY_MAX_COST_USD = "max_cost_usd"
KEY_MAX_AGENT_ITERATIONS = "max_agent_iterations"
KEY_DEADLINE_SECONDS = "deadline_seconds"

# ── 结算用量维度（budget_usage 键）─────────────────────────────
KEY_USAGE_SUB_QUESTIONS = "sub_questions"
KEY_USAGE_SEARCH_RESULTS = "search_results"
KEY_USAGE_FETCH = "fetch"
KEY_USAGE_LLM_TOKENS = "llm_tokens"
KEY_USAGE_PROVIDER_CALLS = "provider_calls"
KEY_USAGE_COST_USD = "cost_usd"
KEY_USAGE_AGENT_ITERATIONS = "agent_iterations"

_FROZEN_DIMENSION_KEYS = (
    KEY_MAX_SUB_QUESTIONS,
    KEY_MAX_SEARCH_RESULTS,
    KEY_MAX_FETCH,
    KEY_MAX_LLM_TOKENS,
    KEY_MAX_PROVIDER_CALLS,
    KEY_MAX_COST_USD,
    KEY_MAX_AGENT_ITERATIONS,
    KEY_DEADLINE_SECONDS,
)

_USAGE_KEYS = (
    KEY_USAGE_SUB_QUESTIONS,
    KEY_USAGE_SEARCH_RESULTS,
    KEY_USAGE_FETCH,
    KEY_USAGE_LLM_TOKENS,
    KEY_USAGE_PROVIDER_CALLS,
    KEY_USAGE_COST_USD,
    KEY_USAGE_AGENT_ITERATIONS,
)


def derive_default_budget(requirements: dict, source_strategy: str) -> dict:
    """服务端默认推导冻结上限（§14，客户端不传预算字段）。

    Args:
        requirements: 任务 requirements dict（含 max_sources）。
        source_strategy: knowledge / web / hybrid。
            knowledge 无 Web Fetch（RESEARCH_PIPELINE §17.1：Fetch 明确 skipped）。

    Returns:
        冻结上限快照（含 schema_version）。
    """
    max_sources = 0
    try:
        max_sources = int((requirements or {}).get("max_sources", 0))
    except (TypeError, ValueError):
        max_sources = 0

    search_results_limit = max(
        settings.TAVILY_TOTAL_RESULTS_LIMIT,
        max_sources,
    )
    max_fetch = 0 if source_strategy == "knowledge" else settings.FETCH_MAX_URLS_PER_TASK

    return {
        "schema_version": BUDGET_SCHEMA_VERSION,
        KEY_MAX_SUB_QUESTIONS: settings.BUDGET_MAX_SUB_QUESTIONS,
        KEY_MAX_SEARCH_RESULTS: search_results_limit,
        KEY_MAX_FETCH: max_fetch,
        KEY_MAX_LLM_TOKENS: settings.BUDGET_MAX_LLM_TOKENS,
        KEY_MAX_PROVIDER_CALLS: settings.BUDGET_MAX_PROVIDER_CALLS,
        KEY_MAX_COST_USD: settings.BUDGET_MAX_COST_USD,
        KEY_MAX_AGENT_ITERATIONS: settings.MAX_AGENT_ITERATIONS,
        KEY_DEADLINE_SECONDS: settings.BUDGET_DEADLINE_SECONDS,
    }


def _empty_usage() -> dict:
    """初始结算用量（全部归零）。"""
    return {
        "schema_version": BUDGET_SCHEMA_VERSION,
        KEY_USAGE_SUB_QUESTIONS: 0,
        KEY_USAGE_SEARCH_RESULTS: 0,
        KEY_USAGE_FETCH: 0,
        KEY_USAGE_LLM_TOKENS: 0,
        KEY_USAGE_PROVIDER_CALLS: 0,
        KEY_USAGE_COST_USD: 0.0,
        KEY_USAGE_AGENT_ITERATIONS: 0,
    }


def freeze_budget(task: Any, requirements: dict, source_strategy: str) -> None:
    """创建任务时冻结预算上限并初始化结算用量。

    Args:
        task: ResearchTask ORM 实例（写入 budget_frozen / budget_usage）。
        requirements: 任务 requirements dict。
        source_strategy: 来源策略。
    """
    task.budget_frozen = derive_default_budget(requirements, source_strategy)
    task.budget_usage = _empty_usage()
    task.budget_stopped_at = None


def _usage(task: Any) -> dict:
    usage = getattr(task, "budget_usage", None)
    if not isinstance(usage, dict):
        return _empty_usage()
    return usage


def _frozen(task: Any) -> dict | None:
    frozen = getattr(task, "budget_frozen", None)
    return frozen if isinstance(frozen, dict) else None


def _deadline_passed(task: Any) -> bool:
    """总时限（deadline）检查：started_at + deadline_seconds 是否已过。"""
    frozen = _frozen(task)
    started_at = getattr(task, "started_at", None)
    if not frozen or started_at is None:
        return False
    deadline_seconds = frozen.get(KEY_DEADLINE_SECONDS)
    if not isinstance(deadline_seconds, (int, float)) or deadline_seconds <= 0:
        return False
    try:
        deadline = started_at + timedelta(seconds=deadline_seconds)
        return datetime.now(timezone.utc) > deadline
    except (TypeError, AttributeError):
        return False


def is_budget_stopped(task: Any) -> bool:
    """任务是否已触发预算停止。"""
    return getattr(task, "budget_stopped_at", None) is not None


def can_reserve(task: Any) -> bool:
    """外部调用前预留检查（§14：无法预留则停止新调用）。

    预算已停止或已超过总时限时拒绝新调用。
    """
    if is_budget_stopped(task):
        return False
    if _deadline_passed(task):
        return False
    return True


def _dimension_exceeded(task: Any) -> str | None:
    """检查是否任一冻结维度已被用量触及上限，返回超限维度名或 None。

    预算停止以「用量 >= 上限」为触发条件（§14：无法预留则停止新调用）。
    """
    frozen = _frozen(task)
    usage = _usage(task)
    if not frozen:
        return None

    mapping = {
        KEY_USAGE_SUB_QUESTIONS: KEY_MAX_SUB_QUESTIONS,
        KEY_USAGE_SEARCH_RESULTS: KEY_MAX_SEARCH_RESULTS,
        KEY_USAGE_FETCH: KEY_MAX_FETCH,
        KEY_USAGE_LLM_TOKENS: KEY_MAX_LLM_TOKENS,
        KEY_USAGE_PROVIDER_CALLS: KEY_MAX_PROVIDER_CALLS,
        KEY_USAGE_COST_USD: KEY_MAX_COST_USD,
        KEY_USAGE_AGENT_ITERATIONS: KEY_MAX_AGENT_ITERATIONS,
    }
    for usage_key, frozen_key in mapping.items():
        used = usage.get(usage_key, 0)
        cap = frozen.get(frozen_key, 0)
        if isinstance(cap, (int, float)) and cap > 0 and used >= cap:
            return frozen_key
    return None


def settle_budget(task: Any, usage_delta: dict) -> bool:
    """外部调用完成后结算实际用量（§14）。

    Args:
        task: ResearchTask ORM 实例。
        usage_delta: 本次实际用量增量，如
            {"provider_calls": 1, "llm_tokens": 500, "cost_usd": 0.01}。

    Returns:
        True 表示本次结算后触发预算停止（budget_stopped_at 已写入）。
    """
    usage = _usage(task)
    if not isinstance(usage, dict) or "schema_version" not in usage:
        usage = _empty_usage()
        task.budget_usage = usage

    for key, value in (usage_delta or {}).items():
        if key not in _USAGE_KEYS:
            continue
        current = usage.get(key, 0)
        try:
            usage[key] = current + float(value) if key == KEY_USAGE_COST_USD else current + int(value)
        except (TypeError, ValueError):
            continue

    task.budget_usage = usage

    exceeded = _dimension_exceeded(task)
    if exceeded is not None:
        task.budget_stopped_at = datetime.now(timezone.utc)
        return True
    return False


def budget_stop_reason(task: Any) -> str | None:
    """返回预算停止的超限维度描述；未停止返回 None。"""
    if not is_budget_stopped(task):
        return None
    exceeded = _dimension_exceeded(task)
    if exceeded is not None:
        return exceeded
    if _deadline_passed(task):
        return "总时限"
    return "预算停止"


def budget_disclosure(task: Any) -> str | None:
    """报告披露：预算停止时返回需披露的缺失说明（RESEARCH_PIPELINE §14）。

    未预算停止返回 None。
    """
    if not is_budget_stopped(task):
        return None
    reason = budget_stop_reason(task) or "预算限制"
    return (
        f"本次研究因{reason}提前停止，部分子问题或来源未能覆盖，"
        f"报告内容可能不完整，请如实披露该局限。"
    )
