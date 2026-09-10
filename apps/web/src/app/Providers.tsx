import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { PropsWithChildren } from 'react'
import { useEffect } from 'react'

import { registerAuthFailureHandler } from '@/api/client'
import { authSession } from '@/features/auth/authSession'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
})

export function AppProviders({ children }: PropsWithChildren) {
  useEffect(() => {
    // 会话敏感清理（FRONTEND §4.1/§11/§13.3）：退出登录/Refresh 失败/登录失败时随认证
    // 一起清空全部 Query 缓存，避免切换账号后残留上一用户的知识库、会话、任务等受保护数据。
    const unregisterCleanup = authSession.registerSensitiveCleanup(() => queryClient.clear())
    // 认证失败（Access Token 刷新失败/被后端判为无效）清理会话并返回登录（FRONTEND §11），
    // 修复此前会话中途刷新失败后 token 被清空但状态仍为已登录、导致所有请求 401 卡死的缺陷。
    const unregisterAuth = registerAuthFailureHandler(() =>
      authSession.handleAuthenticationFailed(),
    )
    return () => {
      unregisterCleanup()
      unregisterAuth()
    }
  }, [])
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}
