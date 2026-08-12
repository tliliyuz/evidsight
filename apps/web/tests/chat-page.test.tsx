import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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
  await user.click(screen.getByRole('button', { name: /已选知识库/ }))
  await user.click(await screen.findByRole('option', { name: /产品手册/ }))
  await waitFor(() => {
    expect(screen.getByText(/本对话已选择「产品手册」/)).toBeInTheDocument()
  })
}

async function runGeneration(
  user: ReturnType<typeof userEvent.setup>,
  sourceChunk: Record<string, unknown>,
  confidence?: string,
) {
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
    streamMock.current?.emit({ type: 'message.delta', id: 2, data: { delta: '完整回答' } })
    streamMock.current?.emit({
      type: 'sources',
      id: 3,
      data: { chunks: [sourceChunk], confidence },
    })
    streamMock.current?.emit({ type: 'done', id: 4, data: { message_id: 5, title: '新对话' } })
    streamMock.current?.resolve()
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
    mockedKnowledge.getKnowledgeBase.mockResolvedValue(KB)
    renderChatPage(['/chat?kb=kb-1'])

    // 选择器自动选中 kb-1（徽章数量 1），scope-summary 展示知识库名称
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /已选知识库 1/ })).toBeInTheDocument()
    })
    expect(await screen.findByText(/本对话已选择「产品手册」/)).toBeInTheDocument()
    expect(mockedKnowledge.getKnowledgeBase).toHaveBeenCalledWith('kb-1')
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

    await user.click(screen.getByRole('button', { name: /已选知识库/ }))
    await user.click(await screen.findByRole('option', { name: /另本手册/ }))

    // 切换前必须明确提示范围变化
    expect(screen.getByRole('dialog')).toHaveAccessibleName('切换知识库')
    expect(screen.getByText(/当前会话「历史问答」的范围会变化/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '切换' }))

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
    expect(screen.getByText(/本对话已选择「另本手册」/)).toBeInTheDocument()
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

    // 完成后历史回读，来源引用锚点仍可见（点击序号打开来源详情抽屉）
    await waitFor(() => expect(screen.getByText('完整回答')).toBeInTheDocument())
    // 实时气泡与历史消息切换会重建引用锚点节点，反复查询取最新引用
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '引用来源 1' })).toBeInTheDocument()
    })

    // 点击引用序号打开来源详情抽屉
    await user.click(screen.getByRole('button', { name: '引用来源 1' }))
    expect(screen.getByRole('dialog')).toHaveAccessibleName('回答依据')

    // 来源详情抽屉「进入文档切片」打开既有切片抽屉，自动展开引用切片并实时请求 location
    await user.click(screen.getByRole('button', { name: '进入文档切片' }))
    expect(screen.getByRole('dialog', { name: '文档切片' })).toBeInTheDocument()
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

  it('刷新/重新打开历史会话后，来源由持久化 message.sources 恢复（无需流式生成）', async () => {
    mockedConversations.detail.mockResolvedValue({
      uuid: 'conv-9',
      owner_user_id: 'user-1',
      kb_uuid: 'kb-1',
      kb_status: 'active',
      kb_name: '产品手册',
      original_kb_uuid: null,
      original_kb_name: null,
      title: '历史问答',
      message_count: 2,
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-01T00:00:00Z',
      last_message_at: '2026-08-01T08:00:00Z',
      messages: [
        { id: 1, role: 'user', content: '历史问题', created_at: '2026-08-01T00:00:00Z' },
        {
          id: 2,
          role: 'assistant',
          content: '历史回答',
          created_at: '2026-08-01T00:00:00Z',
          sources: [
            {
              chunk_index: 1,
              doc_name: '持久化手册',
              score: 0.9,
              document_uuid: 'doc-uuid-1',
              segment_id: 'seg-1',
            },
          ],
        },
      ],
    })

    renderChatPage(['/chat?conversation=conv-9'])

    expect(await screen.findByText('历史回答')).toBeInTheDocument()
    // 来源以引用锚点呈现（点击序号打开来源详情抽屉查看文档名）
    expect(screen.getByRole('button', { name: '引用来源 1' })).toBeInTheDocument()
  })

  it('持久化来源优先于内存快照：采用持久化来源时不展示置信度', async () => {
    mockedKnowledge.listKnowledgeBases.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      items: [KB],
    })
    // 服务端回读携带与当轮 SSE 不同的持久化来源（B文档），当轮内存快照为 A文档+置信度
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
        {
          id: 5,
          role: 'assistant',
          content: '完整回答',
          created_at: '2026-08-01T00:00:00Z',
          sources: [{ chunk_index: 1, doc_name: 'B文档', score: 0.6 }],
        },
      ],
    })
    const user = userEvent.setup()
    renderChatPage()
    await selectKnowledgeBase(user)
    await runGeneration(
      user,
      {
        chunk_index: 1,
        document_uuid: 'doc-uuid-1',
        segment_id: 'seg-1',
        doc_name: 'A文档',
        score: 0.9,
      },
      '高',
    )

    // 回读完成后历史消息渲染持久化来源（B文档），丢弃当轮快照与置信度；
    // 点击引用序号打开来源详情抽屉，验证展示的是持久化来源
    await waitFor(() => {
      expect(mockedConversations.detail).toHaveBeenCalledWith('conv-1')
    })
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '引用来源 1' })).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: '引用来源 1' }))
    const drawer = screen.getByRole('dialog', { name: '回答依据' })
    expect(within(drawer).getByText('B文档')).toBeInTheDocument()
    expect(screen.queryByText('A文档')).not.toBeInTheDocument()
  })

  it('持久化来源为空时，内存快照作为回读前兜底', async () => {
    mockedKnowledge.listKnowledgeBases.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      items: [KB],
    })
    // 服务端回读的消息没有 sources → 回退到当轮内存快照（A文档 + 置信度）
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
    await runGeneration(
      user,
      {
        chunk_index: 1,
        document_uuid: 'doc-uuid-1',
        segment_id: 'seg-1',
        doc_name: 'A文档',
        score: 0.9,
      },
      '高',
    )

    await waitFor(() => {
      expect(mockedConversations.detail).toHaveBeenCalledWith('conv-1')
    })
    // 回退到当轮内存快照：引用锚点可见，点击打开来源详情抽屉查看 A文档
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '引用来源 1' })).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: '引用来源 1' }))
    const drawer = screen.getByRole('dialog', { name: '回答依据' })
    expect(within(drawer).getByText('A文档')).toBeInTheDocument()
  })

  it('页头展示真实会话标题与「← 问答历史」入口', async () => {
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

    await screen.findByText('历史问题')
    expect(screen.getByRole('heading', { name: '历史问答' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '← 问答历史' })).toHaveAttribute(
      'href',
      '/chat/history',
    )
  })

  it('消息显示角色标识与时间（你 / EvidSight · HH:mm）', async () => {
    mockedConversations.detail.mockResolvedValue({
      uuid: 'conv-9',
      owner_user_id: 'user-1',
      kb_uuid: 'kb-1',
      kb_status: 'active',
      kb_name: '产品手册',
      original_kb_uuid: null,
      original_kb_name: null,
      title: '历史问答',
      message_count: 2,
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-01T00:00:00Z',
      last_message_at: '2026-08-01T08:00:00Z',
      messages: [
        { id: 1, role: 'user', content: '历史问题', created_at: '2026-08-01T00:00:00Z' },
        { id: 2, role: 'assistant', content: '历史回答', created_at: '2026-08-01T00:00:00Z' },
      ],
    })

    renderChatPage(['/chat?conversation=conv-9'])

    await screen.findByText('历史问题')
    expect(screen.getByText(/你 · \d{2}:\d{2}/)).toBeInTheDocument()
    expect(screen.getByText(/EvidSight · \d{2}:\d{2}/)).toBeInTheDocument()
  })

  it('来源缺少 document_uuid 时降级展示且不提供进入切片入口', async () => {
    mockedConversations.detail.mockResolvedValue({
      uuid: 'conv-9',
      owner_user_id: 'user-1',
      kb_uuid: 'kb-1',
      kb_status: 'active',
      kb_name: '产品手册',
      original_kb_uuid: null,
      original_kb_name: null,
      title: '历史问答',
      message_count: 2,
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-01T00:00:00Z',
      last_message_at: '2026-08-01T08:00:00Z',
      messages: [
        { id: 1, role: 'user', content: '历史问题', created_at: '2026-08-01T00:00:00Z' },
        {
          id: 2,
          role: 'assistant',
          content: '历史回答',
          created_at: '2026-08-01T00:00:00Z',
          sources: [{ chunk_index: 1, doc_name: '无切片来源', score: 0.5 }],
        },
      ],
    })
    const user = userEvent.setup()
    renderChatPage(['/chat?conversation=conv-9'])

    // 引用锚点展示该来源；点击序号打开来源详情抽屉
    await user.click(await screen.findByRole('button', { name: '引用来源 1' }))
    const drawer = screen.getByRole('dialog', { name: '回答依据' })
    expect(screen.queryByRole('button', { name: '进入文档切片' })).not.toBeInTheDocument()
    expect(within(drawer).getByText(/原文切片暂不可用/)).toBeInTheDocument()
  })

  it('Composer：Shift+Enter 不发送、输入法组合期间不误发送、Enter 发送', async () => {
    mockedKnowledge.listKnowledgeBases.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      items: [KB],
    })
    const user = userEvent.setup()
    renderChatPage()
    await selectKnowledgeBase(user)

    const input = screen.getByLabelText('输入问题')
    await user.type(input, '第一行')

    // Shift+Enter 换行不发送
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true })
    expect(streamMock.current).toBeNull()

    // 输入法组合开始后 Enter 不发送
    fireEvent.compositionStart(input)
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(streamMock.current).toBeNull()
    fireEvent.compositionEnd(input)

    // 组合结束后 Enter 发送
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => expect(streamMock.current).not.toBeNull())
  })

  it('aria-live 收窄：对话线程不整段播报，流式状态行以 role=status 呈现', async () => {
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
      streamMock.current?.emit({ type: 'message.delta', id: 2, data: { delta: '部分输出' } })
    })

    expect(screen.getByRole('region', { name: '对话内容' })).not.toHaveAttribute('aria-live')
    expect(screen.getByRole('status')).toHaveTextContent('生成中')
  })

  it('新建会话（无会话）时「重命名」按钮禁用', () => {
    renderChatPage()
    expect(screen.getByRole('button', { name: '重命名' })).toBeDisabled()
  })

  it('有会话时页头「重命名」打开对话框并提交 rename', async () => {
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
    mockedConversations.rename.mockResolvedValue({
      uuid: 'conv-9',
      owner_user_id: 'user-1',
      kb_uuid: 'kb-1',
      kb_status: 'active',
      kb_name: '产品手册',
      original_kb_uuid: null,
      original_kb_name: null,
      title: '已改名',
      message_count: 1,
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-01T00:00:00Z',
      last_message_at: '2026-08-01T08:00:00Z',
    })
    const user = userEvent.setup()
    renderChatPage(['/chat?conversation=conv-9'])

    await screen.findByText('历史问题')
    expect(screen.getByRole('button', { name: '重命名' })).toBeEnabled()

    await user.click(screen.getByRole('button', { name: '重命名' }))
    expect(screen.getByRole('dialog')).toHaveAccessibleName('重命名会话')

    const input = screen.getByLabelText('会话名称')
    await user.clear(input)
    await user.type(input, '已改名')
    await user.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => {
      expect(mockedConversations.rename).toHaveBeenCalledWith('conv-9', '已改名')
    })
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
  })

  it('回答底部信息栏展示知识库与来源数量，并提供复制回答', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    mockedConversations.detail.mockResolvedValue({
      uuid: 'conv-9',
      owner_user_id: 'user-1',
      kb_uuid: 'kb-1',
      kb_status: 'active',
      kb_name: '产品手册',
      original_kb_uuid: null,
      original_kb_name: null,
      title: '历史问答',
      message_count: 2,
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-01T00:00:00Z',
      last_message_at: '2026-08-01T08:00:00Z',
      messages: [
        { id: 1, role: 'user', content: '历史问题', created_at: '2026-08-01T00:00:00Z' },
        {
          id: 2,
          role: 'assistant',
          content: '历史回答',
          created_at: '2026-08-01T00:00:00Z',
          sources: [
            { chunk_index: 1, doc_name: '文档甲', score: 0.9 },
            { chunk_index: 2, doc_name: '文档乙', score: 0.8 },
          ],
        },
      ],
    })
    renderChatPage(['/chat?conversation=conv-9'])

    await screen.findByText('历史回答')
    expect(screen.getByText(/使用 1 个知识库 · 2 个来源/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '复制回答' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('历史回答'))
    expect(await screen.findByText('已复制')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('引用编号以小方块锚点呈现：仅编号、aria-label 保留，文档名由来源卡片承载', async () => {
    mockedConversations.detail.mockResolvedValue({
      uuid: 'conv-9',
      owner_user_id: 'user-1',
      kb_uuid: 'kb-1',
      kb_status: 'active',
      kb_name: '产品手册',
      original_kb_uuid: null,
      original_kb_name: null,
      title: '历史问答',
      message_count: 2,
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-01T00:00:00Z',
      last_message_at: '2026-08-01T08:00:00Z',
      messages: [
        { id: 1, role: 'user', content: '历史问题', created_at: '2026-08-01T00:00:00Z' },
        {
          id: 2,
          role: 'assistant',
          content: '历史回答',
          created_at: '2026-08-01T00:00:00Z',
          sources: [{ chunk_index: 1, doc_name: '持久化手册', score: 0.9 }],
        },
      ],
    })
    renderChatPage(['/chat?conversation=conv-9'])

    await screen.findByText('历史回答')
    const citation = screen.getByRole('button', { name: '引用来源 1' })
    expect(citation).toHaveTextContent('01')
    // 引用锚点只显示序号；文档名由主动点击后打开的来源详情抽屉承载
    expect(citation).not.toHaveTextContent('持久化手册')
  })

  it('孤儿会话（知识库已删除/无权限）在输入框上方警示并禁用发送', async () => {
    mockedConversations.detail.mockResolvedValue({
      uuid: 'conv-9',
      owner_user_id: 'user-1',
      kb_uuid: 'kb-1',
      kb_status: 'deleted',
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

    await screen.findByText('历史问题')
    expect(screen.getByText(/这个会话的知识库已被删除或暂无权限/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '发送' })).toBeDisabled()
  })
})
