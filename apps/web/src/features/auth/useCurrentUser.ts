import { useSyncExternalStore } from 'react'

import type { UserSummary } from '@/api/auth'
import { authSession } from '@/features/auth/authSession'

/**
 * 读取当前登录用户（外部 Store authSession，与 Router 的 AuthenticatedShell 同源）。
 *
 * 页面组件可通过 `currentUser` prop 覆盖（测试注入）；生产路径从 authSession 读取。
 * 权限判断以 `/me` 返回的服务端身份为准（Platform User UUID + role），
 * 不依赖本地可被伪造的客户端标记。
 */
export function useCurrentUser(override?: UserSummary | null): UserSummary | null {
  const auth = useSyncExternalStore(authSession.subscribe, authSession.getSnapshot)
  return override ?? auth.user
}
