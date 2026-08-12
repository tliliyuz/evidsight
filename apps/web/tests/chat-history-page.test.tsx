import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { conversationsApi, type Conversation } from '@/api/conversations'
import { ToastProvider } from '@/components/feedback/ToastProvider'
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

function renderPage(initialEntries: string[] = ['/chat/history']) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={initialEntries}>
          <ConversationHistoryPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

/** 打开首行的 ⋮ 溢出菜单并点击指定动作（重命名/删除已收敛到菜单内）。 */
async function openRowAction(label: '重命名' | '删除') {
  await userEvent.click(screen.getByRole('button', { name: /会话操作/ }))
  await userEvent.click(screen.getByRole('menuitem', { name: label }))
}

describe('问答历史页（服务端搜索/排序/分页）', () => {
  it('渲染台账列表：标题、知识库、消息数、最近更新、打开对话与新建对话', async () => {
    mockedConversations.list.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 10,
      items: [makeConversation({})],
    })

    renderPage()

    expect(await screen.findByText('如何排查网络问题')).toBeInTheDocument()
    expect(screen.getByText('产品手册')).toBeInTheDocument()
    expect(screen.getByText('3 条消息')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '如何排查网络问题' })).toHaveAttribute(
      'href',
      '/chat?conversation=550e8400-e29b-41d4-a716-446655440000',
    )
    expect(screen.getByRole('link', { name: '打开对话' })).toHaveAttribute(
      'href',
      '/chat?conversation=550e8400-e29b-41d4-a716-446655440000',
    )
    // 新建对话主操作
    expect(screen.getByRole('link', { name: '新建对话' })).toHaveAttribute('href', '/chat')
    // 初始查询按服务端语义带默认参数
    expect(mockedConversations.list).toHaveBeenCalledWith({
      q: undefined,
      sort_by: 'last_message_at',
      order: 'desc',
      page: 1,
      page_size: 10,
    })
  })

  it('搜索使用服务端 q（仅标题）：输入后带 q 重新查询，不做浏览器端过滤', async () => {
    mockedConversations.list.mockImplementation(async ({ q } = {}) => {
      const keyword = q ?? ''
      const all = [
        makeConversation({ uuid: 'aaa', title: '网络问题排查' }),
        makeConversation({ uuid: 'bbb', title: '报销流程说明' }),
      ]
      const items = keyword ? all.filter((c) => c.title.includes(keyword)) : all
      return { total: items.length, page: 1, page_size: 10, items }
    })

    renderPage()
    await screen.findByText('网络问题排查')

    await userEvent.type(screen.getByPlaceholderText('搜索会话名称'), '报销')

    await waitFor(() => {
      expect(mockedConversations.list).toHaveBeenCalledWith(
        expect.objectContaining({ q: '报销', page: 1 }),
      )
    })
    // 服务端返回什么就渲染什么：'网络问题排查' 由服务端（仅标题匹配）过滤掉，
    // 前端不再做浏览器端标题/知识库名过滤
    expect(screen.queryByText('网络问题排查')).not.toBeInTheDocument()
    expect(screen.getByText('报销流程说明')).toBeInTheDocument()
  })

  it('搜索无结果时展示「没有匹配的会话」并可清除搜索', async () => {
    mockedConversations.list.mockResolvedValue({
      total: 0,
      page: 1,
      page_size: 10,
      items: [],
    })

    renderPage(['/chat/history?q=不存在'])
    await screen.findByText('没有匹配的会话')

    await userEvent.click(screen.getByRole('button', { name: /清除搜索/ }))

    await waitFor(() => {
      expect(screen.queryByText('没有匹配的会话')).not.toBeInTheDocument()
    })
  })

  it('更新时间排序可切换 order 并同步 URL（sort）', async () => {
    mockedConversations.list.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 10,
      items: [makeConversation({})],
    })

    renderPage()
    await screen.findByText('如何排查网络问题')

    await userEvent.click(screen.getByRole('button', { name: /更新时间/ }))

    await waitFor(() => {
      expect(mockedConversations.list).toHaveBeenCalledWith(
        expect.objectContaining({ order: 'asc', page: 1 }),
      )
    })
  })

  it('分页调用服务端 page 参数并同步 URL', async () => {
    mockedConversations.list.mockResolvedValue({
      total: 25,
      page: 1,
      page_size: 10,
      items: Array.from({ length: 10 }, (_, i) =>
        makeConversation({ uuid: `c-${i}`, title: `会话 ${i}` }),
      ),
    })

    renderPage()
    await screen.findByText('会话 0')

    await userEvent.click(screen.getByRole('button', { name: '下一页' }))

    await waitFor(() => {
      expect(mockedConversations.list).toHaveBeenCalledWith(expect.objectContaining({ page: 2 }))
    })
  })

  it('URL 参数驱动首屏查询：q / sort / page 透传到服务端', async () => {
    mockedConversations.list.mockResolvedValue({
      total: 1,
      page: 2,
      page_size: 10,
      items: [makeConversation({})],
    })

    renderPage(['/chat/history?q=报销&sort=asc&page=2'])

    await screen.findByText('如何排查网络问题')
    expect(mockedConversations.list).toHaveBeenCalledWith({
      q: '报销',
      sort_by: 'last_message_at',
      order: 'asc',
      page: 2,
      page_size: 10,
    })
  })

  it('删除当前页最后一项（page>1 且仅一条）后回退一页', async () => {
    const conversation = makeConversation({})
    mockedConversations.list.mockResolvedValue({
      total: 1,
      page: 2,
      page_size: 10,
      items: [conversation],
    })
    mockedConversations.remove.mockResolvedValue(undefined)

    renderPage(['/chat/history?page=2'])
    await screen.findByText('如何排查网络问题')

    await openRowAction('删除')
    await userEvent.click(screen.getByRole('button', { name: '删除会话' }))

    await waitFor(() => {
      expect(mockedConversations.remove).toHaveBeenCalledWith(conversation.uuid)
    })
    await waitFor(() => {
      expect(mockedConversations.list).toHaveBeenCalledWith(expect.objectContaining({ page: 1 }))
    })
  })

  it('查询失败展示错误态并可重试', async () => {
    mockedConversations.list
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce({
        total: 1,
        page: 1,
        page_size: 10,
        items: [makeConversation({})],
      })

    renderPage()

    expect(await screen.findByText('暂时无法加载')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '重试' }))

    expect(await screen.findByText('如何排查网络问题')).toBeInTheDocument()
    expect(mockedConversations.list).toHaveBeenCalledTimes(2)
  })

  it('重命名失败：toast 反馈且对话框保持打开', async () => {
    mockedConversations.list.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 10,
      items: [makeConversation({})],
    })
    mockedConversations.rename.mockRejectedValue({
      response: { data: { error: { message: '服务器繁忙，请稍后再试' } } },
    })

    renderPage()
    await screen.findByText('如何排查网络问题')

    await openRowAction('重命名')
    await userEvent.click(screen.getByRole('button', { name: '保存' }))

    expect(await screen.findByText('服务器繁忙，请稍后再试')).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toHaveAccessibleName('重命名会话')
  })

  it('删除失败：toast 反馈且确认框保持打开', async () => {
    mockedConversations.list.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 10,
      items: [makeConversation({})],
    })
    mockedConversations.remove.mockRejectedValue({
      response: { data: { error: { message: '删除失败，请稍后再试' } } },
    })

    renderPage()
    await screen.findByText('如何排查网络问题')

    await openRowAction('删除')
    await userEvent.click(screen.getByRole('button', { name: '删除会话' }))

    expect(await screen.findByText('删除失败，请稍后再试')).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toHaveAccessibleName('删除问答会话')
  })

  it('重命名会话：提交后调用 rename 并以服务端回读确认', async () => {
    const conversation = makeConversation({})
    mockedConversations.list.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 10,
      items: [conversation],
    })
    mockedConversations.rename.mockResolvedValue({ ...conversation, title: '已改名' })

    renderPage()
    await screen.findByText('如何排查网络问题')

    await openRowAction('重命名')
    const input = screen.getByLabelText('会话名称')
    await userEvent.clear(input)
    await userEvent.type(input, '已改名')
    await userEvent.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => {
      expect(mockedConversations.rename).toHaveBeenCalledWith(conversation.uuid, '已改名')
    })
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
  })

  it('删除会话：二次确认显示会话名称，确认后调用 remove', async () => {
    const conversation = makeConversation({})
    mockedConversations.list.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 10,
      items: [conversation],
    })
    mockedConversations.remove.mockResolvedValue(undefined)

    renderPage()
    await screen.findByText('如何排查网络问题')

    await openRowAction('删除')
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
      page_size: 10,
      items: [makeConversation({})],
    })

    renderPage()
    await screen.findByText('如何排查网络问题')

    await openRowAction('删除')
    await userEvent.click(screen.getByRole('button', { name: '取消' }))

    expect(mockedConversations.remove).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('时间范围分类「今天/本周」：按 last_message_at 前端筛选当前列表', async () => {
    const now = new Date()
    const iso = (d: Date) => d.toISOString()
    mockedConversations.list.mockResolvedValue({
      total: 2,
      page: 1,
      page_size: 10,
      items: [
        makeConversation({ uuid: 'a', title: '今天会话', last_message_at: iso(now) }),
        makeConversation({
          uuid: 'b',
          title: '上周会话',
          last_message_at: iso(new Date(now.getTime() - 10 * 86_400_000)),
        }),
      ],
    })

    renderPage()
    await screen.findByText('今天会话')
    expect(screen.getByText('上周会话')).toBeInTheDocument()

    // 「今天」只保留今天更新的会话
    await userEvent.click(screen.getByRole('button', { name: '今天' }))
    expect(screen.getByText('今天会话')).toBeInTheDocument()
    expect(screen.queryByText('上周会话')).not.toBeInTheDocument()
  })
})
