/**
 * Research v1 canonical SSE 解析器（API.md §13）。
 *
 * 只消费 `GET /api/v1/research/tasks/{task_id}/events` 输出的 canonical 事件：
 * `snapshot` / `task.updated` / `phase.updated` / `step.updated` / `task.canceled` /
 * `error` / `stream.end{reason}`。心跳使用 SSE 注释帧（`:` 开头），本解析器忽略。
 *
 * 与 Chat SSE 的差异：
 * - Research 是非终态事件才带 `id`（持久游标 sequence）；终态 `snapshot`/`stream.end`
 *   无 `id`，因此事件 id 为 `number | null`；
 * - 事件 data 的 OpenAPI Schema 为 `additionalProperties:true`，本解析器只归一化已知
 *   字段，未知字段与畸形帧按容错原则忽略，不阻断后续事件。
 *
 * 解析器为增量式：网络分帧可能把单个事件拆到多个 chunk，内部维护缓冲区，
 * 每次喂入 chunk 返回本次已完整收到的事件数组。
 */

import type {
  ResearchPhaseUpdatedEventData,
  ResearchStepUpdatedEventData,
  ResearchStreamEndEventData,
  ResearchTaskCanceledEventData,
  ResearchTaskState,
  ResearchTaskStateStep,
  ResearchTaskStatus,
  ResearchTaskUpdatedEventData,
} from '@/api/research'

export type ResearchSseEvent =
  | { type: 'snapshot'; id: number | null; data: ResearchTaskState }
  | { type: 'task.updated'; id: number | null; data: ResearchTaskUpdatedEventData }
  | { type: 'phase.updated'; id: number | null; data: ResearchPhaseUpdatedEventData }
  | { type: 'step.updated'; id: number | null; data: ResearchStepUpdatedEventData }
  | { type: 'task.canceled'; id: number | null; data: ResearchTaskCanceledEventData }
  | {
      type: 'error'
      id: number | null
      data: { error_code: string; message: string; retryable: boolean }
    }
  | { type: 'stream.end'; id: number | null; data: ResearchStreamEndEventData }

type Frame = {
  event: string | null
  id: number | null
  data: string | null
}

const EVENT_NAMES = new Set([
  'snapshot',
  'task.updated',
  'phase.updated',
  'step.updated',
  'task.canceled',
  'error',
  'stream.end',
])

function str(value: unknown): string | null {
  if (value === null || value === undefined) return null
  return String(value)
}

function num(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

function bool(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null
}

function obj(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : null
}

function normalizeProgress(raw: Record<string, unknown>) {
  return {
    completed_steps: num(raw.completed_steps) ?? 0,
    total_steps: num(raw.total_steps) ?? 0,
    progress: num(raw.progress) ?? 0,
  }
}

function normalizeStep(raw: Record<string, unknown>): ResearchTaskStateStep {
  return {
    id: str(raw.id) ?? '',
    step_type: str(raw.step_type) ?? '',
    status: str(raw.status) ?? '',
    label: str(raw.label),
    started_at: str(raw.started_at),
    completed_at: str(raw.completed_at),
    sub_questions_count: num(raw.sub_questions_count),
    after_dedup: num(raw.after_dedup),
    sources_created: num(raw.sources_created),
    successful: num(raw.successful),
    failed: num(raw.failed),
    error_code: str(raw.error_code),
    error_message: str(raw.error_message),
    duration_ms: num(raw.duration_ms),
    progress_label: str(raw.progress_label),
  }
}

function normalizeState(raw: Record<string, unknown>): ResearchTaskState {
  return {
    task_id: str(raw.task_id) ?? '',
    topic: str(raw.topic) ?? '',
    status: str(raw.status) as ResearchTaskStatus,
    current_phase: str(raw.current_phase),
    progress: normalizeProgress(obj(raw.progress) ?? {}),
    steps: Array.isArray(raw.steps)
      ? raw.steps
          .filter((s): s is Record<string, unknown> => typeof s === 'object' && s !== null)
          .map(normalizeStep)
      : [],
    error: obj(raw.error)
      ? {
          error_code: str((raw.error as Record<string, unknown>).error_code) ?? '',
          error_message: str((raw.error as Record<string, unknown>).error_message) ?? '',
          recoverable: (raw.error as Record<string, unknown>).recoverable === true,
        }
      : null,
    stats: {
      total_sources: num(obj(raw.stats)?.total_sources) ?? 0,
      total_evidence: num(obj(raw.stats)?.total_evidence) ?? 0,
    },
    report_id: str(raw.report_id),
    created_at: str(raw.created_at) ?? '',
    started_at: str(raw.started_at),
    completed_at: str(raw.completed_at),
  }
}

function normalizeTaskUpdated(raw: Record<string, unknown>): ResearchTaskUpdatedEventData {
  return {
    task_id: str(raw.task_id),
    status: str(raw.status),
    current_phase: str(raw.current_phase),
    completed_steps: num(raw.completed_steps),
    total_steps: num(raw.total_steps),
    progress: num(raw.progress),
    message: str(raw.message),
    error_code: str(raw.error_code),
    error_message: str(raw.error_message),
    completed_at: str(raw.completed_at),
    recoverable: typeof raw.recoverable === 'boolean' ? raw.recoverable : null,
  }
}

function normalizePhaseUpdated(raw: Record<string, unknown>): ResearchPhaseUpdatedEventData {
  return {
    phase: str(raw.phase),
    timestamp: str(raw.timestamp),
    duration_ms: num(raw.duration_ms),
  }
}

function normalizeStepUpdated(raw: Record<string, unknown>): ResearchStepUpdatedEventData {
  return {
    step_id: str(raw.step_id),
    step_type: str(raw.step_type),
    status: str(raw.status),
    label: str(raw.label),
    timestamp: str(raw.timestamp),
    phase: str(raw.phase),
    last_completed_step_id: str(raw.last_completed_step_id),
    output: obj(raw.output),
    iteration: num(raw.iteration),
    tool_call_id: str(raw.tool_call_id),
    tool_name: str(raw.tool_name),
    arguments: obj(raw.arguments),
    observation: str(raw.observation),
    success: bool(raw.success),
  }
}

function normalizeCanceled(raw: Record<string, unknown>): ResearchTaskCanceledEventData {
  return {
    task_id: str(raw.task_id) ?? '',
    status: str(raw.status) ?? '',
    cancel_requested: raw.cancel_requested === true,
  }
}

function parseFrame(raw: string): Frame {
  let event: string | null = null
  let id: number | null = null
  const dataLines: string[] = []
  for (const line of raw.split('\n')) {
    if (line === '' || line.startsWith(':')) {
      // 空行与注释帧跳过
      continue
    }
    if (line.startsWith('event:')) {
      event = line.slice('event:'.length).trim()
    } else if (line.startsWith('id:')) {
      const value = line.slice('id:'.length).trim()
      if (value !== '') {
        const parsed = Number(value)
        if (Number.isFinite(parsed)) {
          id = parsed
        }
      }
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trimStart())
    }
    // 其他字段（retry 等）忽略
  }
  return { event, id, data: dataLines.length ? dataLines.join('\n') : null }
}

/**
 * 增量式 Research canonical SSE 解析器。
 * 每次调用喂入一段流式文本，返回本次完整解析出的业务事件。
 */
export function createResearchSseParser(): (chunk: string) => ResearchSseEvent[] {
  let buffer = ''
  return (chunk: string): ResearchSseEvent[] => {
    buffer += chunk
    const events: ResearchSseEvent[] = []
    let boundary: number
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const frame = parseFrame(raw)
      if (frame.event === null || frame.data === null || !EVENT_NAMES.has(frame.event)) {
        // 畸形帧或未知事件：按容错原则忽略，不阻断后续事件
        continue
      }
      let data: unknown
      try {
        data = JSON.parse(frame.data)
      } catch {
        // data 非法的帧忽略
        continue
      }
      if (typeof data !== 'object' || data === null) {
        continue
      }
      const payload = data as Record<string, unknown>
      switch (frame.event) {
        case 'snapshot':
          events.push({ type: 'snapshot', id: frame.id, data: normalizeState(payload) })
          break
        case 'task.updated':
          events.push({
            type: 'task.updated',
            id: frame.id,
            data: normalizeTaskUpdated(payload),
          })
          break
        case 'phase.updated':
          events.push({
            type: 'phase.updated',
            id: frame.id,
            data: normalizePhaseUpdated(payload),
          })
          break
        case 'step.updated':
          events.push({
            type: 'step.updated',
            id: frame.id,
            data: normalizeStepUpdated(payload),
          })
          break
        case 'task.canceled':
          events.push({
            type: 'task.canceled',
            id: frame.id,
            data: normalizeCanceled(payload),
          })
          break
        case 'error':
          events.push({
            type: 'error',
            id: frame.id,
            data: {
              error_code: str(payload.error_code) ?? '',
              message: str(payload.message) ?? '',
              retryable: payload.retryable === true,
            },
          })
          break
        case 'stream.end':
          events.push({
            type: 'stream.end',
            id: frame.id,
            data: { reason: str(payload.reason) ?? '' },
          })
          break
      }
    }
    return events
  }
}
