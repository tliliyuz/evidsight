import { describe, expect, it } from 'vitest'

import {
  chatGenerationReducer,
  initialChatGenerationSnapshot,
} from '@/features/chat/chatGenerationMachine'

function meta(id: string, generationId: string) {
  return {
    type: 'sse' as const,
    event: {
      type: 'meta' as const,
      id: 1,
      data: { conversation_id: id, generation_id: generationId },
    },
  }
}

function delta(text: string) {
  return {
    type: 'sse' as const,
    event: { type: 'message.delta' as const, id: 2, data: { delta: text } },
  }
}

function sources() {
  return {
    type: 'sse' as const,
    event: {
      type: 'sources' as const,
      id: 3,
      data: {
        chunks: [
          {
            chunk_index: 1,
            document_uuid: 'doc-1',
            segment_id: 'seg-1',
            doc_name: '手册',
            score: 0.9,
            page: null,
            section_title: null,
            section_path: null,
            preview_text: null,
            preview_range: null,
            highlight_start: null,
            highlight_end: null,
          },
        ],
      },
    },
  }
}

function done() {
  return {
    type: 'sse' as const,
    event: { type: 'done' as const, id: 4, data: { message_id: 12, title: '标题' } },
  }
}

function errorEvent() {
  return {
    type: 'sse' as const,
    event: {
      type: 'error' as const,
      id: 5,
      data: { error_code: 'CHAT_LLM_UPSTREAM', message: 'LLM 调用失败', retryable: true },
    },
  }
}

describe('Chat SSE 状态机', () => {
  it('发送问题：idle → connecting 并重置上一轮状态', () => {
    let s = initialChatGenerationSnapshot
    s = chatGenerationReducer(s, meta('c1', 'g1'))
    s = chatGenerationReducer(s, delta('部分答案'))
    s = chatGenerationReducer(s, sources())
    s = chatGenerationReducer(s, done())

    const next = chatGenerationReducer(s, { type: 'send' })
    expect(next.phase).toBe('connecting')
    expect(next.text).toBe('')
    expect(next.sources).toBeNull()
    expect(next.generationId).toBeNull()
    expect(next.doneMessageId).toBeNull()
  })

  it('meta 绑定 generation_id 与 conversation_id 并进入 streaming', () => {
    const s = chatGenerationReducer(initialChatGenerationSnapshot, { type: 'send' })
    const next = chatGenerationReducer(s, meta('conv-9', 'gen-9'))
    expect(next.phase).toBe('streaming')
    expect(next.generationId).toBe('gen-9')
    expect(next.conversationId).toBe('conv-9')
  })

  it('delta 在 streaming 累加文本', () => {
    let s = chatGenerationReducer(initialChatGenerationSnapshot, { type: 'send' })
    s = chatGenerationReducer(s, meta('c1', 'g1'))
    s = chatGenerationReducer(s, delta('你'))
    s = chatGenerationReducer(s, delta('好'))
    expect(s.text).toBe('你好')
  })

  it('sources 进入 awaitingSources 并绑定来源，done 后进入唯一成功终态', () => {
    let s = chatGenerationReducer(initialChatGenerationSnapshot, { type: 'send' })
    s = chatGenerationReducer(s, meta('c1', 'g1'))
    s = chatGenerationReducer(s, sources())
    expect(s.phase).toBe('awaitingSources')
    expect(s.sources).not.toBeNull()

    const next = chatGenerationReducer(s, done())
    expect(next.phase).toBe('completed')
    expect(next.doneMessageId).toBe(12)
  })

  it('done 后当轮 sources 按 message_id 绑定到 completedSources（历史回读后来源仍可见）', () => {
    let s = chatGenerationReducer(initialChatGenerationSnapshot, { type: 'send' })
    s = chatGenerationReducer(s, meta('c1', 'g1'))
    s = chatGenerationReducer(s, sources())
    s = chatGenerationReducer(s, done())

    expect(s.completedSources[12]).toEqual({
      sources: expect.arrayContaining([
        expect.objectContaining({ chunk_index: 1, doc_name: '手册' }),
      ]),
      confidence: undefined,
      confidenceNote: undefined,
    })
  })

  it('新一轮 send 保留已完成消息的来源（多轮历史来源卡片持续可见）', () => {
    let s = chatGenerationReducer(initialChatGenerationSnapshot, { type: 'send' })
    s = chatGenerationReducer(s, meta('c1', 'g1'))
    s = chatGenerationReducer(s, sources())
    s = chatGenerationReducer(s, done())
    expect(s.completedSources[12]).toBeDefined()

    const next = chatGenerationReducer(s, { type: 'send' })
    expect(next.completedSources[12]).toBeDefined()
  })

  it('无 sources 的 done 不写入 completedSources', () => {
    let s = chatGenerationReducer(initialChatGenerationSnapshot, { type: 'send' })
    s = chatGenerationReducer(s, meta('c1', 'g1'))
    s = chatGenerationReducer(s, delta('无来源回答'))
    s = chatGenerationReducer(s, done())

    expect(s.completedSources).toEqual({})
  })

  it('done 前不得进入成功终态', () => {
    let s = chatGenerationReducer(initialChatGenerationSnapshot, { type: 'send' })
    s = chatGenerationReducer(s, meta('c1', 'g1'))
    s = chatGenerationReducer(s, delta('只有部分输出'))
    s = chatGenerationReducer(s, sources())
    expect(s.phase).not.toBe('completed')
    // 流直接断开（未收到 done）不得伪装完整答案
    const closed = chatGenerationReducer(s, { type: 'streamClosed', reason: 'disconnect' })
    expect(closed.phase).not.toBe('completed')
    expect(closed.phase).toBe('canceled')
  })

  it('error 进入 failed，且后续 delta 被拒绝', () => {
    let s = chatGenerationReducer(initialChatGenerationSnapshot, { type: 'send' })
    s = chatGenerationReducer(s, meta('c1', 'g1'))
    s = chatGenerationReducer(s, delta('已有文本'))
    s = chatGenerationReducer(s, errorEvent())
    expect(s.phase).toBe('failed')
    expect(s.error?.code).toBe('CHAT_LLM_UPSTREAM')

    const after = chatGenerationReducer(s, delta('不应拼入'))
    expect(after.text).toBe('已有文本')
  })

  it('HTTP 失败进入 failed 并携带错误', () => {
    const s = chatGenerationReducer(initialChatGenerationSnapshot, { type: 'send' })
    const next = chatGenerationReducer(s, {
      type: 'streamClosed',
      reason: 'http-error',
      error: { code: 'E1010', message: '用户被禁用' },
    })
    expect(next.phase).toBe('failed')
    expect(next.error?.code).toBe('E1010')
  })

  it('用户中止：streaming → canceling，连接关闭后 → canceled', () => {
    let s = chatGenerationReducer(initialChatGenerationSnapshot, { type: 'send' })
    s = chatGenerationReducer(s, meta('c1', 'g1'))
    s = chatGenerationReducer(s, delta('部分'))
    s = chatGenerationReducer(s, { type: 'cancelRequested' })
    expect(s.phase).toBe('canceling')

    const next = chatGenerationReducer(s, { type: 'streamClosed', reason: 'cancel' })
    expect(next.phase).toBe('canceled')
  })

  it('取消竞态一：done 已处理后再点击停止，保持 completed', () => {
    let s = chatGenerationReducer(initialChatGenerationSnapshot, { type: 'send' })
    s = chatGenerationReducer(s, meta('c1', 'g1'))
    s = chatGenerationReducer(s, sources())
    s = chatGenerationReducer(s, done())
    expect(s.phase).toBe('completed')

    const after = chatGenerationReducer(s, { type: 'cancelRequested' })
    expect(after.phase).toBe('completed')
  })

  it('取消竞态二：已进入 canceling 后到达的 done 被忽略，最终 canceled', () => {
    let s = chatGenerationReducer(initialChatGenerationSnapshot, { type: 'send' })
    s = chatGenerationReducer(s, meta('c1', 'g1'))
    s = chatGenerationReducer(s, { type: 'cancelRequested' })
    expect(s.phase).toBe('canceling')

    s = chatGenerationReducer(s, done())
    expect(s.phase).toBe('canceling')

    const after = chatGenerationReducer(s, { type: 'streamClosed', reason: 'cancel' })
    expect(after.phase).toBe('canceled')
  })

  it('SSE 意外断开（无 done 无 error）显示已中止（canceled）', () => {
    let s = chatGenerationReducer(initialChatGenerationSnapshot, { type: 'send' })
    s = chatGenerationReducer(s, meta('c1', 'g1'))
    s = chatGenerationReducer(s, delta('输出中断'))
    const next = chatGenerationReducer(s, { type: 'streamClosed', reason: 'disconnect' })
    expect(next.phase).toBe('canceled')
  })

  it('done 后拒绝后续 delta 与 error', () => {
    let s = chatGenerationReducer(initialChatGenerationSnapshot, { type: 'send' })
    s = chatGenerationReducer(s, meta('c1', 'g1'))
    s = chatGenerationReducer(s, sources())
    s = chatGenerationReducer(s, done())

    s = chatGenerationReducer(s, delta('多余的'))
    s = chatGenerationReducer(s, errorEvent())
    expect(s.phase).toBe('completed')
    expect(s.text).toBe('')
  })

  it('failed 后重试：send 回到 connecting 并清空错误', () => {
    let s = chatGenerationReducer(initialChatGenerationSnapshot, { type: 'send' })
    s = chatGenerationReducer(s, meta('c1', 'g1'))
    s = chatGenerationReducer(s, errorEvent())
    expect(s.phase).toBe('failed')

    const next = chatGenerationReducer(s, { type: 'send' })
    expect(next.phase).toBe('connecting')
    expect(next.error).toBeNull()
  })

  it('来源严格绑定当前 generation：新一轮 send 清空上一轮来源', () => {
    let s = chatGenerationReducer(initialChatGenerationSnapshot, { type: 'send' })
    s = chatGenerationReducer(s, meta('c1', 'g1'))
    s = chatGenerationReducer(s, sources())
    expect(s.sources).not.toBeNull()

    const next = chatGenerationReducer(s, { type: 'send' })
    expect(next.sources).toBeNull()
    expect(next.generationId).toBeNull()
  })

  it('completed 后继续提问：send 回到 connecting 且不保留旧文本', () => {
    let s = chatGenerationReducer(initialChatGenerationSnapshot, { type: 'send' })
    s = chatGenerationReducer(s, meta('c1', 'g1'))
    s = chatGenerationReducer(s, sources())
    s = chatGenerationReducer(s, done())

    const next = chatGenerationReducer(s, { type: 'send' })
    expect(next.phase).toBe('connecting')
    expect(next.text).toBe('')
    expect(next.sources).toBeNull()
  })
})
