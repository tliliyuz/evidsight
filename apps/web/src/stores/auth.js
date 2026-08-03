import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as loginApi, register as registerApi, refreshToken as refreshApi, logout as logoutApi, getMe as getMeApi } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const token = ref(localStorage.getItem('access_token') || '')
  const refreshTokenValue = ref(localStorage.getItem('refresh_token') || '')
  /** 身份是否已从 /me 就绪（未就绪时 isLoggedIn 为 false，受保护路由不得提前进入） */
  const _meReady = ref(false)

  /** access_token 过期前自动刷新的定时器 ID */
  let refreshTimerId = null
  /** 防止并发刷新（避免定时器与时拦截器同时触发） */
  let _refreshing = false

  const isLoggedIn = computed(() => !!token.value && _meReady.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  /** 统一存储 token 对到 state + localStorage */
  function setTokens(accessToken, refreshTokenStr) {
    token.value = accessToken
    refreshTokenValue.value = refreshTokenStr
    localStorage.setItem('access_token', accessToken)
    localStorage.setItem('refresh_token', refreshTokenStr)
  }

  /**
   * 从 /me 拉取当前用户（UserSummary，id 为 UUID 字符串，username/role/status 来自数据库当前状态）。
   * 成功才建立 user 并置 _meReady。客户端不得从 Access Token Claim 解析用户名/角色/状态。
   */
  async function fetchMe() {
    const res = await getMeApi()
    const me = res.data
    user.value = {
      id: me.id,          // UUID 字符串，不做数值解析
      username: me.username,
      role: me.role,
      status: me.status,
    }
    localStorage.setItem('user', JSON.stringify(user.value))
    _meReady.value = true
    return user.value
  }

  /**
   * 用 Access Token 恢复身份（页面重载时调用）。失败则清态并返回 null。
   * 不恢复持久化的 user（其身份可能已过期/变更）。
   */
  async function restoreSession() {
    if (!token.value) {
      _meReady.value = false
      return null
    }
    try {
      return await fetchMe()
    } catch {
      clearState()
      return null
    }
  }

  /** 启动 Token 自动刷新定时器（到期前 60s 触发） */
  function scheduleRefresh() {
    clearRefreshTimer()
    try {
      const payload = JSON.parse(atob(token.value.split('.')[1]))
      const expiresAt = payload.exp * 1000  // JWT exp 是秒级时间戳
      const now = Date.now()
      const delay = Math.max(expiresAt - now - 60 * 1000, 5000)  // 提前 60s，最少 5s
      refreshTimerId = setTimeout(() => {
        refresh()
      }, delay)
    } catch {
      // JWT 解析失败不启动定时器
    }
  }

  /** 清除自动刷新定时器 */
  function clearRefreshTimer() {
    if (refreshTimerId) {
      clearTimeout(refreshTimerId)
      refreshTimerId = null
    }
  }

  /** 登录 — 调用 API 并持久化 token 对，随后用 /me 建立用户身份 */
  async function loginAction(username, password) {
    const res = await loginApi(username, password)
    const { access_token, refresh_token } = res.data.data
    setTokens(access_token, refresh_token)

    try {
      await fetchMe()
    } catch (e) {
      // 身份建立失败 → 清除刚保存的 token 对，按未登录处理（FRONTEND.md §5.1.1）
      clearState()
      throw e
    }

    // 启动自动刷新
    scheduleRefresh()
    return user.value
  }

  /** 刷新 Token — 调用 refresh API 换取新 token 对，随后重新调用 /me 获取最新状态。
   *  带并发防护：避免定时器与拦截器同时触发刷新时，第二个请求
   *  使用已被 Rotation 吊销的旧 refresh_token 导致踢下线。 */
  async function refresh() {
    if (!refreshTokenValue.value) {
      throw new Error('无 refresh_token')
    }
    if (_refreshing) {
      // 已有刷新进行中，直接返回（调用方可通过 token 获取最新值）
      return true
    }
    _refreshing = true
    try {
      const res = await refreshApi(refreshTokenValue.value)
      const { access_token, refresh_token } = res.data.data
      setTokens(access_token, refresh_token)

      // 更新用户信息（角色/状态可能变化）
      await fetchMe()

      // 重新启动定时器
      scheduleRefresh()
      return true
    } catch (err) {
      // 刷新失败 → 清除全部状态
      clearState()
      throw err
    } finally {
      _refreshing = false
    }
  }

  /** 注册 — 仅调用 API，不自动登录 */
  async function registerAction(username, password) {
    const res = await registerApi(username, password)
    return res.data.data
  }

  /** 清除本地状态（token + user + 定时器） */
  function clearState() {
    clearRefreshTimer()
    user.value = null
    token.value = ''
    refreshTokenValue.value = ''
    _meReady.value = false
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user')
  }

  /** 退出登录 — 调后端吊销 refresh_token + 清除本地状态 */
  async function logout() {
    // 尝试调后端吊销 refresh_token（失败不影响本地清除）
    if (refreshTokenValue.value) {
      try {
        await logoutApi(refreshTokenValue.value)
      } catch {
        // 吊销失败不阻塞退出流程
      }
    }
    clearState()
  }

  return {
    // 状态
    user,
    token,
    refreshToken: refreshTokenValue,
    isLoggedIn,
    isAdmin,

    // 方法
    setTokens,
    login: loginAction,
    register: registerAction,
    refresh,
    logout,
    restoreSession,
    fetchMe,
    scheduleRefresh,
    clearRefreshTimer,
  }
})