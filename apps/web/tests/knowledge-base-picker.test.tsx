import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { knowledgeApi, type KnowledgeBase } from '@/api/knowledge'
import { KnowledgeBasePicker } from '@/features/chat/KnowledgeBasePicker'

vi.mock('@/api/knowledge', () => ({
  knowledgeApi: { listKnowledgeBases: vi.fn() },
}))

const mockedKnowledge = vi.mocked(knowledgeApi)

const KB1: KnowledgeBase = {
  uuid: 'kb-1',
  name: '产品手册',
  description: null,
  owner: 'user-1',
  visibility: 'private',
  status: 'active',
  doc_count: 3,
  chunk_count: 10,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: null,
}
const KB2: KnowledgeBase = {
  ...KB1,
  uuid: 'kb-2',
  name: '客户反馈',
  visibility: 'public',
  owner: 'user-2',
}

function renderPicker(value: string | null = null, onSelect = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <KnowledgeBasePicker value={value} onSelect={onSelect} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('知识库选择器可达性（FRONTEND §5.5）', () => {
  it('打开后焦点移入搜索框', async () => {
    mockedKnowledge.listKnowledgeBases.mockResolvedValue({
      total: 2,
      page: 1,
      page_size: 20,
      items: [KB1, KB2],
    })
    const user = userEvent.setup()
    renderPicker()

    await user.click(screen.getByRole('button', { name: /已选知识库/ }))

    await waitFor(() => expect(screen.getByRole('combobox')).toHaveFocus())
  })

  it('Escape 关闭浮层并将焦点返回触发按钮', async () => {
    mockedKnowledge.listKnowledgeBases.mockResolvedValue({
      total: 2,
      page: 1,
      page_size: 20,
      items: [KB1, KB2],
    })
    const user = userEvent.setup()
    renderPicker()

    const trigger = screen.getByRole('button', { name: /已选知识库/ })
    await user.click(trigger)
    await waitFor(() => expect(screen.getByRole('combobox')).toHaveFocus())

    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Escape' })

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('点击浮层外部关闭', async () => {
    mockedKnowledge.listKnowledgeBases.mockResolvedValue({
      total: 2,
      page: 1,
      page_size: 20,
      items: [KB1, KB2],
    })
    const user = userEvent.setup()
    renderPicker()

    await user.click(screen.getByRole('button', { name: /已选知识库/ }))
    expect(screen.getByRole('listbox')).toBeInTheDocument()

    await user.click(document.body)

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('ArrowDown 移动候选、Enter 确认选择并关闭', async () => {
    mockedKnowledge.listKnowledgeBases.mockResolvedValue({
      total: 2,
      page: 1,
      page_size: 20,
      items: [KB1, KB2],
    })
    const onSelect = vi.fn()
    const user = userEvent.setup()
    renderPicker(null, onSelect)

    await user.click(screen.getByRole('button', { name: /已选知识库/ }))
    const search = screen.getByRole('combobox')
    await waitFor(() => expect(search).toHaveFocus())

    fireEvent.keyDown(search, { key: 'ArrowDown' })
    expect(screen.getByRole('option', { name: /产品手册/ })).toHaveAttribute('aria-current', 'true')

    fireEvent.keyDown(search, { key: 'Enter' })

    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ uuid: 'kb-1' }))
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('已选知识库触发按钮展示数量徽章；搜索过滤不影响徽章（名称由页面 scope-summary 承载）', async () => {
    mockedKnowledge.listKnowledgeBases.mockImplementation(async ({ q } = {}) => ({
      total: 1,
      page: 1,
      page_size: 20,
      items: q ? [KB2] : [KB1, KB2],
    }))
    const user = userEvent.setup()
    renderPicker('kb-1')

    // 已选时徽章为 1
    expect(screen.getByRole('button', { name: /已选知识库 1/ })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /已选知识库 1/ }))
    await user.type(screen.getByRole('combobox'), '客户')
    await waitFor(() =>
      expect(screen.queryByRole('option', { name: /产品手册/ })).not.toBeInTheDocument(),
    )

    // 搜索过滤不影响触发按钮徽章
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Escape' })
    expect(screen.getByRole('button', { name: /已选知识库 1/ })).toBeInTheDocument()
  })

  it('空态展示「没有可用的知识库」', async () => {
    mockedKnowledge.listKnowledgeBases.mockResolvedValue({
      total: 0,
      page: 1,
      page_size: 20,
      items: [],
    })
    const user = userEvent.setup()
    renderPicker()

    await user.click(screen.getByRole('button', { name: /已选知识库/ }))

    expect(await screen.findByText('没有可用的知识库')).toBeInTheDocument()
  })

  it('失败态提供重试', async () => {
    mockedKnowledge.listKnowledgeBases
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce({
        total: 1,
        page: 1,
        page_size: 20,
        items: [KB1],
      })
    const user = userEvent.setup()
    renderPicker()

    await user.click(screen.getByRole('button', { name: /已选知识库/ }))

    expect(await screen.findByText('加载失败')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '重试' }))

    expect(await screen.findByRole('option', { name: /产品手册/ })).toBeInTheDocument()
  })

  it('保持 v1 单知识库约束：多选入口不可执行', async () => {
    mockedKnowledge.listKnowledgeBases.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      items: [KB1],
    })
    const user = userEvent.setup()
    renderPicker()

    await user.click(screen.getByRole('button', { name: /已选知识库/ }))

    const multi = screen.getByRole('option', { name: /多知识库问答/ })
    expect(multi).toBeDisabled()
    expect(multi).toHaveAttribute('title', '多知识库问答规划中')
  })
})
