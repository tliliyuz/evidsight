import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LoginDrawer } from '@/features/auth/LoginDrawer'
import { authSession } from '@/features/auth/authSession'

describe('登录抽屉', () => {
  beforeEach(() => authSession.resetForTesting())

  it('提交期间防止重复并在成功后返回目标路由', async () => {
    const login = vi.spyOn(authSession, 'login').mockResolvedValue()
    render(
      <MemoryRouter initialEntries={[{ pathname: '/login', state: { returnTo: '/research' } }]}>
        <Routes>
          <Route path="/login" element={<LoginDrawer />} />
          <Route path="/research" element={<div>研究任务</div>} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByLabelText('账号'), { target: { value: 'alice' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'password' } })
    fireEvent.click(screen.getByRole('button', { name: '登录' }))

    expect(screen.getByRole('button', { name: '正在登录…' })).toBeDisabled()
    await waitFor(() => expect(screen.getByText('研究任务')).toBeInTheDocument())
    expect(login).toHaveBeenCalledOnce()
  })
})
