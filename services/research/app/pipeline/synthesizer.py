"""Synthesis 阶段 —— 跨源综合。

对齐 RESEARCH_PIPELINE.md §6：
- 读取 Rerank 产出的 Evidence[]
- 调用 deepseek-v4-pro（deep_thinking=True, temperature=0.3, max_tokens=5000）
- 完成观点聚类 / 共识识别 / 冲突发现 / 信息缺口
- 输出 SynthesisNotes 写入 research_steps.output，供 Evidence Graph Build 消费

Evidence 索引说明：
- 本阶段内部使用 0-based 索引（对齐 §6.2 示例 [0,3,7]）
- §6.3 Evidence 格式化策略中的「[来源 N]」在内部被转换为 0-based 索引
- 最终 SynthesisNotes.clusters[i].supporting_evidence_indices 保持 0-based
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.exceptions import SynthesisFailedException
from app.core.internal_retrieval_client import resolve_retrieval
from app.core.llm import LLMResult, chat_completion
from app.core.token_counter import estimate_tokens
from app.models.evidence_item import EvidenceItem
from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask
from app.pipeline.sse_bridge import (
    EVENT_STEP_COMPLETED,
    EVENT_STEP_PROGRESS,
    SSEBridge,
)

logger = logging.getLogger(__name__)

# ── System Prompt 模板（对齐 RESEARCH_PIPELINE.md §6.2）────────

_SYSTEM_PROMPT_TEMPLATE = """你是一个研究综合专家。请基于以下研究证据进行跨源综合。

研究主题：{topic}
研究类型：{task_type}

研究证据（共 {evidence_count} 条）：
{evidence_items_formatted}

请完成以下任务：

1. **观点聚类**：将证据按观点/结论分组，每组标注核心主题
2. **共识识别**：标记多个来源共同支持的高置信度结论
3. **冲突发现**：标注不同来源之间的矛盾或分歧
4. **信息缺口**：指出研究主题中未被证据覆盖的方面

输出严格 JSON 格式：
{{
  "clusters": [
    {{
      "theme": "聚类主题",
      "summary": "该聚类的核心结论（1-2 句）",
      "consensus_level": "strong" | "moderate" | "weak",
      "supporting_evidence_indices": [0, 3, 7],
      "conflicting_evidence_indices": []
    }}
  ],
  "claims": [
    {{
      "statement": "最小结论单元（接受证据评估的综合结论）",
      "critical": true,
      "certainty": "high" | "medium" | "low",
      "qualification": "限定、不确定性或时效风险（无则省略）",
      "evidence_relations": [
        {{"evidence_index": 0, "relation_type": "supports" | "contradicts" | "context", "confidence": 0.9}}
      ]
    }}
  ],
  "conflicts": [
    {{
      "topic": "分歧主题",
      "position_a": {{"summary": "...", "evidence_indices": [1]}},
      "position_b": {{"summary": "...", "evidence_indices": [4]}}
    }}
  ],
  "knowledge_gaps": ["未被充分覆盖的方面 1", ...],
  "overall_assessment": "整体证据质量评估（2-3 句）"
}}

claims 要求：
1. statement 是接受证据评估的最小结论，不得编造不存在的来源；
2. critical=true 表示关键结论（必须至少一条 supports）；
3. evidence_relations 的 evidence_index 必须引用证据详情中的 0-based 编号；
4. 存在 contradicts 关系时，statement 不得写成无条件确定结论；
5. confidence 为 0-1 的关系判断置信度，不代表来源绝对真实性。"""

# ── 数据类型 ──────────────────────────────────────────────────


@dataclass
class ClaimEvidenceRelation:
    """Claim 的拟议证据关系（DATABASE.md §7.5）。"""

    evidence_index: int
    relation_type: str  # supports / contradicts / context
    confidence: float = 0.0


@dataclass
class SynthesisClaim:
    """报告最小结论单元（RESEARCH_PIPELINE §8.1 / DATABASE.md §7.4）。"""

    statement: str
    critical: bool
    certainty: str  # high / medium / low
    qualification: str | None
    evidence_relations: list[ClaimEvidenceRelation]


@dataclass
class ConflictPosition:
    """冲突中的一方立场。"""

    summary: str
    evidence_indices: list[int]


@dataclass
class SynthesisCluster:
    """观点聚类。"""

    theme: str
    summary: str
    consensus_level: str  # strong / moderate / weak
    supporting_evidence_indices: list[int]
    conflicting_evidence_indices: list[int]


@dataclass
class SynthesisConflict:
    """冲突发现。"""

    topic: str
    position_a: ConflictPosition
    position_b: ConflictPosition


@dataclass
class SynthesisNotes:
    """Synthesis 阶段最终输出。"""

    clusters: list[SynthesisCluster]
    conflicts: list[SynthesisConflict]
    knowledge_gaps: list[str]
    overall_assessment: str
    claims: list[SynthesisClaim]


# ── 工具函数 ──────────────────────────────────────────────────


def _extract_json_from_text(text: str) -> str:
    """从 LLM 输出中提取 JSON（处理可能的 markdown 代码块包装）。"""
    text = text.strip()

    code_block_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_block_match:
        return code_block_match.group(1).strip()

    brace_start = text.find("{")
    if brace_start == -1:
        return text

    brace_end = text.rfind("}")
    if brace_end == -1:
        return text

    return text[brace_start : brace_end + 1]


def _format_evidence_items(
    items: list[EvidenceItem],
    max_sources: int,
    resolved: dict[int, str] | None = None,
) -> tuple[str, list[EvidenceItem]]:
    """将 EvidenceItem[] 格式化为 Prompt 文本，并受 TOKEN_BUDGET_SOFT_LIMIT 约束。

    internal EvidenceItem 无正文（content=None），必须由当前 Step attempt
    按稳定身份重取（RESEARCH_PIPELINE §8.1 / ADR-003），resolved 提供
    {evidence_id: 正文} 的内存工作集，不持久化。

    处理逻辑：
    1. 按 relevance_score 降序（防御性重排）
    2. 在 token 软上限内逐步减少 evidence 数量与单条长度
    3. 使用 0-based 索引 [来源 0], [来源 1]...

    Returns:
        (formatted_text, selected_items)
    """
    resolved = resolved or {}

    def _item_content(ev: EvidenceItem) -> str:
        if ev.source_type == "internal":
            return resolved.get(ev.id) or ""
        return ev.content or ""

    def _item_title(ev: EvidenceItem) -> str:
        if ev.source_type == "internal":
            return ev.document_display_name_snapshot or ev.display_title or "内部来源"
        source = ev.source
        if source:
            return source.title or "无标题"
        return "无标题"

    sorted_items = sorted(
        items,
        key=lambda e: e.relevance_score or 0.0,
        reverse=True,
    )

    # 在 token 预算内截断：先减少条数，再缩短单条长度
    content_limit = 1500
    count_limit = min(max_sources, len(sorted_items))
    while count_limit >= 1:
        selected = sorted_items[:count_limit]
        parts: list[str] = []
        for i, ev in enumerate(selected, start=0):
            if ev.source_type == "internal":
                label = f"内部来源：[来源 {i}] {_item_title(ev)}"
            else:
                source = ev.source
                domain = source.domain if source else "unknown"
                label = f"来源标注：[来源 {i}] {domain} — {_item_title(ev)}"
            content = _item_content(ev)[:content_limit]
            parts.append(f"{label}\n内容：{content}")

        formatted = "\n\n".join(parts)
        if estimate_tokens(formatted) <= settings.TOKEN_BUDGET_SOFT_LIMIT:
            if count_limit < min(max_sources, len(sorted_items)) or content_limit < 1500:
                logger.warning(
                    "Synthesis Evidence 截断: %d→%d 条, content_limit=%d",
                    len(sorted_items),
                    count_limit,
                    content_limit,
                )
            return formatted, selected

        if content_limit >= 500:
            content_limit -= 250
            continue

        count_limit -= 1
        content_limit = 1500

    # 兜底保留 1 条最短内容
    selected = sorted_items[:1]
    ev = selected[0]
    if ev.source_type == "internal":
        label = f"内部来源：[来源 0] {_item_title(ev)}"
    else:
        source = ev.source
        domain = source.domain if source else "unknown"
        label = f"来源标注：[来源 0] {domain} — {_item_title(ev)}"
    formatted = f"{label}\n内容：{_item_content(ev)[:250]}"
    return formatted, selected


def _build_synthesis_prompt(
    topic: str,
    task_type: str,
    evidence_items_formatted: str,
    evidence_count: int,
) -> list[dict[str, str]]:
    """构建 Synthesis Prompt。"""
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        topic=topic,
        task_type=task_type,
        evidence_count=evidence_count,
        evidence_items_formatted=evidence_items_formatted,
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "请基于上述研究证据进行跨源综合，输出严格 JSON 格式。"},
    ]


def _validate_indices(indices: list[Any], expected_count: int, field_name: str) -> list[int]:
    """校验 evidence 索引列表。

    - 非整数索引 → raise ValueError（触发重试）
    - 越界索引 → raise ValueError（§8.1 严格引用闭包校验：LLM 引用未知
      Candidate/Evidence ID 时不得静默过滤，§17.2-6 由 Graph Build 失败体现）

    Returns:
        全部合法的 int 索引列表
    """
    valid: list[int] = []
    for idx in indices:
        if not isinstance(idx, int):
            raise ValueError(f"{field_name} 包含非整数索引: {idx!r}")
        if not (0 <= idx < expected_count):
            raise ValueError(f"{field_name} 越界索引: {idx}（有效范围 0-{expected_count - 1}）")
        valid.append(idx)
    return valid


def _parse_synthesis_output(raw_text: str, expected_count: int) -> SynthesisNotes:
    """解析 LLM 输出为 SynthesisNotes。

    Raises:
        ValueError: JSON 无效、clusters 缺失/格式错误、索引非整数
    """
    json_text = _extract_json_from_text(raw_text)
    data = json.loads(json_text)

    if not isinstance(data, dict):
        raise ValueError("LLM 输出不是 JSON 对象")

    # clusters 必须存在且为数组
    clusters_raw = data.get("clusters")
    if not isinstance(clusters_raw, list):
        raise ValueError("缺少 clusters 数组")

    clusters: list[SynthesisCluster] = []
    for i, c in enumerate(clusters_raw):
        if not isinstance(c, dict):
            raise ValueError(f"clusters[{i}] 不是对象")

        theme = c.get("theme", "")
        summary = c.get("summary", "")
        if not isinstance(theme, str) or not theme.strip():
            raise ValueError(f"clusters[{i}].theme 为空")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError(f"clusters[{i}].summary 为空")

        consensus_level = c.get("consensus_level", "")
        if consensus_level not in {"strong", "moderate", "weak"}:
            raise ValueError(f"clusters[{i}].consensus_level 非法: {consensus_level}")

        supporting = _validate_indices(
            c.get("supporting_evidence_indices", []) or [],
            expected_count,
            f"clusters[{i}].supporting_evidence_indices",
        )
        conflicting = _validate_indices(
            c.get("conflicting_evidence_indices", []) or [],
            expected_count,
            f"clusters[{i}].conflicting_evidence_indices",
        )

        # RESEARCH_PIPELINE §9.5 / PRD FR-EV-003：存在 contradicts（冲突证据）时
        # 不得合成为无条件确定结论——含冲突证据的 cluster 不允许 consensus_level=strong。
        if conflicting and consensus_level == "strong":
            raise ValueError(
                f"clusters[{i}].consensus_level=strong 与 conflicting_evidence_indices "
                f"{conflicting} 冲突：含冲突证据的聚类不得标记为无条件确定结论"
            )

        clusters.append(
            SynthesisCluster(
                theme=theme.strip(),
                summary=summary.strip(),
                consensus_level=consensus_level,
                supporting_evidence_indices=supporting,
                conflicting_evidence_indices=conflicting,
            )
        )

    # conflicts 允许 null → 空数组
    conflicts_raw = data.get("conflicts")
    if conflicts_raw is None:
        conflicts_raw = []
    if not isinstance(conflicts_raw, list):
        raise ValueError("conflicts 必须是数组或 null")

    conflicts: list[SynthesisConflict] = []
    for i, c in enumerate(conflicts_raw):
        if not isinstance(c, dict):
            raise ValueError(f"conflicts[{i}] 不是对象")

        topic = c.get("topic", "")
        if not isinstance(topic, str) or not topic.strip():
            raise ValueError(f"conflicts[{i}].topic 为空")

        pos_a_raw = c.get("position_a", {})
        pos_b_raw = c.get("position_b", {})
        if not isinstance(pos_a_raw, dict) or not isinstance(pos_b_raw, dict):
            raise ValueError(f"conflicts[{i}] position 不是对象")

        pos_a = ConflictPosition(
            summary=str(pos_a_raw.get("summary", "")).strip(),
            evidence_indices=_validate_indices(
                pos_a_raw.get("evidence_indices", []) or [],
                expected_count,
                f"conflicts[{i}].position_a.evidence_indices",
            ),
        )
        pos_b = ConflictPosition(
            summary=str(pos_b_raw.get("summary", "")).strip(),
            evidence_indices=_validate_indices(
                pos_b_raw.get("evidence_indices", []) or [],
                expected_count,
                f"conflicts[{i}].position_b.evidence_indices",
            ),
        )

        conflicts.append(
            SynthesisConflict(
                topic=topic.strip(),
                position_a=pos_a,
                position_b=pos_b,
            )
        )

    # knowledge_gaps 允许空数组
    gaps_raw = data.get("knowledge_gaps", [])
    if not isinstance(gaps_raw, list):
        raise ValueError("knowledge_gaps 必须是数组")
    knowledge_gaps = [str(g).strip() for g in gaps_raw if isinstance(g, str) and g.strip()]

    # overall_assessment 必须是非空字符串
    overall = data.get("overall_assessment", "")
    if not isinstance(overall, str) or not overall.strip():
        raise ValueError("overall_assessment 为空")

    # claims 允许缺省 → 空数组（DATABASE.md §7.4 / RESEARCH_PIPELINE §8.1）
    claims_raw = data.get("claims", [])
    if claims_raw is None:
        claims_raw = []
    if not isinstance(claims_raw, list):
        raise ValueError("claims 必须是数组或 null")

    claims: list[SynthesisClaim] = []
    for i, c in enumerate(claims_raw):
        if not isinstance(c, dict):
            raise ValueError(f"claims[{i}] 不是对象")

        statement = c.get("statement", "")
        if not isinstance(statement, str) or not statement.strip():
            raise ValueError(f"claims[{i}].statement 为空")
        if statement.strip() == "[]":
            raise ValueError(f"claims[{i}].statement 不能为占位符")

        critical = c.get("critical", False)
        if not isinstance(critical, bool):
            raise ValueError(f"claims[{i}].critical 必须是布尔值")

        certainty = c.get("certainty", "medium")
        if certainty not in {"high", "medium", "low"}:
            raise ValueError(f"claims[{i}].certainty 非法: {certainty}")

        qualification = c.get("qualification")
        if qualification is not None and not isinstance(qualification, str):
            raise ValueError(f"claims[{i}].qualification 必须是字符串或 null")
        qualification = qualification.strip() if isinstance(qualification, str) else None

        relations_raw = c.get("evidence_relations", []) or []
        if not isinstance(relations_raw, list):
            raise ValueError(f"claims[{i}].evidence_relations 必须是数组")

        relations: list[ClaimEvidenceRelation] = []
        for j, rel in enumerate(relations_raw):
            if not isinstance(rel, dict):
                raise ValueError(f"claims[{i}].evidence_relations[{j}] 不是对象")
            rel_type = rel.get("relation_type", "")
            if rel_type not in {"supports", "contradicts", "context"}:
                raise ValueError(
                    f"claims[{i}].evidence_relations[{j}].relation_type 非法: {rel_type}"
                )
            idx_raw = rel.get("evidence_index")
            if not isinstance(idx_raw, int) or isinstance(idx_raw, bool):
                raise ValueError(
                    f"claims[{i}].evidence_relations[{j}].evidence_index 非整数: {idx_raw!r}"
                )
            if not (0 <= idx_raw < expected_count):
                # §8.1 严格引用闭包校验：越界索引 = 引用不存在的 Candidate，拒绝而非过滤
                raise ValueError(
                    f"claims[{i}].evidence_relations[{j}].evidence_index 越界: "
                    f"{idx_raw}（有效范围 0-{expected_count - 1}）"
                )
            confidence = rel.get("confidence", 0.0)
            if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
                raise ValueError(
                    f"claims[{i}].evidence_relations[{j}].confidence 非法: {confidence!r}"
                )
            if not (0 <= float(confidence) <= 1):
                raise ValueError(
                    f"claims[{i}].evidence_relations[{j}].confidence 超出 0-1: {confidence}"
                )
            relations.append(
                ClaimEvidenceRelation(
                    evidence_index=idx_raw,
                    relation_type=rel_type,
                    confidence=float(confidence),
                )
            )

        # §9.5 门禁 5 / PRD FR-EV-003：存在 contradicts 的 claim 不得合成为
        # 无条件确定结论——certainty=high 且无 qualification 限定即拒绝。
        has_contradicts = any(r.relation_type == "contradicts" for r in relations)
        if has_contradicts and certainty == "high" and not qualification:
            raise ValueError(
                f"claims[{i}] 含 contradicts 且 certainty=high 但无 qualification："
                f"存在相反证据时不得合成为无条件确定结论"
            )

        claims.append(
            SynthesisClaim(
                statement=statement.strip(),
                critical=critical,
                certainty=certainty,
                qualification=qualification,
                evidence_relations=relations,
            )
        )
    return SynthesisNotes(
        clusters=clusters,
        conflicts=conflicts,
        knowledge_gaps=knowledge_gaps,
        overall_assessment=overall.strip(),
        claims=claims,
    )


# ── 上游数据读取 ──────────────────────────────────────────────


async def _load_evidence(
    session: AsyncSession,
    task: ResearchTask,
) -> list[EvidenceItem]:
    """读取 Rerank 产出的 EvidenceItem[]（含 source 关系）。"""
    stmt = (
        select(EvidenceItem)
        .where(EvidenceItem.task_id == task.id)
        .options(selectinload(EvidenceItem.source))
        .order_by(
            sa.case((EvidenceItem.relevance_score.is_(None), 1), else_=0),
            EvidenceItem.relevance_score.desc(),
        )
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _resolve_internal_evidence(
    task: ResearchTask,
    items: list[EvidenceItem],
) -> dict[int, str]:
    """按稳定身份重取 internal Evidence 当前正文（仅当前 Step 内存）。

    对齐 RESEARCH_PIPELINE §8.1 / ADR-003：Synthesis 的 Step attempt 使用
    EvidenceResolveRequest 精确重取，构造临时工作集；正文不持久化。

    Returns:
        dict {evidence_id: minimal_excerpt}；resolve 失败（KB_FORBIDDEN /
        契约错误 / 瞬时不可用重试耗尽）按客户端错误映射 fail-closed 抛出。
    """
    internal = [ev for ev in items if ev.source_type == "internal"]
    if not internal:
        return {}

    references = [
        {
            "knowledge_base_id": ev.knowledge_base_id,
            "document_id": ev.document_id,
            "document_version_id": ev.document_version_id,
            "segment_id": ev.segment_id,
        }
        for ev in internal
    ]
    resolved = await resolve_retrieval(user_id=str(task.user_id), references=references)
    return {ev.id: getattr(ref, "minimal_excerpt", "") or "" for ev, ref in zip(internal, resolved)}


# ── LLM 综合 ──────────────────────────────────────────────────


async def _llm_synthesize(
    topic: str,
    task_type: str,
    evidence_items_formatted: str,
    evidence_count: int,
) -> tuple[SynthesisNotes, int, int, int]:
    """调用 LLM 完成跨源综合。

    Returns:
        (notes, prompt_tokens, completion_tokens, retry_count)

    Raises:
        SynthesisFailedException: 重试耗尽或输出无效
    """
    messages = _build_synthesis_prompt(
        topic=topic,
        task_type=task_type,
        evidence_items_formatted=evidence_items_formatted,
        evidence_count=evidence_count,
    )

    total_prompt_tokens = 0
    total_completion_tokens = 0
    last_error: Exception | None = None
    result: LLMResult | None = None

    max_retries = settings.PIPELINE_SYNTHESIS_MAX_RETRIES
    for attempt in range(max_retries + 1):
        try:
            result = await chat_completion(
                messages=messages,
                model=settings.LLM_MODEL,
                deep_thinking=True,
                temperature=0.3,
                max_tokens=5000,
            )

            total_prompt_tokens += result.prompt_tokens
            total_completion_tokens += result.completion_tokens

            notes = _parse_synthesis_output(result.content, evidence_count)
            return notes, total_prompt_tokens, total_completion_tokens, attempt

        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            logger.warning("Synthesis LLM 输出解析失败 (attempt %d): %s", attempt, e)
            if attempt < max_retries:
                messages.append({"role": "assistant", "content": result.content if result else ""})
                messages.append(
                    {
                        "role": "user",
                        "content": f"输出格式错误：{e}。请重新输出严格 JSON，确保 clusters 格式正确。",
                    }
                )
                continue
            break

        except Exception as e:
            last_error = e
            logger.warning("Synthesis LLM 调用失败 (attempt %d): %s", attempt, e)
            if attempt < max_retries:
                continue
            break

    raise SynthesisFailedException(
        detail=f"LLM Synthesis 失败（{max_retries} 次重试耗尽）: {last_error}"
    )


# ── 序列化辅助 ────────────────────────────────────────────────


def _cluster_to_dict(cluster: SynthesisCluster) -> dict:
    return {
        "theme": cluster.theme,
        "summary": cluster.summary,
        "consensus_level": cluster.consensus_level,
        "supporting_evidence_indices": cluster.supporting_evidence_indices,
        "conflicting_evidence_indices": cluster.conflicting_evidence_indices,
    }


def _conflict_to_dict(conflict: SynthesisConflict) -> dict:
    return {
        "topic": conflict.topic,
        "position_a": {
            "summary": conflict.position_a.summary,
            "evidence_indices": conflict.position_a.evidence_indices,
        },
        "position_b": {
            "summary": conflict.position_b.summary,
            "evidence_indices": conflict.position_b.evidence_indices,
        },
    }


def _claim_to_dict(claim: SynthesisClaim) -> dict:
    return {
        "statement": claim.statement,
        "critical": claim.critical,
        "certainty": claim.certainty,
        "qualification": claim.qualification,
        "evidence_relations": [
            {
                "evidence_index": rel.evidence_index,
                "relation_type": rel.relation_type,
                "confidence": rel.confidence,
            }
            for rel in claim.evidence_relations
        ],
    }


# ── 主入口 ────────────────────────────────────────────────────


async def run_synthesis(
    task: ResearchTask,
    step: ResearchStep,
    session: AsyncSession,
    sse_bridge: SSEBridge,
) -> dict:
    """执行 Synthesis 阶段。

    1. 读取 EvidenceItem[]
    2. 按 relevance_score 降序 + max_sources 截断
    3. 调用 LLM 完成跨源综合
    4. 发射 SSE 事件
    5. 返回 output dict（写入 step.output）

    Returns:
        output dict（含 clusters / conflicts / knowledge_gaps / overall_assessment）
    """
    task_id = str(task.id)
    step_id = str(step.id)

    requirements = task.requirements or {}
    task_type = requirements.get("task_type", "explainer")
    max_sources = int(requirements.get("max_sources", 10))

    logger.info(
        "Synthesis 开始: task_id=%s, task_type=%s, max_sources=%d", task_id, task_type, max_sources
    )

    # 1. 读取上游 Evidence
    evidence_items = await _load_evidence(session, task)
    if not evidence_items:
        raise SynthesisFailedException(detail="没有可供综合的证据")

    # 2. 重取 internal Evidence 当前正文（仅当前 Step 内存，不持久化）
    resolved = await _resolve_internal_evidence(task, evidence_items)

    # 3. 格式化 Evidence（0-based 索引）
    evidence_items_formatted, selected_items = _format_evidence_items(
        evidence_items,
        max_sources=max_sources,
        resolved=resolved,
    )
    evidence_count = len(selected_items)

    logger.info(
        "Synthesis Evidence 准备完成: task_id=%s, total=%d, selected=%d",
        task_id,
        len(evidence_items),
        evidence_count,
    )

    await sse_bridge.publish(
        EVENT_STEP_PROGRESS,
        {
            "step_id": step_id,
            "phase": "synthesizing",
            "label": f"正在对 {evidence_count} 条来源进行跨源综合...",
            "evidence_count": evidence_count,
        },
    )

    # 4. 调用 LLM 综合
    notes, prompt_tokens, completion_tokens, retry_count = await _llm_synthesize(
        topic=task.topic,
        task_type=task_type,
        evidence_items_formatted=evidence_items_formatted,
        evidence_count=evidence_count,
    )

    # 4. 进度事件（聚类完成）
    await sse_bridge.publish(
        EVENT_STEP_PROGRESS,
        {
            "step_id": step_id,
            "phase": "synthesizing",
            "label": f"综合完成，生成 {len(notes.clusters)} 个观点聚类",
            "clusters_count": len(notes.clusters),
        },
    )

    # 5. 完成事件
    await sse_bridge.publish(
        EVENT_STEP_COMPLETED,
        {
            "step_id": step_id,
            "clusters": [_cluster_to_dict(c) for c in notes.clusters],
            "claims": [_claim_to_dict(c) for c in notes.claims],
            "conflicts": [_conflict_to_dict(c) for c in notes.conflicts],
            "clusters_count": len(notes.clusters),
            "claims_count": len(notes.claims),
            "conflicts_count": len(notes.conflicts),
            "gaps_count": len(notes.knowledge_gaps),
        },
    )

    output = {
        "clusters": [_cluster_to_dict(c) for c in notes.clusters],
        "claims": [_claim_to_dict(c) for c in notes.claims],
        "conflicts": [_conflict_to_dict(c) for c in notes.conflicts],
        "knowledge_gaps": notes.knowledge_gaps,
        "overall_assessment": notes.overall_assessment,
        "clusters_count": len(notes.clusters),
        "claims_count": len(notes.claims),
        "conflicts_count": len(notes.conflicts),
        "gaps_count": len(notes.knowledge_gaps),
        "model": settings.LLM_MODEL,
        "retry_count": retry_count,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "evidence_count": evidence_count,
    }

    logger.info(
        "Synthesis 完成: task_id=%s, clusters=%d, claims=%d, conflicts=%d, gaps=%d, retries=%d",
        task_id,
        len(notes.clusters),
        len(notes.claims),
        len(notes.conflicts),
        len(notes.knowledge_gaps),
        retry_count,
    )

    return output
