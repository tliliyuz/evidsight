/**
 * Research 展示标签与阶段顺序（FRONTEND §5.9 / 后端 TASK_PHASE_ENUM）。
 *
 * 七阶段为线性顺序，但 `current_phase` / `phase.updated.phase` 在 OpenAPI 中是自由
 * string，前端必须容忍未知非终态值并降级为「处理中」（FRONTEND §8）。
 */

import type { BadgeTone } from '@/components/feedback/StatusBadge'
import type { ResearchSourceStrategy, ResearchTaskStatus } from '@/api/research'

export const RESEARCH_PHASE_ORDER = [
  'planning',
  'searching',
  'fetching',
  'reranking',
  'synthesizing',
  'building_evidence_graph',
  'rendering',
] as const

const RESEARCH_PHASE_LABELS: Record<string, string> = {
  planning: '规划',
  searching: '检索',
  fetching: '获取',
  reranking: '重排',
  synthesizing: '综合',
  building_evidence_graph: '证据图谱',
  rendering: '生成',
}

export function researchPhaseLabel(phase: string | null | undefined): string {
  if (!phase) return '处理中'
  return RESEARCH_PHASE_LABELS[phase] ?? '处理中'
}

export const RESEARCH_STATUS_LABELS: Record<ResearchTaskStatus, string> = {
  pending: '排队中',
  running: '进行中',
  completed: '已完成',
  partially_completed: '部分完成',
  failed: '运行失败',
  canceled: '已取消',
  paused: '已暂停',
}

export const RESEARCH_STATUS_TONES: Record<ResearchTaskStatus, BadgeTone> = {
  pending: 'neutral',
  running: 'processing',
  completed: 'success',
  partially_completed: 'warning',
  failed: 'danger',
  canceled: 'neutral',
  paused: 'warning',
}

/** 来源策略短标签（channel 徽章/紧凑行） */
export const RESEARCH_STRATEGY_LABELS: Record<ResearchSourceStrategy, string> = {
  knowledge: '内部',
  web: '公开',
  hybrid: '混合',
}

/** 来源策略完整名称（任务信息栏/说明） */
export const RESEARCH_STRATEGY_NAMES: Record<ResearchSourceStrategy, string> = {
  knowledge: '内部知识',
  web: '公开网络',
  hybrid: '混合研究',
}

export const RESEARCH_TASK_TYPE_LABELS: Record<string, string> = {
  comparison: '对比研究',
  explainer: '解释型',
  analysis: '影响分析',
}
