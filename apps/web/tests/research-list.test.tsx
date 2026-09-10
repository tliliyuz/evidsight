import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ResearchApi, ResearchTaskListItem } from '@/api/research'
import { ToastProvider } from '@/components/feedback/ToastProvider'
import { ResearchTaskListPage } from '@/features/research/ResearchTaskListPage'
import { formatTimestamp } from '@/features/knowledge/format'

const RUNNING_TASK_ID = '11111111-2222-4333-8444-555555555501'
const DONE_TASK_ID = '11111111-2222-4333-8444-555555555502'

function task(overrides: Partial<ResearchTaskListItem> = {}): ResearchTaskListItem {
  return {
    task_id: RUNNING_TASK_ID,
    topic: '全球 AI Agent 竞争格局',
    status: 'running',
    task_type: 'comparison',
    source_strategy: 'hybrid',
    progress: 0.57,
    total_sources: 12,
    total_evidence: 34,
    report_id: null,
    created_at: '2026-08-12T06:00:00Z',
    completed_at: null,
    ...overrides,
  }
}

function makeApi(overrides: Partial<ResearchApi> = {}): ResearchApi {
  return {
    listResearchTasks: vi.fn().mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 10,
      items: [task()],
    }),
    createResearchTask: vi.fn(),
    getResearchTask: vi.fn(),
    cancelResearchTask: vi.fn(),
    resumeResearchTask: vi.fn(),
    deleteResearchTask: vi.fn().mockResolvedValue(undefined),
    getResearchTaskState: vi.fn(),
    ...overrides,
  }
}

function renderPage(api: ResearchApi, initialEntry = '/research') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes>
            <Route path="/research" element={<ResearchTaskListPage api={api} />} />
            <Route path="/research/:taskId" element={<div data-testid="run-mock" />} />
            <Route path="/reports/:reportId" element={<div data-testid="report-mock" />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('研究任务列表页', () => {
  beforeEach(() => vi.clearAllMocks())

  it('渲染页头、新建按钮、筛选工具栏与 Ledger 列头', async () => {
    renderPage(makeApi())

    expect(screen.getByRole('heading', { name: '研究任务' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /新建研究/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '全部' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '进行中' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '已完成' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '异常' })).toBeInTheDocument()
    expect(screen.getByRole('searchbox', { name: '搜索研究主题' })).toBeInTheDocument()
    expect(await screen.findByText('全球 AI Agent 竞争格局')).toBeInTheDocument()
  })

  it('行展示题目/类型、来源策略、状态与绝对时间戳', async () => {
    renderPage(makeApi())
    await screen.findByText('全球 AI Agent 竞争格局')

    const row = screen.getByText('全球 AI Agent 竞争格局').closest('li')
    expect(row).not.toBeNull()
    expect(within(row as HTMLElement).getByText('对比研究')).toBeInTheDocument()
    expect(within(row as HTMLElement).getByText('混合')).toBeInTheDocument()
    expect(within(row as HTMLElement).getByText('进行中')).toBeInTheDocument()
    expect(
      within(row as HTMLElement).getByText(formatTimestamp(task().created_at)),
    ).toBeInTheDocument()
  })

  it('切换状态标签后以 status 参数重新请求；关键词搜索以 keyword 请求', async () => {
    const api = makeApi()
    renderPage(api)
    await screen.findByText('全球 AI Agent 竞争格局')

    fireEvent.click(screen.getByRole('button', { name: '已完成' }))
    await waitFor(() =>
      expect(api.listResearchTasks).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: 'completed' }),
      ),
    )

    fireEvent.click(screen.getByRole('button', { name: '全部' }))
    const search = screen.getByRole('searchbox', { name: '搜索研究主题' })
    fireEvent.change(search, { target: { value: 'AI' } })
    fireEvent.submit(screen.getByRole('search', { name: '搜索研究主题' }))
    await waitFor(() =>
      expect(api.listResearchTasks).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: undefined, keyword: 'AI' }),
      ),
    )
  })

  it('运行中任务行主操作「进入现场」', async () => {
    renderPage(makeApi())
    await screen.findByText('全球 AI Agent 竞争格局')

    expect(screen.getByRole('link', { name: '进入现场' })).toHaveAttribute(
      'href',
      `/research/${RUNNING_TASK_ID}`,
    )
  })

  it('已完成且存在报告的行主操作「查看报告」', async () => {
    renderPage(
      makeApi({
        listResearchTasks: vi.fn().mockResolvedValue({
          total: 1,
          page: 1,
          page_size: 10,
          items: [
            task({
              task_id: DONE_TASK_ID,
              status: 'completed',
              progress: 1,
              report_id: 'report-1',
              completed_at: '2026-08-12T07:00:00Z',
            }),
          ],
        }),
      }),
    )
    await screen.findByText('全球 AI Agent 竞争格局')

    expect(screen.getByRole('link', { name: '查看报告' })).toHaveAttribute(
      'href',
      '/reports/report-1',
    )
  })

  it('终态行可经 ⋮ 菜单删除：具名确认 → 调用删除 → 行移除 + 全局反馈', async () => {
    // 删除后列表接口不再返回该任务（与真实后端一致），验证行从列表消失
    let deleted = false
    const api = makeApi({
      listResearchTasks: vi.fn().mockImplementation(() =>
        Promise.resolve({
          total: deleted ? 0 : 1,
          page: 1,
          page_size: 10,
          items: deleted
            ? []
            : [
                task({
                  task_id: DONE_TASK_ID,
                  topic: 'Q2 客户流失分析',
                  status: 'failed',
                  progress: 0.8,
                  completed_at: '2026-08-12T07:00:00Z',
                }),
              ],
        }),
      ),
      deleteResearchTask: vi.fn().mockImplementation(() => {
        deleted = true
        return Promise.resolve(undefined)
      }),
    })
    renderPage(api)
    await screen.findByText('Q2 客户流失分析')

    fireEvent.click(screen.getByRole('button', { name: '研究任务操作 Q2 客户流失分析' }))
    fireEvent.click(screen.getByRole('menuitem', { name: '删除研究任务' }))
    expect(await screen.findByText(/确定删除研究任务「Q2 客户流失分析」/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }))

    await waitFor(() => expect(api.deleteResearchTask).toHaveBeenCalledWith(DONE_TASK_ID))
    await waitFor(() => expect(screen.queryByText('Q2 客户流失分析')).not.toBeInTheDocument())
    expect(await screen.findByText(/已删除研究任务「Q2 客户流失分析」/)).toBeInTheDocument()
  })

  it('运行中任务行不提供删除（无 ⋮ 菜单）', async () => {
    renderPage(makeApi())
    await screen.findByText('全球 AI Agent 竞争格局')

    expect(screen.queryByRole('button', { name: /研究任务操作/ })).not.toBeInTheDocument()
  })

  it('无匹配时展示空态', async () => {
    renderPage(
      makeApi({
        listResearchTasks: vi.fn().mockResolvedValue({
          total: 0,
          page: 1,
          page_size: 10,
          items: [],
        }),
      }),
      '/research?keyword=不存在',
    )
    expect(await screen.findByText('没有匹配的研究任务')).toBeInTheDocument()
  })
})
