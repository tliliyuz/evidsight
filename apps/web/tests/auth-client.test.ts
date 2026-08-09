import type { AxiosAdapter, AxiosResponse } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { createApiClient, readCsrfToken, setAccessToken } from '@/api/client'

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
})
