import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { KnowledgeBase } from '@/api/knowledge'
import type { ResearchTaskListItem } from '@/api/research'
import { authSession } from '@/features/auth/authSession'
import { WorkbenchPage, type WorkbenchApi } from '@/features/workbench/WorkbenchPage'

function task(overrides: Partial<ResearchTaskListItem> = {}): ResearchTaskListItem {
  return {
    task_id: 't-1',
    topic: '研究主题',
    status: 'running',
    task_type: 'comparison',
    source_strategy: 'hybrid',
    progress: 0.68,
    total_sources: 12,
    total_evidence: 5,
    report_id: null,
    created_at: '2026-08-08T00:00:00Z',
    completed_at: null,
    ...overrides,
  }
}

function kb(overrides: Partial<KnowledgeBase> = {}): KnowledgeBase {
  return {
    uuid: 'kb-1',
    name: '客户反馈与访谈',
    description: '访谈记录',
    owner: '550e8400-e29b-41d4-a716-446655440001',
    visibility: 'private',
    status: 'active',
    doc_count: 489,
    chunk_count: 1200,
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-08T00:00:00Z',
    ...overrides,
  }
}

function makeApi(overrides: Partial<WorkbenchApi> = {}): WorkbenchApi {
  return {
    listResearchTasks: vi.fn().mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 5,
      items: [task()],
    }),
    listKnowledgeBases: vi.fn().mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 5,
      items: [kb()],
    }),
    ...overrides,
  }
}

function renderWorkbench(api: WorkbenchApi) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <WorkbenchPage api={api} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.spyOn(authSession, 'getSnapshot').mockReturnValue({
    status: 'authenticated',
    user: {
      id: '550e8400-e29b-41d4-a716-446655440001',
      username: 'linmo',
      role: 'user',
      status: 'active',
    },
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('工作台', () => {
  it('无历史时提供行动入口而不是空 KPI', async () => {
    renderWorkbench(
      makeApi({
        listResearchTasks: vi.fn().mockResolvedValue({
          total: 0,
          page: 1,
          page_size: 5,
          items: [],
        }),
        listKnowledgeBases: vi.fn().mockResolvedValue({
          total: 0,
          page: 1,
          page_size: 5,
          items: [],
        }),
      }),
    )

    expect(await screen.findByRole('link', { name: '开始研究' })).toHaveAttribute(
      'href',
      '/research/new',
    )
    expect(screen.getByRole('link', { name: '创建知识库' })).toHaveAttribute(
      'href',
      '/knowledge-bases?create=1',
    )
    expect(screen.queryByText(/KPI/i)).not.toBeInTheDocument()
  })

  it('RECENT RESEARCH 空态：「开始研究」按钮与说明句同一水平线右侧（beside 布局）', async () => {
    renderWorkbench(
      makeApi({
        listResearchTasks: vi.fn().mockResolvedValue({
          total: 0,
          page: 1,
          page_size: 5,
          items: [],
        }),
        listKnowledgeBases: vi.fn().mockResolvedValue({
          total: 0,
          page: 1,
          page_size: 5,
          items: [],
        }),
      }),
    )

    const start = await screen.findByRole('link', { name: '开始研究' })
    const section = start.closest('.empty-state') as HTMLElement | null
    // 空态使用 beside 变体：说明文案与动作同一行、动作居右
    expect(section?.classList.contains('empty-state--beside')).toBe(true)
    const row = section?.querySelector('.empty-state__action-row') as HTMLElement | null
    expect(row).not.toBeNull()
    expect(
      within(row as HTMLElement).getByText('明确研究范围，系统会持续保存任务事实。'),
    ).toBeInTheDocument()
    expect(within(row as HTMLElement).getByRole('link', { name: '开始研究' })).toBe(start)
  })

  it('快速开始卡片：说明标题居左、动作文案居右（launcher-card 布局）', () => {
    renderWorkbench(makeApi())

    const chatCard = screen.getByRole('link', { name: /向企业知识提问/ })
    // 标题/说明文案在左侧文案组，动作文案在右侧动作元素中，两者分离
    const copy = chatCard.querySelector('.launcher-card__copy') as HTMLElement | null
    expect(copy).not.toBeNull()
    expect(within(copy as HTMLElement).getByText('向企业知识提问')).toBeInTheDocument()
    expect(chatCard.querySelector('.launcher-card__action')?.textContent).toContain('进入问答')
    expect(within(copy as HTMLElement).queryByText(/进入问答/)).not.toBeInTheDocument()

    const researchCard = screen.getByRole('link', { name: /发起新的研究任务/ })
    expect(researchCard.querySelector('.launcher-card__copy')).not.toBeNull()
    expect(researchCard.querySelector('.launcher-card__action')?.textContent).toContain('定义范围')
  })

  it('标题使用用户化问候，用户名来自 /me', () => {
    renderWorkbench(makeApi())

    expect(screen.getByRole('heading', { level: 1 }).textContent).toMatch(/linmo/)
  })

  it('RECENT RESEARCH 使用连续列表展示来源类型/状态/进度/继续入口', async () => {
    renderWorkbench(makeApi())

    // 来源类型（hybrid → 混合）与来源类型标签
    expect(await screen.findByText('混合')).toBeInTheDocument()
    // 主题同时出现在任务行与「进行中的研究」卡片
    expect(screen.getAllByText('研究主题').length).toBeGreaterThan(0)
    // 运行中任务显示进度
    expect(screen.getByLabelText('进度 68%')).toBeInTheDocument()
    // 继续入口：进入现场，而不是重新创建任务
    expect(screen.getByRole('link', { name: '进入现场' })).toHaveAttribute('href', '/research/t-1')
  })

  it('正在运行的任务显示进入研究现场，不重新创建任务', async () => {
    renderWorkbench(makeApi())

    const entry = await screen.findByRole('link', { name: /进入研究现场/ })
    expect(entry).toHaveAttribute('href', '/research/t-1')
  })

  it('RECENT KNOWLEDGE 放入右侧紧凑列表', async () => {
    renderWorkbench(makeApi())

    expect(await screen.findByText('客户反馈与访谈')).toBeInTheDocument()
    expect(screen.getByText(/489 个文档/)).toBeInTheDocument()
  })

  it('无运行任务时「进行中的研究」卡片保留并显示占位', async () => {
    renderWorkbench(
      makeApi({
        listResearchTasks: vi.fn().mockImplementation((params) =>
          Promise.resolve({
            total: params.status === 'running' ? 0 : 1,
            page: 1,
            page_size: 5,
            items: params.status === 'running' ? [] : [task({ status: 'completed' })],
          }),
        ),
      }),
    )

    // 卡片始终渲染：没有运行任务时显示占位文案，不把右栏整个隐藏
    const mission = await screen.findByLabelText('进行中的研究')
    expect(mission).toBeInTheDocument()
    expect(within(mission).getByText(/暂无进行中的研究/)).toBeInTheDocument()
    // 占位提供行动入口；RECENT KNOWLEDGE 固定在卡片下方
    expect(within(mission).getByRole('link', { name: /开始研究/ })).toHaveAttribute(
      'href',
      '/research/new',
    )
    expect(screen.getByRole('region', { name: '最近知识库' })).toBeInTheDocument()
  })

  it('paused 状态渲染为已暂停徽标且不提供进入现场入口', async () => {
    renderWorkbench(
      makeApi({
        listResearchTasks: vi.fn().mockResolvedValue({
          total: 1,
          page: 1,
          page_size: 5,
          items: [task({ status: 'paused' })],
        }),
      }),
    )

    expect(await screen.findByText('已暂停')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '进入现场' })).not.toBeInTheDocument()
  })
})
