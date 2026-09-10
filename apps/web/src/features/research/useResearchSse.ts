import { useCallback, useEffect, useRef, useState } from 'react'

import { openResearchTaskStream, researchApi, ResearchStreamHttpError } from '@/api/research'
import {
  initialResearchSseSnapshot,
  researchSseReducer,
  type ResearchSseError,
  type ResearchSseSnapshot,
} from '@/features/research/researchSseMachine'

const TERMINAL_STATUSES: ReadonlySet<string> = new Set([
  'completed',
  'failed',
  'canceled',
  'partially_completed',
])

/** 断线重连间隔（秒）。SSE 心跳 15s，2s 内重连不影响任务；任务在后台持续运行。 */
const RETRY_DELAY_MS = 2000

function isTerminalStatus(status: string | null | undefined): boolean {
  return status != null && TERMINAL_STATUSES.has(status)
}

function toError(error: unknown): ResearchSseError {
  if (error instanceof ResearchStreamHttpError) {
    return { code: error.errorCode, message: error.message }
  }
  return { code: 'NETWORK_ERROR', message: '网络连接中断' }
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) {
      resolve()
      return
    }
    const handleAbort = () => {
      window.clearTimeout(timer)
      resolve()
    }
    const timer = window.setTimeout(() => {
      signal.removeEventListener('abort', handleAbort)
      resolve()
    }, ms)
    signal.addEventListener('abort', handleAbort, { once: true })
  })
}

/**
 * Research 运行态生命周期 Hook（FRONTEND §8 / API.md §13）。
 *
 * - 挂载：先 `GET /state` 取服务端持久状态快照（LoadingSnapshot → Subscribing），
 *   终态任务直接停止不再订阅；非终态打开 SSE 订阅（→ Live）；
 * - 订阅是观察通道：断开/切页/卸载一律 abort 连接，绝不发送取消；任务在后台持续运行；
 * - 断线进入 Reconnecting，携带 Last-Event-ID 游标自动重连；4xx（403/404 等）不再重连；
 * - abort 归属校验：新任务/卸载会 abort 旧 controller，陈旧回调直接丢弃，避免污染新状态。
 */
export function useResearchSse(taskId: string | undefined) {
  const [snapshot, setSnapshot] = useState<ResearchSseSnapshot>(initialResearchSseSnapshot)
  const abortRef = useRef<AbortController | null>(null)
  const cursorRef = useRef<number | null>(null)

  const dispatch = useCallback((action: Parameters<typeof researchSseReducer>[1]) => {
    setSnapshot((current) => researchSseReducer(current, action))
  }, [])

  const run = useCallback(
    async (id: string) => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      cursorRef.current = null

      // 阶段 1：服务端持久状态快照（LoadingSnapshot）
      try {
        const state = await researchApi.getResearchTaskState(id)
        if (abortRef.current !== controller) return
        dispatch({ type: 'snapshotLoaded', state })
        if (isTerminalStatus(state.status)) return // 终态由快照确定，不再订阅
      } catch (error) {
        if (abortRef.current !== controller) return
        if (controller.signal.aborted) return
        dispatch({ type: 'httpError', error: toError(error) })
        return // 快照失败交给页面重试入口，不自动无限重试
      }

      // 阶段 2：SSE 订阅循环（Subscribing → Live → Reconnecting → 重连带游标）
      for (;;) {
        if (controller.signal.aborted) return
        try {
          await openResearchTaskStream(
            id,
            (event) => {
              if (abortRef.current !== controller) return
              if (event.id !== null) cursorRef.current = event.id
              dispatch({ type: 'sse', event })
            },
            controller.signal,
            { lastEventId: cursorRef.current },
          )
          // stream.end 只表示本次连接结束，必须重新读取 MySQL 快照收口；
          // 不能依赖 task.failed/task.completed 的增量字段完整或到达顺序。
          const latest = await researchApi.getResearchTaskState(id)
          if (abortRef.current !== controller) return
          dispatch({ type: 'snapshotLoaded', state: latest })
          if (isTerminalStatus(latest.status)) return
        } catch (error) {
          if (controller.signal.aborted) return
          const err = toError(error)
          dispatch({ type: 'httpError', error: err })
          // 4xx（403/404 等权限/不存在）不再重连；网络中断/5xx 等待后重连
          if (
            error instanceof ResearchStreamHttpError &&
            error.status >= 400 &&
            error.status < 500
          ) {
            return
          }
        }
        await sleep(RETRY_DELAY_MS, controller.signal)
      }
    },
    [dispatch],
  )

  useEffect(() => {
    if (!taskId) return undefined
    // run() 在 GET /state 网络 await 之后才 dispatch（并非 effect 同步 setState）；
    // 订阅生命周期必须在挂载即启动，与 useChatAutoScroll 相同的定向豁免先例。
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void run(taskId)
    return () => {
      abortRef.current?.abort()
    }
  }, [taskId, run])

  const retry = useCallback(() => {
    if (taskId) void run(taskId)
  }, [taskId, run])

  return { snapshot, retry }
}
