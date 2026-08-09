import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { authApi } from '@/api/auth'
import { LoginDrawer } from '@/features/auth/LoginDrawer'
import { authSession } from '@/features/auth/authSession'

function renderDrawer(initialPath = '/login') {
  return render(
    <MemoryRouter initialEntries={[{ pathname: initialPath, state: { returnTo: '/research' } }]}>
      <Routes>
        <Route path="/login" element={<LoginDrawer />} />
        <Route path="/research" element={<div>研究任务</div>} />
        <Route path="/" element={<div>入口页</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('登录抽屉', () => {
  beforeEach(() => authSession.resetForTesting())

  it('提交期间防止重复并在成功后返回目标路由', async () => {
    const login = vi.spyOn(authSession, 'login').mockResolvedValue()
    renderDrawer()

    fireEvent.change(screen.getByLabelText('账号'), { target: { value: 'alice' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'password' } })
    fireEvent.click(screen.getByRole('button', { name: '登录' }))

    expect(screen.getByRole('button', { name: '正在登录…' })).toBeDisabled()
    await waitFor(() => expect(screen.getByText('研究任务')).toBeInTheDocument())
    expect(login).toHaveBeenCalledOnce()
  })

  it('包含统一暗色 Overlay，Drawer 宽度处于 420–520px', () => {
    const { container } = renderDrawer()

    expect(container.querySelector('.login-overlay')).not.toBeNull()
    expect(screen.getByRole('dialog', { name: '登录据见' })).toBeInTheDocument()

    // jsdom 不计算样式表宽度，直接核对 landing.css 中 .login-drawer 的声明宽度
    const css = readFileSync(resolve(process.cwd(), 'src/styles/landing.css'), 'utf8')
    const block = css.match(/\.login-drawer\s*\{([^}]*)\}/)?.[1] ?? ''
    const width = Number(block.match(/width:\s*(\d+)px/)?.[1])
    expect(width).toBeGreaterThanOrEqual(420)
    expect(width).toBeLessThanOrEqual(520)
  })

  it('关闭按钮使用统一图标按钮并提供 aria-label="关闭登录"', () => {
    renderDrawer()

    expect(screen.getByRole('button', { name: '关闭登录' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '关闭' })).not.toBeInTheDocument()
  })

  it('提供规范要求的「记住登录状态」控件', () => {
    renderDrawer()

    expect(screen.getByRole('checkbox', { name: /记住登录状态/ })).toBeInTheDocument()
  })

  it('登录失败通过 role=alert 通知，并以 aria-describedby 关联表单', async () => {
    vi.spyOn(authSession, 'login').mockRejectedValue(new Error('unauthorized'))
    const user = userEvent.setup()
    renderDrawer()

    await user.type(screen.getByLabelText('账号'), 'alice')
    await user.type(screen.getByLabelText('密码'), 'wrong-password')
    await user.click(screen.getByRole('button', { name: '登录' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/账号或密码/)
    const form = alert.closest('form')!
    expect(form).toHaveAttribute('aria-describedby', 'login-error')
    expect(alert).toHaveAttribute('id', 'login-error')
  })

  it('注册失败使用独立于登录失败的错误文案', async () => {
    vi.spyOn(authApi, 'register').mockRejectedValue(new Error('username taken'))
    const user = userEvent.setup()
    renderDrawer()

    await user.click(screen.getByRole('button', { name: '还没有账号？创建账号' }))
    await user.type(screen.getByLabelText('账号'), 'alice')
    await user.type(screen.getByLabelText('密码'), 'password')
    await user.click(screen.getByRole('button', { name: '注册并登录' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/创建账号失败/)
    expect(alert).not.toHaveTextContent(/账号或密码/)
  })

  it('保留注册入口（PRD/API 仍允许注册）', () => {
    renderDrawer()

    expect(screen.getByRole('button', { name: '还没有账号？创建账号' })).toBeInTheDocument()
  })

  it('不实现没有规格/API 支持的「忘记密码」假入口', () => {
    renderDrawer()

    expect(screen.queryByRole('link', { name: /忘记密码/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /忘记密码/ })).not.toBeInTheDocument()
  })
})
