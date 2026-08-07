"""M3 AC 验证指标纯函数。

对齐 TESTING.md §5（AC-001/003/004/010 验证入口）与 PRD §12 指标门槛，
供 `scripts/verify_ac*` 验证脚本与单元测试复用。纯函数、无 I/O，全部指标
由调用方从数据库或 API 读取数据后传入。

指标定义：
- AC-001 关键结论有效引用率 ≥ 90%：报告章节正文 [来源N] 引用闭合到该章节
  实际关联的 Evidence（Claim—Evidence 关系自动检查）；
- AC-003 深度研究任务成功率 ≥ 95%：排除用户主动取消后的任务统计；
- AC-004 可恢复任务恢复成功率 ≥ 95%：Worker 中断与租约恢复演练结果统计；
- AC-010 来源可追溯性 100%：source_type 存在，内部证据可定位文档位置，
  外部证据展示 URL 与获取时间。
"""

from __future__ import annotations

import re

# 报告正文中的引用标记：[来源N]（N 为 0-based Evidence Graph index）
CITATION_RE = re.compile(r"\[来源(\d+)\]")


def extract_citations(content: str | None) -> list[int]:
    """从报告正文提取全部 [来源N] 引用 index（按出现顺序）。

    Args:
        content: 章节正文 Markdown。

    Returns:
        N 列表；无匹配或正文为空时返回空列表。
    """
    if not content:
        return []
    return [int(m) for m in CITATION_RE.findall(content)]


def evaluate_citation_validity(
    sections: list[dict],
    section_evidence: dict[int, list[int]],
    evidence_index: dict[int, int],
) -> tuple[int, int, float]:
    """AC-001：逐章节校验 [来源N] 引用是否闭合到有效且关联的 Evidence。

    Args:
        sections: [{"id": int, "content": str}] 报告章节；
        section_evidence: section_id -> [evidence_item_id] 章节实际关联证据；
        evidence_index: evidence_item_id -> Evidence Graph 0-based index。

    Returns:
        (valid, total, rate)。无引用时 rate = 0.0。
        一条引用当且仅当「index 存在于 evidence_index 映射」且「对应
        evidence_item_id 属于该 section 的 section_evidence」时计为有效。
    """
    total = 0
    valid = 0
    for section in sections:
        section_id = section.get("id")
        linked_ids = set(section_evidence.get(section_id, []))
        # 该 section 实际关联证据在 Graph 中的 index 集合
        linked_indices = {
            evidence_index.get(eid)
            for eid in linked_ids
            if eid in evidence_index
        }
        for idx in extract_citations(section.get("content")):
            total += 1
            if idx in linked_indices:
                valid += 1
    rate = (valid / total) if total else 0.0
    return valid, total, rate


def compute_task_success_rate(
    status_counts: dict[str, int],
) -> tuple[int, int, float]:
    """AC-003：排除用户主动取消后的任务成功率。

    Args:
        status_counts: 终态计数，形如 {"completed": n, "partially_completed": n,
            "failed": n, "canceled": n}。

    Returns:
        (success, denominator, rate)。success = completed + partially_completed；
        denominator 排除 canceled（用户主动取消，PRD AC-003 明确不计入失败）。
    """
    success = status_counts.get("completed", 0) + status_counts.get(
        "partially_completed", 0
    )
    failed = status_counts.get("failed", 0)
    denominator = success + failed
    rate = (success / denominator) if denominator else 0.0
    return success, denominator, rate


def compute_recovery_success_rate(outcomes: list[bool]) -> tuple[int, int, float]:
    """AC-004：恢复演练成功率。

    Args:
        outcomes: 每个演练样本是否成功恢复。

    Returns:
        (success, total, rate)。空样本时 rate = 0.0。
    """
    total = len(outcomes)
    success = sum(1 for o in outcomes if o)
    rate = (success / total) if total else 0.0
    return success, total, rate


# AC-010 可追溯性：internal 必须可定位文档位置，web 必须展示 URL 与获取时间
_INTERNAL_TRACEABILITY_FIELDS = (
    "knowledge_base_id",
    "document_id",
    "document_version_id",
    "segment_id",
    "location_summary",
)


def check_evidence_traceability(items: list[dict]) -> tuple[int, int, list[str]]:
    """AC-010：逐条 Evidence 校验可追溯性。

    Args:
        items: Evidence 字典列表，字段对齐 EvidenceItem 列名。

    Returns:
        (traceable, total, problems)。

    判定规则：
    - source_type 必须为 internal|web；
    - internal：内部稳定 ID（KB/Document/Version/Segment）与 location_summary 均非空；
    - web：canonical_url_snapshot 与 fetched_at_snapshot 均非空。
    """
    traceable = 0
    total = 0
    problems: list[str] = []
    for item in items:
        total += 1
        source_type = item.get("source_type")
        if source_type == "internal":
            ok = all(item.get(field) for field in _INTERNAL_TRACEABILITY_FIELDS)
            if not ok:
                problems.append(
                    f"item[{total - 1}]: internal 缺可定位位置或稳定 ID"
                )
        elif source_type == "web":
            ok = bool(item.get("canonical_url_snapshot")) and bool(
                item.get("fetched_at_snapshot")
            )
            if not ok:
                problems.append(
                    f"item[{total - 1}]: web 缺 URL 或获取时间"
                )
        else:
            ok = False
            problems.append(f"item[{total - 1}]: source_type 缺失或非法")
        if ok:
            traceable += 1
    return traceable, total, problems
