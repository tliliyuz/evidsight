import { type FormEvent, useRef, useState } from 'react'

import { authApi } from '@/api/auth'
import { apiErrorMessage } from '@/api/errors'
import { useAppToast } from '@/components/feedback/toastContext'
import { Icon } from '@/components/icons/Icon'
import { useOverlayFocus } from '@/components/overlay/useOverlayFocus'

type Props = { onClose: () => void }

/** 修改密码右侧抽屉（FRONTEND §3.2：修改密码使用右侧抽屉）。
 * 当前密码错误（E5002）在改密语境不展示登录文案「用户名或密码错误」，映射为「当前密码不正确」；
 * 新旧相同（E7004）沿用后端安全文案；成功弹全局 Toast「密码已修改」并关闭抽屉。
 * 后端契约：PUT /api/v1/auth/password { old_password, new_password }（均 ≥6 字符，无需 CSRF）。
 */
export function PasswordChangeDrawer({ onClose }: Props) {
  const { show } = useAppToast()
  const drawerRef = useRef<HTMLElement>(null)
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPasswords, setShowPasswords] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useOverlayFocus({ containerRef: drawerRef, onClose, canClose: !submitting })

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting) return
    // 两次输入的新密码必须一致（后端无 confirm 字段，这里防误输）
    if (newPassword !== confirmPassword) {
      setError('两次输入的新密码不一致，请重新输入。')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await authApi.changePassword(oldPassword, newPassword)
      show('密码已修改')
      onClose()
    } catch (err) {
      const message = apiErrorMessage(err, '修改密码失败，请稍后重试。')
      setError(message === '用户名或密码错误' ? '当前密码不正确，请重新输入。' : message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="drawer-overlay" role="presentation">
      <aside
        ref={drawerRef}
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label="修改密码"
        tabIndex={-1}
      >
        <header className="drawer__header">
          <h2>修改密码</h2>
          <button
            type="button"
            className="drawer__close"
            aria-label="关闭"
            onClick={onClose}
            disabled={submitting}
          >
            <Icon name="close" />
          </button>
        </header>
        <form
          className="drawer__body"
          onSubmit={submit}
          aria-describedby={error ? 'password-error' : undefined}
        >
          <div className="drawer-field">
            <label htmlFor="old-password">当前密码</label>
            <input
              id="old-password"
              data-overlay-initial-focus
              type={showPasswords ? 'text' : 'password'}
              autoComplete="current-password"
              minLength={6}
              placeholder="请输入当前密码（6-128 字）"
              value={oldPassword}
              onChange={(event) => setOldPassword(event.target.value)}
              aria-invalid={error ? true : undefined}
              required
            />
          </div>
          <div className="drawer-field">
            <label htmlFor="new-password">新密码</label>
            <input
              id="new-password"
              type={showPasswords ? 'text' : 'password'}
              autoComplete="new-password"
              minLength={6}
              placeholder="请输入新密码（6-128 字）"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              aria-invalid={error ? true : undefined}
              required
            />
          </div>
          <div className="drawer-field">
            <label htmlFor="confirm-password">确认新密码</label>
            <input
              id="confirm-password"
              type={showPasswords ? 'text' : 'password'}
              autoComplete="new-password"
              minLength={6}
              placeholder="请再次输入新密码"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              aria-invalid={error ? true : undefined}
              required
            />
          </div>
          <label className="check-row">
            <input
              type="checkbox"
              checked={showPasswords}
              onChange={(event) => setShowPasswords(event.target.checked)}
            />
            <span>显示密码</span>
          </label>
          {error ? (
            <p className="form-error" id="password-error" role="alert">
              {error}
            </p>
          ) : null}
          <div className="drawer__footer">
            <button type="button" className="btn" onClick={onClose} disabled={submitting}>
              取消
            </button>
            <button type="submit" className="btn btn--primary" disabled={submitting}>
              {submitting ? '保存中…' : '保存修改'}
            </button>
          </div>
        </form>
      </aside>
    </div>
  )
}
