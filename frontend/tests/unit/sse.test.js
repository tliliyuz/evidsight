/**
 * SSE 解析工具单元测试 — 覆盖 src/utils/sse.js
 *
 * 对齐 ROADMAP.md §3.9：
 *   - 各 event 类型解析
 *   - 注释帧跳过（心跳 : ping）
 *   - buffer 分割（不完整 frame 保留）
 *   - 异常格式容错
 *   - 多行 data 拼接
 *   - 连接状态机（5 态）
 *   - 重连逻辑（指数退避）
 *   - 手动关闭
 *
 * 测试策略：
 *   - 解析测试：Mock fetch 返回「永不完成」的 ReadableStream（悬空），
 *     断言 onEvent 被正确调用后手动 close()
 *   - 重连测试：使用 real timers + 短延迟
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { connectSSE } from '@/utils/sse'

// ===== 辅助函数 =====

const encoder = new TextEncoder()

/**
 * 构造一个「永不完成」的 ReadableStream，用于解析测试。
 * 推送完 chunks 后悬空（不 done），避免触发 scheduleReconnect。
 */
function makeHangingStream(chunks) {
  let index = 0
  return {
    getReader() {
      return {
        async read() {
          if (index >= chunks.length) {
            // 悬空：永不 resolve，模拟 SSE 长连接
            return new Promise(() => {})
          }
          const value = encoder.encode(chunks[index])
          index++
          return { done: false, value }
        },
        cancel: vi.fn().mockResolvedValue(),
      }
    },
  }
}

function mockFetchHanging(chunks, status = 200) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    body: makeHangingStream(chunks),
  })
}

/**
 * 等待微任务队列清空 + 额外延迟，确保 ReadableStream reader 的 read() 被处理
 */
async function flushPromises(ms = 50) {
  for (let i = 0; i < 3; i++) {
    await new Promise((r) => setTimeout(r, 0))
  }
  await new Promise((r) => setTimeout(r, ms))
}

// ===== 解析测试 =====

describe('connectSSE — SSE 事件解析', () => {
  beforeEach(() => {
    localStorage.setItem('access_token', 'test-token')
  })

  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('解析单行 event + data 帧', async () => {
    const onEvent = vi.fn()
    const onStatusChange = vi.fn()
    global.fetch = mockFetchHanging([
      'event: task.created\ndata: {"task_id":"abc-123","status":"running"}\n\n',
    ])

    const conn = connectSSE('/api/research/abc-123/stream', { onEvent, onStatusChange })
    await flushPromises(100)
    conn.close()

    expect(onEvent).toHaveBeenCalledWith('task.created', {
      task_id: 'abc-123',
      status: 'running',
    })
  })

  it('跳过注释帧（心跳 : ping）', async () => {
    const onEvent = vi.fn()
    const onStatusChange = vi.fn()
    global.fetch = mockFetchHanging([
      ': ping\n\n',
      ': heartbeat\n\n',
      'event: phase.started\ndata: {"phase":"planning"}\n\n',
    ])

    const conn = connectSSE('/api/research/abc-123/stream', { onEvent, onStatusChange })
    await flushPromises(100)
    conn.close()

    expect(onEvent).toHaveBeenCalledTimes(1)
    expect(onEvent).toHaveBeenCalledWith('phase.started', { phase: 'planning' })
  })

  it('纯注释帧无有效事件_onEvent不被调用', async () => {
    const onEvent = vi.fn()
    const onStatusChange = vi.fn()
    global.fetch = mockFetchHanging([
      ': heartbeat\n\n',
      ': another comment\n\n',
    ])

    const conn = connectSSE('/api/research/abc-123/stream', { onEvent, onStatusChange })
    await flushPromises(100)
    conn.close()

    expect(onEvent).not.toHaveBeenCalled()
  })

  it('多行 data 拼接为一个 JSON 对象', async () => {
    const onEvent = vi.fn()
    const onStatusChange = vi.fn()
    global.fetch = mockFetchHanging([
      'event: task.status.snapshot\ndata: {"task_id":"t1"\ndata: ,"status":"running"}\n\n',
    ])

    const conn = connectSSE('/api/research/abc-123/stream', { onEvent, onStatusChange })
    await flushPromises(100)
    conn.close()

    expect(onEvent).toHaveBeenCalledWith('task.status.snapshot', {
      task_id: 't1',
      status: 'running',
    })
  })

  it('不完整 frame 保留到 buffer_跨 chunk 解析', async () => {
    const onEvent = vi.fn()
    const onStatusChange = vi.fn()
    global.fetch = mockFetchHanging([
      'event: step.started\ndata: {"step_id"',
      ': "s1","step_type":"planning"}\n\n',
    ])

    const conn = connectSSE('/api/research/abc-123/stream', { onEvent, onStatusChange })
    await flushPromises(100)
    conn.close()

    expect(onEvent).toHaveBeenCalledWith('step.started', {
      step_id: 's1',
      step_type: 'planning',
    })
  })

  it('JSON 解析失败_跳过帧并触发 onError', async () => {
    const onEvent = vi.fn()
    const onStatusChange = vi.fn()
    const onError = vi.fn()
    global.fetch = mockFetchHanging([
      'event: task.progress\ndata: {invalid json\n\n',
    ])

    const conn = connectSSE('/api/research/abc-123/stream', {
      onEvent,
      onStatusChange,
      onError,
    })
    await flushPromises(100)
    conn.close()

    expect(onEvent).not.toHaveBeenCalled()
    expect(onError).toHaveBeenCalledTimes(1)
    expect(onError.mock.calls[0][0].message).toContain('SSE 数据解析失败')
  })

  it('event 无空格前缀（event:xxx）也解析', async () => {
    const onEvent = vi.fn()
    const onStatusChange = vi.fn()
    global.fetch = mockFetchHanging([
      'event:task.completed\ndata: {"status":"completed"}\n\n',
    ])

    const conn = connectSSE('/api/research/abc-123/stream', { onEvent, onStatusChange })
    await flushPromises(100)
    conn.close()

    expect(onEvent).toHaveBeenCalledWith('task.completed', { status: 'completed' })
  })

  it('data 无空格前缀（data:xxx）也解析', async () => {
    const onEvent = vi.fn()
    const onStatusChange = vi.fn()
    global.fetch = mockFetchHanging([
      'event:task.completed\ndata:{"ok":true}\n\n',
    ])

    const conn = connectSSE('/api/research/abc-123/stream', { onEvent, onStatusChange })
    await flushPromises(100)
    conn.close()

    expect(onEvent).toHaveBeenCalledWith('task.completed', { ok: true })
  })

  it('空帧被跳过', async () => {
    const onEvent = vi.fn()
    const onStatusChange = vi.fn()
    global.fetch = mockFetchHanging([
      '\n\n',
      'event: task.completed\ndata: {"ok":true}\n\n',
    ])

    const conn = connectSSE('/api/research/abc-123/stream', { onEvent, onStatusChange })
    await flushPromises(100)
    conn.close()

    expect(onEvent).toHaveBeenCalledTimes(1)
    expect(onEvent).toHaveBeenCalledWith('task.completed', { ok: true })
  })

  it('全 14 种事件类型名正确传递', async () => {
    const allEvents = [
      'task.created',
      'task.status.snapshot',
      'phase.started',
      'phase.completed',
      'step.started',
      'step.progress',
      'step.completed',
      'step.failed',
      'step.skipped',
      'task.progress',
      'checkpoint.saved',
      'task.warning',
      'task.completed',
      'task.failed',
    ]
    const onEvent = vi.fn()
    const onStatusChange = vi.fn()

    const frames = allEvents.map((evt) => `event: ${evt}\ndata: {"_event":"${evt}"}\n\n`)
    global.fetch = mockFetchHanging(frames)

    const conn = connectSSE('/api/research/abc-123/stream', { onEvent, onStatusChange })
    await flushPromises(200)
    conn.close()

    expect(onEvent).toHaveBeenCalledTimes(allEvents.length)
    const receivedEvents = onEvent.mock.calls.map((c) => c[0])
    expect(receivedEvents).toEqual(allEvents)
  })
})

// ===== 连接状态机 =====

describe('connectSSE — 连接状态机', () => {
  beforeEach(() => {
    localStorage.setItem('access_token', 'test-token')
  })

  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('首次连接_经历 connecting → connected', async () => {
    vi.useFakeTimers()
    const onEvent = vi.fn()
    const onStatusChange = vi.fn()
    global.fetch = mockFetchHanging([])

    const conn = connectSSE('/api/research/abc-123/stream', { onEvent, onStatusChange })
    // 让初始 connect() 的微任务执行
    await vi.advanceTimersByTimeAsync(0)

    const statuses = onStatusChange.mock.calls.map((c) => c[0])
    expect(statuses[0]).toBe('connecting')
    expect(statuses).toContain('connected')

    conn.close()
    vi.useRealTimers()
  })

  it('手动 close_状态变为 disconnected', async () => {
    vi.useFakeTimers()
    const onEvent = vi.fn()
    const onStatusChange = vi.fn()
    global.fetch = mockFetchHanging([])

    const conn = connectSSE('/api/research/abc-123/stream', { onEvent, onStatusChange })
    await vi.advanceTimersByTimeAsync(0)
    conn.close()

    const statuses = onStatusChange.mock.calls.map((c) => c[0])
    expect(statuses).toContain('disconnected')

    vi.useRealTimers()
  })

  it('无 access_token 时请求头不含 Authorization', () => {
    vi.useFakeTimers()
    localStorage.removeItem('access_token')
    const onEvent = vi.fn()
    const onStatusChange = vi.fn()
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      body: makeHangingStream([]),
    })
    global.fetch = fetchSpy

    const conn = connectSSE('/api/research/abc-123/stream', { onEvent, onStatusChange })
    const headers = fetchSpy.mock.calls[0][1].headers
    expect(headers['Authorization']).toBeUndefined()

    conn.close()
    vi.useRealTimers()
  })

  it('有 access_token 时携带 Authorization 头', () => {
    vi.useFakeTimers()
    const onEvent = vi.fn()
    const onStatusChange = vi.fn()
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      body: makeHangingStream([]),
    })
    global.fetch = fetchSpy

    const conn = connectSSE('/api/research/abc-123/stream', { onEvent, onStatusChange })
    const headers = fetchSpy.mock.calls[0][1].headers
    expect(headers['Authorization']).toBe('Bearer test-token')

    conn.close()
    vi.useRealTimers()
  })
})

// ===== 重连逻辑 =====

describe('connectSSE — 重连逻辑', () => {
  beforeEach(() => {
    localStorage.setItem('access_token', 'test-token')
  })

  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('HTTP 错误后触发 reconnecting 状态', async () => {
    vi.useFakeTimers()
    const onEvent = vi.fn()
    const onStatusChange = vi.fn()
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      body: makeHangingStream([]),
    })

    const conn = connectSSE('/api/research/abc-123/stream', {
      onEvent,
      onStatusChange,
      maxRetries: 2,
      retryDelay: 1000,
    })
    await vi.advanceTimersByTimeAsync(0)

    // 初始连接失败 → scheduleReconnect → setTimeout 1000ms
    // 推进 1000ms 让第一次重连触发
    await vi.advanceTimersByTimeAsync(1000)

    const statuses = onStatusChange.mock.calls.map((c) => c[0])
    expect(statuses).toContain('reconnecting')

    conn.close()
    vi.useRealTimers()
  })

  it('close 后不再重连', async () => {
    vi.useFakeTimers()
    const onEvent = vi.fn()
    const onStatusChange = vi.fn()
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      body: makeHangingStream([]),
    })

    const conn = connectSSE('/api/research/abc-123/stream', {
      onEvent,
      onStatusChange,
      maxRetries: 3,
      retryDelay: 1000,
    })
    // close 在首次连接失败发出 reconnecting 后尽快调用
    await vi.advanceTimersByTimeAsync(0)

    // 首次失败 → reconnecting（已发出），随后 close → disconnected
    conn.close()

    // 推进时间确认不会再有新的 connect 调用（重连已被 close 阻止）
    // scheduleReconnect 中的 setTimeout 在 conn.close() 后触发，
    // 但由于 shouldReconnect=false，不会再创建新的 setTimeout
    await vi.advanceTimersByTimeAsync(5000)

    // 最终状态为 disconnected（close 触发）
    const statuses = onStatusChange.mock.calls.map((c) => c[0])
    // 最终的 disconnected（由 close 触发）
    expect(statuses[statuses.length - 1]).toBe('disconnected')

    vi.useRealTimers()
  })

  it('重连耗尽后进入 error 态', async () => {
    vi.useFakeTimers()
    const onEvent = vi.fn()
    const onStatusChange = vi.fn()
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      body: makeHangingStream([]),
    })

    const conn = connectSSE('/api/research/abc-123/stream', {
      onEvent,
      onStatusChange,
      maxRetries: 1,
      retryDelay: 100,
    })
    await vi.advanceTimersByTimeAsync(0)
    // 第一次 setTimeout 100ms → 重连失败 → 第 2 次 200ms
    await vi.advanceTimersByTimeAsync(500)

    const statuses = onStatusChange.mock.calls.map((c) => c[0])
    expect(statuses).toContain('error')

    conn.close()
    vi.useRealTimers()
  })

  it('重连成功后状态恢复 connected', async () => {
    vi.useFakeTimers()
    const onEvent = vi.fn()
    const onStatusChange = vi.fn()

    let callCount = 0
    global.fetch = vi.fn().mockImplementation(() => {
      callCount++
      if (callCount <= 1) {
        // 第一次失败
        return Promise.resolve({
          ok: false,
          status: 500,
          body: makeHangingStream([]),
        })
      }
      // 第二次成功（悬空流）
      return Promise.resolve({
        ok: true,
        body: makeHangingStream([]),
      })
    })

    const conn = connectSSE('/api/research/abc-123/stream', {
      onEvent,
      onStatusChange,
      maxRetries: 3,
      retryDelay: 100,
    })
    await vi.advanceTimersByTimeAsync(0)
    // 触发重连
    await vi.advanceTimersByTimeAsync(300)

    const statuses = onStatusChange.mock.calls.map((c) => c[0])
    expect(statuses).toContain('connected')

    conn.close()
    vi.useRealTimers()
  })
})
