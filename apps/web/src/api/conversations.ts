/**
 * Conversation v1 API 客户端（API.md §7）。
 *
 * 字段契约以 `docs/openapi/evidsight-v1.yaml` 为唯一权威源：v1 创建请求统一使用
 * `knowledge_base_id`（对齐 Chat v1），更新用 PATCH，删除返回 204 无正文。
 * 所有资源端点按 API.md §4 直接返回资源或分页对象。
 */

import type { AxiosInstance } from 'axios'

import { apiClient } from '@/api/client'

/** 来源引用 canonical wire 投影（API.md §12；对齐 OpenAPI ChatSource） */
export type ChatSource = {
  chunk_index: number
  doc_name: string
  score: number
  document_uuid?: string | null
  segment_id?: string | null
  page?: number | null
  section_title?: string | null
  section_path?: string | null
  preview_text?: string | null
  preview_range?: { start: number; end: number } | null
  highlight_start?: number | null
  highlight_end?: number | null
}

export type ChatMessage = {
  id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  thinking_content?: string | null
  created_at: string
  /** SSE sources 持久化到消息后的回读（无来源为 []） */
  sources?: ChatSource[]
}

export type Conversation = {
  uuid: string
  owner_user_id: string
  kb_uuid: string | null
  kb_status: 'active' | 'deleted' | 'unavailable' | null
  kb_name: string | null
  original_kb_uuid: string | null
  original_kb_name: string | null
  title: string
  message_count: number
  created_at: string
  updated_at: string
  last_message_at: string | null
}

export type ConversationDetail = Conversation & {
  messages: ChatMessage[]
}

export type ConversationList = {
  total: number
  page: number
  page_size: number
  items: Conversation[]
}

export type ConversationListParams = {
  page?: number
  page_size?: number
  /** 会话标题模糊搜索（API.md §7 查询语义） */
  q?: string
  /** 排序字段允许列表，当前仅 last_message_at */
  sort_by?: 'last_message_at'
  order?: 'asc' | 'desc'
}

export type ConversationsApi = {
  list(params?: ConversationListParams): Promise<ConversationList>
  detail(conversationId: string): Promise<ConversationDetail>
  create(input: { knowledge_base_id: string; title?: string | null }): Promise<Conversation>
  rename(conversationId: string, title: string): Promise<Conversation>
  remove(conversationId: string): Promise<void>
}

export function createConversationsApi(client: AxiosInstance): ConversationsApi {
  return {
    async list(params: ConversationListParams = {}): Promise<ConversationList> {
      const { data } = await client.get<ConversationList>('/api/v1/conversations', {
        params,
      })
      return data
    },

    async detail(conversationId: string): Promise<ConversationDetail> {
      const { data } = await client.get<ConversationDetail>(
        `/api/v1/conversations/${conversationId}`,
      )
      return data
    },

    async create(input: {
      knowledge_base_id: string
      title?: string | null
    }): Promise<Conversation> {
      const { data } = await client.post<Conversation>('/api/v1/conversations', input)
      return data
    },

    async rename(conversationId: string, title: string): Promise<Conversation> {
      const { data } = await client.patch<Conversation>(`/api/v1/conversations/${conversationId}`, {
        title,
      })
      return data
    },

    async remove(conversationId: string): Promise<void> {
      await client.delete(`/api/v1/conversations/${conversationId}`)
    },
  }
}

export const conversationsApi = createConversationsApi(apiClient)
