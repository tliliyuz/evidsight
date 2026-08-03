/**
 * v1 Auth API（Cookie + CSRF）测试 — S6 事件③ 前端联动
 *
 * 对齐 FRONTEND.md §5.1.2 / API.md §5：
 * - API 客户端启用凭据携带（withCredentials），使 Refresh Cookie 随请求发送；
 * - login 调用 POST /api/v1/auth/login（建立 Refresh/CSRF Cookie 的入口）；
 * - refreshToken / logout 调用 POST /api/v1/auth/refresh / logout，
 *   读取非 HttpOnly CSRF Cookie 并以 X-CSRF-Token Header 回传，不带 body refresh_token。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

/** jsdom 下设置 / 清除 Cookie */
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

describe('v1 Auth API（Cookie + CSRF 目标态）', () => {
  let api
  let authApi
  let adapter

  beforeEach(async () => {
    vi.clearAllMocks()
    clearCookies()
    vi.resetModules()
    const indexMod = await import('@/api/index')
    api = indexMod.default
    adapter = vi.fn().mockResolvedValue({ data: {} })
    api.defaults.adapter = adapter
    authApi = await import('@/api/auth')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('Axios 实例启用凭据携带（withCredentials）且 baseURL 指向 /api', () => {
    expect(api.defaults.withCredentials).toBe(true)
    expect(api.defaults.baseURL).toBe('/api')
  })

  it('login 调用 POST /v1/auth/login（登录为 Cookie 建立入口）', async () => {
    await authApi.login('user', 'pass')
    const cfg = adapter.mock.calls[0][0]
    expect(cfg.method).toBe('post')
    expect(cfg.url).toBe('/v1/auth/login')
    const body = JSON.parse(cfg.data)
    expect(body.username).toBe('user')
    expect(body.password).toBe('pass')
  })

  it('refreshToken 调用 POST /v1/auth/refresh，携带 X-CSRF-Token 且不带 body refresh_token', async () => {
    setCookie('evidsight_csrf', 'csrf-token-123')
    await authApi.refreshToken()
    const cfg = adapter.mock.calls[0][0]
    expect(cfg.method).toBe('post')
    expect(cfg.url).toBe('/v1/auth/refresh')
    expect(cfg.data == null).toBe(true) // 无 body refresh_token
    expect(cfg.headers['X-CSRF-Token']).toBe('csrf-token-123')
  })

  it('logout 调用 POST /v1/auth/logout，携带 X-CSRF-Token 且不带 body refresh_token', async () => {
    setCookie('evidsight_csrf', 'csrf-token-456')
    await authApi.logout()
    const cfg = adapter.mock.calls[0][0]
    expect(cfg.method).toBe('post')
    expect(cfg.url).toBe('/v1/auth/logout')
    expect(cfg.data == null).toBe(true)
    expect(cfg.headers['X-CSRF-Token']).toBe('csrf-token-456')
  })

  it('getCsrfToken 读取非 HttpOnly CSRF Cookie', async () => {
    setCookie('evidsight_csrf', 'abc-xyz')
    const { getCsrfToken } = await import('@/api/index')
    expect(getCsrfToken()).toBe('abc-xyz')
  })

  it('CSRF Cookie 缺失时 getCsrfToken 返回空串', async () => {
    const { getCsrfToken } = await import('@/api/index')
    expect(getCsrfToken()).toBe('')
  })
})
