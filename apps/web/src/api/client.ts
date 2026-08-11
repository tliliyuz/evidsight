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

async function requestFreshAccessToken(): Promise<string> {
  const csrfToken = readCsrfToken()
  if (!csrfToken) {
    throw new Error('缺少 CSRF Token')
  }
  const response = await axios.post<{ access_token: string }>('/api/v1/auth/refresh', null, {
    headers: { 'X-CSRF-Token': csrfToken },
    withCredentials: true,
  })
  return response.data.access_token
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
      refreshInFlight ??= (options.refreshAccessToken ?? requestFreshAccessToken)()
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
