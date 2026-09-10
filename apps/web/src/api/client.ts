import axios, {
  AxiosError,
  type AxiosAdapter,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from 'axios'

const CSRF_COOKIE_NAME = 'evidsight_csrf'
let accessToken: string | null = null

export function getAccessToken(): string | null {
  return accessToken
}

export function setAccessToken(token: string | null): void {
  accessToken = token
}

export function readCsrfToken(): string | null {
  const prefix = `${CSRF_COOKIE_NAME}=`
  const encoded = document.cookie
    .split(';')
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix))
    ?.slice(prefix.length)
  return encoded ? decodeURIComponent(encoded) : null
}

function errorCode(error: AxiosError): string | undefined {
  const body = error.response?.data as { error?: { error_code?: string } } | undefined
  return body?.error?.error_code
}

const REFRESH_CONCURRENT_MAX_ATTEMPTS = 2
const REFRESH_CONCURRENT_RETRY_DELAY_MS = 300

function isConcurrentRefreshConflict(error: AxiosError): boolean {
  const body = error.response?.data as
    { error?: { error_code?: string }; code?: string } | undefined
  return body?.error?.error_code === 'AUTH_REFRESH_CONCURRENT' || body?.code === 'E5011'
}

async function postRefresh(): Promise<{ access_token: string }> {
  const csrfToken = readCsrfToken()
  if (!csrfToken) {
    throw new Error('缺少 CSRF Token')
  }
  const response = await axios.post<{ access_token: string }>('/api/v1/auth/refresh', null, {
    headers: { 'X-CSRF-Token': csrfToken },
    withCredentials: true,
  })
  return response.data
}

/** 刷新 Access Token；并发刷新冲突（409 AUTH_REFRESH_CONCURRENT）时短等后重试一次。
 *  并发冲突是良性竞态（多标签页同时用同一 Cookie 刷新）：胜者响应已把新 Cookie 写入
 *  jar，重试即用新值恢复（FRONTEND §11 / IA-011）。其余失败原样抛出交调用方登出。 */
export async function refreshAccessTokenWithRetry(attempt = 0): Promise<string> {
  try {
    const { access_token } = await postRefresh()
    setAccessToken(access_token)
    return access_token
  } catch (error) {
    const axiosError = error as AxiosError
    if (isConcurrentRefreshConflict(axiosError) && attempt + 1 < REFRESH_CONCURRENT_MAX_ATTEMPTS) {
      await new Promise((resolve) => setTimeout(resolve, REFRESH_CONCURRENT_RETRY_DELAY_MS))
      return refreshAccessTokenWithRetry(attempt + 1)
    }
    throw error
  }
}

type RetriableConfig = InternalAxiosRequestConfig & { __authRetried?: boolean }

// 生产认证失败处理器（FRONTEND §11：401/刷新失败 → 清理敏感状态并返回登录）。
// 由应用根组件通过 registerAuthFailureHandler 接线到 authSession（避免 client↔authSession 循环依赖）。
let authFailureHandler: (() => void) | undefined

/** 注册认证失败处理器，返回注销函数。传 null 可清除。 */
export function registerAuthFailureHandler(handler: (() => void) | null): () => void {
  authFailureHandler = handler ?? undefined
  return () => {
    if (authFailureHandler === handler) authFailureHandler = undefined
  }
}

type ClientOptions = {
  adapter?: AxiosAdapter
  refreshAccessToken?: () => Promise<string>
  onAuthenticationFailed?: () => void
}

export function createApiClient(options: ClientOptions = {}): AxiosInstance {
  const client = axios.create({
    adapter: options.adapter,
    withCredentials: true,
  })
  let refreshInFlight: Promise<string> | null = null

  client.interceptors.request.use((config) => {
    if (accessToken) {
      config.headers.Authorization = `Bearer ${accessToken}`
    }
    return config
  })

  client.interceptors.response.use(undefined, async (rawError: unknown) => {
    const error = rawError as AxiosError
    const config = error.config as RetriableConfig | undefined
    const is401 = error.response?.status === 401
    const isExpired = errorCode(error) === 'AUTH_TOKEN_EXPIRED'

    // Access Token 过期（E5003）：并发共享单次刷新并携带新 token 重放。
    if (is401 && isExpired && config && !config.__authRetried) {
      config.__authRetried = true
      refreshInFlight ??= (options.refreshAccessToken ?? refreshAccessTokenWithRetry)()
        .then((token) => {
          setAccessToken(token)
          return token
        })
        .catch((refreshError) => {
          setAccessToken(null)
          ;(options.onAuthenticationFailed ?? authFailureHandler)?.()
          throw refreshError
        })
        .finally(() => {
          refreshInFlight = null
        })

      const token = await refreshInFlight
      config.headers.Authorization = `Bearer ${token}`
      return client.request(config)
    }

    // 其余 401（token 无效 E5004/用户禁用 E5010 等）或刷新失败不可恢复：
    // 清理 Access Token 并触发认证失败处理器返回登录（FRONTEND §11），避免会话卡死在「已登录但无 token」。
    if (is401) {
      setAccessToken(null)
      ;(options.onAuthenticationFailed ?? authFailureHandler)?.()
    }
    throw error
  })

  return client
}

export const apiClient = createApiClient()
