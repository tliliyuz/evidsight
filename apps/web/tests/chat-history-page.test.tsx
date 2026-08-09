import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { conversationsApi, type Conversation } from '@/api/conversations'
import { ConversationHistoryPage } from '@/features/chat/ConversationHistoryPage'

vi.mock('@/api/conversations', () => ({
  conversationsApi: {
    list: vi.fn(),
    detail: vi.fn(),
    create: vi.fn(),
    rename: vi.fn(),
    remove: vi.fn(),
  },
}))

const mockedConversations = vi.mocked(conversationsApi)

function makeConversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    uuid: '550e8400-e29b-41d4-a716-446655440000',
    owner_user_id: '550e8400-e29b-41d4-a716-446655440001',
    kb_uuid: '550e8400-e29b-41d4-a716-446655440002',
    kb_status: 'active',
    kb_name: '产品手册',
    original_kb_uuid: null,
    original_kb_name: null,
    title: '如何排查网络问题',
    message_count: 3,
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
    last_message_at: '2026-08-01T08:00:00Z',
    ...overrides,
  }
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ConversationHistoryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('问答历史页', () => {
  it('渲染会话列表：标题、知识库名与消息数', async () => {
    mockedConversations.list.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      items: [makeConversation({})],
    })

    renderPage()

    expect(await screen.findByText('如何排查网络问题')).toBeInTheDocument()
    expect(screen.getByText(/产品手册/)).toBeInTheDocument()
    expect(screen.getByText(/3 条消息/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /如何排查网络问题/ })).toHaveAttribute(
      'href',
      '/chat?conversation=550e8400-e29b-41d4-a716-446655440000',
    )
  })

  it('名称搜索过滤会话', async () => {
    mockedConversations.list.mockResolvedValue({
      total: 2,
      page: 1,
      page_size: 20,
      items: [
        makeConversation({ uuid: 'aaa', title: '网络问题排查' }),
        makeConversation({ uuid: 'bbb', title: '报销流程说明' }),
      ],
    })

    renderPage()
    await screen.findByText('网络问题排查')

    await userEvent.type(screen.getByPlaceholderText('搜索会话名称或知识库'), '报销')

    expect(screen.queryByText('网络问题排查')).not.toBeInTheDocument()
    expect(screen.getByText('报销流程说明')).toBeInTheDocument()
  })

  it('更新时间排序可切换升降序', async () => {
    mockedConversations.list.mockResolvedValue({
      total: 2,
      page: 1,
      page_size: 20,
      items: [
        makeConversation({
          uuid: 'old',
          title: '较早会话',
          last_message_at: '2026-08-01T08:00:00Z',
        }),
        makeConversation({
          uuid: 'new',
          title: '较新会话',
          last_message_at: '2026-08-05T08:00:00Z',
        }),
      ],
    })

    renderPage()
    await screen.findByText('较新会话')
    const listItems = screen.getAllByRole('listitem')
    // 默认降序：较新在前
    expect(listItems[0]).toHaveTextContent('较新会话')
    expect(listItems[1]).toHaveTextContent('较早会话')

    await userEvent.click(screen.getByRole('button', { name: /更新时间/ }))
    const ascendingItems = screen.getAllByRole('listitem')
    expect(ascendingItems[0]).toHaveTextContent('较早会话')
    expect(ascendingItems[1]).toHaveTextContent('较新会话')
  })

  it('重命名会话：打开对话框、提交后调用 rename 并以服务端回读确认', async () => {
    const conversation = makeConversation({})
    mockedConversations.list.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      items: [conversation],
    })
    mockedConversations.rename.mockResolvedValue({ ...conversation, title: '已改名' })

    renderPage()
    await screen.findByText('如何排查网络问题')

    await userEvent.click(screen.getByRole('button', { name: '重命名' }))
    const input = screen.getByLabelText('会话名称')
    await userEvent.clear(input)
    await userEvent.type(input, '已改名')
    await userEvent.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => {
      expect(mockedConversations.rename).toHaveBeenCalledWith(conversation.uuid, '已改名')
    })
    await waitFor(() => {
      expect(mockedConversations.list).toHaveBeenCalledTimes(2)
    })
  })

  it('删除会话：二次确认显示会话名称，确认后调用 remove', async () => {
    const conversation = makeConversation({})
    mockedConversations.list.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      items: [conversation],
    })
    mockedConversations.remove.mockResolvedValue(undefined)

    renderPage()
    await screen.findByText('如何排查网络问题')

    await userEvent.click(screen.getByRole('button', { name: '删除' }))
    expect(screen.getByRole('dialog')).toHaveAccessibleName('删除问答会话')
    expect(screen.getByText(/确定删除会话「如何排查网络问题」吗/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '删除会话' }))

    await waitFor(() => {
      expect(mockedConversations.remove).toHaveBeenCalledWith(conversation.uuid)
    })
  })

  it('删除确认可取消，不调用 remove', async () => {
    mockedConversations.list.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      items: [makeConversation({})],
    })

    renderPage()
    await screen.findByText('如何排查网络问题')

    await userEvent.click(screen.getByRole('button', { name: '删除' }))
    await userEvent.click(screen.getByRole('button', { name: '取消' }))

    expect(mockedConversations.remove).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
