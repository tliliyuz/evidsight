import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AppProviders } from '@/app/Providers'
import { authSession } from '@/features/auth/authSession'

beforeEach(() => {
  vi.restoreAllMocks()
  authSession.resetForTesting()
})

/** 捕获 AppProviders 实际创建的 QueryClient 实例（模块私有，需经 hook 获取）。 */
function QueryClientProbe({ onClient }: { onClient: (client: QueryClient) => void }) {
  const client = useQueryClient()
  onClient(client)
  return null
}

describe('退出登录清理受保护 Query（FRONTEND §4.1/§11/§13.3）', () => {
  it('退出登录后经 registerSensitiveCleanup 清空 Query 缓存，不残留上一用户数据', async () => {
    let captured: QueryClient | null = null
    render(
      <AppProviders>
        <QueryClientProbe
          onClient={(client) => {
            captured = client
          }}
        />
      </AppProviders>,
    )
    expect(captured).not.toBeNull()

    // 预置一个受保护查询缓存（模拟已加载的知识库/会话等敏感数据）
    captured!.setQueryData(['knowledge-base', 'kb-1'], { owner: 'alice', sensitive: true })
    expect(captured!.getQueryData(['knowledge-base', 'kb-1'])).toEqual({
      owner: 'alice',
      sensitive: true,
    })

    // 真实退出登录：仅 mock 服务端登出调用，clearSession 仍会执行敏感清理回调
    await authSession.logout({ logout: vi.fn().mockResolvedValue(undefined) } as never)

    expect(captured!.getQueryData(['knowledge-base', 'kb-1'])).toBeUndefined()
    expect(captured!.getQueryCache().findAll()).toHaveLength(0)
  })

  it('会话中途认证失败（刷新失败）经 handleAuthenticationFailed 清理会话与 Query 缓存', async () => {
    let captured: QueryClient | null = null
    render(
      <AppProviders>
        <QueryClientProbe
          onClient={(client) => {
            captured = client
          }}
        />
      </AppProviders>,
    )
    expect(captured).not.toBeNull()

    captured!.setQueryData(['conversation', 'c-1'], { sensitive: true })
    expect(captured!.getQueryData(['conversation', 'c-1'])).toEqual({ sensitive: true })

    // 模拟会话中途认证失败（Access Token 刷新失败/被后端判为无效，FRONTEND §11）
    authSession.setRestoringForTesting()
    authSession.handleAuthenticationFailed()

    expect(authSession.getSnapshot()).toEqual({ status: 'anonymous', user: null })
    expect(captured!.getQueryData(['conversation', 'c-1'])).toBeUndefined()
    expect(captured!.getQueryCache().findAll()).toHaveLength(0)
  })
})
