/**
 * 身份恢复流程 RED 测试 — 前端从 /me 获取 UserSummary（UUID），不再 parseInt 或解析 JWT Claim。
 *
 * 覆盖事件② §5 流程：登录后用 /me 建 user；重载用 /me 恢复；/me 失败清态；
 * Refresh 成功后重取 /me；isLoggedIn 在 /me 完成前保持未就绪。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const mockLoginApi = vi.fn()
const mockRefreshApi = vi.fn()
const mockGetMeApi = vi.fn()

vi.mock('@/api/auth', () => ({
  login: (...args) => mockLoginApi(...args),
  register: vi.fn(),
  refreshToken: (...args) => mockRefreshApi(...args),
  logout: vi.fn(),
  getMe: (...args) => mockGetMeApi(...args),
}))

function makeJwt(payload) {
  const header = btoa(JSON.stringify({ alg: 'HS256' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.signature`
}

const UUID = '550e8400-e29b-41d4-a716-446655440001'

let useAuthStore

beforeEach(async () => {
  vi.clearAllMocks()
  localStorage.clear()
  vi.resetModules()
  setActivePinia(createPinia())
  const mod = await import('@/stores/auth')
  useAuthStore = mod.useAuthStore
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('身份恢复：登录后从 /me 获取 UserSummary', () => {
  it('登录成功后调用 /me，user.id 为 UUID 字符串（不 parseInt）', async () => {
    const store = useAuthStore()
    const jwt = makeJwt({ sub: UUID, role: 'user', exp: Math.floor(Date.now() / 1000) + 3600 })
    mockLoginApi.mockResolvedValue({
      data: { access_token: jwt, token_type: 'bearer', expires_in: 900, user: { id: UUID, username: 'u', role: 'user', status: 'active' } },
    })
    mockGetMeApi.mockResolvedValue({
      data: { id: UUID, username: 'testuser', role: 'user', status: 'active' },
    })

    const user = await store.login('testuser', 'password')

    expect(mockGetMeApi).toHaveBeenCalledTimes(1)
    expect(user.id).toBe(UUID)
    expect(store.user.id).toBe(UUID)
    expect(store.user.username).toBe('testuser')
    expect(store.user.role).toBe('user')
  })

  it('user 不来自 JWT Claim 拼装（不解析 token 内部 username）', async () => {
    const store = useAuthStore()
    // token 的 sub 是 UUID，payload 无 username（事件②已移除）
    const jwt = makeJwt({ sub: UUID, role: 'user', exp: Math.floor(Date.now() / 1000) + 3600 })
    mockLoginApi.mockResolvedValue({
      data: { access_token: jwt, token_type: 'bearer', expires_in: 900, user: { id: UUID, username: 'u', role: 'user', status: 'active' } },
    })
    mockGetMeApi.mockResolvedValue({
      data: { id: UUID, username: 'db-name', role: 'admin', status: 'active' },
    })

    await store.login('testuser', 'password')

    // 角色/用户名来自 /me（DB 当前状态），而非 token claim
    expect(store.user.username).toBe('db-name')
    expect(store.user.role).toBe('admin')
  })
})

describe('身份恢复：页面重载', () => {
  it('有 token 时调用 /me 恢复身份，不恢复持久化 user', async () => {
    const jwt = makeJwt({ sub: UUID, role: 'user', exp: Math.floor(Date.now() / 1000) + 3600 })
    // 预置 localStorage 中过期的 user（应立即被 /me 覆盖/忽略）
    localStorage.setItem('access_token', jwt)
    localStorage.setItem('user', JSON.stringify({ id: 999, username: 'stale', role: 'user' }))
    mockGetMeApi.mockResolvedValue({
      data: { id: UUID, username: 'db-name', role: 'user', status: 'active' },
    })

    vi.resetModules()
    setActivePinia(createPinia())
    const mod = await import('@/stores/auth')
    const store = mod.useAuthStore()

    // 页面重载由路由守卫调用 restoreSession 恢复身份（/me 为异步，须 await）
    await store.restoreSession()

    expect(mockGetMeApi).toHaveBeenCalled()
    expect(store.user.username).toBe('db-name')
    expect(store.user.id).toBe(UUID)
  })
})

describe('身份恢复：失败处理', () => {
  it('/me 返回 401 时清态并视为未登录', async () => {
    const store = useAuthStore()
    const jwt = makeJwt({ sub: UUID, role: 'user', exp: Math.floor(Date.now() / 1000) + 3600 })
    store.setTokens(jwt)
    mockGetMeApi.mockRejectedValue(new Error('Unauthorized'))

    await store.restoreSession()

    expect(store.token).toBe('')
    expect(store.user).toBeNull()
    expect(store.isLoggedIn).toBe(false)
  })
})

describe('身份恢复：Refresh 后重取与 isLoggedIn 门控', () => {
  it('Refresh 成功后重新调用 /me 获取最新角色与状态', async () => {
    const store = useAuthStore()
    const jwt = makeJwt({ sub: UUID, role: 'user', exp: Math.floor(Date.now() / 1000) + 3600 })
    store.setTokens(jwt)
    store.user = { id: UUID, username: 'old', role: 'user', status: 'active' }

    const newJwt = makeJwt({ sub: UUID, role: 'admin', exp: Math.floor(Date.now() / 1000) + 7200 })
    mockRefreshApi.mockResolvedValue({
      data: { access_token: newJwt, token_type: 'bearer', expires_in: 900 },
    })
    mockGetMeApi.mockResolvedValue({
      data: { id: UUID, username: 'old', role: 'admin', status: 'active' },
    })

    await store.refresh()

    expect(mockGetMeApi).toHaveBeenCalled()
    expect(store.user.role).toBe('admin')
  })

  it('/me 完成前 isLoggedIn 保持未就绪', async () => {
    const store = useAuthStore()
    const jwt = makeJwt({ sub: UUID, role: 'user', exp: Math.floor(Date.now() / 1000) + 3600 })
    store.setTokens(jwt)

    // 挂起 /me，断言期间 isLoggedIn 为 false
    let resolveMe
    mockGetMeApi.mockReturnValue(new Promise(r => { resolveMe = r }))
    const p = store.restoreSession()
    expect(store.isLoggedIn).toBe(false)

    resolveMe({ data: { id: UUID, username: 'u', role: 'user', status: 'active' } })
    await p
    expect(store.isLoggedIn).toBe(true)
  })
})