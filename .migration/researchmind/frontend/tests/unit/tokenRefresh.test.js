// 前端 Token 刷新测试 — 覆盖 src/api/index.js 的 Axios 拦截器
// 对齐 TESTING_STRATEGY.md §5.1：Token 自动刷新（E1003/E1004）、并发请求防抖、错误码处理、刷新失败跳转 /login

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// 拦截真实网络：mock axios 模块整体
vi.mock('axios', async () => {
  const actual = await vi.importActual('axios')
  return {
    ...actual,
    default: {
      ...actual.default,
      create: vi.fn(() => actual.default.create()),
      post: vi.fn(),
    },
  }
})

import axios from 'axios'
// 在导入 api/index.js 之前清空 localStorage，避免触发 store 定时器副作用
localStorage.clear()

import api from '@/api/index'

function make401Error(code) {
  return {
    response: {
      status: 401,
      data: { code, message: 'err' },
    },
    config: { url: '/api/research', headers: {}, _retry: undefined },
  }
}

describe('Axios 拦截器 Token 刷新', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
    axios.post.mockReset()
    // Mock api 适配器：使 api(config) 请求重放直接 resolve，避免 jsdom xhr→Network Error
    api.defaults.adapter = vi.fn().mockResolvedValue({ data: { ok: true }, status: 200 })
    delete window.location
    window.location = { pathname: '/research', href: '' }
  })

  it('请求拦截器_自动附加Bearer Token', async () => {
    localStorage.setItem('access_token', 'my-token')
    // 拦截 create 返回实例的请求 —— 用 spy 监听底层
    const dispatchSpy = vi.spyOn(axios, 'post').mockResolvedValue({ data: {} })
    // 通过拦截器路径：直接用 api.post 触发请求拦截器
    // 用 axios-mock 比较复杂，改为验证拦截器逻辑：手动调用请求拦截函数
    // 这里验证 token 存在时 config 注入 Authorization
    const reqInterceptor = api.interceptors.request.handlers[0]
    const config = { headers: {} }
    const result = reqInterceptor.fulfilled(config)
    expect(result.headers.Authorization).toBe('Bearer my-token')
  })

  it('无token_请求拦截器不附加Authorization', async () => {
    const reqInterceptor = api.interceptors.request.handlers[0]
    const config = { headers: {} }
    const result = reqInterceptor.fulfilled(config)
    expect(result.headers.Authorization).toBeUndefined()
  })

  it('E1003过期_触发刷新并重放原请求', async () => {
    localStorage.setItem('refresh_token', 'old-rt')
    const newAt = 'new-access-token'
    axios.post.mockResolvedValueOnce({
      data: { data: { access_token: newAt, refresh_token: 'new-rt' } },
    })

    const error = make401Error('E1003')
    const respInterceptor = api.interceptors.response.handlers[0]

    await expect(respInterceptor.rejected(error)).resolves.toBeDefined()
    // doRefresh 调用了原始 axios.post('/api/auth/refresh')
    expect(axios.post).toHaveBeenCalledWith(
      '/api/auth/refresh',
      { refresh_token: 'old-rt' },
      expect.objectContaining({ headers: { 'Content-Type': 'application/json' } })
    )
    // 新 token 写入 localStorage
    expect(localStorage.getItem('access_token')).toBe(newAt)
    // 原请求重放成功（adapter mock resolves）
  })

  it('E1002密码错误_不触发刷新_直接透传错误', async () => {
    const error = make401Error('E1002')
    const respInterceptor = api.interceptors.response.handlers[0]
    await expect(respInterceptor.rejected(error)).rejects.toBe(error)
    expect(axios.post).not.toHaveBeenCalled()
  })

  it('E1010用户禁用_不触发刷新_直接透传', async () => {
    const error = make401Error('E1010')
    const respInterceptor = api.interceptors.response.handlers[0]
    await expect(respInterceptor.rejected(error)).rejects.toBe(error)
    expect(axios.post).not.toHaveBeenCalled()
  })

  it('已重试的请求_不再重试_直接拒绝', async () => {
    const error = make401Error('E1003')
    error.config._retry = true
    const respInterceptor = api.interceptors.response.handlers[0]
    await expect(respInterceptor.rejected(error)).rejects.toBe(error)
    expect(axios.post).not.toHaveBeenCalled()
  })

  it('刷新失败_清除token并跳转login', async () => {
    localStorage.setItem('access_token', 'expired-at')
    localStorage.setItem('refresh_token', 'old-rt')
    // 当前不在 /login，应触发跳转
    window.location.pathname = '/research'
    axios.post.mockRejectedValue(new Error('refresh failed'))

    const error = make401Error('E1003')
    const respInterceptor = api.interceptors.response.handlers[0]

    await expect(respInterceptor.rejected(error)).rejects.toBeDefined()
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(localStorage.getItem('refresh_token')).toBeNull()
    expect(window.location.href).toBe('/login')
  })

  it('非401错误_直接拒绝不刷新', async () => {
    const error = { response: { status: 500, data: { code: 'E9001' } }, config: {} }
    const respInterceptor = api.interceptors.response.handlers[0]
    await expect(respInterceptor.rejected(error)).rejects.toBeDefined()
    expect(axios.post).not.toHaveBeenCalled()
  })

  it('并发多个E1003请求_仅刷新一次_排队请求重放', async () => {
    localStorage.setItem('refresh_token', 'old-rt')
    const newAt = 'new-access-token'
    // doRefresh 仅应调用一次
    axios.post.mockResolvedValueOnce({
      data: { data: { access_token: newAt, refresh_token: 'new-rt' } },
    })

    const respInterceptor = api.interceptors.response.handlers[0]

    const e1 = make401Error('E1003')
    const e2 = make401Error('E1003')
    e2.config = { url: '/api/research2', headers: {} }

    const [r1, r2] = await Promise.allSettled([
      respInterceptor.rejected(e1),
      respInterceptor.rejected(e2),
    ])
    // 两个请求最终都通过 adapter mock 重放成功
    expect(r1.status).toBe('fulfilled')
    expect(r2.status).toBe('fulfilled')
    // refresh 仅调用一次（防并发）
    expect(axios.post).toHaveBeenCalledTimes(1)
  })
})
