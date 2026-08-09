/**
 * Chat v1 API 客户端。
 *
 * - `openChatStream`：以 `fetch` 流式消费 `POST /api/v1/chat/stream` 的 canonical SSE，
 *   逐事件回调解析器产出的事件；不经过 axios（axios 不支持 SSE 增量流）。
 * - `cancelChatGeneration`：幂等取消 generation（API.md §7，202）。
 *
 * SSE 事件解析见 `@/features/chat/chatSseParser`，状态机见
 * `@/features/chat/chatGenerationMachine`。
 */

import { apiClient, getAccessToken } from '@/api/client'
import { createChatSseParser, type ChatSseEvent } from '@/features/chat/chatSseParser'

export type ChatStreamRequest = {
  conversation_id: string | null
  knowledge_base_id: string
  question: string
}

export class ChatStreamHttpError extends Error {
  readonly status: number
  readonly errorCode: string

  constructor(status: number, errorCode: string, message: string) {
    super(message)
    this.name = 'ChatStreamHttpError'
    this.status = status
    this.errorCode = errorCode
  }
}

export type OpenChatStreamOptions = {
  fetchFn?: typeof fetch
  accessToken?: () => string | null
}

async function buildStreamError(response: Response): Promise<ChatStreamHttpError> {
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
  return new ChatStreamHttpError(response.status, errorCode, message)
}

/**
 * 打开 Chat SSE 流并逐事件回调。流正常结束（含 done 或 error 后的 EOF）时 resolve；
 * HTTP 层错误抛 `ChatStreamHttpError`；中止时抛 AbortError 由调用方处理。
 */
export async function openChatStream(
  request: ChatStreamRequest,
  onEvent: (event: ChatSseEvent) => void,
  signal: AbortSignal,
  options: OpenChatStreamOptions = {},
): Promise<void> {
  const fetchFn = options.fetchFn ?? fetch
  const token = (options.accessToken ?? getAccessToken)()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  const response = await fetchFn('/api/v1/chat/stream', {
    method: 'POST',
    headers,
    body: JSON.stringify(request),
    signal,
    credentials: 'include',
  })
  if (!response.ok) {
    throw await buildStreamError(response)
  }
  if (!response.body) {
    throw new ChatStreamHttpError(response.status, 'EMPTY_BODY', '流式响应为空')
  }
  const parser = createChatSseParser()
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

export async function cancelChatGeneration(generationId: string): Promise<void> {
  await apiClient.post(`/api/v1/chat/generations/${generationId}/cancel`)
}
