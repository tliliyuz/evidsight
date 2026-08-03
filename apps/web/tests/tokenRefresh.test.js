/** Token 自动刷新测试 — S6 事件③ v1 Cookie + CSRF 目标态（FRONTEND.md §5.1.2） */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

function makeJwt(payload) {
  const header = btoa(JSON.stringify({ alg: 'HS256' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.signature`
}

describe('Axios 拦截器 — 请求拦截器', () => {
  let api

  beforeEach(async () => {
    vi.clearAllMocks()
    localStorage.clear()
    vi.resetModules()
    const mod = await import('@/api/index')
    api = mod.default
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('请求拦截器自动附加 Authorization 头', async () => {
    localStorage.setItem('access_token', 'my-token')

    const mockAdapter = vi.fn().mockResolvedValue({ data: {} })
    api.defaults.adapter = mockAdapter

    await api.get('/test')

    const callConfig = mockAdapter.mock.calls[0][0]
    expect(callConfig.headers.Authorization).toBe('Bearer my-token')
  })

  it('无 token 时不附加 Authorization 头', async () => {
    const mockAdapter = vi.fn().mockResolvedValue({ data: {} })
    api.defaults.adapter = mockAdapter

    await api.get('/test')

    const callConfig = mockAdapter.mock.calls[0][0]
    expect(callConfig.headers.Authorization).toBeUndefined()
  })

  it('非 401 错误直接拒绝（不触发刷新）', async () => {
    localStorage.setItem('access_token', 'token')

    const error500 = {
      response: { status: 500, data: { code: 'E9001', message: '服务器错误' } },
      config: { headers: {} },
    }

    const mockAdapter = vi.fn().mockRejectedValue(error500)
    api.defaults.adapter = mockAdapter

    await expect(api.get('/test')).rejects.toEqual(error500)
    // Token 不应被清除
    expect(localStorage.getItem('access_token')).toBe('token')
  })

  it('401 + E5004 Token 无效时清除 token（并清理遗留 refresh_token）', async () => {
    localStorage.setItem('access_token', 'token')
    // 迁移期遗留键：清除本地状态时应一并清理（FRONTEND.md §5.1.2 不依赖它）
    localStorage.setItem('refresh_token', 'legacy')

    const error401 = {
      response: { status: 401, data: { code: 'E5004', message: 'Token 无效' } },
      config: { headers: {} },
    }

    const mockAdapter = vi.fn().mockRejectedValue(error401)
    api.defaults.adapter = mockAdapter

    await expect(api.get('/test')).rejects.toThrow()

    expect(localStorage.getItem('access_token')).toBeNull()
    expect(localStorage.getItem('refresh_token')).toBeNull()
  })

  it('401 + E5002 密码错误时不触发清除（透传给调用方）', async () => {
    localStorage.setItem('access_token', 'token')

    const error401 = {
      response: { status: 401, data: { code: 'E5002', message: '用户名或密码错误' } },
      config: { headers: {} },
    }

    const mockAdapter = vi.fn().mockRejectedValue(error401)
    api.defaults.adapter = mockAdapter

    await expect(api.get('/test')).rejects.toEqual(error401)

    // E5002 是业务错误（密码错误），token 不应被清除
    expect(localStorage.getItem('access_token')).toBe('token')
  })

  it('401 + E5003 → 刷新成功（v1 Cookie 刷新）后重放原请求', async () => {
    const oldJwt = 'expired-token'
    const newJwt = makeJwt({ sub: '1', exp: Math.floor(Date.now() / 1000) + 3600 })
    localStorage.setItem('access_token', oldJwt)

    const error401 = {
      response: { status: 401, data: { code: 'E5003', message: 'Token 过期' } },
      config: { headers: {}, _retry: false },
    }

    // v1 刷新：unwrapped RefreshV1Response
    const axios = (await import('axios')).default
    vi.spyOn(axios, 'post').mockResolvedValue({
      data: { access_token: newJwt, token_type: 'bearer', expires_in: 900 },
    })

    const mockAdapter = vi.fn()
      .mockRejectedValueOnce(error401)   // 原请求 401
      .mockResolvedValueOnce({ data: { replayed: true } })  // 刷新后重放
      .mockResolvedValueOnce({ data: { id: 'u', username: 'u', role: 'user', status: 'active' } })  // refreshToken 内 fetchMe
    api.defaults.adapter = mockAdapter

    const res = await api.get('/test')

    expect(res.data.replayed).toBe(true)
    // 重放请求使用新 token
    const replayConfig = mockAdapter.mock.calls[1][0]
    expect(replayConfig.headers.Authorization).toBe(`Bearer ${newJwt}`)
    expect(localStorage.getItem('access_token')).toBe(newJwt)
    // Refresh Token 不写入 localStorage
    expect(localStorage.getItem('refresh_token')).toBeNull()
  })

  it('401 + E5003 且刷新失败 → 清除 token（CSRF/Refresh Cookie 缺失按刷新失败处理）', async () => {
    localStorage.setItem('access_token', 'expired-token')

    const error401 = {
      response: { status: 401, data: { code: 'E5003', message: 'Token 过期' } },
      config: { headers: {}, _retry: false },
    }

    const mockAdapter = vi.fn().mockRejectedValue(error401)
    api.defaults.adapter = mockAdapter

    // 刷新端点失败（如 CSRF Cookie 缺失 → E5004/E5008）
    const axios = (await import('axios')).default
    vi.spyOn(axios, 'post').mockRejectedValue(new Error('刷新失败'))

    await expect(api.get('/test')).rejects.toThrow('刷新失败')

    expect(localStorage.getItem('access_token')).toBeNull()
  })
})

describe('authStore Token 管理（v1 Cookie 目标态）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    vi.resetModules()
  })

  it('setTokens 只更新 access_token，不写入 refresh_token', async () => {
    const { createPinia, setActivePinia } = await import('pinia')
    setActivePinia(createPinia())

    const { useAuthStore } = await import('@/stores/auth')
    const store = useAuthStore()

    store.setTokens('new-access')

    expect(store.token).toBe('new-access')
    expect(localStorage.getItem('access_token')).toBe('new-access')
    // S6：Refresh Token 不得写入 localStorage（FRONTEND.md §5.1.2）
    expect(localStorage.getItem('refresh_token')).toBeNull()
  })

  it('logout 清除全部本地状态（含遗留 refresh_token）', async () => {
    const { createPinia, setActivePinia } = await import('pinia')
    setActivePinia(createPinia())

    const { useAuthStore } = await import('@/stores/auth')
    const store = useAuthStore()

    store.setTokens('access')
    await store.logout()

    expect(store.token).toBe('')
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(localStorage.getItem('refresh_token')).toBeNull()
  })

  it('logout 后端吊销失败时仍清除本地状态', async () => {
    // Mock fetch to simulate backend failure
    const originalFetch = global.fetch
    global.fetch = vi.fn().mockRejectedValue(new Error('网络错误'))

    const { createPinia, setActivePinia } = await import('pinia')
    setActivePinia(createPinia())

    const { useAuthStore } = await import('@/stores/auth')
    const store = useAuthStore()

    store.setTokens('access')
    await store.logout()

    // 即使后端失败，本地状态也要清除
    expect(store.token).toBe('')
    expect(store.isLoggedIn).toBe(false)
    expect(localStorage.getItem('access_token')).toBeNull()

    global.fetch = originalFetch
  })

  it('从 localStorage 恢复 token 状态（身份经 /me 重建）', async () => {
    localStorage.setItem('access_token', 'stored-access')
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'test', role: 'user' }))

    const { createPinia, setActivePinia } = await import('pinia')
    setActivePinia(createPinia())

    const { useAuthStore } = await import('@/stores/auth')
    const store = useAuthStore()

    expect(store.token).toBe('stored-access')
    // 未调用 /me 前 isLoggedIn 未就绪
    expect(store.isLoggedIn).toBe(false)
  })

  it('isLoggedIn 在无 token 时为 false', async () => {
    const { createPinia, setActivePinia } = await import('pinia')
    setActivePinia(createPinia())

    const { useAuthStore } = await import('@/stores/auth')
    const store = useAuthStore()

    expect(store.isLoggedIn).toBe(false)
  })

  it('isAdmin 在用户角色为 admin 时为 true', async () => {
    localStorage.setItem('access_token', 'token')
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'admin', role: 'admin' }))

    const { createPinia, setActivePinia } = await import('pinia')
    setActivePinia(createPinia())

    const { useAuthStore } = await import('@/stores/auth')
    const store = useAuthStore()

    // 角色来自 /me（DB 当前状态），而非 localStorage 持久化 user
    expect(store.isAdmin).toBe(false)
  })
})

describe('conversationStore 会话管理', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.resetModules()
  })

  it('初始状态为空列表', async () => {
    const { createPinia, setActivePinia } = await import('pinia')
    setActivePinia(createPinia())

    const { useConversationStore } = await import('@/stores/conversation')
    const store = useConversationStore()

    expect(store.conversations).toEqual([])
    expect(store.loading).toBe(false)
  })

  it('addConversation 新增会话到列表头部', async () => {
    const { createPinia, setActivePinia } = await import('pinia')
    setActivePinia(createPinia())

    const { useConversationStore } = await import('@/stores/conversation')
    const store = useConversationStore()

    store.addConversation({ uuid: 'uuid-1', title: '会话1' })
    store.addConversation({ uuid: 'uuid-2', title: '会话2' })

    expect(store.conversations).toHaveLength(2)
    expect(store.conversations[0].uuid).toBe('uuid-2')  // 新增的在头部
    expect(store.conversations[1].uuid).toBe('uuid-1')
  })

  it('addConversation 去重：重复 ID 更新而非新增', async () => {
    const { createPinia, setActivePinia } = await import('pinia')
    setActivePinia(createPinia())

    const { useConversationStore } = await import('@/stores/conversation')
    const store = useConversationStore()

    store.addConversation({ uuid: 'uuid-dup', title: '原标题' })
    store.addConversation({ uuid: 'uuid-dup', title: '更新标题' })

    expect(store.conversations).toHaveLength(1)
    expect(store.conversations[0].title).toBe('更新标题')
  })

  it('updateConversationTitle 更新指定会话标题', async () => {
    const { createPinia, setActivePinia } = await import('pinia')
    setActivePinia(createPinia())

    const { useConversationStore } = await import('@/stores/conversation')
    const store = useConversationStore()

    store.addConversation({ uuid: 'uuid-title', title: '旧标题' })
    store.updateConversationTitle('uuid-title', '新标题')

    expect(store.conversations[0].title).toBe('新标题')
  })

  it('updateConversationTitle 不存在的 ID 不报错', async () => {
    const { createPinia, setActivePinia } = await import('pinia')
    setActivePinia(createPinia())

    const { useConversationStore } = await import('@/stores/conversation')
    const store = useConversationStore()

    store.addConversation({ uuid: 'uuid-noexist', title: '标题' })
    store.updateConversationTitle('uuid-nonexist', '不存在')

    expect(store.conversations[0].title).toBe('标题')
  })

  it('reset 清空所有状态', async () => {
    const { createPinia, setActivePinia } = await import('pinia')
    setActivePinia(createPinia())

    const { useConversationStore } = await import('@/stores/conversation')
    const store = useConversationStore()

    store.addConversation({ id: 1, title: '会话' })
    store.reset()

    expect(store.conversations).toEqual([])
    expect(store.loading).toBe(false)
  })

  it('groupedConversations 按时间正确分组', async () => {
    const { createPinia, setActivePinia } = await import('pinia')
    setActivePinia(createPinia())

    const { useConversationStore } = await import('@/stores/conversation')
    const store = useConversationStore()

    const now = new Date()
    const today = now.toISOString()
    const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString()
    const threeDaysAgo = new Date(now.getTime() - 3 * 24 * 60 * 60 * 1000).toISOString()
    const tenDaysAgo = new Date(now.getTime() - 10 * 24 * 60 * 60 * 1000).toISOString()

    store.conversations = [
      { id: 1, title: '今天', updated_at: today },
      { id: 2, title: '昨天', updated_at: yesterday },
      { id: 3, title: '三天前', updated_at: threeDaysAgo },
      { id: 4, title: '十天前', updated_at: tenDaysAgo },
    ]

    const groups = store.groupedConversations
    expect(groups.today).toHaveLength(1)
    expect(groups.today[0].title).toBe('今天')
    expect(groups.yesterday).toHaveLength(1)
    expect(groups.yesterday[0].title).toBe('昨天')
    expect(groups.recent).toHaveLength(1)
    expect(groups.recent[0].title).toBe('三天前')
    expect(groups.older).toHaveLength(1)
    expect(groups.older[0].title).toBe('十天前')
  })
})
