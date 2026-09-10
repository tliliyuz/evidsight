import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { createResearchApi, openResearchTaskStream } from '@/api/research'

function fakeClient() {
  const mocks = {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  }
  return mocks as unknown as AxiosInstance & typeof mocks
}

function sseBody(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk))
      }
      controller.close()
    },
  })
}

function fakeResponse(init: {
  ok: boolean
  status: number
  body?: ReadableStream<Uint8Array> | null
  json?: () => Promise<unknown>
}): Response {
  return {
    ok: init.ok,
    status: init.status,
    statusText: String(init.status),
    headers: new Headers(),
    body: init.body ?? null,
    json: init.json ?? (() => Promise.reject(new Error('no json'))),
  } as unknown as Response
}

describe('Research v1 API 客户端', () => {
  it('创建研究：POST /api/v1/research/tasks 携带 Idempotency-Key Header 与固定请求体', async () => {
    const client = fakeClient()
    client.post.mockResolvedValue({
      data: {
        task_id: '11111111-2222-4333-8444-555555555555',
        status: 'pending',
        created_at: '2026-08-12T06:00:00Z',
        direct_answer: false,
        idempotent_replayed: false,
        report_id: null,
      },
    })
    const api = createResearchApi(client)

    const input = {
      topic: '对比 AI Agent 平台',
      requirements: { task_type: 'comparison' as const, depth: 'quick' as const },
      source_strategy: 'hybrid' as const,
      knowledge_base_ids: ['kb-1'],
    }
    const result = await api.createResearchTask(input, 'idem-key-1')

    expect(client.post).toHaveBeenCalledWith('/api/v1/research/tasks', input, {
      headers: { 'Idempotency-Key': 'idem-key-1' },
    })
    expect(result.task_id).toBe('11111111-2222-4333-8444-555555555555')
    expect(result.idempotent_replayed).toBe(false)
  })

  it('列表透传 status / keyword / 分页参数', async () => {
    const client = fakeClient()
    client.get.mockResolvedValue({
      data: { total: 0, page: 1, page_size: 20, items: [] },
    })
    const api = createResearchApi(client)

    await api.listResearchTasks({ status: 'running', keyword: 'AI', page: 2, page_size: 10 })

    expect(client.get).toHaveBeenCalledWith('/api/v1/research/tasks', {
      params: { status: 'running', keyword: 'AI', page: 2, page_size: 10 },
    })
  })

  it('详情 / 取消 / 恢复 / 删除 / state 各自路由正确', async () => {
    const client = fakeClient()
    client.get.mockImplementation(async (url: string) => {
      if (url.endsWith('/state')) {
        return {
          data: {
            task_id: 't-1',
            topic: '主题',
            status: 'running',
            current_phase: 'searching',
            progress: { completed_steps: 1, total_steps: 7, progress: 0.14 },
            steps: [],
            error: null,
            stats: { total_sources: 0, total_evidence: 0 },
            report_id: null,
            created_at: '2026-08-12T06:00:00Z',
            started_at: null,
            completed_at: null,
          },
        }
      }
      return { data: { task_id: 't-1', topic: '主题', status: 'running' } }
    })
    client.post.mockImplementation(async (url: string) => {
      if (url.endsWith('/cancel')) {
        return { data: { task_id: 't-1', status: 'running', cancel_requested: true } }
      }
      return {
        data: {
          task_id: 't-1',
          status: 'running',
          resume_from: {
            phase: 'searching',
            last_completed_step_id: 's1',
            next_step_type: 'search',
          },
        },
      }
    })
    client.delete.mockResolvedValue({ status: 204 })
    const api = createResearchApi(client)

    const task = await api.getResearchTask('t-1')
    expect(client.get).toHaveBeenCalledWith('/api/v1/research/tasks/t-1')
    expect(task.status).toBe('running')

    const canceled = await api.cancelResearchTask('t-1')
    expect(canceled.cancel_requested).toBe(true)

    const resumed = await api.resumeResearchTask('t-1')
    expect(resumed.resume_from.next_step_type).toBe('search')

    await api.deleteResearchTask('t-1')
    expect(client.delete).toHaveBeenCalledWith('/api/v1/research/tasks/t-1')

    const state = await api.getResearchTaskState('t-1')
    expect(state.current_phase).toBe('searching')
    expect(state.progress.completed_steps).toBe(1)
  })
})

describe('Research v1 SSE 流式客户端', () => {
  it('GET /api/v1/research/tasks/{id}/events 携带 Bearer 与 Last-Event-ID 游标', async () => {
    const fetchFn = vi.fn().mockResolvedValue(
      fakeResponse({
        ok: true,
        status: 200,
        body: sseBody([
          'event: task.updated\ndata: {"task_id":"t-1","status":"running"}\n\n',
          'event: stream.end\ndata: {"reason":"subscription_ended"}\n\n',
        ]),
      }),
    )
    const onEvent = vi.fn()

    await openResearchTaskStream('t-1', onEvent, new AbortController().signal, {
      lastEventId: 42,
      fetchFn,
      accessToken: () => 'access-token',
    })

    expect(fetchFn).toHaveBeenCalledWith(
      '/api/v1/research/tasks/t-1/events',
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({
          Authorization: 'Bearer access-token',
          'Last-Event-ID': '42',
        }),
        credentials: 'include',
      }),
    )
    expect(onEvent).toHaveBeenCalledTimes(2)
  })

  it('未携带游标时请求头不含 Last-Event-ID，事件逐帧回调', async () => {
    const fetchFn = vi.fn().mockResolvedValue(
      fakeResponse({
        ok: true,
        status: 200,
        body: sseBody(['event: snapshot\ndata: {"task_id":"t-1","status":"running"}\n\n']),
      }),
    )
    const onEvent = vi.fn()

    await openResearchTaskStream('t-1', onEvent, new AbortController().signal, { fetchFn })

    const [, init] = fetchFn.mock.calls[0]
    expect(init.headers['Last-Event-ID']).toBeUndefined()
    expect(onEvent).toHaveBeenCalledTimes(1)
    expect(onEvent.mock.calls[0][0]).toMatchObject({ type: 'snapshot' })
  })

  it('HTTP 非 2xx 抛 ResearchStreamHttpError（含 status / error_code / message）', async () => {
    const fetchFn = vi.fn().mockResolvedValue(
      fakeResponse({
        ok: false,
        status: 403,
        json: () =>
          Promise.resolve({
            error: { error_code: 'RS_TASK_FORBIDDEN', message: '无权查看该任务' },
          }),
      }),
    )

    await expect(
      openResearchTaskStream('t-1', vi.fn(), new AbortController().signal, { fetchFn }),
    ).rejects.toMatchObject({
      name: 'ResearchStreamHttpError',
      status: 403,
      errorCode: 'RS_TASK_FORBIDDEN',
      message: '无权查看该任务',
    })
  })
})
