import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { authApi } from '@/api/auth'
import { ToastProvider } from '@/components/feedback/ToastProvider'
import { PasswordChangeDrawer } from '@/features/auth/PasswordChangeDrawer'

function renderDrawer(onClose = vi.fn()) {
  return render(
    <ToastProvider>
      <PasswordChangeDrawer onClose={onClose} />
    </ToastProvider>,
  )
}

describe('修改密码右侧抽屉', () => {
  it('提供当前密码/新密码/确认新密码三个字段与提交按钮', () => {
    renderDrawer()

    expect(screen.getByRole('dialog', { name: '修改密码' })).toBeInTheDocument()
    expect(screen.getByLabelText('当前密码')).toBeInTheDocument()
    expect(screen.getByLabelText('新密码')).toBeInTheDocument()
    expect(screen.getByLabelText('确认新密码')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '保存修改' })).toBeInTheDocument()
    // 三个输入框内嵌提示（对齐创建知识库表单占位符模式）
    expect(screen.getByPlaceholderText('请输入当前密码（6-128 字）')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入新密码（6-128 字）')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请再次输入新密码')).toBeInTheDocument()
  })

  it('两次新密码不一致时前端拦截，不调用 API 并提示', async () => {
    const changePassword = vi.spyOn(authApi, 'changePassword').mockResolvedValue()
    const user = userEvent.setup()
    renderDrawer()

    await user.type(screen.getByLabelText('当前密码'), 'old-pass-1')
    await user.type(screen.getByLabelText('新密码'), 'new-pass-1')
    await user.type(screen.getByLabelText('确认新密码'), 'new-pass-2')
    await user.click(screen.getByRole('button', { name: '保存修改' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/新密码不一致/)
    expect(changePassword).not.toHaveBeenCalled()
  })

  it('修改成功弹「密码已修改」Toast 并关闭抽屉', async () => {
    const changePassword = vi.spyOn(authApi, 'changePassword').mockResolvedValue()
    const onClose = vi.fn()
    const user = userEvent.setup()
    renderDrawer(onClose)

    await user.type(screen.getByLabelText('当前密码'), 'old-pass-1')
    await user.type(screen.getByLabelText('新密码'), 'new-pass-123')
    await user.type(screen.getByLabelText('确认新密码'), 'new-pass-123')
    await user.click(screen.getByRole('button', { name: '保存修改' }))

    await waitFor(() => expect(changePassword).toHaveBeenCalledWith('old-pass-1', 'new-pass-123'))
    expect(screen.getByRole('status')).toHaveTextContent('密码已修改')
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('当前密码错误（E5002）展示「当前密码不正确」，不展示登录文案', async () => {
    vi.spyOn(authApi, 'changePassword').mockRejectedValue({
      response: { data: { error: { message: '用户名或密码错误', error_code: 'E5002' } } },
    })
    const user = userEvent.setup()
    renderDrawer()

    await user.type(screen.getByLabelText('当前密码'), 'wrong-pass')
    await user.type(screen.getByLabelText('新密码'), 'new-pass-123')
    await user.type(screen.getByLabelText('确认新密码'), 'new-pass-123')
    await user.click(screen.getByRole('button', { name: '保存修改' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('当前密码不正确')
  })

  it('新旧密码相同（E7004）展示后端文案「新密码不能与原密码相同」', async () => {
    vi.spyOn(authApi, 'changePassword').mockRejectedValue({
      response: { data: { error: { message: '新密码不能与原密码相同', error_code: 'E7004' } } },
    })
    const user = userEvent.setup()
    renderDrawer()

    await user.type(screen.getByLabelText('当前密码'), 'same-pass')
    await user.type(screen.getByLabelText('新密码'), 'same-pass')
    await user.type(screen.getByLabelText('确认新密码'), 'same-pass')
    await user.click(screen.getByRole('button', { name: '保存修改' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('新密码不能与原密码相同')
  })
})
