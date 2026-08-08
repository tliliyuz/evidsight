"""Pipeline 阶段定义 —— 七阶段流水线的常量与 Phase 函数类型。

对齐 RESEARCH_PIPELINE.md §1.2 / ADR-009：Planning→Search→Fetch→Rerank→
Synthesis→EvidenceGraph→Render 线性串行流水线。

本模块为阶段定义的**唯一权威来源**。原定义位于已删除的
`app.services.pipeline_orchestrator`（切片 7 收敛），迁移至此；
AgentRuntime、TaskLifecycle、Resolver 等相关模块统一从这里引用，
不再各自维护副本。
"""

from __future__ import annotations

from typing import Any, Callable

from app.models.enums import STEP_TYPE_ENUM

# Phase 函数类型：每个 Phase handler 接收 (task, step, session, sse) 返回 output dict。
# 使用 Callable[..., Any] 保持轻量，避免 definition 依赖具体 handler 签名变化。
PhaseFunc = Callable[..., Any]

# 七阶段 step_type 顺序（线性串行，v1.0）
PHASE_ORDER: list[str] = list(STEP_TYPE_ENUM)

# 阶段标签（前端展示用）
PHASE_LABELS: dict[str, str] = {
    "planning": "Planning：拆解研究主题",
    "search": "Search：多子问题搜索",
    "fetch": "Fetch：网页内容抓取",
    "rerank": "Rerank：来源粗筛精排",
    "synthesis": "Synthesis：跨源综合",
    "evidence_graph": "来源图谱：结构化认知资产构建",
    "render": "Render：报告渲染",
}

# Phase → phase 名称映射（step_type → TASK_PHASE_ENUM 的进行时名称，SSE 事件使用）
STEP_TYPE_TO_PHASE: dict[str, str] = {
    "planning": "planning",
    "search": "searching",
    "fetch": "fetching",
    "rerank": "reranking",
    "synthesis": "synthesizing",
    "evidence_graph": "building_evidence_graph",
    "render": "rendering",
}
