"""离线评估常量

指标目标值、分箱边界、人工评估维度定义。所有目标值与 docs/TESTING_STRATEGY.md §11.3 对齐。
"""

from decimal import Decimal

# Search Recall 默认 K 值，与 TAVILY_MAX_RESULTS_PER_QUERY 保持一致
SEARCH_RECALL_K = 5

# Rerank 分数分箱边界（左闭右开，最后一档闭区间）
SCORE_BINS = [Decimal("0.00"), Decimal("0.20"), Decimal("0.40"), Decimal("0.60"), Decimal("0.80"), Decimal("1.00")]

# 高质量证据阈值
HIGH_QUALITY_THRESHOLD = Decimal("0.60")

# 涉及 LLM 调用的 Step 类型（用于 LLM Call Success Rate 统计）
LLM_STEP_TYPES = {"planning", "rerank", "synthesis", "render"}

# v1.0 评估目标值（含系统级可靠性指标）
TARGETS = {
    "search_coverage_rate": 0.90,
    "search_recall_at_5": 0.80,
    "fetch_success_rate": 0.70,
    "rerank_mean_score": 0.65,
    "rerank_high_quality_ratio": 0.60,
    "task_completion_rate": 0.90,
    "llm_call_success_rate": 0.99,
}

# 人工评估维度
MANUAL_DIMENSIONS = ["结构完整性", "引用准确性", "综合质量", "可读性"]

# 人工评分的有效范围
MIN_MANUAL_SCORE = 1
MAX_MANUAL_SCORE = 5
