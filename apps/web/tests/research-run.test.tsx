import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { researchApi } from '@/api/research'
import type { ResearchTaskState } from '@/api/research'
import { ToastProvider } from '@/components/feedback/ToastProvider'
import { ResearchRunPage } from '@/features/research/ResearchRunPage'

const { TASK_ID } = vi.hoisted(() => ({
  TASK_ID: '11111111-2222-4333-8444-555555555555',
}))

const streamMock = vi.hoisted(() => ({
  current: null as {
    emit: (event: unknown) => void
    resolve: () => void
    reject: (error: unknown) => void
  } | null,
}))

vi.mock('@/api/research', () => ({
  researchApi: {
    listResearchTasks: vi.fn(),
    createResearchTask: vi.fn(),
    getResearchTask: vi.fn(),
    cancelResearchTask: vi
      .fn()
      .mockResolvedValue({ task_id: TASK_ID, status: 'running', cancel_requested: true }),
    resumeResearchTask: vi.fn().mockResolvedValue({
      task_id: TASK_ID,
      status: 'running',
      resume_from: { phase: 'searching', last_completed_step_id: 's1', next_step_type: 'search' },
    }),
    deleteResearchTask: vi.fn(),
    getResearchTaskState: vi.fn(),
  },
  openResearchTaskStream: vi.fn(
    (_taskId: string, onEvent: (event: unknown) => void, signal: AbortSignal) =>
      new Promise<void>((resolve, reject) => {
        streamMock.current = { emit: onEvent, resolve, reject }
        signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
      }),
  ),
  ResearchStreamHttpError: class extends Error {},
}))

const mockedApi = vi.mocked(researchApi)

function stateFixture(overrides: Partial<ResearchTaskState> = {}): ResearchTaskState {
  return {
    task_id: TASK_ID,
    topic: '全球 AI Agent 竞争格局',
    status: 'running',
    current_phase: 'synthesizing',
    progress: { completed_steps: 4, total_steps: 7, progress: 0.57 },
    steps: [],
    error: null,
    stats: { total_sources: 12, total_evidence: 34 },
    report_id: null,
    created_at: '2026-08-12T06:00:00Z',
    started_at: '2026-08-12T06:00:01Z',
    completed_at: null,
    ...overrides,
  }
}

function renderPage(initialEntry = `/research/${TASK_ID}`, state?: unknown) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={[{ pathname: initialEntry, state }]}>
          <Routes>
            <Route path="/research/:taskId" element={<ResearchRunPage />} />
            <Route path="/research" element={<div data-testid="list-mock" />} />
            <Route path="/reports/:reportId" element={<div data-testid="report-mock" />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('研究运行态页', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    streamMock.current = null
    mockedApi.getResearchTaskState.mockResolvedValue(stateFixture())
  })

  it('渲染标题、返回链接、取消入口与七阶段 Pipeline', async () => {
    renderPage()
    expect(await screen.findByText('全球 AI Agent 竞争格局')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '← 研究任务' })).toHaveAttribute('href', '/research')
    expect(screen.getByRole('button', { name: /取消任务/ })).toBeInTheDocument()

    for (const label of ['规划', '检索', '获取', '重排', '综合', '证据图谱', '生成']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
    expect(screen.getByText('整体进度')).toBeInTheDocument()
  })

  it('渲染任务信息 Context Rail（研究类型/来源策略/当前证据/知识库路由传参）', async () => {
    renderPage(`/research/${TASK_ID}`, {
      kbNames: ['产品规划', '客户反馈'],
      taskType: 'comparison',
      strategy: 'hybrid',
    })
    await screen.findByText('全球 AI Agent 竞争格局')

    expect(screen.getByText('研究类型')).toBeInTheDocument()
    expect(screen.getByText('对比研究')).toBeInTheDocument()
    expect(screen.getByText('来源策略')).toBeInTheDocument()
    expect(screen.getByText('混合研究')).toBeInTheDocument()
    expect(screen.getByText('当前证据')).toBeInTheDocument()
    expect(screen.getByText('产品规划')).toBeInTheDocument()
    expect(screen.getByText('客户反馈')).toBeInTheDocument()
    expect(screen.getByText('34 项')).toBeInTheDocument()
  })

  it('SSE 事件驱动进度与事件流更新（task.updated / phase.updated / step.updated）', async () => {
    renderPage()
    await screen.findByText('全球 AI Agent 竞争格局')

    act(() => {
      streamMock.current?.emit({
        type: 'task.updated',
        id: 5,
        data: {
          task_id: TASK_ID,
          status: 'running',
          current_phase: 'synthesizing',
          completed_steps: 5,
          total_steps: 7,
          progress: 0.71,
          message: null,
          error_code: null,
          error_message: null,
        },
      })
      streamMock.current?.emit({
        type: 'phase.updated',
        id: 6,
        data: { phase: 'searching', timestamp: '2026-08-12T06:01:00Z', duration_ms: 45000 },
      })
      streamMock.current?.emit({
        type: 'step.updated',
        id: 7,
        data: {
          step_id: 's2',
          step_type: 'search',
          status: 'running',
          label: '来源检索',
          timestamp: '2026-08-12T06:01:00Z',
          phase: 'searching',
          last_completed_step_id: null,
          output: null,
          iteration: null,
          tool_call_id: null,
          tool_name: null,
          arguments: null,
          observation: null,
          success: null,
        },
      })
    })

    expect(await screen.findByText('来源检索')).toBeInTheDocument()
    expect(screen.getByText(/进入阶段：检索/)).toBeInTheDocument()
  })

  it('取消任务：具名确认 → 调用取消 → task.canceled 事件展示「已请求取消」', async () => {
    renderPage()
    await screen.findByText('全球 AI Agent 竞争格局')

    fireEvent.click(screen.getByRole('button', { name: /取消任务/ }))
    expect(
      await screen.findByText(/确定取消研究任务「全球 AI Agent 竞争格局」/),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '确认取消' }))

    await waitFor(() => expect(mockedApi.cancelResearchTask).toHaveBeenCalledWith(TASK_ID))

    act(() => {
      streamMock.current?.emit({
        type: 'task.canceled',
        id: 8,
        data: { task_id: TASK_ID, status: 'running', cancel_requested: true },
      })
    })
    await waitFor(() => {
      // 页头「已请求取消」+ 事件流同标题各一处
      expect(screen.getAllByText('已请求取消').length).toBeGreaterThanOrEqual(1)
    })
  })

  it('可恢复失败任务展示「继续任务」并调用 resume', async () => {
    mockedApi.getResearchTaskState.mockResolvedValue(
      stateFixture({
        status: 'failed',
        error: { error_code: 'SYSTEM_UNAVAILABLE', error_message: '服务不可用', recoverable: true },
      }),
    )
    renderPage()
    expect(await screen.findByRole('button', { name: /继续任务/ })).toBeInTheDocument()
    expect(await screen.findByText('服务不可用')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /继续任务/ }))
    await waitFor(() => expect(mockedApi.resumeResearchTask).toHaveBeenCalledWith(TASK_ID))
  })

  it('终态任务展示实际耗时（completed_at − started_at）而非墙钟时长', async () => {
    mockedApi.getResearchTaskState.mockResolvedValue(
      stateFixture({
        status: 'failed',
        completed_at: '2026-08-12T06:00:43Z', // 与 started_at 06:00:01Z 相差 42 秒
        error: { error_code: 'E3103', error_message: '预算停止', recoverable: false },
      }),
    )
    renderPage()
    await screen.findByText('全球 AI Agent 竞争格局')

    // 实际耗时 42 秒，不随当前时间增长（文本嵌在「已完成 X/Y 步 · 运行 42 秒」中）
    expect(screen.getByText(/运行 42 秒/)).toBeInTheDocument()
    // 不再按 started_at → 当前时刻显示「已运行 X 分」
    expect(screen.queryByText(/已运行 \d+ 分/)).not.toBeInTheDocument()
    // 「后台持续运行」说明仅非终态展示
    expect(screen.queryByText('任务在后台持续运行，关闭页面不会中止研究。')).not.toBeInTheDocument()
  })

  it('非终态任务显示「已运行」时长与后台持续运行说明', async () => {
    renderPage() // 默认 running
    await screen.findByText('全球 AI Agent 竞争格局')

    expect(screen.getByText(/已运行 \d+ 分 \d+ 秒/)).toBeInTheDocument()
    expect(screen.getByText('任务在后台持续运行，关闭页面不会中止研究。')).toBeInTheDocument()
  })

  it('非终态运行时长每秒更新，终态后不再依赖当前时间', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-12T06:00:05Z'))
    try {
      renderPage()
      await act(async () => {
        await Promise.resolve()
        await Promise.resolve()
      })

      expect(screen.getByText(/已运行 4 秒/)).toBeInTheDocument()
      await act(async () => {
        vi.advanceTimersByTime(2000)
      })
      expect(screen.getByText(/已运行 6 秒/)).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('收到失败终态 SSE 后立即收口，不需要刷新页面', async () => {
    renderPage()
    await screen.findByText('全球 AI Agent 竞争格局')

    act(() => {
      streamMock.current?.emit({
        type: 'task.updated',
        id: 10,
        data: {
          task_id: TASK_ID,
          status: 'failed',
          current_phase: null,
          completed_steps: 0,
          total_steps: 7,
          progress: 0,
          message: null,
          error_code: 'E3110',
          error_message: 'LLM 认证失败',
          completed_at: '2026-08-12T06:00:08Z',
          recoverable: false,
        },
      })
    })

    expect(await screen.findByText('LLM 认证失败')).toBeInTheDocument()
    expect(screen.getByText(/运行 7 秒/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /取消任务/ })).not.toBeInTheDocument()
  })

  it('SSE 自然结束后回读服务端快照并收口', async () => {
    mockedApi.getResearchTaskState.mockResolvedValueOnce(stateFixture()).mockResolvedValueOnce(
      stateFixture({
        status: 'failed',
        completed_at: '2026-08-12T06:00:08Z',
        error: { error_code: 'E3110', error_message: 'LLM 认证失败', recoverable: false },
      }),
    )
    renderPage()
    await screen.findByText('全球 AI Agent 竞争格局')

    const stream = streamMock.current
    await act(async () => {
      stream?.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(await screen.findByText('LLM 认证失败')).toBeInTheDocument()
    expect(mockedApi.getResearchTaskState).toHaveBeenCalledTimes(2)
  })

  it('终态任务展示状态与「查看报告」入口（report_id 非空）', async () => {
    mockedApi.getResearchTaskState.mockResolvedValue(
      stateFixture({
        status: 'completed',
        completed_at: '2026-08-12T07:00:00Z',
        report_id: 'report-1',
      }),
    )
    renderPage()
    await screen.findByText('全球 AI Agent 竞争格局')

    expect(screen.getByText('已完成')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /查看报告/ })).toHaveAttribute(
      'href',
      '/reports/report-1',
    )
  })

  it('快照加载失败（尚无任务事实）展示错误态并可重试', async () => {
    mockedApi.getResearchTaskState.mockRejectedValueOnce(new Error('network down'))
    renderPage()

    expect(await screen.findByText(/暂时无法加载/)).toBeInTheDocument()
    const retry = screen.getByRole('button', { name: /重试/ })
    mockedApi.getResearchTaskState.mockResolvedValue(stateFixture())
    fireEvent.click(retry)
    expect(await screen.findByText('全球 AI Agent 竞争格局')).toBeInTheDocument()
  })

  it('断线进入重连状态并保留内容', async () => {
    renderPage()
    await screen.findByText('全球 AI Agent 竞争格局')

    act(() => {
      streamMock.current?.reject(new TypeError('network down'))
    })
    expect(await screen.findByText(/正在重连/)).toBeInTheDocument()
    expect(screen.getByText('全球 AI Agent 竞争格局')).toBeInTheDocument()
  })
})
