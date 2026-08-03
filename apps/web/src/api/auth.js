import api, { getCsrfToken } from './index'

/**
 * 注册（旧 /api/auth/register 迁移期兼容入口，返回旧 UserResponse(id=int)）。
 * 目标态为 /api/v1/auth/register（见事件①），切换由独立事件推进。
 */
export function register(username, password) {
  return api.post('/auth/register', { username, password })
}

/**
 * 登录（v1，ADR-006 / API.md §5）：POST /api/v1/auth/login
 * 响应体为 unwrapped LoginV1Response：{ access_token, token_type, expires_in, user: UserSummary }，
 * 不含 refresh_token 明文；Refresh/CSRF Cookie 由后端通过响应 Set-Cookie 建立。
 */
export function login(username, password) {
  return api.post('/v1/auth/login', { username, password })
}

/**
 * 获取当前用户身份摘要（UserSummary：id 为 UUID 字符串，username/role/status 来自数据库当前状态）
 * 对齐 FRONTEND.md §5.1.1：客户端不得从 Access Token Claim 解析用户名/角色/状态。
 * @returns {Promise<{data: {id: string, username: string, role: string, status: string}}>}
 */
export function getMe() {
  return api.get('/v1/auth/me')
}

/**
 * 刷新 Token（v1，Cookie + CSRF）：POST /api/v1/auth/refresh
 * Refresh Token 由后端 HttpOnly Cookie 持有并随请求自动发送（withCredentials）；
 * CSRF 从非 HttpOnly Cookie 读取并以 X-CSRF-Token Header 回传（FRONTEND.md §5.1.2）。
 * 响应体为 unwrapped RefreshV1Response：{ access_token, token_type, expires_in }。
 */
export function refreshToken() {
  // 无 body：Refresh Token 凭据来自 HttpOnly Cookie（ADR-006），不通过请求体传递
  return api.post('/v1/auth/refresh', undefined, {
    headers: { 'X-CSRF-Token': getCsrfToken() },
  })
}

/**
 * 退出登录（v1，Cookie + CSRF）：POST /api/v1/auth/logout，成功 204。
 * Refresh Token 凭据来自 HttpOnly Cookie，幂等；CSRF 以 X-CSRF-Token 回传。
 */
export function logout() {
  // 无 body：凭据来自 HttpOnly Cookie + CSRF Header（ADR-006）
  return api.post('/v1/auth/logout', undefined, {
    headers: { 'X-CSRF-Token': getCsrfToken() },
  })
}

/**
 * 修改密码（改密后全部 refresh_token 吊销，须重新登录；旧 /api/auth/password 迁移期入口）
 * @param {string} oldPassword - 当前密码
 * @param {string} newPassword - 新密码
 */
export function changePassword(oldPassword, newPassword) {
  return api.put('/auth/password', { old_password: oldPassword, new_password: newPassword })
}
