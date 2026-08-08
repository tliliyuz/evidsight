"""Evidence Completeness 完整度三分项纯函数。

对齐 RESEARCH_PIPELINE §10.1：
- question_coverage = 有至少一条 available Evidence 的 required 子问题数 / required 子问题总数
- channel_success = 成功产出至少一条有效 Evidence 的计划通道数 / 计划通道总数
- claim_coverage = 有至少一条 supports Evidence 的 critical Claim 数 / critical Claim 总数
- evidence_completeness = 0.50 × question_coverage + 0.25 × channel_success + 0.25 × claim_coverage

纯函数、无 I/O；分子、分母与规则版本由 Report Publisher 持久化到 Revision 摘要。
分数可由固定 Fixture 复算，不由 LLM 直接给出。
"""

# 完整度规则版本（RESEARCH_PIPELINE §10.1 权重）
COMPLETENESS_RULE_VERSION = 1


def compute_question_coverage(
    required_questions: int,
    questions_with_evidence: int,
) -> tuple[float, int, int]:
    """required 子问题覆盖比例。

    Raises:
        ValueError: required_questions <= 0（零 required 不得用空集合得分 1）。
    """
    if required_questions <= 0:
        raise ValueError("required_questions 必须大于 0（零 required 不允许）")
    questions_with_evidence = max(0, min(questions_with_evidence, required_questions))
    return (
        questions_with_evidence / required_questions,
        questions_with_evidence,
        required_questions,
    )


def compute_channel_success(
    planned: int,
    succeeded: int,
) -> tuple[float, int, int]:
    """计划通道成功比例。planned=0 时返回 0（防御性，无通道计划）。"""
    if planned <= 0:
        return 0.0, 0, 0
    succeeded = max(0, min(succeeded, planned))
    return succeeded / planned, succeeded, planned


def compute_claim_coverage(
    critical_claims: int,
    claims_with_supports: int,
) -> tuple[float, int, int]:
    """critical Claim 的 supports 覆盖比例。无 critical Claim 时返回 0。"""
    if critical_claims <= 0:
        return 0.0, 0, 0
    claims_with_supports = max(0, min(claims_with_supports, critical_claims))
    return claims_with_supports / critical_claims, claims_with_supports, critical_claims


def compute_evidence_completeness(
    question_coverage: float,
    channel_success: float,
    claim_coverage: float,
) -> float:
    """按 RESEARCH_PIPELINE §10.1 权重计算完整度总分（0-1）。

    Raises:
        ValueError: 任一输入超出 [0, 1]。
    """
    for name, v in (
        ("question_coverage", question_coverage),
        ("channel_success", channel_success),
        ("claim_coverage", claim_coverage),
    ):
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"{name} 超出 [0,1]: {v}")
    return 0.50 * question_coverage + 0.25 * channel_success + 0.25 * claim_coverage


def build_completeness_summary(
    question_coverage: tuple[float, int, int],
    channel_success: tuple[float, int, int],
    claim_coverage: tuple[float, int, int],
) -> dict:
    """构建持久化到 ReportRevision.evidence_completeness 的完整摘要。

    对齐 RESEARCH_PIPELINE §10.1（切片 6）：三分项各含 `{numerator, denominator,
    ratio}`，另含总分 `score` 与 `rule_version`，便于审计与复算。

    Args:
        三分项参数均为 compute_* 的 (ratio, numerator, denominator) 返回元组。
    """
    q_ratio, q_num, q_den = question_coverage
    c_ratio, c_num, c_den = channel_success
    k_ratio, k_num, k_den = claim_coverage
    score = compute_evidence_completeness(
        question_coverage=q_ratio,
        channel_success=c_ratio,
        claim_coverage=k_ratio,
    )
    return {
        "question_coverage": {
            "numerator": q_num,
            "denominator": q_den,
            "ratio": round(q_ratio, 4),
        },
        "channel_success": {
            "numerator": c_num,
            "denominator": c_den,
            "ratio": round(c_ratio, 4),
        },
        "claim_coverage": {
            "numerator": k_num,
            "denominator": k_den,
            "ratio": round(k_ratio, 4),
        },
        "score": round(score, 4),
        "rule_version": COMPLETENESS_RULE_VERSION,
    }
