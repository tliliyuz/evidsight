import { useCallback, useEffect, useRef, useState } from 'react'

import { cancelChatGeneration, ChatStreamHttpError, openChatStream } from '@/api/chat'
import {
  chatGenerationReducer,
  initialChatGenerationSnapshot,
  type ChatGenerationSnapshot,
} from '@/features/chat/chatGenerationMachine'

type SendInput = {
  conversationId: string | null
  knowledgeBaseId: string
  question: string
}

const ACTIVE_PHASES = new Set(['connecting', 'streaming', 'awaitingSources'])

/**
 * Chat generation 生命周期 Hook。
 *
 * 包装纯 reducer 状态机 + `openChatStream` + `cancelChatGeneration`：
 * - 发送新问题会中止上一轮仍在进行的流，并通过 abort 归属校验丢弃陈旧回调，
 *   避免「取消竞态」把新一轮 generation 误判为已中止；
 * - 用户停止：先进入 canceling，再 abort 连接，并调用 cancel API 终止服务端生成；
 * - 卸载或切换会话时关闭当前 SSE。
 */
export function useChatGeneration() {
  const [snapshot, setSnapshot] = useState<ChatGenerationSnapshot>(initialChatGenerationSnapshot)
  const abortRef = useRef<AbortController | null>(null)
  const snapshotRef = useRef(snapshot)
  useEffect(() => {
    snapshotRef.current = snapshot
  }, [snapshot])

  const dispatch = useCallback((action: Parameters<typeof chatGenerationReducer>[1]) => {
    setSnapshot((current) => chatGenerationReducer(current, action))
  }, [])

  const send = useCallback(
    async ({ conversationId, knowledgeBaseId, question }: SendInput) => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      dispatch({ type: 'send' })
      try {
        await openChatStream(
          {
            conversation_id: conversationId,
            knowledge_base_id: knowledgeBaseId,
            question,
          },
          (event) => dispatch({ type: 'sse', event }),
          controller.signal,
        )
        if (abortRef.current === controller) {
          dispatch({ type: 'streamClosed', reason: 'disconnect' })
        }
      } catch (error) {
        // 已被新一轮 send 取代的陈旧回调直接丢弃，不得污染新状态
        if (abortRef.current !== controller) return
        if (controller.signal.aborted) {
          dispatch({ type: 'streamClosed', reason: 'cancel' })
          return
        }
        if (error instanceof ChatStreamHttpError) {
          dispatch({
            type: 'streamClosed',
            reason: 'http-error',
            error: { code: error.errorCode, message: error.message },
          })
          return
        }
        dispatch({
          type: 'streamClosed',
          reason: 'http-error',
          error: { code: 'NETWORK_ERROR', message: '网络连接中断' },
        })
      }
    },
    [dispatch],
  )

  const cancel = useCallback(() => {
    const current = snapshotRef.current
    if (!ACTIVE_PHASES.has(current.phase)) return
    dispatch({ type: 'cancelRequested' })
    abortRef.current?.abort()
    if (current.generationId) {
      void cancelChatGeneration(current.generationId).catch(() => {
        // 取消失败不改变本地「已中止」展示；服务端取消命令幂等
      })
    }
  }, [dispatch])

  useEffect(() => {
    return () => abortRef.current?.abort()
  }, [])

  const isActive = ACTIVE_PHASES.has(snapshot.phase)

  return { snapshot, send, cancel, isActive }
}
