/**
 * TaskStore 单元测试 — 覆盖 src/stores/task.js
 *
 * 对齐 ROADMAP.md §3.9：
 *   - create() → current 更新 → SSE 自动连接
 *   - fetchList() 分页
 *   - cancel() → SSE 断开
 *   - sseStatus 5 态流转
 *   - deleteTask() 本地移除 + 空页回退
 *   - fetchDetail() 设置 current
 *   - handleSSEEvent 各事件类型处理
 *
 * Mock 策略：在 API 边界截断（@/api/research + @/utils/sse），
 * Store 核心逻辑真实运行。
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useTaskStore } from '@/stores/task'
import * as researchApi from '@/api/research'

// Mock API 模块
vi.mock('@/api/research', () => ({
  createTask: vi.fn(),
  getTaskList: vi.fn(),
  getTaskDetail: vi.fn(),
  deleteTask: vi.fn(),
  cancelTask: vi.fn(),
  getTaskState: vi.fn(),
}))

// Mock SSE 模块
vi.mock('@/utils/sse', () => ({
  connectSSE: vi.fn(() => ({ close: vi.fn() })),
}))

import { connectSSE } from '@/utils/sse'

// ===== 辅助函数 =====

function mockApiResponse(data) {
  return { data: { data } }
}

describe('TaskStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  // ===== createTask =====

  describe('createTask', () => {
    it('创建成功_current 包含 task_id 和 topic', async () => {
      researchApi.createTask.mockResolvedValue(
        mockApiResponse({ task_id: 'task-001', status: 'pending', created_at: '2026-06-24T10:00:00Z' })
      )

      const store = useTaskStore()
      const result = await store.createTask('量子计算的影响', {
        task_type: 'analysis',
        depth: 'quick',
        max_sources: 10,
        language: 'zh',
      })

      expect(result.task_id).toBe('task-001')
      expect(store.current.task_id).toBe('task-001')
      expect(store.current.topic).toBe('量子计算的影响')
      expect(store.current.status).toBe('pending')
      expect(store.current.requirements.task_type).toBe('analysis')
    })

    it('创建后 sseStatus 重置为 disconnected', async () => {
      researchApi.createTask.mockResolvedValue(
        mockApiResponse({ task_id: 'task-002', status: 'pending', created_at: '2026-06-24T10:00:00Z' })
      )

      const store = useTaskStore()
      store.sseStatus = 'connected'
      await store.createTask('测试主题', {
        task_type: 'explainer',
        depth: 'quick',
        max_sources: 5,
        language: 'en',
      })

      expect(store.sseStatus).toBe('disconnected')
    })

    it('创建失败_API 异常抛出_loading 恢复', async () => {
      researchApi.createTask.mockRejectedValue(new Error('网络错误'))

      const store = useTaskStore()
      await expect(
        store.createTask('测试', { task_type: 'comparison', depth: 'quick', max_sources: 10, language: 'zh' })
      ).rejects.toBeDefined()

      expect(store.loading).toBe(false)
    })
  })

  // ===== fetchList =====

  describe('fetchList', () => {
    it('获取列表成功_taskList 和 total 正确赋值', async () => {
      researchApi.getTaskList.mockResolvedValue(
        mockApiResponse({
          items: [
            { task_id: 't1', topic: '主题A', status: 'completed' },
            { task_id: 't2', topic: '主题B', status: 'running' },
          ],
          total: 2,
          page: 1,
          page_size: 20,
        })
      )

      const store = useTaskStore()
      await store.fetchList({ page: 1, page_size: 20 })

      expect(store.taskList).toHaveLength(2)
      expect(store.taskList[0].task_id).toBe('t1')
      expect(store.total).toBe(2)
      expect(store.currentPage).toBe(1)
    })

    it('空列表_taskList 为空数组_total 为 0', async () => {
      researchApi.getTaskList.mockResolvedValue(
        mockApiResponse({ items: [], total: 0, page: 1, page_size: 20 })
      )

      const store = useTaskStore()
      await store.fetchList()

      expect(store.taskList).toEqual([])
      expect(store.total).toBe(0)
    })

    it('status 筛选参数正确传递', async () => {
      researchApi.getTaskList.mockResolvedValue(
        mockApiResponse({ items: [], total: 0, page: 1, page_size: 20 })
      )

      const store = useTaskStore()
      await store.fetchList({ status: 'completed' })

      expect(researchApi.getTaskList).toHaveBeenCalledWith({
        page: 1,
        page_size: 20,
        status: 'completed',
      })
    })

    it('第二页数据正确加载', async () => {
      researchApi.getTaskList.mockResolvedValue(
        mockApiResponse({
          items: [{ task_id: 't3', topic: '第三页主题', status: 'failed' }],
          total: 45,
          page: 3,
          page_size: 20,
        })
      )

      const store = useTaskStore()
      await store.fetchList({ page: 3, page_size: 20 })

      expect(store.currentPage).toBe(3)
      expect(store.total).toBe(45)
    })
  })

  // ===== fetchDetail =====

  describe('fetchDetail', () => {
    it('获取详情成功_current 包含完整字段', async () => {
      researchApi.getTaskDetail.mockResolvedValue(
        mockApiResponse({
          task_id: 'task-detail-1',
          topic: '深度学习研究',
          status: 'running',
          current_phase: 'search',
          requirements: { task_type: 'explainer', depth: 'quick', max_sources: 10, language: 'zh' },
          progress: { completed_steps: 3, total_steps: 10, progress: 30 },
          total_sources: 5,
          total_evidence: 2,
          error_code: null,
          error_message: null,
          recoverable: false,
          created_at: '2026-06-24T08:00:00Z',
          started_at: '2026-06-24T08:00:05Z',
          completed_at: null,
        })
      )

      const store = useTaskStore()
      const data = await store.fetchDetail('task-detail-1')

      expect(store.current.task_id).toBe('task-detail-1')
      expect(store.current.current_phase).toBe('search')
      expect(store.current.progress.progress).toBe(30)
      expect(data.status).toBe('running')
    })

    it('不存在的任务_API 异常抛出', async () => {
      researchApi.getTaskDetail.mockRejectedValue({
        response: { status: 404, data: { code: 'E2001' } },
      })

      const store = useTaskStore()
      await expect(store.fetchDetail('non-existent')).rejects.toBeDefined()
    })
  })

  // ===== deleteTask =====

  describe('deleteTask', () => {
    it('删除成功_本地 taskList 移除_target total 减 1', async () => {
      researchApi.deleteTask.mockResolvedValue({})

      const store = useTaskStore()
      store.taskList = [
        { task_id: 't1', topic: 'A' },
        { task_id: 't2', topic: 'B' },
        { task_id: 't3', topic: 'C' },
      ]
      store.total = 3

      await store.deleteTask('t2')

      expect(store.taskList).toHaveLength(2)
      expect(store.taskList.map((t) => t.task_id)).toEqual(['t1', 't3'])
      expect(store.total).toBe(2)
    })

    it('删除的是当前查看的任务_清空 current', async () => {
      researchApi.deleteTask.mockResolvedValue({})

      const store = useTaskStore()
      store.current = { task_id: 't1', topic: 'A', status: 'completed' }
      store.taskList = [{ task_id: 't1', topic: 'A' }]
      store.total = 1

      await store.deleteTask('t1')

      expect(store.current).toBeNull()
    })

    it('删除的不是当前任务_current 保持不变', async () => {
      researchApi.deleteTask.mockResolvedValue({})

      const store = useTaskStore()
      store.current = { task_id: 't1', topic: 'A', status: 'completed' }
      store.taskList = [
        { task_id: 't1', topic: 'A' },
        { task_id: 't2', topic: 'B' },
      ]
      store.total = 2

      await store.deleteTask('t2')

      expect(store.current).not.toBeNull()
      expect(store.current.task_id).toBe('t1')
    })
  })

  // ===== cancelTask =====

  describe('cancelTask', () => {
    it('取消成功_断开 SSE_更新 current.status 为 canceled', async () => {
      researchApi.cancelTask.mockResolvedValue({})

      const store = useTaskStore()
      store.current = { task_id: 't1', topic: 'A', status: 'running' }
      store.sseStatus = 'connected'
      store.sseConnection = { close: vi.fn() }

      await store.cancelTask('t1')

      expect(store.sseStatus).toBe('disconnected')
      expect(store.current.status).toBe('canceled')
      expect(researchApi.cancelTask).toHaveBeenCalledWith('t1')
    })

    it('取消非当前任务_不更新 current', async () => {
      researchApi.cancelTask.mockResolvedValue({})

      const store = useTaskStore()
      store.current = { task_id: 't1', topic: 'A', status: 'running' }

      await store.cancelTask('t2')

      expect(store.current.status).toBe('running')
    })
  })

  // ===== connectSSE / disconnectSSE =====

  describe('connectSSE / disconnectSSE — SSE 连接管理', () => {
    it('connectSSE 设置 sseStatus 为 connecting_然后 connected', async () => {
      connectSSE.mockImplementation((url, opts) => {
        opts.onStatusChange('connecting')
        opts.onStatusChange('connected')
        return { close: vi.fn() }
      })

      const store = useTaskStore()
      await store.connectSSE('task-001')

      expect(store.sseStatus).toBe('connected')
      expect(connectSSE).toHaveBeenCalled()
      expect(store.sseConnection).not.toBeNull()
    })

    it('disconnectSSE 关闭连接_设置 disconnected', () => {
      const closeFn = vi.fn()
      const store = useTaskStore()
      store.sseConnection = { close: closeFn }
      store.sseStatus = 'connected'

      store.disconnectSSE()

      expect(closeFn).toHaveBeenCalled()
      expect(store.sseStatus).toBe('disconnected')
      expect(store.sseConnection).toBeNull()
    })

    it('重复 disconnectSSE 不报错', () => {
      const store = useTaskStore()
      store.disconnectSSE()
      store.disconnectSSE()
      expect(store.sseStatus).toBe('disconnected')
    })

    it('clearCurrent 断开 SSE 并清空 current', () => {
      const store = useTaskStore()
      store.current = { task_id: 't1', topic: 'A', status: 'completed' }
      store.sseConnection = { close: vi.fn() }
      store.sseStatus = 'connected'

      store.clearCurrent()

      expect(store.current).toBeNull()
      expect(store.sseStatus).toBe('disconnected')
      expect(store.progress.progress).toBe(0)
    })
  })

  // ===== handleSSEEvent =====

  describe('handleSSEEvent — SSE 事件处理', () => {
    function makeStore() {
      const store = useTaskStore()
      store.current = { task_id: 'task-001', topic: '测试', status: 'running' }
      return store
    }

    it('task.created 更新 current.status 为 running', () => {
      const store = makeStore()
      store.handleSSEEvent('task.created', { task_id: 'task-001', status: 'running' })
      expect(store.current.status).toBe('running')
    })

    it('task.created 不同 task_id_不更新', () => {
      const store = makeStore()
      store.current.status = 'pending'
      store.handleSSEEvent('task.created', { task_id: 'other-task', status: 'running' })
      expect(store.current.status).toBe('pending')
    })

    it('task.status.snapshot 恢复完整进度', () => {
      const store = makeStore()
      store.handleSSEEvent('task.status.snapshot', {
        status: 'running',
        current_phase: 'search',
        progress: { completed_steps: 5, total_steps: 20, progress: 25 },
        stats: { total_sources: 8, total_evidence: 3 },
      })

      expect(store.current.current_phase).toBe('search')
      expect(store.progress.completed_steps).toBe(5)
      expect(store.progress.total_steps).toBe(20)
      expect(store.current.total_sources).toBe(8)
      expect(store.current.total_evidence).toBe(3)
    })

    it('phase.started 更新 current.current_phase', () => {
      const store = makeStore()
      store.handleSSEEvent('phase.started', { phase: 'planning' })
      expect(store.current.current_phase).toBe('planning')
    })

    it('task.progress 更新进度', () => {
      const store = makeStore()
      store.handleSSEEvent('task.progress', { completed_steps: 3, total_steps: 10, progress: 30 })
      expect(store.progress.completed_steps).toBe(3)
      expect(store.progress.progress).toBe(30)
    })

    it('task.completed 设置状态并断开 SSE', () => {
      const store = makeStore()
      store.handleSSEEvent('task.completed', {
        trace: { sources: 12, evidence: 5 },
      })
      expect(store.current.status).toBe('completed')
      expect(store.sseStatus).toBe('disconnected')
    })

    it('task.failed 设置错误信息并断开 SSE', () => {
      const store = makeStore()
      store.handleSSEEvent('task.failed', {
        error_type: 'E3101',
        error_description: 'Planning 失败：无法拆解主题',
        recoverable: true,
      })
      expect(store.current.status).toBe('failed')
      expect(store.current.error_code).toBe('E3101')
      expect(store.current.error_message).toContain('Planning 失败')
      expect(store.current.recoverable).toBe(true)
      expect(store.sseStatus).toBe('disconnected')
    })

    it('task.canceled 设置状态并断开 SSE', () => {
      const store = makeStore()
      store.handleSSEEvent('task.canceled', {})
      expect(store.current.status).toBe('canceled')
      expect(store.sseStatus).toBe('disconnected')
    })

    it('未知事件类型_不影响 current', () => {
      const store = makeStore()
      store.handleSSEEvent('unknown.event', { data: 'test' })
      expect(store.current.status).toBe('running')
    })
  })
})
