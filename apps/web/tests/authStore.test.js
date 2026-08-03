/** auth store 单元测试 — JWT 解析、刷新定时器、并发守卫、登录/注册/登出 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// Mock API 层
const mockLoginApi = vi.fn()
const mockRegisterApi = vi.fn()
const mockRefreshApi = vi.fn()
const mockLogoutApi = vi.fn()
const mockGetMeApi = vi.fn()

vi.mock('@/api/auth', () => ({
  login: (...args) => mockLoginApi(...args),
  register: (...args) => mockRegisterApi(...args),
  refreshToken: (...args) => mockRefreshApi(...args),
  logout: (...args) => mockLogoutApi(...args),
  getMe: (...args) => mockGetMeApi(...args),
}))

// 生成 JWT token 辅助函数
function makeJwt(payload) {
  const header = btoa(JSON.stringify({ alg: 'HS256' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.signature`
}

let useAuthStore

beforeEach(async () => {
  vi.clearAllMocks()
  localStorage.clear()
  vi.resetModules()
  // 默认 safe mock：防止未配置时 refresh() 访问 undefined.data
  mockRefreshApi.mockResolvedValue({ data: { data: { access_token: '', refresh_token: '' } } })
  // 默认 safe mock：防止未配置时 fetchMe() 访问 undefined.data
  mockGetMeApi.mockResolvedValue({ data: { id: 'u', username: 'u', role: 'user', status: 'active' } })
  setActivePinia(createPinia())
  const mod = await import('@/stores/auth')
  useAuthStore = mod.useAuthStore
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

// =====================================================
// 身份获取（经 /me，而非 JWT Claim）
// =====================================================
describe('身份获取（/me）', () => {
  it('登录成功后从 /me 获取 user（id 为 UUID 字符串，不做数值解析）', async () => {
    const store = useAuthStore()
    const jwt = makeJwt({ sub: '42', username: 'ignored', role: 'user' })
    // 通过 loginAction 完整链路验证：user 来自 /me，而非 JWT Claim
    mockLoginApi.mockResolvedValue({
      data: { data: { access_token: jwt, refresh_token: 'refresh-xxx' } },
    })
    mockGetMeApi.mockResolvedValue({
      data: { id: '550e8400-e29b-41d4-a716-446655440001', username: 'testuser', role: 'admin', status: 'active' },
    })
    await store.login('testuser', 'password')
    expect(store.user.id).toBe('550e8400-e29b-41d4-a716-446655440001')
    expect(store.user.username).toBe('testuser')
    expect(store.user.role).toBe('admin')
  })

  it('user 不来自 JWT Claim（token 中 username 被忽略，高度以 /me 为准）', async () => {
    const store = useAuthStore()
    const jwt = makeJwt({ sub: '42', username: 'claim-user', role: 'user' })
    mockLoginApi.mockResolvedValue({
      data: { data: { access_token: jwt, refresh_token: 'refresh-xxx' } },
    })
    mockGetMeApi.mockResolvedValue({
      data: { id: '550e8400-e29b-41d4-a716-446655440001', username: 'db-user', role: 'user', status: 'active' },
    })
    await store.login('x', 'pass')
    expect(store.user.username).toBe('db-user')
  })

  it('/me 失败时登录流程抛错（身份无法建立）', async () => {
    const store = useAuthStore()
    const jwt = makeJwt({ sub: '1', username: 'u', role: 'user' })
    mockLoginApi.mockResolvedValue({
      data: { data: { access_token: jwt, refresh_token: 'refresh-xxx' } },
    })
    mockGetMeApi.mockRejectedValue(new Error('Unauthorized'))
    await expect(store.login('u', 'pass')).rejects.toThrow('Unauthorized')
  })

  it('登录后 /me 失败时清除刚保存的 Token（不留半登录态）', async () => {
    const store = useAuthStore()
    const jwt = makeJwt({ sub: '42', role: 'user', exp: Math.floor(Date.now() / 1000) + 3600 })
    mockLoginApi.mockResolvedValue({
      data: { data: { access_token: jwt, refresh_token: 'refresh-abc' } },
    })
    mockGetMeApi.mockRejectedValue(new Error('Unauthorized'))

    await expect(store.login('u', 'pass')).rejects.toThrow('Unauthorized')

    // 身份建立失败 → 清除 token 对与 user，按未登录处理（FRONTEND.md §5.1.1）
    expect(store.token).toBe('')
    expect(store.refreshToken).toBe('')
    expect(store.user).toBeNull()
    expect(store.isLoggedIn).toBe(false)
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(localStorage.getItem('refresh_token')).toBeNull()
  })
})

// =====================================================
// scheduleRefresh() / clearRefreshTimer()
// =====================================================
describe('scheduleRefresh() / clearRefreshTimer()', () => {
  it('根据 JWT exp 计算定时器延迟（提前 60s）', () => {
    vi.useFakeTimers()
    const store = useAuthStore()
    const now = Date.now()
    // exp = now + 120s（提前 60s → 延迟 60s）
    const exp = Math.floor((now + 120 * 1000) / 1000)
    const jwt = makeJwt({ sub: '1', username: 'u', role: 'user', exp })

    // 防止 timer 触发时 refresh() 因 mock 未就绪而抛错
    mockRefreshApi.mockReturnValue(new Promise(() => {}))  // 永远 pending
    store.setTokens(jwt, 'refresh-xxx')
    const countBefore = vi.getTimerCount()
    store.scheduleRefresh()
    expect(vi.getTimerCount()).toBe(countBefore + 1)
    vi.useRealTimers()
  })

  it('delay < 5s 时保底为 5000ms', () => {
    vi.useFakeTimers()
    // 清除 store 初始化时创建的定时器
    vi.clearAllTimers()
    const store = useAuthStore()
    const now = Date.now()
    // exp = now + 3s（提前 60s → -57s，取最大 5s）
    const exp = Math.floor((now + 3 * 1000) / 1000)
    const jwt = makeJwt({ sub: '1', username: 'u', role: 'user', exp })

    store.setTokens(jwt, 'refresh-xxx')
    mockRefreshApi.mockReturnValue(new Promise(() => {}))
    const countBefore = vi.getTimerCount()
    store.scheduleRefresh()
    expect(vi.getTimerCount()).toBe(countBefore + 1)
    vi.useRealTimers()
  })

  it('scheduleRefresh 重复调用只保留一个定时器', () => {
    vi.useFakeTimers()
    vi.clearAllTimers()
    const store = useAuthStore()

    const now = Date.now()
    const exp = Math.floor((now + 120 * 1000) / 1000)
    const jwt = makeJwt({ sub: '1', username: 'u', role: 'user', exp })
    store.setTokens(jwt, 'refresh-xxx')
    mockRefreshApi.mockReturnValue(new Promise(() => {}))

    // 调用两次 scheduleRefresh
    const countBefore = vi.getTimerCount()
    store.scheduleRefresh()
    store.scheduleRefresh()

    // 应只增加一个定时器（第二次调用先清除旧的再设新的）
    expect(vi.getTimerCount()).toBe(countBefore + 1)
    vi.useRealTimers()
  })

  it('JWT 解析失败不设定时器且不抛异常', () => {
    const store = useAuthStore()
    store.token = 'invalid.jwt'
    expect(() => store.scheduleRefresh()).not.toThrow()
  })
})

// =====================================================
// _refreshing 并发守卫
// =====================================================
describe('refresh() 并发守卫', () => {
  it('单次刷新成功更新 token 并重取 /me', async () => {
    const store = useAuthStore()
    const oldJwt = makeJwt({ sub: '1', username: 'old', role: 'user', exp: Math.floor(Date.now() / 1000) + 3600 })
    store.setTokens(oldJwt, 'old-refresh')

    const newJwt = makeJwt({ sub: '1', username: 'new', role: 'admin', exp: Math.floor(Date.now() / 1000) + 7200 })
    mockRefreshApi.mockResolvedValue({
      data: { data: { access_token: newJwt, refresh_token: 'new-refresh' } },
    })
    mockGetMeApi.mockResolvedValue({
      data: { id: '550e8400-e29b-41d4-a716-446655440001', username: 'new', role: 'admin', status: 'active' },
    })

    const result = await store.refresh()
    expect(result).toBe(true)
    expect(mockRefreshApi).toHaveBeenCalledTimes(1)
    expect(mockGetMeApi).toHaveBeenCalledTimes(1)
    expect(store.user.username).toBe('new')
    expect(store.user.role).toBe('admin')
    expect(store.token).toBe(newJwt)
    expect(store.refreshToken).toBe('new-refresh')
  })

  it('并发刷新：第二个调用直接返回 true 不调 API', async () => {
    const store = useAuthStore()
    const jwt = makeJwt({ sub: '1', username: 'u', role: 'user', exp: Math.floor(Date.now() / 1000) + 3600 })
    store.setTokens(jwt, 'old-refresh')

    // 让第一次刷新挂起
    let resolveRefresh
    mockRefreshApi.mockReturnValue(new Promise(r => { resolveRefresh = r }))

    const p1 = store.refresh()
    const p2 = store.refresh()

    expect(mockRefreshApi).toHaveBeenCalledTimes(1)
    expect(await p2).toBe(true)

    // 完成第一次刷新
    const newJwt = makeJwt({ sub: '1', username: 'u', role: 'user', exp: Math.floor(Date.now() / 1000) + 7200 })
    resolveRefresh({ data: { data: { access_token: newJwt, refresh_token: 'new-refresh' } } })
    await p1
  })

  it('刷新 API 失败时清除所有状态并抛异常', async () => {
    const store = useAuthStore()
    const jwt = makeJwt({ sub: '1', username: 'u', role: 'user', exp: Math.floor(Date.now() / 1000) + 3600 })
    store.setTokens(jwt, 'old-refresh')
    store.user = { id: 1, username: 'u', role: 'user' }

    mockRefreshApi.mockRejectedValue(new Error('Refresh failed'))

    await expect(store.refresh()).rejects.toThrow('Refresh failed')
    expect(store.token).toBe('')
    expect(store.refreshToken).toBe('')
    expect(store.user).toBeNull()
    expect(store.isLoggedIn).toBe(false)
  })
})

// =====================================================
// loginAction() / registerAction()
// =====================================================
describe('loginAction() / registerAction()', () => {
  it('登录成功：设置 token、经 /me 建立 user、持久化', async () => {
    const store = useAuthStore()
    const jwt = makeJwt({ sub: '42', username: 'loginuser', role: 'user', exp: Math.floor(Date.now() / 1000) + 3600 })
    mockLoginApi.mockResolvedValue({
      data: { data: { access_token: jwt, refresh_token: 'refresh-abc' } },
    })
    mockGetMeApi.mockResolvedValue({
      data: { id: '550e8400-e29b-41d4-a716-446655440001', username: 'loginuser', role: 'admin', status: 'active' },
    })

    const user = await store.login('loginuser', 'password123')

    expect(user.id).toBe('550e8400-e29b-41d4-a716-446655440001')
    expect(user.username).toBe('loginuser')
    expect(user.role).toBe('admin')
    expect(store.token).toBe(jwt)
    expect(store.refreshToken).toBe('refresh-abc')
    expect(store.isLoggedIn).toBe(true)
    expect(localStorage.getItem('access_token')).toBe(jwt)
    expect(localStorage.getItem('refresh_token')).toBe('refresh-abc')
    expect(localStorage.getItem('user')).toBe(JSON.stringify(user))
  })

  it('登录 API 失败时抛异常，不破坏已有状态', async () => {
    const store = useAuthStore()
    // 预置登录态（经 /me 建立，isLoggedIn 需 _meReady）
    const oldJwt = makeJwt({ sub: '1', username: 'existing', role: 'user', exp: Math.floor(Date.now() / 1000) + 3600 })
    store.setTokens(oldJwt, 'existing-refresh')
    mockGetMeApi.mockResolvedValue({
      data: { id: '550e8400-e29b-41d4-a716-446655440001', username: 'existing', role: 'user', status: 'active' },
    })
    await store.restoreSession()

    mockLoginApi.mockRejectedValue(new Error('密码错误'))

    await expect(store.login('bad', 'wrong')).rejects.toThrow('密码错误')
    // 已有状态不变
    expect(store.token).toBe(oldJwt)
    expect(store.isLoggedIn).toBe(true)
  })

  it('注册成功返回 API 数据，不设置 token', async () => {
    const store = useAuthStore()
    mockRegisterApi.mockResolvedValue({
      data: { data: { id: 99, username: 'newuser' } },
    })

    const result = await store.register('newuser', 'password')
    expect(result.id).toBe(99)
    expect(store.token).toBe('')
    expect(store.isLoggedIn).toBe(false)
  })

  it('注册 API 失败时抛异常', async () => {
    const store = useAuthStore()
    mockRegisterApi.mockRejectedValue(new Error('用户名已存在'))

    await expect(store.register('dup', 'password')).rejects.toThrow('用户名已存在')
    expect(store.isLoggedIn).toBe(false)
  })
})

// =====================================================
// logout()
// =====================================================
describe('logout()', () => {
  it('正常登出：调 API 吊销 + 清除所有本地状态', async () => {
    const store = useAuthStore()
    const jwt = makeJwt({ sub: '1', username: 'u', role: 'user' })
    store.setTokens(jwt, 'refresh-abc')
    store.user = { id: 1, username: 'u', role: 'user' }
    mockLogoutApi.mockResolvedValue({ data: {} })

    await store.logout()

    expect(mockLogoutApi).toHaveBeenCalledWith('refresh-abc')
    expect(store.token).toBe('')
    expect(store.refreshToken).toBe('')
    expect(store.user).toBeNull()
    expect(store.isLoggedIn).toBe(false)
    expect(localStorage.getItem('access_token')).toBeNull()
  })

  it('登出 API 失败仍清除本地状态（优雅降级）', async () => {
    const store = useAuthStore()
    store.setTokens('token', 'refresh-xyz')
    mockLogoutApi.mockRejectedValue(new Error('网络错误'))

    await store.logout()

    expect(store.token).toBe('')
    expect(store.isLoggedIn).toBe(false)
  })

  it('无 refresh_token 时不调 API，直接清除状态', async () => {
    const store = useAuthStore()
    store.setTokens('token', '')  // 无 refresh_token

    await store.logout()

    expect(mockLogoutApi).not.toHaveBeenCalled()
    expect(store.token).toBe('')
    expect(store.isLoggedIn).toBe(false)
  })
})

// =====================================================
// Store 初始化恢复
// =====================================================
describe('Store 初始化恢复', () => {
  it('localStorage 有 token 时经 /me 恢复身份（不恢复持久化 user）', async () => {
    const jwt = makeJwt({ sub: '5', username: 'cached', role: 'user', exp: Math.floor(Date.now() / 1000) + 3600 })
    // 持久化的 user 应立即被 /me 覆盖/忽略
    localStorage.setItem('access_token', jwt)
    localStorage.setItem('refresh_token', 'cached-refresh')
    localStorage.setItem('user', JSON.stringify({ id: 99, username: 'stale', role: 'user' }))
    mockGetMeApi.mockResolvedValue({
      data: { id: '550e8400-e29b-41d4-a716-446655440001', username: 'fresh', role: 'user', status: 'active' },
    })

    vi.resetModules()
    setActivePinia(createPinia())
    const mod = await import('@/stores/auth')
    const store = mod.useAuthStore()

    // 身份未就绪前 isLoggedIn=false
    expect(store.isLoggedIn).toBe(false)
    await store.restoreSession()
    expect(store.isLoggedIn).toBe(true)
    expect(store.token).toBe(jwt)
    expect(store.user.id).toBe('550e8400-e29b-41d4-a716-446655440001')
    expect(store.user.username).toBe('fresh')
  })

  it('空 localStorage 时未登录', async () => {
    vi.resetModules()
    setActivePinia(createPinia())
    const mod = await import('@/stores/auth')
    const store = mod.useAuthStore()

    expect(store.isLoggedIn).toBe(false)
    expect(store.isAdmin).toBe(false)
    expect(store.user).toBeNull()
  })

  it('isAdmin 根据 /me 返回的 role 正确计算', async () => {
    const jwt = makeJwt({ sub: '1', username: 'admin', role: 'admin', exp: Math.floor(Date.now() / 1000) + 3600 })
    localStorage.setItem('access_token', jwt)
    localStorage.setItem('refresh_token', 'r')
    mockGetMeApi.mockResolvedValue({
      data: { id: '550e8400-e29b-41d4-a716-446655440002', username: 'admin', role: 'admin', status: 'active' },
    })

    vi.resetModules()
    setActivePinia(createPinia())
    const mod = await import('@/stores/auth')
    const store = mod.useAuthStore()

    await store.restoreSession()
    expect(store.isAdmin).toBe(true)
  })
})
