import { describe, expect, it } from 'vitest'

import { createResearchSseParser } from '@/features/research/researchSseParser'

function stateFixture() {
  return {
    task_id: '11111111-2222-4333-8444-555555555555',
    topic: '全球 AI Agent 竞争格局',
    status: 'running',
    current_phase: 'synthesizing',
    progress: { completed_steps: 4, total_steps: 7, progress: 0.57 },
    steps: [
      {
        id: 's1',
        step_type: 'planning',
        status: 'completed',
        label: '研究计划',
        started_at: '2026-08-12T06:00:00Z',
        completed_at: '2026-08-12T06:00:30Z',
        sub_questions_count: 3,
        after_dedup: null,
        sources_created: null,
        successful: null,
        failed: null,
        error_code: null,
        error_message: null,
        duration_ms: 30000,
        progress_label: null,
      },
    ],
    error: null,
    stats: { total_sources: 12, total_evidence: 34 },
    report_id: null,
    created_at: '2026-08-12T06:00:00Z',
    started_at: '2026-08-12T06:00:01Z',
    completed_at: null,
  }
}

describe('Research canonical SSE 解析器', () => {
  it('解析完整 canonical 事件流并保留事件 id', () => {
    const parser = createResearchSseParser()
    const events = parser(
      [
        'event: task.updated',
        'data: {"task_id":"t-1","status":"running","current_phase":"searching","completed_steps":2,"total_steps":7,"progress":0.3}',
        '',
        'event: phase.updated',
        'data: {"phase":"searching","timestamp":"2026-08-12T06:01:00Z","duration_ms":45000}',
        '',
        'event: step.updated',
        'data: {"step_id":"s2","step_type":"search","status":"running","label":"来源检索","timestamp":"2026-08-12T06:01:00Z","phase":"searching","last_completed_step_id":"s1","observation":"正在检索内部知识库"}',
        '',
        'event: snapshot',
        `data: ${JSON.stringify(stateFixture())}`,
        '',
        'event: task.canceled',
        'data: {"task_id":"t-1","status":"running","cancel_requested":true}',
        '',
        'event: stream.end',
        'data: {"reason":"subscription_ended"}',
        '',
        '',
      ].join('\n'),
    )

    expect(events.map((e) => e.type)).toEqual([
      'task.updated',
      'phase.updated',
      'step.updated',
      'snapshot',
      'task.canceled',
      'stream.end',
    ])
    const taskUpdated = events.find((e) => e.type === 'task.updated')
    expect(taskUpdated?.data).toMatchObject({
      task_id: 't-1',
      status: 'running',
      completed_steps: 2,
      total_steps: 7,
      progress: 0.3,
    })
    const snapshot = events.find((e) => e.type === 'snapshot')
    expect(snapshot?.data).toMatchObject({
      status: 'running',
      current_phase: 'synthesizing',
      progress: { completed_steps: 4, total_steps: 7, progress: 0.57 },
      stats: { total_sources: 12, total_evidence: 34 },
    })
  })

  it('解析 error 事件（含 retryable）与 stream.end 的 reason', () => {
    const parser = createResearchSseParser()
    const events = parser(
      [
        'event: error',
        'data: {"error_code":"SYSTEM_UNAVAILABLE","message":"研究服务暂时不可用","retryable":true}',
        '',
        'event: stream.end',
        'data: {"reason":"terminal_snapshot"}',
        '',
        '',
      ].join('\n'),
    )

    expect(events).toEqual([
      {
        type: 'error',
        id: null,
        data: { error_code: 'SYSTEM_UNAVAILABLE', message: '研究服务暂时不可用', retryable: true },
      },
      { type: 'stream.end', id: null, data: { reason: 'terminal_snapshot' } },
    ])
  })

  it('增量式：单事件被网络分帧拆到多个 chunk 也能完整解析', () => {
    const parser = createResearchSseParser()
    const first = parser('event: task.upd')
    expect(first).toEqual([])
    const second = parser(['ated', 'data: {"task_id":"t-1","status":"running"}', '', ''].join('\n'))
    expect(second).toHaveLength(1)
    expect(second[0]).toMatchObject({ type: 'task.updated', data: { task_id: 't-1' } })
  })

  it('心跳注释帧与未知事件被容错忽略，不阻断后续事件', () => {
    const parser = createResearchSseParser()
    const events = parser(
      [
        ': ping',
        '',
        'event: unknown.event',
        'data: {"foo":1}',
        '',
        'event: task.updated',
        'data: {"task_id":"t-1","status":"running"}',
        '',
        '',
      ].join('\n'),
    )

    expect(events).toHaveLength(1)
    expect(events[0].type).toBe('task.updated')
  })

  it('data 非 JSON 或非对象的帧被忽略', () => {
    const parser = createResearchSseParser()
    const events = parser(
      [
        'event: task.updated',
        'data: not-json',
        '',
        'event: phase.updated',
        'data: 42',
        '',
        'event: step.updated',
        'data: {"step_id":"s1"}',
        '',
        '',
      ].join('\n'),
    )

    expect(events).toHaveLength(1)
    expect(events[0].type).toBe('step.updated')
  })

  it('已知字段做安全归一化：缺失/类型不符回退默认值，未知字段保留容错', () => {
    const parser = createResearchSseParser()
    const events = parser(
      [
        'event: task.updated',
        'data: {"status":123,"completed_steps":"5","progress":"0.5","extra_field":"survives"}',
        '',
        'event: phase.updated',
        'data: {"phase":"searching","duration_ms":"999"}',
        '',
        '',
      ].join('\n'),
    )

    expect(events[0].data).toMatchObject({
      status: '123',
      completed_steps: 5,
      progress: 0.5,
    })
    expect(events[1].data).toMatchObject({ phase: 'searching', duration_ms: 999 })
  })
})
