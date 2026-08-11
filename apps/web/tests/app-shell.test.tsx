import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AppShell } from '@/app/AppShell'
import type { UserSummary } from '@/api/auth'
import type { ResearchApi } from '@/api/research'
import { ToastProvider } from '@/components/feedback/ToastProvider'
import { authSession } from '@/features/auth/authSession'

const navigateMock = vi.fn()

// 仅 mock useNavigate，Link/NavLink/MemoryRouter/useLocation 保持真实
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => navigateMock }
})

beforeEach(() => {
  navigateMock.mockReset()
})

const user = {
  id: '550e8400-e29b-41d4-a716-446655440001',
  username: 'alice',
  role: 'user' as const,
  status: 'active' as const,
}

function makeResearchApi(runningTotal: number): ResearchApi {
  return {
    listResearchTasks: vi.fn().mockResolvedValue({
      total: runningTotal,
      page: 1,
      page_size: 1,
      items: [],
    }),
  }
}

function renderShell(api: ResearchApi, path = '/workbench', overrides: Partial<UserSummary> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <ToastProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[path]}>
          <AppShell user={{ ...user, ...overrides }} researchApi={api}>
            <div>内容</div>
          </AppShell>
        </MemoryRouter>
      </QueryClientProvider>
    </ToastProvider>,
  )
}

describe('统一应用壳层', () => {
  it('按规范顺序展示六项导航且普通用户不显示管理入口', () => {
    renderShell(makeResearchApi(0))

    const nav = within(screen.getByRole('navigation', { name: '主导航' }))
    expect(nav.getAllByRole('link').map((link) => link.textContent)).toEqual([
      '工作台',
      '据见问答',
      '问答历史',
      '知识库',
      '深度研究',
      '研究任务',
    ])
    expect(screen.queryByText('管理中心')).not.toBeInTheDocument()
  })

  it('顶部栏展示真实 Breadcrumb：EVIDSIGHT / 当前页面', () => {
    renderShell(makeResearchApi(0), '/chat/history')

    const breadcrumb = screen.getByText('EVIDSIGHT').closest('.breadcrumb') as HTMLElement
    expect(breadcrumb).not.toBeNull()
    expect(within(breadcrumb).getByText('EVIDSIGHT')).toBeInTheDocument()
    expect(within(breadcrumb).getByText('问答历史')).toBeInTheDocument()
  })

  it('运行任务 Chip 常显真实数量，点击弹确认框，确认后跳转研究任务', async () => {
    const user = userEvent.setup()
    renderShell(makeResearchApi(3))

    const chip = await screen.findByRole('button', { name: /3 项研究进行中/ })
    await user.click(chip)
    expect(screen.getByRole('dialog', { name: '跳转研究任务' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /前往研究任务/ }))
    expect(navigateMock).toHaveBeenCalledWith('/research')
    expect(screen.queryByRole('dialog', { name: '跳转研究任务' })).not.toBeInTheDocument()
  })

  it('无运行任务时 Chip 常显「暂无任务进行」，点击仍可确认跳转', async () => {
    const user = userEvent.setup()
    renderShell(makeResearchApi(0))

    const chip = await screen.findByRole('button', { name: /暂无任务进行/ })
    expect(chip).toBeInTheDocument()

    await user.click(chip)
    await user.click(screen.getByRole('button', { name: /前往研究任务/ }))
    expect(navigateMock).toHaveBeenCalledWith('/research')
  })

  it('退出登录先弹具名确认框，确认后清除会话并弹「已退出登录」成功反馈', async () => {
    const user = userEvent.setup()
    const logoutSpy = vi.spyOn(authSession, 'logout').mockResolvedValue()
    renderShell(makeResearchApi(0))

    await user.click(screen.getByRole('button', { name: /alice/ }))
    await user.click(screen.getByRole('menuitem', { name: /退出登录/ }))
    const confirmDialog = screen.getByRole('dialog', { name: '退出登录' })
    expect(confirmDialog).toBeInTheDocument()

    await user.click(within(confirmDialog).getByRole('button', { name: '退出登录' }))
    expect(logoutSpy).toHaveBeenCalledOnce()
    // 成功反馈经全局 ToastProvider（跨 AppShell 卸载存活），非 AppShell 局部状态
    expect(await screen.findByRole('status')).toHaveTextContent('已退出登录')
  })

  it('账号菜单「修改密码」打开右侧抽屉（FRONTEND §3.2）', async () => {
    const user = userEvent.setup()
    renderShell(makeResearchApi(0))

    await user.click(screen.getByRole('button', { name: /alice/ }))
    await user.click(screen.getByRole('menuitem', { name: /修改密码/ }))
    expect(screen.getByRole('dialog', { name: '修改密码' })).toBeInTheDocument()
    expect(screen.getByLabelText('当前密码')).toBeInTheDocument()
  })

  it('账号区展示头像与角色层级，Trigger 携带 aria-expanded/aria-controls', () => {
    renderShell(makeResearchApi(0))

    const trigger = screen.getByRole('button', { name: /alice/ })
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(trigger).toHaveAttribute('aria-controls', 'account-menu')
    expect(within(trigger).getByText('成员')).toBeInTheDocument()

    fireEvent.click(trigger)
    expect(screen.getByRole('button', { name: /alice/ })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('menu')).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /退出登录/ })).toBeInTheDocument()
  })

  it('管理员显示管理中心入口', () => {
    renderShell(makeResearchApi(0), '/workbench', { role: 'admin' })

    expect(screen.getByRole('link', { name: '管理中心' })).toHaveAttribute('href', '/admin')
  })

  it('账号菜单支持方向键/Home/End 循环与 Escape 关闭返回触发器', async () => {
    const user = userEvent.setup()
    renderShell(makeResearchApi(0))

    const trigger = screen.getByRole('button', { name: /alice/ })
    await user.click(trigger)
    expect(screen.getByRole('menuitem', { name: /修改密码/ })).toHaveFocus()

    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('menuitem', { name: /主题选择/ })).toHaveFocus()
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('menuitem', { name: /退出登录/ })).toHaveFocus()
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('menuitem', { name: /修改密码/ })).toHaveFocus()

    await user.keyboard('{End}')
    expect(screen.getByRole('menuitem', { name: /退出登录/ })).toHaveFocus()
    await user.keyboard('{Home}')
    expect(screen.getByRole('menuitem', { name: /修改密码/ })).toHaveFocus()

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('主题选择：确认卡片叠加在选择之上，确认后才切换、持久化并弹成功反馈', async () => {
    localStorage.removeItem('evidsight-theme')
    document.documentElement.dataset.theme = 'light'
    const user = userEvent.setup()
    renderShell(makeResearchApi(0))

    await user.click(screen.getByRole('button', { name: /alice/ }))
    await user.click(screen.getByRole('menuitem', { name: /主题选择/ }))
    expect(screen.getByRole('dialog', { name: '选择界面主题' })).toBeInTheDocument()

    // 点击当前已选中的浅色：无反应，不弹确认
    await user.click(screen.getByRole('radio', { name: /浅色/ }))
    expect(screen.queryByRole('dialog', { name: '切换主题？' })).not.toBeInTheDocument()

    // 点击未选中的深色 → 确认卡片叠加出现，选择卡片仍保留；未立即生效
    await user.click(screen.getByRole('radio', { name: /深色/ }))
    const confirmDialog = screen.getByRole('dialog', { name: '切换主题？' })
    expect(confirmDialog).toBeInTheDocument()
    expect(localStorage.getItem('evidsight-theme')).not.toBe('dark')

    await user.click(within(confirmDialog).getByRole('button', { name: '确认切换' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(localStorage.getItem('evidsight-theme')).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(screen.getByRole('status')).toHaveTextContent(/已切换为深色主题/)
  })

  it('主题确认卡片取消返回选择，选择卡片取消关闭且不改变主题', async () => {
    localStorage.setItem('evidsight-theme', 'light')
    document.documentElement.dataset.theme = 'light'
    const user = userEvent.setup()
    renderShell(makeResearchApi(0))

    await user.click(screen.getByRole('button', { name: /alice/ }))
    await user.click(screen.getByRole('menuitem', { name: /主题选择/ }))

    // 确认卡片取消 → 回到选择卡片，主题不变
    await user.click(screen.getByRole('radio', { name: /深色/ }))
    const confirmDialog = screen.getByRole('dialog', { name: '切换主题？' })
    await user.click(within(confirmDialog).getByRole('button', { name: '取消' }))
    expect(screen.getByRole('dialog', { name: '选择界面主题' })).toBeInTheDocument()
    expect(localStorage.getItem('evidsight-theme')).toBe('light')
    expect(document.documentElement.dataset.theme).toBe('light')

    // 选择卡片取消 → 关闭
    await user.click(screen.getByRole('button', { name: '取消' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(localStorage.getItem('evidsight-theme')).toBe('light')
  })
})
