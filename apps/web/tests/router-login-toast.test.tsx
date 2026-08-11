import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, type RouteObject } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { routes, RootLayout } from '@/app/Router'
import { LoginDrawer } from '@/features/auth/LoginDrawer'
import { authSession } from '@/features/auth/authSession'

function collectPaths(routeList: RouteObject[]): string[] {
  return routeList.flatMap((route) => {
    const own = route.path ? [route.path] : []
    return own.concat(route.children ? collectPaths(route.children) : [])
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
  authSession.resetForTesting()
})

describe('登录成功反馈的 ToastProvider 位置（FRONTEND §5.1：挂在路由之上）', () => {
  it('真实路由所用根 layout（RootLayout）为 /login 提供 ToastProvider：登录成功 Toast 跨导航存活', async () => {
    // 不手动包裹 ToastProvider——由真实根 layout RootLayout 提供，与生产同源
    vi.spyOn(authSession, 'login').mockResolvedValue()
    render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route element={<RootLayout />}>
            <Route path="/login" element={<LoginDrawer />} />
            <Route path="/workbench" element={<div>工作台</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByLabelText('账号'), { target: { value: 'alice' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'password' } })
    fireEvent.click(screen.getByRole('button', { name: '登录' }))

    // 登录成功后导航到 /workbench，ToastProvider 仍为同一实例（RootLayout 不随子路由卸载）
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('欢迎回来，alice'))
  })

  it('真实路由配置：根 layout 是 RootLayout，/login 在其子树内、不在登录后壳层子树内', () => {
    const root = routes[0] as {
      element: { type: unknown }
      children: RouteObject[]
    }
    // 根 layout 必须是 RootLayout（ToastProvider 包裹者）
    expect(root.element.type).toBe(RootLayout)

    const rootPaths = collectPaths(root.children)
    expect(rootPaths).toContain('/login')

    // 登录后壳层（ProtectedRoute/AuthenticatedShell）子树内不能有 /login
    const shellChildren = (root.children[1] as { children: RouteObject[] }).children
    expect(collectPaths(shellChildren)).not.toContain('/login')
  })
})
