import { describe, expect, it } from 'vitest'

import { createChatSseParser } from '@/features/chat/chatSseParser'

describe('Chat canonical SSE 解析器', () => {
  it('解析完整流 meta → message.delta → sources → done 并保留事件 id', () => {
    const parser = createChatSseParser()
    const events = parser(
      [
        'id: 1',
        'event: meta',
        'data: {"conversation_id":"conv-1","generation_id":"gen-1"}',
        '',
        'id: 2',
        'event: message.delta',
        'data: {"delta":"你好"}',
        '',
        'id: 3',
        'event: sources',
        'data: {"chunks":[{"chunk_index":1,"document_uuid":"doc-1","segment_id":"seg-1","doc_name":"手册","score":0.9,"page":2}]}',
        '',
        'id: 4',
        'event: done',
        'data: {"message_id":12,"title":"标题","token_usage":{"prompt":1,"completion":2,"total":3}}',
        '',
        '',
      ].join('\n'),
    )

    expect(events).toEqual([
      { type: 'meta', id: 1, data: { conversation_id: 'conv-1', generation_id: 'gen-1' } },
      { type: 'message.delta', id: 2, data: { delta: '你好' } },
      {
        type: 'sources',
        id: 3,
        data: {
          chunks: [
            {
              chunk_index: 1,
              document_uuid: 'doc-1',
              segment_id: 'seg-1',
              doc_name: '手册',
              score: 0.9,
              page: 2,
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
      {
        type: 'done',
        id: 4,
        data: {
          message_id: 12,
          title: '标题',
          token_usage: { prompt: 1, completion: 2, total: 3 },
        },
      },
    ])
  })

  it('跨 chunk 分帧仍能正确续接解析', () => {
    const parser = createChatSseParser()
    const first = parser('id: 1\nevent: meta\ndata: {"convers')
    const second = parser(
      'ation_id":"conv-1","generation_id":"gen-1"}\n\nid: 2\nevent: message.delta\ndata: {"delta":"续接"}\n\n',
    )
    expect(first).toEqual([])
    expect(second).toEqual([
      { type: 'meta', id: 1, data: { conversation_id: 'conv-1', generation_id: 'gen-1' } },
      { type: 'message.delta', id: 2, data: { delta: '续接' } },
    ])
  })

  it('忽略心跳注释帧（以冒号开头）', () => {
    const parser = createChatSseParser()
    const events = parser(
      ': ping\n\nid: 1\nevent: meta\ndata: {"conversation_id":"c","generation_id":"g"}\n\n: keep-alive\n\n',
    )
    expect(events).toEqual([
      { type: 'meta', id: 1, data: { conversation_id: 'c', generation_id: 'g' } },
    ])
  })

  it('忽略未知事件（如 v1 不输出的 thinking）', () => {
    const parser = createChatSseParser()
    const events = parser(
      'id: 1\nevent: thinking\ndata: {"delta":"推理"}\n\nid: 2\nevent: meta\ndata: {"conversation_id":"c","generation_id":"g"}\n\n',
    )
    expect(events).toEqual([
      { type: 'meta', id: 2, data: { conversation_id: 'c', generation_id: 'g' } },
    ])
  })

  it('忽略缺少 event 或 data 的畸形帧，不抛出', () => {
    const parser = createChatSseParser()
    const events = parser('data: {"delta":"缺少事件名"}\n\nevent: meta\n\n')
    expect(events).toEqual([])
  })

  it('忽略 data 非法的 JSON 帧，不抛出', () => {
    const parser = createChatSseParser()
    const events = parser(
      'id: 1\nevent: meta\ndata: {broken json}\n\nid: 2\nevent: done\ndata: {"message_id":1}\n\n',
    )
    expect(events).toEqual([{ type: 'done', id: 2, data: { message_id: 1, title: null } }])
  })

  it('解析流内 error 事件', () => {
    const parser = createChatSseParser()
    const events = parser(
      'id: 1\nevent: meta\ndata: {"conversation_id":"c","generation_id":"g"}\n\nid: 2\nevent: error\ndata: {"error_code":"CHAT_LLM_UPSTREAM","message":"LLM 调用失败","retryable":true}\n\n',
    )
    expect(events).toEqual([
      { type: 'meta', id: 1, data: { conversation_id: 'c', generation_id: 'g' } },
      {
        type: 'error',
        id: 2,
        data: { error_code: 'CHAT_LLM_UPSTREAM', message: 'LLM 调用失败', retryable: true },
      },
    ])
  })

  it('sources 事件携带 confidence 与 confidence_note', () => {
    const parser = createChatSseParser()
    const events = parser(
      'id: 1\nevent: sources\ndata: {"chunks":[],"confidence":"high","confidence_note":"证据一致"}\n\n',
    )
    expect(events).toEqual([
      {
        type: 'sources',
        id: 1,
        data: { chunks: [], confidence: 'high', confidence_note: '证据一致' },
      },
    ])
  })
})
