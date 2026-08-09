/**
 * Chat SSE 状态机（纯 reducer，无 React 依赖）。
 *
 * 对齐 FRONTEND.md §7 与 API.md §12：
 * - 事件序列 `meta` → 零到多个 `message.delta` → `sources` → `done`；
 * - 只在 `done` 后进入成功终态（completed）；`done` 前不得伪装完整答案；
 * - `error` 后拒绝拼接任何后续 delta；
 * - `sources` 与当前 generation 严格绑定，新一轮发送会清空上一轮来源；
 * - 用户中止进入 canceling，连接关闭后进入 canceled（已中止）；
 * - SSE 意外断开（无 done 无 error）同样展示「已中止」，不视为完整答案；
 * - HTTP 失败进入 failed 并携带安全错误。
 */

import type { ChatSseEvent, ChatSourceChunk } from '@/features/chat/chatSseParser'

export type ChatGenerationPhase =
  | 'idle'
  | 'connecting'
  | 'streaming'
  | 'awaitingSources'
  | 'completed'
  | 'failed'
  | 'canceling'
  | 'canceled'

export type ChatGenerationError = {
  code: string
  message: string
  detail?: string
}

export type CompletedMessageSources = {
  sources: ChatSourceChunk[]
  confidence: string | undefined
  confidenceNote: string | undefined
}

export type ChatGenerationSnapshot = {
  phase: ChatGenerationPhase
  /** meta 事件绑定的 generation 稳定 ID，取消时必须携带 */
  generationId: string | null
  conversationId: string | null
  text: string
  sources: ChatSourceChunk[] | null
  confidence: string | undefined
  confidenceNote: string | undefined
  error: ChatGenerationError | null
  doneMessageId: number | null
  doneTitle: string | null
  /**
   * 已完成消息的来源：sources 事件不随消息持久化（Message 仅存 content），
   * done 时把当轮 sources 按 message_id 绑定到此表，历史回读后来源卡片仍可见
   * （FRONTEND §5.5）。
   */
  completedSources: Record<number, CompletedMessageSources>
}

export const initialChatGenerationSnapshot: ChatGenerationSnapshot = {
  phase: 'idle',
  generationId: null,
  conversationId: null,
  text: '',
  sources: null,
  confidence: undefined,
  confidenceNote: undefined,
  error: null,
  doneMessageId: null,
  doneTitle: null,
  completedSources: {},
}

export type ChatGenerationAction =
  | { type: 'send' }
  | { type: 'sse'; event: ChatSseEvent }
  | { type: 'cancelRequested' }
  | {
      type: 'streamClosed'
      reason: 'cancel' | 'disconnect' | 'http-error'
      error?: ChatGenerationError
    }

const INACTIVE_FOR_DELTA: ReadonlySet<ChatGenerationPhase> = new Set([
  'idle',
  'completed',
  'failed',
  'canceling',
  'canceled',
])

function resetForSend(state: ChatGenerationSnapshot): ChatGenerationSnapshot {
  // 保留已完成消息的来源（按全局消息 id 索引，跨轮/跨会话不冲突），
  // 使同一会话多轮历史消息的来源卡片持续可见（FRONTEND §5.5）
  return {
    ...initialChatGenerationSnapshot,
    phase: 'connecting',
    completedSources: state.completedSources,
  }
}

function handleSse(state: ChatGenerationSnapshot, event: ChatSseEvent): ChatGenerationSnapshot {
  switch (event.type) {
    case 'meta': {
      if (state.phase !== 'connecting') return state
      return {
        ...state,
        phase: 'streaming',
        generationId: event.data.generation_id,
        conversationId: event.data.conversation_id,
      }
    }
    case 'message.delta': {
      // error 后、成功终态后、已中止后均拒绝拼接新的 delta
      if (INACTIVE_FOR_DELTA.has(state.phase)) return state
      return { ...state, text: state.text + event.data.delta }
    }
    case 'sources': {
      if (INACTIVE_FOR_DELTA.has(state.phase)) return state
      return {
        ...state,
        phase: 'awaitingSources',
        sources: event.data.chunks,
        confidence: event.data.confidence,
        confidenceNote: event.data.confidence_note,
      }
    }
    case 'error': {
      if (state.phase === 'completed' || state.phase === 'canceled') return state
      return {
        ...state,
        phase: 'failed',
        error: { code: event.data.error_code, message: event.data.message },
      }
    }
    case 'done': {
      if (state.phase !== 'streaming' && state.phase !== 'awaitingSources') {
        return state
      }
      // 把当轮 sources 绑定到持久化消息 id（仅在有来源时）
      const completedSources = state.sources
        ? {
            ...state.completedSources,
            [event.data.message_id]: {
              sources: state.sources,
              confidence: state.confidence,
              confidenceNote: state.confidenceNote,
            },
          }
        : state.completedSources
      return {
        ...state,
        phase: 'completed',
        doneMessageId: event.data.message_id,
        doneTitle: event.data.title,
        completedSources,
      }
    }
  }
}

export function chatGenerationReducer(
  state: ChatGenerationSnapshot,
  action: ChatGenerationAction,
): ChatGenerationSnapshot {
  switch (action.type) {
    case 'send':
      return resetForSend(state)
    case 'sse':
      return handleSse(state, action.event)
    case 'cancelRequested': {
      if (
        state.phase === 'streaming' ||
        state.phase === 'awaitingSources' ||
        state.phase === 'connecting'
      ) {
        return { ...state, phase: 'canceling' }
      }
      // completed / failed / canceled / idle 不接受中止
      return state
    }
    case 'streamClosed': {
      if (state.phase === 'canceling') {
        return { ...state, phase: 'canceled' }
      }
      if (state.phase === 'completed' || state.phase === 'failed' || state.phase === 'canceled') {
        return state
      }
      if (action.reason === 'http-error') {
        return {
          ...state,
          phase: 'failed',
          error: action.error ?? { code: 'NETWORK_ERROR', message: '网络请求失败' },
        }
      }
      // connecting / streaming / awaitingSources 断开且未收到 done → 已中止
      return { ...state, phase: 'canceled' }
    }
  }
}
