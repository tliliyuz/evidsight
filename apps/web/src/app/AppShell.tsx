import { type PropsWithChildren, useState } from 'react'
import { Link, NavLink } from 'react-router-dom'

import type { UserSummary } from '@/api/auth'
import { authSession } from '@/features/auth/authSession'
import { setTheme, type Theme } from '@/state/theme'

const primaryNavigation = [
  ['/workbench', '工作台'],
  ['/chat', '据见问答'],
  ['/chat/history', '问答历史'],
  ['/knowledge-bases', '知识库'],
  ['/research/new', '深度研究'],
  ['/research', '研究任务'],
] as const

type Props = PropsWithChildren<{
  user: UserSummary
  runningTaskCount?: number
}>

export function AppShell({ user, runningTaskCount = 0, children }: Props) {
  const [accountOpen, setAccountOpen] = useState(false)

  function chooseTheme(theme: Theme) {
    setTheme(theme)
    setAccountOpen(false)
  }

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <Link className="app-sidebar__brand" to="/workbench">
          <span aria-hidden="true" className="brand-mark" />
          EvidSight
        </Link>
        <nav aria-label="主导航">
          {primaryNavigation.map(([to, label]) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? 'active' : '')}>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="app-sidebar__footer">
          {user.role === 'admin' ? <Link to="/admin">管理中心</Link> : null}
          <button type="button" onClick={() => setAccountOpen((open) => !open)}>
            <span>{user.username}</span>
            <small>{user.role === 'admin' ? '管理员' : '成员'}</small>
          </button>
          {accountOpen ? (
            <div className="account-menu" role="menu">
              <button type="button" role="menuitem">
                修改密码
              </button>
              <button type="button" role="menuitem" onClick={() => chooseTheme('light')}>
                浅色主题
              </button>
              <button type="button" role="menuitem" onClick={() => chooseTheme('dark')}>
                深色主题
              </button>
              <button type="button" role="menuitem" onClick={() => void authSession.logout()}>
                退出登录
              </button>
            </div>
          ) : null}
        </div>
      </aside>
      <section className="app-shell__workspace">
        <header className="context-bar">
          <span>证据工作区</span>
          {runningTaskCount > 0 ? (
            <Link to="/research?status=running">{runningTaskCount} 个研究任务运行中</Link>
          ) : (
            <span>当前无运行任务</span>
          )}
        </header>
        <div className="app-shell__content">{children}</div>
      </section>
    </div>
  )
}
