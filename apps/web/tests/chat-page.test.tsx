import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { conversationsApi } from '@/api/conversations'
import { knowledgeApi } from '@/api/knowledge'
import { ChatPage } from '@/features/chat/ChatPage'

const streamMock = vi.hoisted(() => ({
  current: null as {
    emit: (event: unknown) => void
    resolve: () => void
    reject: (error: unknown) => void
  } | null,
}))

vi.mock('@/api/chat', () => ({
  openChatStream: vi.fn(
    (_request: unknown, onEvent: (event: unknown) => void, signal: AbortSignal) =>
      new Promise<void>((resolve, reject) => {
        streamMock.current = { emit: onEvent, resolve, reject }
        signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
      }),
  ),
  cancelChatGeneration: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('@/api/conversations', () => ({
  conversationsApi: {
    list: vi.fn(),
    detail: vi.fn(),
    create: vi.fn(),
    rename: vi.fn(),
    remove: vi.fn(),
  },
}))

vi.mock('@/api/knowledge', () => ({
  knowledgeApi: {
    listKnowledgeBases: vi.fn(),
    createKnowledgeBase: vi.fn(),
    getKnowledgeBase: vi.fn(),
    updateKnowledgeBase: vi.fn(),
    deleteKnowledgeBase: vi.fn(),
    listDocuments: vi.fn(),
    uploadDocument: vi.fn(),
    getDocument: vi.fn(),
    deleteDocument: vi.fn(),
    getDocumentChunks: vi.fn(),
    reprocessDocument: vi.fn(),
    getDocumentLocation: vi.fn(),
  },
}))

const mockedConversations = vi.mocked(conversationsApi)
const mockedKnowledge = vi.mocked(knowledgeApi)
const mockedCancel = vi.mocked((await import('@/api/chat')).cancelChatGeneration)

const KB = {
  uuid: 'kb-1',
  name: '产品手册',
  description: null,
  owner: 'user-1',
  visibility: 'private' as const,
  status: 'active' as const,
  doc_count: 3,
  chunk_count: 10,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: null,
}

function renderChatPage(initialEntries: string[] = ['/chat']) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <ChatPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function selectKnowledgeBase(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: '未选择知识库' }))
  await user.click(await screen.findByRole('option', { name: /产品手册/ }))
  await waitFor(() => {
    expect(screen.getByRole('button', { name: /产品手册/ })).toBeInTheDocument()
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  streamMock.current = null
})

describe('据见问答页', () => {
  it('新会话未选知识库时提示先选择，发送按钮禁用', () => {
    renderChatPage()
    expect(screen.getByText('请先选择知识库，再开始问答。')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '发送' })).toBeDisabled()
  })

  it('从知识库「用它提问」进入（?kb=）时自动勾选对应知识库', async () => {
    mockedKnowledge.listKnowledgeBases.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      items: [KB],
    })
    renderChatPage(['/chat?kb=kb-1'])

    // 选择器自动选中 kb-1，无需手动点击选择
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /产品手册/ })).toBeInTheDocument()
    })
  })

  it('选择知识库后发送，流式展示生成中状态与增量文本', async () => {
    mockedKnowledge.listKnowledgeBases.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      items: [KB],
    })
    const user = userEvent.setup()
    renderChatPage()
    await selectKnowledgeBase(user)

    await user.type(screen.getByLabelText('输入问题'), '网络怎么排查')
    await user.click(screen.getByRole('button', { name: '发送' }))

    await waitFor(() => {
      expect(streamMock.current).not.toBeNull()
    })

    act(() => {
      streamMock.current?.emit({
        type: 'meta',
        id: 1,
        data: { conversation_id: 'conv-1', generation_id: 'gen-1' },
      })
      streamMock.current?.emit({
        type: 'message.delta',
        id: 2,
        data: { delta: '先检查网线' },
      })
    })

    expect(screen.getByText('先检查网线')).toBeInTheDocument()
    expect(screen.getByText('生成中')).toBeInTheDocument()
  })

  it('用户停止生成：调用 generation cancel API 并显示已中止', async () => {
    mockedKnowledge.listKnowledgeBases.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      items: [KB],
    })
    const user = userEvent.setup()
    renderChatPage()
    await selectKnowledgeBase(user)

    await user.type(screen.getByLabelText('输入问题'), '网络怎么排查')
    await user.click(screen.getByRole('button', { name: '发送' }))
    await waitFor(() => {
      expect(streamMock.current).not.toBeNull()
    })

    act(() => {
      streamMock.current?.emit({
        type: 'meta',
        id: 1,
        data: { conversation_id: 'conv-1', generation_id: 'gen-1' },
      })
      streamMock.current?.emit({
        type: 'message.delta',
        id: 2,
        data: { delta: '部分输出' },
      })
    })

    await user.click(screen.getByRole('button', { name: '停止生成' }))

    await waitFor(() => {
      expect(mockedCancel).toHaveBeenCalledWith('gen-1')
    })
    expect(await screen.findByText('已中止')).toBeInTheDocument()
    expect(screen.queryByText('生成中')).not.toBeInTheDocument()
  })

  it('done 后进入成功终态：不再显示生成中，并经服务端回读确认持久化消息', async () => {
    mockedKnowledge.listKnowledgeBases.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      items: [KB],
    })
    mockedConversations.detail.mockResolvedValue({
      uuid: 'conv-1',
      owner_user_id: 'user-1',
      kb_uuid: 'kb-1',
      kb_status: 'active',
      kb_name: '产品手册',
      original_kb_uuid: null,
      original_kb_name: null,
      title: '新对话',
      message_count: 2,
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-01T00:00:00Z',
      last_message_at: null,
      messages: [
        { id: 4, role: 'user', content: '网络怎么排查', created_at: '2026-08-01T00:00:00Z' },
        { id: 5, role: 'assistant', content: '完整回答', created_at: '2026-08-01T00:00:00Z' },
      ],
    })
    const user = userEvent.setup()
    renderChatPage()
    await selectKnowledgeBase(user)

    await user.type(screen.getByLabelText('输入问题'), '网络怎么排查')
    await user.click(screen.getByRole('button', { name: '发送' }))
    await waitFor(() => {
      expect(streamMock.current).not.toBeNull()
    })

    act(() => {
      streamMock.current?.emit({
        type: 'meta',
        id: 1,
        data: { conversation_id: 'conv-1', generation_id: 'gen-1' },
      })
      streamMock.current?.emit({
        type: 'message.delta',
        id: 2,
        data: { delta: '完整回答' },
      })
      streamMock.current?.emit({
        type: 'sources',
        id: 3,
        data: {
          chunks: [
            {
              chunk_index: 1,
              document_uuid: '550e8400-e29b-41d4-a716-446655440200',
              segment_id: '550e8400-e29b-41d4-a716-446655440300',
              doc_name: '手册',
              score: 0.9,
            },
          ],
        },
      })
      streamMock.current?.emit({ type: 'done', id: 4, data: { message_id: 5, title: '新对话' } })
      streamMock.current?.resolve()
    })

    await waitFor(() => {
      expect(mockedConversations.detail).toHaveBeenCalledWith('conv-1')
    })
    // 实时气泡会被同文本的历史消息替换，反复查询取最新引用
    await waitFor(() => expect(screen.getByText('完整回答')).toBeInTheDocument())
    expect(screen.queryByText('生成中')).not.toBeInTheDocument()
  })

  it('打开历史会话（?conversation=:id）恢复消息', async () => {
    mockedConversations.detail.mockResolvedValue({
      uuid: 'conv-9',
      owner_user_id: 'user-1',
      kb_uuid: 'kb-1',
      kb_status: 'active',
      kb_name: '产品手册',
      original_kb_uuid: null,
      original_kb_name: null,
      title: '历史问答',
      message_count: 1,
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-01T00:00:00Z',
      last_message_at: '2026-08-01T08:00:00Z',
      messages: [{ id: 1, role: 'user', content: '历史问题', created_at: '2026-08-01T00:00:00Z' }],
    })

    renderChatPage(['/chat?conversation=conv-9'])

    expect(await screen.findByText('历史问题')).toBeInTheDocument()
    expect(mockedConversations.detail).toHaveBeenCalledWith('conv-9')
  })

  it('会话内切换知识库：先明确提示范围变化，确认后开启新会话视图', async () => {
    mockedKnowledge.listKnowledgeBases.mockResolvedValue({
      total: 2,
      page: 1,
      page_size: 20,
      items: [KB, { ...KB, uuid: 'kb-2', name: '另本手册' }],
    })
    mockedConversations.detail.mockResolvedValue({
      uuid: 'conv-9',
      owner_user_id: 'user-1',
      kb_uuid: 'kb-1',
      kb_status: 'active',
      kb_name: '产品手册',
      original_kb_uuid: null,
      original_kb_name: null,
      title: '历史问答',
      message_count: 1,
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-01T00:00:00Z',
      last_message_at: '2026-08-01T08:00:00Z',
      messages: [{ id: 1, role: 'user', content: '历史问题', created_at: '2026-08-01T00:00:00Z' }],
    })
    const user = userEvent.setup()
    renderChatPage(['/chat?conversation=conv-9'])

    await screen.findByText('历史问题')

    await user.click(screen.getByRole('button', { name: /产品手册/ }))
    await user.click(await screen.findByRole('option', { name: /另本手册/ }))

    // 切换前必须明确提示范围变化
    expect(screen.getByRole('dialog')).toHaveAccessibleName('切换知识库')
    expect(screen.getByText(/当前会话「历史问答」的范围会变化/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '切换' }))

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: /另本手册/ })).toBeInTheDocument()
  })

  it('来源卡片联动切片抽屉：以稳定 document_uuid/segment_id 打开并自动展开引用切片', async () => {
    mockedKnowledge.listKnowledgeBases.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      items: [KB],
    })
    mockedKnowledge.getDocumentChunks.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 50,
      items: [
        {
          id: 1,
          segment_id: 'seg-1',
          chunk_index: 0,
          preview: '片段预览',
          token_count: 10,
          metadata: { page: 1 },
        },
      ],
    })
    mockedKnowledge.getDocumentLocation.mockResolvedValue({
      document_id: 'doc-uuid-1',
      segment_id: 'seg-1',
      minimal_excerpt: '原文正文',
      location: { page_number: 1 },
      source_updated_at: null,
    })
    mockedConversations.detail.mockResolvedValue({
      uuid: 'conv-1',
      owner_user_id: 'user-1',
      kb_uuid: 'kb-1',
      kb_status: 'active',
      kb_name: '产品手册',
      original_kb_uuid: null,
      original_kb_name: null,
      title: '新对话',
      message_count: 2,
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-01T00:00:00Z',
      last_message_at: null,
      messages: [
        { id: 4, role: 'user', content: '网络怎么排查', created_at: '2026-08-01T00:00:00Z' },
        { id: 5, role: 'assistant', content: '完整回答', created_at: '2026-08-01T00:00:00Z' },
      ],
    })
    const user = userEvent.setup()
    renderChatPage()
    await selectKnowledgeBase(user)

    await user.type(screen.getByLabelText('输入问题'), '网络怎么排查')
    await user.click(screen.getByRole('button', { name: '发送' }))
    await waitFor(() => {
      expect(streamMock.current).not.toBeNull()
    })

    act(() => {
      streamMock.current?.emit({
        type: 'meta',
        id: 1,
        data: { conversation_id: 'conv-1', generation_id: 'gen-1' },
      })
      streamMock.current?.emit({
        type: 'message.delta',
        id: 2,
        data: { delta: '完整回答' },
      })
      streamMock.current?.emit({
        type: 'sources',
        id: 3,
        data: {
          chunks: [
            {
              chunk_index: 1,
              document_uuid: 'doc-uuid-1',
              segment_id: 'seg-1',
              doc_name: '手册',
              score: 0.9,
            },
          ],
        },
      })
      streamMock.current?.emit({ type: 'done', id: 4, data: { message_id: 5, title: '新对话' } })
      streamMock.current?.resolve()
    })

    // 完成后历史回读，来源卡片仍可见
    await waitFor(() => expect(screen.getByText('完整回答')).toBeInTheDocument())
    // 实时气泡与历史消息切换会重建来源卡片节点，反复查询取最新引用
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '进入文档切片' })).toBeInTheDocument()
    })

    // 点击进入切片抽屉，自动展开引用切片并实时请求 location
    await user.click(screen.getByRole('button', { name: '进入文档切片' }))
    expect(screen.getByRole('dialog')).toHaveAccessibleName('文档切片')
    await waitFor(() => {
      expect(mockedKnowledge.getDocumentChunks).toHaveBeenCalledWith(
        'doc-uuid-1',
        expect.objectContaining({ page: 1 }),
      )
    })
    await waitFor(() => {
      expect(mockedKnowledge.getDocumentLocation).toHaveBeenCalledWith('doc-uuid-1', 'seg-1')
    })
    expect(await screen.findByText('原文正文')).toBeInTheDocument()
  })
})
