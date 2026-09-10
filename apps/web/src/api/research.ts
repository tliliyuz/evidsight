/**
 * Research Task v1 API 客户端（API.md §8）—— 工作台最小消费子集。
 *
 * 纠偏 2（AppShell 与工作台）只消费列表端点：顶部运行任务 Chip 需要真实运行中
 * 任务数量，工作台 RECENT RESEARCH 需要来源类型/状态/进度/继续入口。字段契约以
 * `docs/openapi/evidsight-v1.yaml` 的 ResearchTaskListItem 为唯一权威源，不得
 * 绑定 legacy DTO 或手工推断字段。
 */

import type { AxiosInstance } from 'axios'

import { apiClient, getAccessToken } from '@/api/client'
import {
  createResearchSseParser,
  type ResearchSseEvent,
} from '@/features/research/researchSseParser'

export type ResearchTaskStatus =
  'pending' | 'running' | 'completed' | 'partially_completed' | 'failed' | 'canceled' | 'paused'

export type ResearchSourceStrategy = 'knowledge' | 'web' | 'hybrid'

export type ResearchTaskListItem = {
  task_id: string
  topic: string
  status: ResearchTaskStatus
  task_type: string
  source_strategy: ResearchSourceStrategy
  progress: number
  total_sources: number
  total_evidence: number
  report_id: string | null
  created_at: string
  completed_at: string | null
}

export type ResearchTaskList = {
  total: number
  page: number
  page_size: number
  items: ResearchTaskListItem[]
}

/**
 * Research v1 DTO（docs/openapi/evidsight-v1.yaml 唯一权威）。
 * ResearchTaskCreate/ResearchRequirements 均为 additionalProperties:false，
 * 客户端不得发送字段权威之外的键（预算/期望输出等会被 422 拒绝）。
 */
export type ResearchRequirements = {
  task_type: 'comparison' | 'explainer' | 'analysis'
  depth?: 'quick'
  max_sources?: number
  language?: string
}

export type ResearchTaskCreate = {
  topic: string
  requirements: ResearchRequirements
  source_strategy: ResearchSourceStrategy
  knowledge_base_ids: string[]
}

export type ResearchTaskCreateResponse = {
  task_id: string
  status: ResearchTaskStatus
  created_at: string
  direct_answer: boolean
  idempotent_replayed: boolean
  report_id: string | null
}

export type ResearchProgress = {
  completed_steps: number
  total_steps: number
  progress: number
}

export type ResearchTask = {
  task_id: string
  topic: string
  status: ResearchTaskStatus
  current_phase: string | null
  requirements: ResearchRequirements
  progress: ResearchProgress
  total_sources: number
  total_evidence: number
  error_code: string | null
  error_message: string | null
  recoverable: boolean | null
  report_id: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export type ResearchTaskStateStep = {
  id: string
  step_type: string
  status: string
  label: string | null
  started_at: string | null
  completed_at: string | null
  sub_questions_count: number | null
  after_dedup: number | null
  sources_created: number | null
  successful: number | null
  failed: number | null
  error_code: string | null
  error_message: string | null
  duration_ms: number | null
  progress_label: string | null
}

export type ResearchTaskState = {
  task_id: string
  topic: string
  status: ResearchTaskStatus
  current_phase: string | null
  progress: ResearchProgress
  steps: ResearchTaskStateStep[]
  error: { error_code: string; error_message: string; recoverable: boolean } | null
  stats: { total_sources: number; total_evidence: number }
  report_id: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export type ResearchCancelResponse = {
  task_id: string
  status: ResearchTaskStatus
  cancel_requested: boolean
}

export type ResearchResumeFrom = {
  phase: string | null
  last_completed_step_id: string | null
  next_step_type: string | null
}

export type ResearchRetryResponse = {
  task_id: string
  status: ResearchTaskStatus
  resume_from: ResearchResumeFrom
}

/** Research SSE 事件 data（OpenAPI additionalProperties:true，未知字段容错，仅归一化已知字段）。 */
export type ResearchTaskUpdatedEventData = {
  task_id: string | null
  status: string | null
  current_phase: string | null
  completed_steps: number | null
  total_steps: number | null
  progress: number | null
  message: string | null
  error_code: string | null
  error_message: string | null
  completed_at?: string | null
  recoverable?: boolean | null
}

export type ResearchPhaseUpdatedEventData = {
  phase: string | null
  timestamp: string | null
  duration_ms: number | null
}

export type ResearchStepUpdatedEventData = {
  step_id: string | null
  step_type: string | null
  status: string | null
  label: string | null
  timestamp: string | null
  phase: string | null
  last_completed_step_id: string | null
  output: Record<string, unknown> | null
  iteration: number | null
  tool_call_id: string | null
  tool_name: string | null
  arguments: Record<string, unknown> | null
  observation: string | null
  success: boolean | null
}

export type ResearchTaskCanceledEventData = {
  task_id: string
  status: string
  cancel_requested: boolean
}

export type ResearchStreamEndEventData = {
  reason: string
}

export class ResearchStreamHttpError extends Error {
  readonly status: number
  readonly errorCode: string

  constructor(status: number, errorCode: string, message: string) {
    super(message)
    this.name = 'ResearchStreamHttpError'
    this.status = status
    this.errorCode = errorCode
  }
}

export type OpenResearchTaskStreamOptions = {
  /** Last-Event-ID 持久游标；重连时携带，服务端回放游标后事件（API.md §13） */
  lastEventId?: number | null
  fetchFn?: typeof fetch
  accessToken?: () => string | null
}

async function buildStreamError(response: Response): Promise<ResearchStreamHttpError> {
  let errorCode = `HTTP_${response.status}`
  let message = `请求失败（${response.status}）`
  try {
    const body = (await response.json()) as {
      error?: { error_code?: string; message?: string }
      message?: string
    } | null
    if (body?.error?.error_code) {
      errorCode = body.error.error_code
    }
    if (body?.error?.message) {
      message = body.error.message
    } else if (typeof body?.message === 'string') {
      message = body.message
    }
  } catch {
    // 非 JSON 错误体保留默认文案
  }
  return new ResearchStreamHttpError(response.status, errorCode, message)
}

/**
 * 打开 Research SSE 订阅流并逐事件回调（GET /api/v1/research/tasks/{task_id}/events）。
 *
 * - 不经过 axios（axios 不支持 SSE 增量流），用 fetch + ReadableStream；
 * - 重连携带 `Last-Event-ID` 游标；流自然结束（含 stream.end）或 HTTP 错误时返回，
 *   HTTP 层错误抛 `ResearchStreamHttpError`；中止抛 AbortError 由调用方处理；
 * - 订阅是观察通道，本函数绝不发送取消；任务在后台持续运行（FRONTEND §8）。
 */
export async function openResearchTaskStream(
  taskId: string,
  onEvent: (event: ResearchSseEvent) => void,
  signal: AbortSignal,
  options: OpenResearchTaskStreamOptions = {},
): Promise<void> {
  const fetchFn = options.fetchFn ?? fetch
  const token = (options.accessToken ?? getAccessToken)()
  const headers: Record<string, string> = {}
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  if (options.lastEventId !== null && options.lastEventId !== undefined) {
    headers['Last-Event-ID'] = String(options.lastEventId)
  }
  const response = await fetchFn(`/api/v1/research/tasks/${taskId}/events`, {
    method: 'GET',
    headers,
    signal,
    credentials: 'include',
  })
  if (!response.ok) {
    throw await buildStreamError(response)
  }
  if (!response.body) {
    throw new ResearchStreamHttpError(response.status, 'EMPTY_BODY', '流式响应为空')
  }
  const parser = createResearchSseParser()
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }
    const text = decoder.decode(value, { stream: true })
    for (const event of parser(text)) {
      onEvent(event)
    }
  }
}

export type ResearchApi = {
  listResearchTasks(params?: {
    page?: number
    page_size?: number
    status?: ResearchTaskStatus
    keyword?: string
  }): Promise<ResearchTaskList>
  createResearchTask(
    input: ResearchTaskCreate,
    idempotencyKey: string,
  ): Promise<ResearchTaskCreateResponse>
  getResearchTask(taskId: string): Promise<ResearchTask>
  cancelResearchTask(taskId: string): Promise<ResearchCancelResponse>
  resumeResearchTask(taskId: string): Promise<ResearchRetryResponse>
  deleteResearchTask(taskId: string): Promise<void>
  getResearchTaskState(taskId: string): Promise<ResearchTaskState>
}

export function createResearchApi(client: AxiosInstance): ResearchApi {
  return {
    async listResearchTasks(
      params: {
        page?: number
        page_size?: number
        status?: ResearchTaskStatus
        keyword?: string
      } = {},
    ): Promise<ResearchTaskList> {
      const { data } = await client.get<ResearchTaskList>('/api/v1/research/tasks', { params })
      return data
    },
    async createResearchTask(
      input: ResearchTaskCreate,
      idempotencyKey: string,
    ): Promise<ResearchTaskCreateResponse> {
      const { data } = await client.post<ResearchTaskCreateResponse>(
        '/api/v1/research/tasks',
        input,
        { headers: { 'Idempotency-Key': idempotencyKey } },
      )
      return data
    },
    async getResearchTask(taskId: string): Promise<ResearchTask> {
      const { data } = await client.get<ResearchTask>(`/api/v1/research/tasks/${taskId}`)
      return data
    },
    async cancelResearchTask(taskId: string): Promise<ResearchCancelResponse> {
      const { data } = await client.post<ResearchCancelResponse>(
        `/api/v1/research/tasks/${taskId}/cancel`,
      )
      return data
    },
    async resumeResearchTask(taskId: string): Promise<ResearchRetryResponse> {
      const { data } = await client.post<ResearchRetryResponse>(
        `/api/v1/research/tasks/${taskId}/resume`,
      )
      return data
    },
    async deleteResearchTask(taskId: string): Promise<void> {
      await client.delete(`/api/v1/research/tasks/${taskId}`)
    },
    async getResearchTaskState(taskId: string): Promise<ResearchTaskState> {
      const { data } = await client.get<ResearchTaskState>(`/api/v1/research/tasks/${taskId}/state`)
      return data
    },
  }
}

export const researchApi = createResearchApi(apiClient)
