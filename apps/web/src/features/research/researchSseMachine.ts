/**
 * Research SSE 状态机（纯 reducer，无 React 依赖）。
 *
 * 对齐 FRONTEND §8 与 API.md §13：
 * - LoadingSnapshot → Subscribing → Live → Reconnecting → Terminal；
 * - `stream.end` 不等于任务成功，任务终态以服务端快照为准；
 * - 断开/切页/关浏览器不得取消任务（断线只进入 Reconnecting，不产生取消）；
 * - 事件按 id 幂等消费：快照替换、增量合并，时间线按事件 id 去重；
 * - 未知非终态 Phase/Step 降级为「处理中」。
 */

import type {
  ResearchStepUpdatedEventData,
  ResearchTaskState,
  ResearchTaskStateStep,
  ResearchTaskStatus,
} from '@/api/research'
import { researchPhaseLabel } from '@/features/research/researchPhases'
import type { ResearchSseEvent } from '@/features/research/researchSseParser'

export type ResearchSsePhase =
  'loadingSnapshot' | 'subscribing' | 'live' | 'reconnecting' | 'subscriptionEnded' | 'terminal'

export type ResearchSseError = { code: string; message: string }

export type ResearchTimelineItem = {
  /** 事件 sequence id；重复事件按 id 幂等，不重复入列 */
  eventId: number | null
  timestamp: string | null
  kind: 'phase' | 'step' | 'error' | 'cancel'
  title: string
  detail: string | null
}

export type ResearchSseSnapshot = {
  phase: ResearchSsePhase
  task: ResearchTaskState | null
  lastEventId: number | null
  cancelRequested: boolean
  error: ResearchSseError | null
  timeline: ResearchTimelineItem[]
}

export const initialResearchSseSnapshot: ResearchSseSnapshot = {
  phase: 'loadingSnapshot',
  task: null,
  lastEventId: null,
  cancelRequested: false,
  error: null,
  timeline: [],
}

export type ResearchSseAction =
  | { type: 'snapshotLoaded'; state: ResearchTaskState }
  | { type: 'sse'; event: ResearchSseEvent }
  | { type: 'disconnected' }
  | { type: 'httpError'; error: ResearchSseError }

const TERMINAL_STATUSES: ReadonlySet<ResearchTaskStatus> = new Set([
  'completed',
  'failed',
  'canceled',
  'partially_completed',
])

function isTerminal(status: ResearchTaskStatus): boolean {
  return TERMINAL_STATUSES.has(status)
}

function appendTimeline(
  timeline: ResearchTimelineItem[],
  item: ResearchTimelineItem,
): ResearchTimelineItem[] {
  if (item.eventId !== null && timeline.some((t) => t.eventId === item.eventId)) {
    return timeline
  }
  return [...timeline, item]
}

function upsertStep(steps: ResearchTaskStateStep[], step: ResearchTaskStateStep) {
  const index = steps.findIndex((s) => s.id === step.id)
  if (index === -1) return [...steps, step]
  const next = [...steps]
  next[index] = step
  return next
}

function applyStepUpdate(steps: ResearchTaskStateStep[], data: ResearchStepUpdatedEventData) {
  const id = data.step_id ?? ''
  if (!id) return steps
  const existing = steps.find((s) => s.id === id)
  const merged: ResearchTaskStateStep = {
    id,
    step_type: data.step_type ?? existing?.step_type ?? '',
    status: data.status ?? existing?.status ?? '',
    label: data.label ?? existing?.label ?? null,
    started_at: existing?.started_at ?? null,
    completed_at:
      data.status === 'completed'
        ? (data.timestamp ?? existing?.completed_at ?? null)
        : (existing?.completed_at ?? null),
    sub_questions_count: existing?.sub_questions_count ?? null,
    after_dedup: existing?.after_dedup ?? null,
    sources_created: existing?.sources_created ?? null,
    successful: existing?.successful ?? null,
    failed: existing?.failed ?? null,
    error_code: existing?.error_code ?? null,
    error_message: existing?.error_message ?? null,
    duration_ms: existing?.duration_ms ?? null,
    progress_label: data.label ?? existing?.progress_label ?? null,
  }
  return upsertStep(steps, merged)
}

function buildStepDetail(data: ResearchStepUpdatedEventData): string | null {
  // step.updated 事件不携带数量/耗时（那些在快照 steps[] 中），只输出安全状态说明，
  // 不展示 arguments/observation/output 等可能含模型隐藏推理的字段（FRONTEND §5.9）。
  if (data.success === false) return '步骤执行失败'
  if (data.success === true) return '步骤执行完成'
  return null
}

function toLive(state: ResearchSseSnapshot): ResearchSseSnapshot {
  if (state.phase === 'subscribing' || state.phase === 'reconnecting') {
    return { ...state, phase: 'live' }
  }
  return state
}

function handleSse(state: ResearchSseSnapshot, event: ResearchSseEvent): ResearchSseSnapshot {
  switch (event.type) {
    case 'snapshot': {
      const task = event.data
      const next = {
        ...state,
        task,
        lastEventId: event.id ?? state.lastEventId,
        error: null,
      }
      if (isTerminal(task.status)) {
        return { ...next, phase: 'terminal' }
      }
      return toLive(next)
    }
    case 'task.updated': {
      const data = event.data
      const task = state.task
        ? {
            ...state.task,
            status: (data.status as ResearchTaskStatus) ?? state.task.status,
            current_phase: data.current_phase ?? state.task.current_phase,
            progress: {
              completed_steps: data.completed_steps ?? state.task.progress.completed_steps,
              total_steps: data.total_steps ?? state.task.progress.total_steps,
              progress: data.progress ?? state.task.progress.progress,
            },
            completed_at: data.completed_at ?? state.task.completed_at,
            error:
              data.error_code !== null || data.error_message !== null
                ? {
                    error_code: data.error_code ?? state.task.error?.error_code ?? '',
                    error_message: data.error_message ?? state.task.error?.error_message ?? '',
                    recoverable: data.recoverable ?? state.task.error?.recoverable ?? false,
                  }
                : state.task.error,
          }
        : state.task
      const next = { ...state, task, lastEventId: event.id ?? state.lastEventId }
      if (task && isTerminal(task.status)) {
        return { ...next, phase: 'terminal' }
      }
      return toLive(next)
    }
    case 'phase.updated': {
      const data = event.data
      const task = state.task
        ? { ...state.task, current_phase: data.phase ?? state.task.current_phase }
        : state.task
      const timeline = appendTimeline(state.timeline, {
        eventId: event.id,
        timestamp: data.timestamp ?? null,
        kind: 'phase',
        title: `进入阶段：${researchPhaseLabel(data.phase)}`,
        detail: null,
      })
      return toLive({ ...state, task, lastEventId: event.id ?? state.lastEventId, timeline })
    }
    case 'step.updated': {
      const data = event.data
      const task = state.task
        ? { ...state.task, steps: applyStepUpdate(state.task.steps, data) }
        : state.task
      const title = data.label ?? (data.step_type ? `步骤：${data.step_type}` : '步骤更新')
      const timeline = appendTimeline(state.timeline, {
        eventId: event.id,
        timestamp: data.timestamp ?? null,
        kind: 'step',
        title,
        detail: buildStepDetail(data),
      })
      return toLive({ ...state, task, lastEventId: event.id ?? state.lastEventId, timeline })
    }
    case 'task.canceled': {
      const timeline = appendTimeline(state.timeline, {
        eventId: event.id,
        timestamp: null,
        kind: 'cancel',
        title: '已请求取消',
        detail: null,
      })
      return toLive({
        ...state,
        cancelRequested: true,
        lastEventId: event.id ?? state.lastEventId,
        timeline,
      })
    }
    case 'error': {
      const timeline = appendTimeline(state.timeline, {
        eventId: event.id,
        timestamp: null,
        kind: 'error',
        title: event.data.message,
        detail: event.data.error_code,
      })
      return {
        ...state,
        error: { code: event.data.error_code, message: event.data.message },
        lastEventId: event.id ?? state.lastEventId,
        timeline,
      }
    }
    case 'stream.end': {
      if (state.task && isTerminal(state.task.status)) {
        return { ...state, phase: 'terminal' }
      }
      return { ...state, phase: 'subscriptionEnded' }
    }
  }
}

export function researchSseReducer(
  state: ResearchSseSnapshot,
  action: ResearchSseAction,
): ResearchSseSnapshot {
  switch (action.type) {
    case 'snapshotLoaded': {
      const task = action.state
      if (isTerminal(task.status)) {
        return { ...state, task, error: null, phase: 'terminal' }
      }
      return { ...state, task, error: null, phase: 'subscribing' }
    }
    case 'sse':
      return handleSse(state, action.event)
    case 'disconnected':
      // 断开只进入 Reconnecting；任务在后台持续运行，不发送任何取消
      return { ...state, phase: 'reconnecting' }
    case 'httpError': {
      if (state.task) {
        return { ...state, phase: 'reconnecting', error: action.error }
      }
      return { ...state, error: action.error }
    }
  }
}
