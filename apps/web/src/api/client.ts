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
  const body = error.response?.data as
    | { error?: { error_code?: string }; code?: string }
    | undefined
  return body?.error?.error_code ?? body?.code
}

async function requestFreshAccessToken(): Promise<string> {
  const csrfToken = readCsrfToken()
  if (!csrfToken) {
    throw new Error('缺少 CSRF Token')
  }
  const response = await axios.post<{ access_token: string }>(
    '/api/v1/auth/refresh',
    null,
    {
      headers: { 'X-CSRF-Token': csrfToken },
      withCredentials: true,
    },
  )
  return response.data.access_token
}

type RetriableConfig = InternalAxiosRequestConfig & { __authRetried?: boolean }

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
    const shouldRefresh =
      error.response?.status === 401 && errorCode(error) === 'E5003' && config && !config.__authRetried

    if (!shouldRefresh) {
      throw error
    }

    config.__authRetried = true
    refreshInFlight ??= (options.refreshAccessToken ?? requestFreshAccessToken)()
      .then((token) => {
        setAccessToken(token)
        return token
      })
      .catch((refreshError) => {
        setAccessToken(null)
        options.onAuthenticationFailed?.()
        throw refreshError
      })
      .finally(() => {
        refreshInFlight = null
      })

    const token = await refreshInFlight
    config.headers.Authorization = `Bearer ${token}`
    return client.request(config)
  })

  return client
}

export const apiClient = createApiClient()
