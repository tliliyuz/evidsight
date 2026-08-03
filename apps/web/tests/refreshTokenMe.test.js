/**
 * refreshToken() 辅助函数测试 — Axios 拦截器 / SSE 共用入口换发 token 后重取 /me。
 *
 * 对齐 FRONTEND.md §5.1.1：Refresh 成功后重新调用 /me，获取可能变化的角色与状态。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const mockGetMeApi = vi.fn()

vi.mock('@/api/auth', () => ({
  login: vi.fn(),
  register: vi.fn(),
  refreshToken: vi.fn(),
  logout: vi.fn(),
  getMe: (...args) => mockGetMeApi(...args),
}))

function makeJwt(payload) {
  const header = btoa(JSON.stringify({ alg: 'HS256' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.signature`
}

const UUID = '550e8400-e29b-41d4-a716-446655440001'
const NEW_ACCESS = makeJwt({ sub: UUID, role: 'admin', exp: Math.floor(Date.now() / 1000) + 7200 })

beforeEach(async () => {
  vi.clearAllMocks()
  localStorage.clear()
  vi.resetModules()
  setActivePinia(createPinia())
  // 默认：/me 返回数据库当前状态
  mockGetMeApi.mockResolvedValue({
    data: { id: UUID, username: 'db-user', role: 'admin', status: 'active' },
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('refreshToken() — 刷新成功后重取 /me', () => {
  it('换发新 token 后重新调用 /me，user 取数据库最新角色/状态', async () => {
    localStorage.setItem('refresh_token', 'old-refresh')

    // refreshToken() 内部使用原始 axios.post 调 /api/auth/refresh
    const axios = (await import('axios')).default
    vi.spyOn(axios, 'post').mockResolvedValue({
      data: { data: { access_token: NEW_ACCESS, refresh_token: 'new-refresh' } },
    })

    // api 实例的 /me 请求走 mock adapter
    const { default: api, refreshToken } = await import('@/api/index')
    api.defaults.adapter = vi.fn().mockResolvedValue({
      data: { id: UUID, username: 'db-user', role: 'admin', status: 'active' },
    })

    const access = await refreshToken()

    expect(access).toBe(NEW_ACCESS)
    expect(localStorage.getItem('access_token')).toBe(NEW_ACCESS)
    expect(localStorage.getItem('refresh_token')).toBe('new-refresh')

    // 刷新成功后重取 /me（角色/状态以数据库为准）
    expect(mockGetMeApi).toHaveBeenCalledTimes(1)

    const { useAuthStore } = await import('@/stores/auth')
    const store = useAuthStore()
    expect(store.user.id).toBe(UUID)
    expect(store.user.username).toBe('db-user')
    expect(store.user.role).toBe('admin')
  })

  it('/me 重取失败不阻断刷新（保留新 token 并返回）', async () => {
    localStorage.setItem('refresh_token', 'old-refresh')

    const axios = (await import('axios')).default
    vi.spyOn(axios, 'post').mockResolvedValue({
      data: { data: { access_token: NEW_ACCESS, refresh_token: 'new-refresh' } },
    })

    const { default: api, refreshToken } = await import('@/api/index')
    api.defaults.adapter = vi.fn().mockResolvedValue({ data: {} })
    mockGetMeApi.mockRejectedValue(new Error('network'))

    const access = await refreshToken()

    // token 刷新已成功，/me 失败不回滚
    expect(access).toBe(NEW_ACCESS)
    expect(localStorage.getItem('access_token')).toBe(NEW_ACCESS)
    expect(localStorage.getItem('refresh_token')).toBe('new-refresh')
  })
})
