/**
 * refreshToken() 辅助函数测试 — Axios 拦截器 / SSE 共用入口（v1 Cookie + CSRF）。
 *
 * 对齐 FRONTEND.md §5.1.1/§5.1.2 / ADR-006：
 * - 刷新走 POST /api/v1/auth/refresh：Refresh Token 由后端 HttpOnly Cookie 持有，
 *   前端不读取 localStorage.refresh_token，CSRF 从非 HttpOnly Cookie 读取回传；
 * - 响应为 unwrapped RefreshV1Response { access_token, ... }；
 * - 刷新成功后同步 Pinia store（setTokens + /me + scheduleRefresh）；
 * - /me 重取失败不阻断刷新。
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

function setCookie(name, value) {
  document.cookie = `${name}=${value}; path=/`
}
function clearCookies() {
  document.cookie.split(';').forEach((c) => {
    const name = c.split('=')[0].trim()
    if (name) {
      document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`
    }
  })
}

beforeEach(async () => {
  vi.clearAllMocks()
  localStorage.clear()
  clearCookies()
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

describe('refreshToken() — v1 Cookie 刷新并同步 store', () => {
  it('走 /api/v1/auth/refresh，携带 X-CSRF-Token，不读写 localStorage.refresh_token', async () => {
    const axios = (await import('axios')).default
    const postSpy = vi.spyOn(axios, 'post').mockResolvedValue({
      data: { access_token: NEW_ACCESS, token_type: 'bearer', expires_in: 900 },
    })
    setCookie('evidsight_csrf', 'csrf-token-abc')

    // api 实例的 /me 请求走 mock adapter
    const { default: api, refreshToken } = await import('@/api/index')
    api.defaults.adapter = vi.fn().mockResolvedValue({
      data: { id: UUID, username: 'db-user', role: 'admin', status: 'active' },
    })

    const access = await refreshToken()

    expect(access).toBe(NEW_ACCESS)
    // 刷新端点与 CSRF 回传
    expect(postSpy.mock.calls[0][0]).toBe('/api/v1/auth/refresh')
    expect(postSpy.mock.calls[0][1] == null).toBe(true) // 无 body refresh_token
    expect(postSpy.mock.calls[0][2].headers['X-CSRF-Token']).toBe('csrf-token-abc')
    // access_token 更新，refresh_token 不再写入
    expect(localStorage.getItem('access_token')).toBe(NEW_ACCESS)
    expect(localStorage.getItem('refresh_token')).toBeNull()

    // 刷新成功后重取 /me（角色/状态以数据库为准）
    expect(mockGetMeApi).toHaveBeenCalledTimes(1)

    const { useAuthStore } = await import('@/stores/auth')
    const store = useAuthStore()
    expect(store.user.id).toBe(UUID)
    expect(store.user.username).toBe('db-user')
    expect(store.user.role).toBe('admin')
    // store 不再持有 refresh_token 状态
    expect(store.refreshToken).toBeUndefined()
  })

  it('/me 重取失败不阻断刷新（保留新 token 并返回）', async () => {
    const axios = (await import('axios')).default
    vi.spyOn(axios, 'post').mockResolvedValue({
      data: { access_token: NEW_ACCESS, token_type: 'bearer', expires_in: 900 },
    })
    setCookie('evidsight_csrf', 'csrf-token-abc')

    const { default: api, refreshToken } = await import('@/api/index')
    api.defaults.adapter = vi.fn().mockResolvedValue({ data: {} })
    mockGetMeApi.mockRejectedValue(new Error('network'))

    const access = await refreshToken()

    // token 刷新已成功，/me 失败不回滚
    expect(access).toBe(NEW_ACCESS)
    expect(localStorage.getItem('access_token')).toBe(NEW_ACCESS)
    expect(localStorage.getItem('refresh_token')).toBeNull()
  })
})
