import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
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
