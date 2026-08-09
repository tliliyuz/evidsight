/**
 * Chat v1 canonical SSE 解析器。
 *
 * 只消费 `POST /api/v1/chat/stream` 输出的 canonical 事件（API.md §12）：
 * `meta` → 零到多个 `message.delta` → `sources` → `done`；失败路径以 `error` 收尾，
 * 成功路径不会发送 `done`。心跳使用 SSE 注释帧（以冒号开头），本解析器忽略。
 *
 * 解析器为增量式：网络分帧可能把单个事件拆到多个 chunk，内部维护缓冲区，
 * 每次喂入 chunk 返回本次已完整收到的事件数组。
 */

export type ChatSourceChunk = {
  chunk_index: number
  document_uuid: string
  segment_id: string
  doc_name: string
  score: number
  page: number | null
  section_title: string | null
  section_path: string | null
  preview_text: string | null
  preview_range: { start: number; end: number } | null
  highlight_start: number | null
  highlight_end: number | null
}

export type ChatSseMetaData = {
  conversation_id: string
  generation_id: string
}

export type ChatSseDeltaData = {
  delta: string
}

export type ChatSseSourcesData = {
  chunks: ChatSourceChunk[]
  confidence?: string
  confidence_note?: string
}

export type ChatSseErrorData = {
  error_code: string
  message: string
  retryable: boolean
}

export type ChatSseDoneData = {
  message_id: number
  title: string | null
  token_usage?: { prompt: number; completion: number; total: number }
}

export type ChatSseEvent =
  | { type: 'meta'; id: number; data: ChatSseMetaData }
  | { type: 'message.delta'; id: number; data: ChatSseDeltaData }
  | { type: 'sources'; id: number; data: ChatSseSourcesData }
  | { type: 'error'; id: number; data: ChatSseErrorData }
  | { type: 'done'; id: number; data: ChatSseDoneData }

type Frame = {
  event: string | null
  id: number | null
  data: string | null
}

const EVENT_NAMES = new Set(['meta', 'message.delta', 'sources', 'error', 'done'])

function normalizeChunk(raw: Record<string, unknown>): ChatSourceChunk {
  return {
    chunk_index: Number(raw.chunk_index ?? 0),
    document_uuid: String(raw.document_uuid ?? ''),
    segment_id: String(raw.segment_id ?? ''),
    doc_name: String(raw.doc_name ?? ''),
    score: Number(raw.score ?? 0),
    page: typeof raw.page === 'number' ? raw.page : null,
    section_title: typeof raw.section_title === 'string' ? raw.section_title : null,
    section_path: typeof raw.section_path === 'string' ? raw.section_path : null,
    preview_text: typeof raw.preview_text === 'string' ? raw.preview_text : null,
    preview_range:
      typeof raw.preview_range === 'object' && raw.preview_range !== null
        ? {
            start: Number((raw.preview_range as { start?: unknown }).start),
            end: Number((raw.preview_range as { end?: unknown }).end),
          }
        : null,
    highlight_start: typeof raw.highlight_start === 'number' ? raw.highlight_start : null,
    highlight_end: typeof raw.highlight_end === 'number' ? raw.highlight_end : null,
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
 * 增量式 canonical SSE 解析器。
 * 每次调用喂入一段流式文本，返回本次完整解析出的业务事件。
 */
export function createChatSseParser(): (chunk: string) => ChatSseEvent[] {
  let buffer = ''
  return (chunk: string): ChatSseEvent[] => {
    buffer += chunk
    const events: ChatSseEvent[] = []
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
        case 'meta':
          events.push({
            type: 'meta',
            id: frame.id ?? 0,
            data: {
              conversation_id: String(payload.conversation_id),
              generation_id: String(payload.generation_id),
            },
          })
          break
        case 'message.delta':
          events.push({
            type: 'message.delta',
            id: frame.id ?? 0,
            data: { delta: String(payload.delta ?? '') },
          })
          break
        case 'sources':
          events.push({
            type: 'sources',
            id: frame.id ?? 0,
            data: {
              chunks: Array.isArray(payload.chunks)
                ? payload.chunks
                    .filter(
                      (c): c is Record<string, unknown> => typeof c === 'object' && c !== null,
                    )
                    .map(normalizeChunk)
                : [],
              confidence: typeof payload.confidence === 'string' ? payload.confidence : undefined,
              confidence_note:
                typeof payload.confidence_note === 'string' ? payload.confidence_note : undefined,
            },
          })
          break
        case 'error':
          events.push({
            type: 'error',
            id: frame.id ?? 0,
            data: {
              error_code: String(payload.error_code ?? ''),
              message: String(payload.message ?? ''),
              retryable: payload.retryable === true,
            },
          })
          break
        case 'done':
          events.push({
            type: 'done',
            id: frame.id ?? 0,
            data: {
              message_id: Number(payload.message_id),
              title: typeof payload.title === 'string' ? payload.title : null,
              token_usage:
                typeof payload.token_usage === 'object' && payload.token_usage !== null
                  ? (payload.token_usage as ChatSseDoneData['token_usage'])
                  : undefined,
            },
          })
          break
      }
    }
    return events
  }
}
