import { type FormEvent, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { authApi } from '@/api/auth'
import { authSession } from '@/features/auth/authSession'

type LocationState = { returnTo?: string } | null

export function LoginDrawer() {
  const navigate = useNavigate()
  const location = useLocation()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting) return
    setSubmitting(true)
    setError(null)
    try {
      if (mode === 'register') {
        await authApi.register(username, password)
      }
      await authSession.login(username, password)
      const state = location.state as LocationState
      navigate(state?.returnTo ?? '/workbench', { replace: true })
    } catch {
      setError('无法登录，请检查账号和密码后重试。')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <aside className="login-drawer" aria-labelledby="login-title">
      <button className="login-drawer__close" type="button" onClick={() => navigate('/')}>
        关闭
      </button>
      <p className="login-drawer__eyebrow">Secure workspace</p>
      <h2 id="login-title">{mode === 'login' ? '登录据见' : '创建账号'}</h2>
      <p>身份确认后，继续回到你的知识、研究与证据现场。</p>
      <form onSubmit={submit}>
        <label htmlFor="username">账号</label>
        <input
          id="username"
          autoComplete="username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          required
        />
        <label htmlFor="password">密码</label>
        <input
          id="password"
          type={showPassword ? 'text' : 'password'}
          autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          minLength={6}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
        />
        <label className="login-drawer__check">
          <input
            type="checkbox"
            checked={showPassword}
            onChange={(event) => setShowPassword(event.target.checked)}
          />
          显示密码
        </label>
        {error ? <p role="alert">{error}</p> : null}
        <button type="submit" disabled={submitting}>
          {submitting ? '正在登录…' : mode === 'login' ? '登录' : '注册并登录'}
        </button>
      </form>
      <button
        className="login-drawer__mode"
        type="button"
        onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
      >
        {mode === 'login' ? '还没有账号？创建账号' : '已有账号？返回登录'}
      </button>
    </aside>
  )
}
