import { useQuery } from '@tanstack/react-query'
import { type KeyboardEvent, type PropsWithChildren, useEffect, useRef, useState } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'

import type { UserSummary } from '@/api/auth'
import { researchApi, type ResearchApi } from '@/api/research'
import { BrandMark } from '@/components/brand/BrandMark'
import { ThemeDialog } from '@/components/feedback/ThemeDialog'
import { Icon, type IconName } from '@/components/icons/Icon'
import { authSession } from '@/features/auth/authSession'
import { setTheme, type Theme } from '@/state/theme'

const primaryNavigation: ReadonlyArray<readonly [string, string, IconName]> = [
  ['/workbench', '工作台', 'home'],
  ['/chat', '据见问答', 'chat'],
  ['/chat/history', '问答历史', 'history'],
  ['/knowledge-bases', '知识库', 'knowledge'],
  ['/research/new', '深度研究', 'research'],
  ['/research', '研究任务', 'tasks'],
]

const ACCOUNT_MENU_ID = 'account-menu'

/** 顶栏 Breadcrumb 的「当前页面」：按路径匹配，顺序优先精确前缀。 */
function routeTitle(pathname: string): string {
  if (pathname.startsWith('/admin')) return '管理中心'
  if (pathname.startsWith('/chat/history')) return '问答历史'
  if (pathname.startsWith('/chat')) return '据见问答'
  if (pathname.startsWith('/knowledge-bases')) return '知识库'
  if (pathname.startsWith('/research/new')) return '深度研究'
  if (pathname.startsWith('/research')) return '研究任务'
  return '工作台'
}

function roleLabel(role: UserSummary['role']): string {
  return role === 'admin' ? '管理员' : '成员'
}

function themeLabel(theme: Theme): string {
  return theme === 'dark' ? '深色' : '浅色'
}

type Props = PropsWithChildren<{
  user: UserSummary
  researchApi?: ResearchApi
}>

/**
 * 统一应用壳层（FRONTEND §3.3 / UIDESIGN §5.2）。
 *
 * - 左侧 232px 固定导航 + 底部账号/管理入口，当前项同时有背景、左侧标记和文字权重；
 * - 顶部 56px 上下文栏：真实 Breadcrumb 与运行任务 Chip；
 * - 运行任务 Chip 只显示真实运行中任务数量，为 0 时不渲染、不伪造运行状态；
 * - 搜索/命令入口未实现，不渲染可点击的假按钮；
 * - 账号区展示头像、用户名、角色层级与展开状态，Trigger 携带 aria-expanded/aria-controls；
 *   菜单支持方向键/Home/End 循环、Escape 关闭并返回触发器、点击外部关闭；
 * - 账号菜单「主题选择」打开居中确认卡片（FRONTEND §3.3），选择立即生效并持久化；
 * - 管理入口仅对管理员显示，最终鉴权仍由服务端承担。
 */
export function AppShell({ user, researchApi: api = researchApi, children }: Props) {
  const { pathname } = useLocation()
  const [accountOpen, setAccountOpen] = useState(false)
  const [themeOpen, setThemeOpen] = useState(false)
  const [theme, setThemeState] = useState<Theme>(() =>
    document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light',
  )
  const [toast, setToast] = useState<string | null>(null)
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const accountRef = useRef<HTMLDivElement>(null)
  const accountTriggerRef = useRef<HTMLButtonElement>(null)
  const accountMenuRef = useRef<HTMLDivElement>(null)

  const runningCountQuery = useQuery({
    queryKey: ['research', 'running-count'],
    queryFn: () => api.listResearchTasks({ status: 'running', page: 1, page_size: 1 }),
    select: (list) => list.total,
  })
  const runningTaskCount = runningCountQuery.data ?? 0

  /** 主题对话框卸载时 useOverlayFocus 会恢复焦点到挂载时的 activeElement（body），
      用宏任务延后聚焦账户触发器，确保在清理之后生效。 */
  function restoreAccountFocus() {
    setTimeout(() => accountTriggerRef.current?.focus(), 0)
  }

  function showToast(message: string) {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    setToast(message)
    toastTimerRef.current = setTimeout(() => setToast(null), 2600)
  }

  function chooseTheme(next: Theme) {
    setTheme(next)
    setThemeState(next)
    setThemeOpen(false)
    setAccountOpen(false)
    restoreAccountFocus()
    showToast(`已切换为${themeLabel(next)}主题`)
  }

  function closeAccount() {
    setAccountOpen(false)
    accountTriggerRef.current?.focus()
  }

  function handleMenuKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const items = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]'),
    ).filter((element) => !element.hidden)
    if (items.length === 0) return

    const currentIndex = items.indexOf(document.activeElement as HTMLElement)
    let nextIndex = -1

    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault()
        nextIndex = currentIndex < 0 || currentIndex === items.length - 1 ? 0 : currentIndex + 1
        break
      case 'ArrowUp':
        event.preventDefault()
        nextIndex = currentIndex <= 0 ? items.length - 1 : currentIndex - 1
        break
      case 'Home':
        event.preventDefault()
        nextIndex = 0
        break
      case 'End':
        event.preventDefault()
        nextIndex = items.length - 1
        break
      case 'Escape':
        event.preventDefault()
        closeAccount()
        return
      case 'Tab':
        setAccountOpen(false)
        return
    }

    if (nextIndex >= 0) items[nextIndex].focus()
  }

  // 打开菜单时焦点进入首项；点击菜单外部关闭
  useEffect(() => {
    if (!accountOpen) return undefined
    accountMenuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus()
    function handlePointerDown(event: MouseEvent | TouchEvent) {
      if (!accountRef.current?.contains(event.target as Node)) {
        setAccountOpen(false)
      }
    }
    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('touchstart', handlePointerDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('touchstart', handlePointerDown)
    }
  }, [accountOpen])

  // 卸载时清理 toast 定时器
  useEffect(() => {
    return () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    }
  }, [])

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <Link className="app-sidebar__brand" to="/workbench">
          <BrandMark className="brand-mark" decorative />
          EvidSight
        </Link>
        <nav aria-label="主导航">
          {primaryNavigation.map(([to, label, icon]) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) => (isActive ? 'active' : undefined)}
            >
              <Icon name={icon} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="app-sidebar__footer">
          {user.role === 'admin' ? (
            <Link to="/admin">
              <Icon name="settings" />
              管理中心
            </Link>
          ) : null}
          <div className="account" ref={accountRef}>
            <button
              ref={accountTriggerRef}
              type="button"
              className="account__trigger"
              aria-expanded={accountOpen}
              aria-controls={ACCOUNT_MENU_ID}
              aria-haspopup="menu"
              onClick={() => (accountOpen ? closeAccount() : setAccountOpen(true))}
            >
              <span className="account__avatar" aria-hidden="true">
                {user.username.charAt(0).toUpperCase()}
              </span>
              <span className="account__text">
                <b>{user.username}</b>
                <small>{roleLabel(user.role)}</small>
              </span>
              <span className="account__caret" aria-hidden="true" />
            </button>
            {accountOpen ? (
              <div
                ref={accountMenuRef}
                id={ACCOUNT_MENU_ID}
                className="account-menu"
                role="menu"
                onKeyDown={handleMenuKeyDown}
              >
                <div className="account-menu__head">
                  <b>{user.username}</b>
                  <small>{roleLabel(user.role)}</small>
                </div>
                <button type="button" role="menuitem">
                  <span className="account-menu__item-copy">
                    <b>修改密码</b>
                    <small>更新当前账户凭据</small>
                  </span>
                  <i aria-hidden="true">→</i>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setAccountOpen(false)
                    setThemeOpen(true)
                  }}
                >
                  <span className="account-menu__item-copy">
                    <b>主题选择</b>
                    <small id="theme-current-label">当前：{themeLabel(theme)}</small>
                  </span>
                  <i aria-hidden="true">→</i>
                </button>
                <button type="button" role="menuitem" onClick={() => void authSession.logout()}>
                  <span className="account-menu__item-copy">
                    <b>退出登录</b>
                    <small>返回据见入口</small>
                  </span>
                  <i aria-hidden="true">→</i>
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </aside>
      <section className="app-shell__workspace">
        <header className="context-bar">
          <div className="breadcrumb" aria-label="面包屑">
            <span>EVIDSIGHT</span>
            <i aria-hidden="true">/</i>
            <b>{routeTitle(pathname)}</b>
          </div>
          {runningTaskCount > 0 ? (
            <Link className="running-chip" to="/research?status=running">
              <span className="running-chip__dot" aria-hidden="true" />
              {runningTaskCount} 项研究进行中
            </Link>
          ) : null}
        </header>
        <div className="app-shell__content">{children}</div>
      </section>
      {themeOpen ? (
        <ThemeDialog
          current={theme}
          onPick={chooseTheme}
          onClose={() => {
            setThemeOpen(false)
            restoreAccountFocus()
          }}
        />
      ) : null}
      {toast ? (
        <div className="toast" role="status">
          <span className="toast__icon" aria-hidden="true">
            ✓
          </span>
          {toast}
        </div>
      ) : null}
    </div>
  )
}
