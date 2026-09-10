import { beforeEach, describe, expect, it, vi } from 'vitest'

import { authSession } from '@/features/auth/authSession'

describe('身份权威恢复', () => {
  beforeEach(() => authSession.resetForTesting())

  it('登录后必须由 me 成功结果建立用户状态', async () => {
    const user = {
      id: '550e8400-e29b-41d4-a716-446655440001',
      username: 'alice',
      role: 'user' as const,
      status: 'active' as const,
    }
    const api = {
      login: vi.fn().mockResolvedValue({ access_token: 'access-1' }),
      me: vi.fn().mockResolvedValue(user),
    }

    await authSession.login('alice', 'password', api)

    expect(authSession.getSnapshot()).toMatchObject({ status: 'authenticated', user })
    expect(api.me).toHaveBeenCalledAfter(api.login)
  })

  it('me 失败时清理身份并执行敏感状态清理器', async () => {
    const cleanup = vi.fn()
    const unregister = authSession.registerSensitiveCleanup(cleanup)
    const api = {
      login: vi.fn().mockResolvedValue({ access_token: 'access-1' }),
      me: vi.fn().mockRejectedValue(new Error('disabled')),
    }

    await expect(authSession.login('alice', 'password', api)).rejects.toThrow('disabled')

    expect(authSession.getSnapshot()).toMatchObject({ status: 'anonymous', user: null })
    expect(cleanup).toHaveBeenCalledOnce()
    unregister()
  })
})
