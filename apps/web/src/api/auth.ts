import axios from 'axios'

import { apiClient, readCsrfToken, refreshAccessTokenWithRetry, setAccessToken } from '@/api/client'

export type UserSummary = {
  id: string
  username: string
  role: 'user' | 'admin'
  status: 'active' | 'disabled'
}

export type LoginResponse = {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: UserSummary
}

function csrfHeaders(): Record<string, string> {
  const token = readCsrfToken()
  if (!token) {
    throw new Error('缺少 CSRF Token')
  }
  return { 'X-CSRF-Token': token }
}

export const authApi = {
  async login(username: string, password: string): Promise<LoginResponse> {
    const { data } = await axios.post<LoginResponse>(
      '/api/v1/auth/login',
      { username, password },
      { withCredentials: true },
    )
    setAccessToken(data.access_token)
    return data
  },

  async register(username: string, password: string): Promise<UserSummary> {
    const { data } = await axios.post<UserSummary>(
      '/api/v1/auth/register',
      { username, password },
      { withCredentials: true },
    )
    return data
  },

  async refresh(): Promise<{ access_token: string }> {
    const access_token = await refreshAccessTokenWithRetry()
    return { access_token }
  },

  async me(): Promise<UserSummary> {
    const { data } = await apiClient.get<UserSummary>('/api/v1/auth/me')
    return data
  },

  async logout(): Promise<void> {
    await apiClient.post('/api/v1/auth/logout', null, { headers: csrfHeaders() })
    setAccessToken(null)
  },

  async changePassword(oldPassword: string, newPassword: string): Promise<void> {
    await apiClient.put('/api/v1/auth/password', {
      old_password: oldPassword,
      new_password: newPassword,
    })
  },
}
