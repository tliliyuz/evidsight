import { setAccessToken } from '@/api/client'
import { authApi, type UserSummary } from '@/api/auth'

type AuthStatus = 'restoring' | 'authenticated' | 'anonymous'
type AuthState = { status: AuthStatus; user: UserSummary | null }
type AuthApi = Pick<typeof authApi, 'login' | 'me'> & Partial<Pick<typeof authApi, 'refresh' | 'logout'>>
type Listener = () => void
type Cleanup = () => void

class AuthSession {
  private state: AuthState = { status: 'restoring', user: null }
  private listeners = new Set<Listener>()
  private sensitiveCleanups = new Set<Cleanup>()
  private restoreInFlight: Promise<void> | null = null

  getSnapshot = (): AuthState => this.state

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  private update(state: AuthState): void {
    this.state = state
    this.listeners.forEach((listener) => listener())
  }

  registerSensitiveCleanup(cleanup: Cleanup): () => void {
    this.sensitiveCleanups.add(cleanup)
    return () => this.sensitiveCleanups.delete(cleanup)
  }

  private clearSession(): void {
    setAccessToken(null)
    this.sensitiveCleanups.forEach((cleanup) => cleanup())
    this.update({ status: 'anonymous', user: null })
  }

  async login(username: string, password: string, api: AuthApi = authApi): Promise<void> {
    try {
      const result = await api.login(username, password)
      setAccessToken(result.access_token)
      const user = await api.me()
      this.update({ status: 'authenticated', user })
    } catch (error) {
      this.clearSession()
      throw error
    }
  }

  async restore(api: AuthApi = authApi): Promise<void> {
    if (this.restoreInFlight) return this.restoreInFlight
    this.update({ status: 'restoring', user: null })
    this.restoreInFlight = (async () => {
      try {
        if (api.refresh) {
          const result = await api.refresh()
          setAccessToken(result.access_token)
        }
        const user = await api.me()
        this.update({ status: 'authenticated', user })
      } catch {
        this.clearSession()
      } finally {
        this.restoreInFlight = null
      }
    })()
    return this.restoreInFlight
  }

  async logout(api: AuthApi = authApi): Promise<void> {
    try {
      await api.logout?.()
    } finally {
      this.clearSession()
    }
  }

  resetForTesting(): void {
    this.restoreInFlight = null
    this.sensitiveCleanups.clear()
    setAccessToken(null)
    this.update({ status: 'anonymous', user: null })
  }

  setRestoringForTesting(): void {
    this.update({ status: 'restoring', user: null })
  }
}

export const authSession = new AuthSession()
