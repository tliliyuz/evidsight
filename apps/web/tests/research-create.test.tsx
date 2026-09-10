import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation, useParams } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { knowledgeApi } from '@/api/knowledge'
import type { KnowledgeBase } from '@/api/knowledge'
import type { ResearchApi } from '@/api/research'
import { ToastProvider } from '@/components/feedback/ToastProvider'
import { ResearchCreatePage } from '@/features/research/ResearchCreatePage'

const TASK_ID = '11111111-2222-4333-8444-555555555555'

const KB1: KnowledgeBase = {
  uuid: '550e8400-e29b-41d4-a716-446655440011',
  name: '产品规划',
  description: '',
  owner: '550e8400-e29b-41d4-a716-446655440001',
  visibility: 'private',
  status: 'active',
  doc_count: 3,
  chunk_count: 30,
  index_status: 'ready',
  owner_username: 'alice',
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-08T00:00:00Z',
}

const KB2: KnowledgeBase = {
  ...KB1,
  uuid: '550e8400-e29b-41d4-a716-446655440012',
  name: '客户反馈',
}

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

const mockedKnowledge = vi.mocked(knowledgeApi)

function makeApi(overrides: Partial<ResearchApi> = {}): ResearchApi {
  return {
    listResearchTasks: vi.fn(),
    createResearchTask: vi.fn(),
    getResearchTask: vi.fn(),
    cancelResearchTask: vi.fn(),
    resumeResearchTask: vi.fn(),
    deleteResearchTask: vi.fn(),
    getResearchTaskState: vi.fn(),
    ...overrides,
  }
}

function RunRouteMock() {
  const { taskId } = useParams()
  const location = useLocation()
  const kbNames = (location.state as { kbNames?: string[] } | null)?.kbNames
  return (
    <div data-testid="run-mock">
      {taskId}
      {kbNames ? `:${kbNames.join(',')}` : ''}
    </div>
  )
}

function renderPage(api: ResearchApi) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={['/research/new']}>
          <Routes>
            <Route path="/research/new" element={<ResearchCreatePage api={api} />} />
            <Route path="/research/:taskId" element={<RunRouteMock />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

async function selectKbs(names: string[]) {
  fireEvent.click(screen.getByRole('button', { name: /内部知识范围/ }))
  for (const name of names) {
    const option = await screen.findByRole('option', { name: new RegExp(name) })
    fireEvent.click(option)
  }
  fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Escape' })
}

describe('创建研究页', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedKnowledge.listKnowledgeBases.mockResolvedValue({
      total: 2,
      page: 1,
      page_size: 20,
      items: [KB1, KB2],
    })
  })

  it('渲染主题 / 研究类型 / 来源策略 / 知识库（默认混合研究）与提交按钮', () => {
    renderPage(makeApi())

    expect(screen.getByLabelText('研究主题')).toBeInTheDocument()
    expect(screen.getByRole('group', { name: '研究类型' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: '来源策略' })).toBeInTheDocument()
    // 默认混合研究 → 显示内部知识范围选择器
    expect(screen.getByRole('button', { name: /内部知识范围/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /启动深度研究/ })).toBeInTheDocument()
  })

  it('切换到公开网络后隐藏知识库选择器', () => {
    renderPage(makeApi())

    fireEvent.click(screen.getByRole('button', { name: '公开网络' }))
    expect(screen.queryByRole('button', { name: /内部知识范围/ })).not.toBeInTheDocument()
  })

  it('主题为空时阻止提交并提示', async () => {
    const api = makeApi()
    renderPage(api)

    fireEvent.click(screen.getByRole('button', { name: /启动深度研究/ }))
    expect(await screen.findByText('请输入研究主题')).toBeInTheDocument()
    expect(api.createResearchTask).not.toHaveBeenCalled()
  })

  it('混合/内部策略未选知识库时阻止提交', async () => {
    const api = makeApi()
    renderPage(api)
    fireEvent.change(screen.getByLabelText('研究主题'), { target: { value: '对比 AI 平台' } })

    fireEvent.click(screen.getByRole('button', { name: /启动深度研究/ }))
    expect(await screen.findByText('请至少选择一个知识库')).toBeInTheDocument()
    expect(api.createResearchTask).not.toHaveBeenCalled()
  })

  it('提交成功：发送固定契约载荷并携带 Idempotency-Key，导航到运行态并传递知识库名称', async () => {
    const api = makeApi({
      createResearchTask: vi.fn().mockResolvedValue({
        task_id: TASK_ID,
        status: 'pending',
        created_at: '2026-08-12T06:00:00Z',
        direct_answer: false,
        idempotent_replayed: false,
        report_id: null,
      }),
    })
    renderPage(api)
    fireEvent.change(screen.getByLabelText('研究主题'), {
      target: { value: '对比三家 AI 平台' },
    })
    await selectKbs(['产品规划', '客户反馈'])

    fireEvent.click(screen.getByRole('button', { name: /启动深度研究/ }))

    await waitFor(() =>
      expect(api.createResearchTask).toHaveBeenCalledWith(
        expect.objectContaining({
          topic: '对比三家 AI 平台',
          requirements: expect.objectContaining({ task_type: 'comparison' }),
          source_strategy: 'hybrid',
          knowledge_base_ids: [KB1.uuid, KB2.uuid],
        }),
        expect.any(String),
      ),
    )
    const [, key] = (api.createResearchTask as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(key).toMatch(/^[0-9a-f-]{36}$/)
    expect(await screen.findByTestId('run-mock')).toHaveTextContent(`${TASK_ID}:产品规划,客户反馈`)
  })

  it('提交失败重试复用同一 Idempotency-Key（幂等），成功后重置', async () => {
    const createResearchTask = vi
      .fn<ResearchApi['createResearchTask']>()
      .mockRejectedValueOnce({
        response: {
          status: 429,
          data: { error: { error_code: 'RS_TASK_CONCURRENCY_LIMIT', message: '并发已达上限' } },
        },
      })
      .mockResolvedValueOnce({
        task_id: TASK_ID,
        status: 'pending',
        created_at: '2026-08-12T06:00:00Z',
        direct_answer: false,
        idempotent_replayed: false,
        report_id: null,
      })
    const api = makeApi({ createResearchTask })
    renderPage(api)
    fireEvent.change(screen.getByLabelText('研究主题'), { target: { value: '对比 AI 平台' } })
    await selectKbs(['产品规划'])

    // 第一次提交 → 429
    fireEvent.click(screen.getByRole('button', { name: /启动深度研究/ }))
    expect(await screen.findByText(/并发已达上限/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /前往任务列表/ })).toBeInTheDocument()
    const key1 = createResearchTask.mock.calls[0][1]

    // 重试 → 复用同一 Key
    fireEvent.click(screen.getByRole('button', { name: /启动深度研究/ }))
    await screen.findByTestId('run-mock')
    const key2 = createResearchTask.mock.calls[1][1]
    expect(key2).toBe(key1)
  })

  it('非限流错误展示安全错误文案，不导航', async () => {
    const api = makeApi({
      createResearchTask: vi.fn().mockRejectedValue({
        response: {
          status: 400,
          data: { error: { error_code: 'VALIDATION_ERROR', message: '请求体不合法' } },
        },
      }),
    })
    renderPage(api)
    fireEvent.change(screen.getByLabelText('研究主题'), { target: { value: '对比 AI 平台' } })
    await selectKbs(['产品规划'])

    fireEvent.click(screen.getByRole('button', { name: /启动深度研究/ }))
    expect(await screen.findByText('请求体不合法')).toBeInTheDocument()
    expect(screen.queryByTestId('run-mock')).not.toBeInTheDocument()
  })

  it('展示研究约定 Context Rail', () => {
    renderPage(makeApi())
    expect(screen.getByText('研究约定')).toBeInTheDocument()
    expect(screen.getByText('范围明确')).toBeInTheDocument()
    expect(screen.getByText('结论有据')).toBeInTheDocument()
  })
})
