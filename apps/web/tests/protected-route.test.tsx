import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { ProtectedRoute } from '@/features/auth/ProtectedRoute'
import { authSession } from '@/features/auth/authSession'

describe('受保护路由', () => {
  beforeEach(() => authSession.resetForTesting())

  it('身份恢复完成前不渲染受保护内容', () => {
    authSession.setRestoringForTesting()
    render(
      <MemoryRouter>
        <ProtectedRoute>
          <div>敏感工作台</div>
        </ProtectedRoute>
      </MemoryRouter>,
    )

    expect(screen.queryByText('敏感工作台')).not.toBeInTheDocument()
    expect(screen.getByText('正在恢复身份…')).toBeInTheDocument()
  })
})
