import { describe, expect, it } from 'vitest'

import type { ResearchTaskState } from '@/api/research'
import {
  initialResearchSseSnapshot,
  researchSseReducer,
  type ResearchSseAction,
} from '@/features/research/researchSseMachine'

function stateFixture(overrides: Partial<ResearchTaskState> = {}): ResearchTaskState {
  return {
    task_id: '11111111-2222-4333-8444-555555555555',
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

function step(action: ResearchSseAction, snapshot = initialResearchSseSnapshot) {
  return researchSseReducer(snapshot, action)
}

describe('Research SSE 状态机（FRONTEND §8）', () => {
  it('LoadingSnapshot → snapshotLoaded(订阅) → 首个 snapshot 事件 → Live', () => {
    const s1 = step({ type: 'snapshotLoaded', state: stateFixture() })
    expect(s1.phase).toBe('subscribing')
    expect(s1.task?.status).toBe('running')

    const s2 = step({ type: 'sse', event: { type: 'snapshot', id: 5, data: stateFixture() } }, s1)
    expect(s2.phase).toBe('live')
    expect(s2.lastEventId).toBe(5)
    expect(s2.task?.progress.progress).toBe(0.57)
  })

  it('snapshot 携带终态状态时直接进入 Terminal（终态以快照为准）', () => {
    const s = step({ type: 'snapshotLoaded', state: stateFixture({ status: 'completed' }) })
    expect(s.phase).toBe('terminal')
  })

  it('task.updated 合并状态与进度；不进入 Live 前的增量不会伪造阶段', () => {
    const s1 = step({ type: 'snapshotLoaded', state: stateFixture() })
    const s2 = step(
      {
        type: 'sse',
        event: {
          type: 'task.updated',
          id: 6,
          data: {
            task_id: 't-1',
            status: 'running',
            current_phase: 'searching',
            completed_steps: 5,
            total_steps: 7,
            progress: 0.71,
            message: null,
            error_code: null,
            error_message: null,
          },
        },
      },
      s1,
    )
    expect(s2.phase).toBe('live')
    expect(s2.task?.current_phase).toBe('searching')
    expect(s2.task?.progress).toMatchObject({ completed_steps: 5, total_steps: 7, progress: 0.71 })
    expect(s2.lastEventId).toBe(6)
  })

  it('task.updated 合并出终态状态时进入 Terminal', () => {
    const s1 = step({ type: 'snapshotLoaded', state: stateFixture() })
    const s2 = step(
      {
        type: 'sse',
        event: {
          type: 'task.updated',
          id: 7,
          data: {
            task_id: 't-1',
            status: 'failed',
            current_phase: null,
            completed_steps: null,
            total_steps: null,
            progress: null,
            message: null,
            error_code: 'RS_TASK_CONCURRENCY_LIMIT',
            error_message: '任务失败',
            completed_at: '2026-08-12T06:00:08Z',
            recoverable: false,
          },
        },
      },
      s1,
    )
    expect(s2.phase).toBe('terminal')
    expect(s2.task?.status).toBe('failed')
    expect(s2.task?.completed_at).toBe('2026-08-12T06:00:08Z')
    expect(s2.task?.error).toEqual({
      error_code: 'RS_TASK_CONCURRENCY_LIMIT',
      error_message: '任务失败',
      recoverable: false,
    })
  })

  it('phase.updated 更新当前阶段并追加安全摘要到时间线', () => {
    const s1 = step({ type: 'snapshotLoaded', state: stateFixture() })
    const s2 = step(
      {
        type: 'sse',
        event: {
          type: 'phase.updated',
          id: 8,
          data: { phase: 'searching', timestamp: '2026-08-12T06:01:00Z', duration_ms: 45000 },
        },
      },
      s1,
    )
    expect(s2.task?.current_phase).toBe('searching')
    expect(s2.timeline).toHaveLength(1)
    expect(s2.timeline[0]).toMatchObject({ eventId: 8, kind: 'phase' })
  })

  it('step.updated 更新步骤并追加时间线；重复事件 id 不重复入列（幂等）', () => {
    const s1 = step({ type: 'snapshotLoaded', state: stateFixture() })
    const event = {
      type: 'sse' as const,
      event: {
        type: 'step.updated' as const,
        id: 9,
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
      },
    }
    const s2 = step(event, s1)
    expect(s2.task?.steps).toHaveLength(1)
    expect(s2.task?.steps[0]).toMatchObject({ id: 's2', status: 'running', label: '来源检索' })
    const s3 = step(event, s2)
    expect(s3.timeline).toHaveLength(1)
    expect(s3.task?.steps).toHaveLength(1)
  })

  it('task.canceled 只记录取消请求，不改变任务状态（取消是请求不是终态）', () => {
    const s1 = step({ type: 'snapshotLoaded', state: stateFixture() })
    const s2 = step(
      {
        type: 'sse',
        event: {
          type: 'task.canceled',
          id: 10,
          data: { task_id: 't-1', status: 'running', cancel_requested: true },
        },
      },
      s1,
    )
    expect(s2.cancelRequested).toBe(true)
    expect(s2.phase).toBe('live')
    expect(s2.task?.status).toBe('running')
  })

  it('stream.end ≠ 成功：非终态任务进入 subscriptionEnded，终态任务进入 Terminal', () => {
    const live = step({ type: 'snapshotLoaded', state: stateFixture() })
    const ended = step(
      {
        type: 'sse',
        event: { type: 'stream.end', id: null, data: { reason: 'subscription_ended' } },
      },
      live,
    )
    expect(ended.phase).toBe('subscriptionEnded')

    const terminalLive = step({
      type: 'snapshotLoaded',
      state: stateFixture({ status: 'completed' }),
    })
    const terminalEnded = step(
      {
        type: 'sse',
        event: { type: 'stream.end', id: null, data: { reason: 'terminal_snapshot' } },
      },
      { ...terminalLive, phase: 'live' },
    )
    expect(terminalEnded.phase).toBe('terminal')
  })

  it('网络断开进入 Reconnecting 且不取消任务、保留本地状态（断开不得取消任务）', () => {
    const live = step({ type: 'snapshotLoaded', state: stateFixture() })
    const reconnected = step({ type: 'disconnected' }, live)
    expect(reconnected.phase).toBe('reconnecting')
    expect(reconnected.task?.status).toBe('running')
    expect(reconnected.cancelRequested).toBe(false)
  })

  it('Reconnecting 收到 snapshot 快照后回到 Live（重连并携带游标收敛）', () => {
    const live = step({ type: 'snapshotLoaded', state: stateFixture() })
    const reconnecting = step({ type: 'disconnected' }, live)
    const recovered = step(
      {
        type: 'sse',
        event: {
          type: 'snapshot',
          id: 11,
          data: stateFixture({ progress: { completed_steps: 6, total_steps: 7, progress: 0.86 } }),
        },
      },
      reconnecting,
    )
    expect(recovered.phase).toBe('live')
    expect(recovered.lastEventId).toBe(11)
    expect(recovered.task?.progress.progress).toBe(0.86)
  })

  it('HTTP 失败：尚无任务事实时保持 loadingSnapshot 并携带错误；已有任务事实时进入 Reconnecting', () => {
    const noTask = step({
      type: 'httpError',
      error: { code: 'NETWORK_ERROR', message: '网络请求失败' },
    })
    expect(noTask.phase).toBe('loadingSnapshot')
    expect(noTask.error?.code).toBe('NETWORK_ERROR')

    const live = step({ type: 'snapshotLoaded', state: stateFixture() })
    const failed = step(
      { type: 'httpError', error: { code: 'SYSTEM_UNAVAILABLE', message: '服务不可用' } },
      live,
    )
    expect(failed.phase).toBe('reconnecting')
    expect(failed.task).not.toBeNull()
  })

  it('error 事件写入错误并追加时间线（stream.end 前可展示安全错误）', () => {
    const s1 = step({ type: 'snapshotLoaded', state: stateFixture() })
    const s2 = step(
      {
        type: 'sse',
        event: {
          type: 'error',
          id: 12,
          data: {
            error_code: 'SYSTEM_UNAVAILABLE',
            message: '研究服务暂时不可用',
            retryable: true,
          },
        },
      },
      s1,
    )
    expect(s2.error?.code).toBe('SYSTEM_UNAVAILABLE')
    expect(s2.timeline.some((item) => item.kind === 'error')).toBe(true)
  })
})
