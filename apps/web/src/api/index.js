import axios from 'axios'

/** 非 HttpOnly CSRF Cookie 名（double-submit 回传用，对齐后端 EVIDSIGHT_PLATFORM_CSRF_COOKIE_NAME 默认值） */
export const CSRF_COOKIE_NAME = 'evidsight_csrf'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
  // FRONTEND.md §5.1.2：启用凭据携带，使 HttpOnly Refresh Cookie 随请求发送到 Auth 端点
  withCredentials: true,
})

// ===== Token 自动刷新机制 =====
// 对齐 FRONTEND.md §1.3.1：401+E5003 → refresh → 重放原请求
// 防并发刷新：isRefreshing 标志位 + requestQueue 队列

let isRefreshing = false
let requestQueue = []  // [{ resolve, reject }]

/** 读取非 HttpOnly CSRF Cookie（double-submit 模式，FRONTEND.md §5.1.2） */
export function getCsrfToken() {
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${CSRF_COOKIE_NAME}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : ''
}

/** 处理刷新队列：刷新成功后统一重放排队中的请求 */
function processQueue(error, newToken) {
  requestQueue.forEach(({ resolve, reject, config }) => {
    if (error) {
      reject(error)
    } else {
      config.headers.Authorization = `Bearer ${newToken}`
      resolve(api(config))
    }
  })
  requestQueue = []
}

/** 清除本地 token 并跳转登录页（removeItem('refresh_token') 仅迁移期遗留清理，新代码不读写该键） */
export function clearAndRedirect() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  localStorage.removeItem('user')
  if (window.location.pathname !== '/login') {
    window.location.href = '/login'
  }
}

/** 执行 Token 刷新（独立调用，不经过拦截器循环）。
 *  v1 Cookie 刷新（ADR-006）：Refresh Token 由后端 HttpOnly Cookie 持有并随请求自动发送，
 *  前端不读取/保存 Refresh Token 明文（FRONTEND.md §5.1.2），CSRF 从非 HttpOnly Cookie 读取回传。
 *  刷新后同步更新 Pinia store（Access Token + /me + 定时器）。
 *
 *  统一入口：Axios 响应拦截器与 SSE 流式请求（utils/sse.js）共用此函数，
 *  避免 SSE 路径单独实现刷新逻辑时漏同步 Pinia store（历史 bug）。 */
export async function refreshToken() {
  // 使用 axios 原生调用，绕过拦截器避免死循环；无 body，Refresh 凭据来自 HttpOnly Cookie
  const res = await axios.post('/api/v1/auth/refresh', undefined, {
    timeout: 10000,
    withCredentials: true,
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': getCsrfToken(),
    },
  })
  const { access_token } = res.data
  localStorage.setItem('access_token', access_token)

  // 同步更新 Pinia store，确保 store 与最新 Access Token 一致
  // （Refresh Token 由 Cookie 持有，store 不再保存）
  try {
    const { useAuthStore } = await import('@/stores/auth')
    const authStore = useAuthStore()
    authStore.setTokens(access_token)
    // FRONTEND.md §5.1.1：Refresh 成功后重新调用 /me，获取可能变化的角色与状态
    await authStore.fetchMe()
    authStore.scheduleRefresh()
  } catch {
    // store 尚未初始化时忽略；/me 重取失败不阻断刷新（用户仍持有新 token）
  }

  return access_token
}

// 请求拦截器 — 自动附加 Bearer Token
api.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器 — 401 时自动刷新 Token 并重放
api.interceptors.response.use(
  response => response,
  async error => {
    const originalConfig = error.config

    // 非 401 或已重试过的请求，直接拒绝
    if (error.response?.status !== 401 || originalConfig._retry) {
      return Promise.reject(error)
    }

    const code = error.response?.data?.code

    // E5002：用户名或密码错误 / E5010：用户被禁用 → 非 token 问题，透传错误给调用方
    if (code === 'E5002' || code === 'E5010') {
      return Promise.reject(error)
    }

    // E5003：Token 过期 → 尝试刷新
    if (code === 'E5003') {
      if (isRefreshing) {
        // 已有刷新请求在进行中，排队等待
        return new Promise((resolve, reject) => {
          requestQueue.push({ resolve, reject, config: originalConfig })
        })
      }

      isRefreshing = true
      originalConfig._retry = true

      try {
        const newToken = await refreshToken()
        // 刷新成功，重放原请求
        originalConfig.headers.Authorization = `Bearer ${newToken}`
        processQueue(null, newToken)
        return api(originalConfig)
      } catch (refreshError) {
        // 刷新失败 → 清除全部 token → 跳转登录
        processQueue(refreshError, null)
        clearAndRedirect()
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    }

    // 其他 401（E5004/E5005/E5006/E5007/E5008/E5009 等）→ 清除 token 跳转登录
    clearAndRedirect()
    return Promise.reject(error)
  }
)

export default api
