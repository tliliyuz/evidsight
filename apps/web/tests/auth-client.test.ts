import axios, { type AxiosAdapter, type AxiosResponse } from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  createApiClient,
  getAccessToken,
  readCsrfToken,
  refreshAccessTokenWithRetry,
  registerAuthFailureHandler,
  setAccessToken,
} from '@/api/client'

function response(
  config: Parameters<AxiosAdapter>[0],
  status: number,
  data: unknown,
): AxiosResponse {
  return {
    config,
    status,
    statusText: String(status),
    headers: {},
    data,
  }
}

describe('API 客户端认证边界', () => {
  it('从 CSRF Cookie 精确读取并解码 token', () => {
    document.cookie = 'evidsight_csrf=token%2Fwith%2Bsymbols'
    expect(readCsrfToken()).toBe('token/with+symbols')
  })

  it('并发过期请求只刷新一次并携带新 Access Token 重放', async () => {
    let protectedCalls = 0
    const adapter: AxiosAdapter = vi.fn(async (config) => {
      protectedCalls += 1
      if (config.headers.Authorization === 'Bearer access-new') {
        return response(config, 200, { ok: true })
      }
      const error = new Error('expired') as Error & {
        response: AxiosResponse
        config: typeof config
      }
      error.config = config
      error.response = response(config, 401, { error: { error_code: 'AUTH_TOKEN_EXPIRED' } })
      throw error
    })
    const refresh = vi.fn().mockResolvedValue('access-new')
    const client = createApiClient({ adapter, refreshAccessToken: refresh })
    setAccessToken('access-old')

    const [first, second] = await Promise.all([client.get('/one'), client.get('/two')])

    expect(first.data).toEqual({ ok: true })
    expect(second.data).toEqual({ ok: true })
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(protectedCalls).toBe(4)
  })

  it('注册的认证失败处理器在刷新失败时被调用并清理 Access Token', async () => {
    const onAuthFailed = vi.fn()
    const unregister = registerAuthFailureHandler(onAuthFailed)
    const adapter: AxiosAdapter = vi.fn(async (config) => {
      const error = new Error('expired') as Error & {
        response: AxiosResponse
        config: typeof config
      }
      error.config = config
      error.response = response(config, 401, { error: { error_code: 'AUTH_TOKEN_EXPIRED' } })
      throw error
    })
    const refresh = vi.fn().mockRejectedValue(new Error('refresh down'))
    const client = createApiClient({ adapter, refreshAccessToken: refresh })
    setAccessToken('access-old')

    await expect(client.get('/one')).rejects.toThrow()
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(getAccessToken()).toBeNull()
    expect(onAuthFailed).toHaveBeenCalledTimes(1)
    unregister()
  })

  it('非过期 401（token 无效）清理 Access Token 并触发认证失败处理器，返回登录', async () => {
    const onAuthFailed = vi.fn()
    const unregister = registerAuthFailureHandler(onAuthFailed)
    const adapter: AxiosAdapter = vi.fn(async (config) => {
      const error = new Error('invalid') as Error & {
        response: AxiosResponse
        config: typeof config
      }
      error.config = config
      error.response = response(config, 401, { error: { error_code: 'AUTH_TOKEN_INVALID' } })
      throw error
    })
    const client = createApiClient({ adapter })
    setAccessToken('access-bad')

    await expect(client.get('/one')).rejects.toThrow()
    expect(getAccessToken()).toBeNull()
    expect(onAuthFailed).toHaveBeenCalledTimes(1)
    unregister()
  })
})

describe('并发刷新冲突（409 AUTH_REFRESH_CONCURRENT）重试', () => {
  afterEach(() => vi.useRealTimers())

  it('409 时短等后重试一次并成功（v1 信封）', async () => {
    vi.useFakeTimers()
    const post = vi.spyOn(axios, 'post')
    post
      .mockRejectedValueOnce({
        response: { status: 409, data: { error: { error_code: 'AUTH_REFRESH_CONCURRENT' } } },
      } as never)
      .mockResolvedValueOnce({ data: { access_token: 'access-new' } } as never)

    const promise = refreshAccessTokenWithRetry()
    await vi.runAllTimersAsync()
    const token = await promise

    expect(token).toBe('access-new')
    expect(getAccessToken()).toBe('access-new')
    expect(post).toHaveBeenCalledTimes(2)
  })

  it('E5011（legacy 信封）同样触发重试', async () => {
    vi.useFakeTimers()
    const post = vi.spyOn(axios, 'post')
    post
      .mockRejectedValueOnce({ response: { status: 409, data: { code: 'E5011' } } } as never)
      .mockResolvedValueOnce({ data: { access_token: 'access-new' } } as never)

    const promise = refreshAccessTokenWithRetry()
    await vi.runAllTimersAsync()
    const token = await promise

    expect(token).toBe('access-new')
    expect(post).toHaveBeenCalledTimes(2)
  })

  it('重试仍冲突时抛出，不清 Access Token（交认证失败处理器登出）', async () => {
    vi.useFakeTimers()
    setAccessToken('access-old')
    const post = vi.spyOn(axios, 'post')
    post.mockRejectedValue({
      response: { status: 409, data: { error: { error_code: 'AUTH_REFRESH_CONCURRENT' } } },
    } as never)

    // 同步挂上拒绝断言（先于 flush 假定时器），避免 Vitest 把 rejection 误判为未处理
    const promise = refreshAccessTokenWithRetry()
    const assertion = expect(promise).rejects.toThrow()
    await vi.runAllTimersAsync()
    await assertion

    expect(post).toHaveBeenCalledTimes(2)
    expect(getAccessToken()).toBe('access-old')
  })
})
