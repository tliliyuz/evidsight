import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { createConversationsApi } from '@/api/conversations'

function fakeClient() {
  const mocks = {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  }
  // 交叉 AxiosInstance 与 vi.fn 的 Mock 类型，使调用点可用 mockResolvedValue
  return mocks as unknown as AxiosInstance & typeof mocks
}

const CONVERSATION = {
  uuid: '550e8400-e29b-41d4-a716-446655440000',
  owner_user_id: '550e8400-e29b-41d4-a716-446655440001',
  kb_uuid: '550e8400-e29b-41d4-a716-446655440002',
  kb_status: 'active',
  kb_name: '产品手册',
  original_kb_uuid: null,
  original_kb_name: null,
  title: '新对话',
  message_count: 0,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-01T00:00:00Z',
  last_message_at: null,
}

describe('Conversation v1 API 客户端', () => {
  it('列表读取直返分页对象并透传分页参数', async () => {
    const client = fakeClient()
    client.get.mockResolvedValue({
      data: { total: 1, page: 1, page_size: 20, items: [CONVERSATION] },
    })
    const api = createConversationsApi(client)

    const result = await api.list({ page: 2, page_size: 10 })

    expect(client.get).toHaveBeenCalledWith('/api/v1/conversations', {
      params: { page: 2, page_size: 10 },
    })
    expect(result.items).toHaveLength(1)
    expect(result.total).toBe(1)
  })

  it('详情直返会话并包含消息历史', async () => {
    const client = fakeClient()
    const detail = {
      ...CONVERSATION,
      messages: [{ id: 1, role: 'user', content: '问题', created_at: '2026-08-01T00:00:00Z' }],
    }
    client.get.mockResolvedValue({ data: detail })
    const api = createConversationsApi(client)

    const result = await api.detail('550e8400-e29b-41d4-a716-446655440000')

    expect(client.get).toHaveBeenCalledWith(
      '/api/v1/conversations/550e8400-e29b-41d4-a716-446655440000',
    )
    expect(result.messages[0].role).toBe('user')
  })

  it('创建使用 knowledge_base_id 对齐 Chat v1', async () => {
    const client = fakeClient()
    client.post.mockResolvedValue({ data: CONVERSATION })
    const api = createConversationsApi(client)

    const result = await api.create({
      knowledge_base_id: '550e8400-e29b-41d4-a716-446655440002',
      title: '新对话',
    })

    expect(client.post).toHaveBeenCalledWith('/api/v1/conversations', {
      knowledge_base_id: '550e8400-e29b-41d4-a716-446655440002',
      title: '新对话',
    })
    expect(result.uuid).toBe(CONVERSATION.uuid)
  })

  it('重命名使用 PATCH 且返回更新后会话', async () => {
    const client = fakeClient()
    client.patch.mockResolvedValue({
      data: { ...CONVERSATION, title: '已改名' },
    })
    const api = createConversationsApi(client)

    const result = await api.rename('550e8400-e29b-41d4-a716-446655440000', '已改名')

    expect(client.patch).toHaveBeenCalledWith(
      '/api/v1/conversations/550e8400-e29b-41d4-a716-446655440000',
      { title: '已改名' },
    )
    expect(result.title).toBe('已改名')
  })

  it('删除返回 204 无正文', async () => {
    const client = fakeClient()
    client.delete.mockResolvedValue({ status: 204, data: '' })
    const api = createConversationsApi(client)

    await api.remove('550e8400-e29b-41d4-a716-446655440000')

    expect(client.delete).toHaveBeenCalledWith(
      '/api/v1/conversations/550e8400-e29b-41d4-a716-446655440000',
    )
  })
})
