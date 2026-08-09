import { describe, expect, it, vi } from 'vitest'

import { openChatStream } from '@/api/chat'

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

describe('Chat v1 SSE 流式客户端', () => {
  it('POST /api/v1/chat/stream 携带 Bearer 与 JSON 请求体', async () => {
    const fetchFn = vi.fn().mockResolvedValue(
      fakeResponse({
        ok: true,
        status: 200,
        body: sseBody([
          'id: 1\nevent: meta\ndata: {"conversation_id":"c","generation_id":"g"}\n\n',
          'id: 2\nevent: done\ndata: {"message_id":1}\n\n',
        ]),
      }),
    )
    const onEvent = vi.fn()

    await openChatStream(
      { conversation_id: null, knowledge_base_id: 'kb-1', question: '问题' },
      onEvent,
      new AbortController().signal,
      { fetchFn, accessToken: () => 'access-token' },
    )

    expect(fetchFn).toHaveBeenCalledWith(
      '/api/v1/chat/stream',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ Authorization: 'Bearer access-token' }),
        body: JSON.stringify({
          conversation_id: null,
          knowledge_base_id: 'kb-1',
          question: '问题',
        }),
        credentials: 'include',
      }),
    )
    expect(onEvent).toHaveBeenCalledTimes(2)
  })

  it('逐帧将解析事件回调给 onEvent', async () => {
    const fetchFn = vi.fn().mockResolvedValue(
      fakeResponse({
        ok: true,
        status: 200,
        body: sseBody([
          'id: 1\nevent: meta\ndata: {"conversation_id":"c","generation_id":"g"}\n\n',
          'id: 2\nevent: message.delta\ndata: {"delta":"你',
          '好"}\n\n',
          'id: 3\nevent: done\ndata: {"message_id":1}\n\n',
        ]),
      }),
    )
    const onEvent = vi.fn()

    await openChatStream(
      { conversation_id: 'c', knowledge_base_id: 'kb-1', question: '问题' },
      onEvent,
      new AbortController().signal,
      { fetchFn, accessToken: () => null },
    )

    expect(onEvent).toHaveBeenNthCalledWith(1, {
      type: 'meta',
      id: 1,
      data: { conversation_id: 'c', generation_id: 'g' },
    })
    expect(onEvent).toHaveBeenNthCalledWith(2, {
      type: 'message.delta',
      id: 2,
      data: { delta: '你好' },
    })
  })

  it('非 2xx 响应抛出携带错误码的 ChatStreamHttpError', async () => {
    const fetchFn = vi.fn().mockResolvedValue(
      fakeResponse({
        ok: false,
        status: 422,
        json: () =>
          Promise.resolve({
            error: { error_code: 'E1001', message: '请求校验失败', request_id: 'r1' },
          }),
      }),
    )

    await expect(
      openChatStream(
        { conversation_id: null, knowledge_base_id: 'kb-1', question: '' },
        vi.fn(),
        new AbortController().signal,
        { fetchFn },
      ),
    ).rejects.toMatchObject({ status: 422, errorCode: 'E1001' })
  })

  it('Abort 传播到 fetch 的 signal', async () => {
    const controller = new AbortController()
    const fetchFn = vi
      .fn()
      .mockResolvedValue(fakeResponse({ ok: true, status: 200, body: sseBody([]) }))
    controller.abort()

    await openChatStream(
      { conversation_id: null, knowledge_base_id: 'kb-1', question: '问题' },
      vi.fn(),
      controller.signal,
      { fetchFn },
    )

    expect(fetchFn).toHaveBeenCalledWith(
      '/api/v1/chat/stream',
      expect.objectContaining({ signal: controller.signal }),
    )
  })
})
