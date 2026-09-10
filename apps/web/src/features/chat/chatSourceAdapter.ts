import type { ChatSource } from '@/api/conversations'
import type { ChatSourceChunk } from '@/features/chat/chatSseParser'

/**
 * 持久化 `Message.sources`（OpenAPI `ChatSource`，API.md §12）→ SSE 解析器 `ChatSourceChunk`
 * 的适配器。两者字段同构，但 API 类型把 `document_uuid`/`segment_id` 声明为 nullable、
 * 其余元数据字段为可选；`ChatSourceChunk` 要求 `document_uuid`/`segment_id` 恒为字符串。
 * 前端只消费 `ChatSourceChunk` 一种渲染结构，避免历史回读路径与流式路径各写一套。
 */
export function chatSourceToChunk(source: ChatSource): ChatSourceChunk {
  return {
    chunk_index: source.chunk_index,
    document_uuid: source.document_uuid ?? '',
    segment_id: source.segment_id ?? '',
    doc_name: source.doc_name,
    score: source.score,
    page: source.page ?? null,
    section_title: source.section_title ?? null,
    section_path: source.section_path ?? null,
    preview_text: source.preview_text ?? null,
    preview_range: source.preview_range ?? null,
    highlight_start: source.highlight_start ?? null,
    highlight_end: source.highlight_end ?? null,
  }
}

export function chatSourceToChunks(sources: ChatSource[]): ChatSourceChunk[] {
  return sources.map(chatSourceToChunk)
}
