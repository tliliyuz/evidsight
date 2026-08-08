import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { AppShell } from '@/app/AppShell'

const user = {
  id: '550e8400-e29b-41d4-a716-446655440001',
  username: 'alice',
  role: 'user' as const,
  status: 'active' as const,
}

describe('统一应用壳层', () => {
  it('按规范顺序展示六项导航且普通用户不显示管理入口', () => {
    render(
      <MemoryRouter>
        <AppShell user={user} runningTaskCount={2}>
          <div>内容</div>
        </AppShell>
      </MemoryRouter>,
    )

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
    expect(screen.getByRole('link', { name: '2 个研究任务运行中' })).toHaveAttribute(
      'href',
      '/research?status=running',
    )
  })
})
