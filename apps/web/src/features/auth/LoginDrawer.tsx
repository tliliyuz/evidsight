import { type FormEvent, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { authApi } from '@/api/auth'
import { BrandMark } from '@/components/brand/BrandMark'
import { useAppToast } from '@/components/feedback/toastContext'
import { Icon } from '@/components/icons/Icon'
import { useOverlayFocus } from '@/components/overlay/useOverlayFocus'
import { authSession } from '@/features/auth/authSession'

type LocationState = { returnTo?: string } | null

/**
 * 登录右侧抽屉（FRONTEND §5.1 / UIDESIGN §6.6，默认浅色）。
 * 保持防重复提交、returnTo 目标路由与 `/me` 身份确认；
 * 视觉对齐跟踪版原型 `#login-drawer`，错误经 role=alert + aria-describedby 关联表单。
 */
export function LoginDrawer() {
  const navigate = useNavigate()
  const location = useLocation()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  // FRONTEND §5.1 要求的「记住登录状态」控件；会话持久化由 Refresh Cookie
  // 生命周期决定（IDENTITY_AND_ACCESS §144-149），该控件不伪造服务端语义。
  const [remember, setRemember] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { show } = useAppToast()
  const drawerRef = useRef<HTMLElement>(null)
  const close = () => navigate('/')
  useOverlayFocus({ containerRef: drawerRef, onClose: close, canClose: !submitting })

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting) return
    setSubmitting(true)
    setError(null)
    try {
      if (mode === 'register') {
        try {
          await authApi.register(username, password)
        } catch {
          setError('创建账号失败，请检查账号信息后重试。')
          return
        }
      }
      await authSession.login(username, password)
      // 登录/注册成功均弹全局成功反馈（ToastProvider 挂在路由之上，跨页面导航存活）
      show(mode === 'register' ? `注册成功，欢迎加入，${username}` : `欢迎回来，${username}`)
      const state = location.state as LocationState
      navigate(state?.returnTo ?? '/workbench', { replace: true })
    } catch {
      setError('账号或密码不正确，请重新输入。')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <div className="login-overlay" aria-hidden="true" onClick={submitting ? undefined : close} />
      <aside
        ref={drawerRef}
        className="login-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="login-title"
        tabIndex={-1}
      >
        <button
          className="login-drawer__close"
          type="button"
          onClick={close}
          disabled={submitting}
          aria-label="关闭登录"
        >
          <Icon name="close" />
        </button>
        <div className="login-drawer__brand">
          <BrandMark className="brand-mark" decorative />
          <span>EvidSight</span>
        </div>
        <div className="login-drawer__copy">
          <p className="login-drawer__eyebrow">{mode === 'login' ? '账户登录' : '新账户'}</p>
          <h2 id="login-title">{mode === 'login' ? '登录据见' : '创建账号'}</h2>
          <p>
            {mode === 'login'
              ? '身份确认后，继续回到你的知识、研究与证据现场。'
              : '创建后即可进入你的知识、研究与证据现场。'}
          </p>
        </div>
        <form onSubmit={submit} aria-describedby={error ? 'login-error' : undefined}>
          <div className="login-drawer__field">
            <label htmlFor="username">账号</label>
            <input
              id="username"
              data-overlay-initial-focus
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              aria-invalid={error ? true : undefined}
              required
            />
          </div>
          <div className="login-drawer__field">
            <label htmlFor="password">密码</label>
            <span className="password-wrap">
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                minLength={6}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                aria-invalid={error ? true : undefined}
                required
              />
              <button
                className="password-toggle"
                type="button"
                onClick={() => setShowPassword((value) => !value)}
              >
                {showPassword ? '隐藏' : '显示'}
              </button>
            </span>
          </div>
          <div className="login-drawer__options">
            <label className="login-drawer__check">
              <input
                type="checkbox"
                checked={remember}
                onChange={(event) => setRemember(event.target.checked)}
              />
              记住登录状态
            </label>
          </div>
          {error ? (
            <p className="login-drawer__error" id="login-error" role="alert">
              {error}
            </p>
          ) : null}
          <button className="login-drawer__submit" type="submit" disabled={submitting}>
            {submitting ? '正在登录…' : mode === 'login' ? '登录' : '注册并登录'}
          </button>
        </form>
        <p className="login-drawer__security">
          登录即表示你同意组织的访问与审计策略。凭据只提交至统一身份服务。
        </p>
        <button
          className="login-drawer__mode"
          type="button"
          onClick={() => {
            setMode(mode === 'login' ? 'register' : 'login')
            setError(null)
          }}
        >
          {mode === 'login' ? '还没有账号？创建账号' : '已有账号？返回登录'}
        </button>
      </aside>
    </>
  )
}
