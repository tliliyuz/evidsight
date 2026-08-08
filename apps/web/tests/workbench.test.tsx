import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { WorkbenchPage } from '@/features/workbench/WorkbenchPage'

describe('工作台', () => {
  it('无历史时提供行动入口而不是空 KPI', () => {
    render(
      <MemoryRouter>
        <WorkbenchPage recentResearch={[]} recentKnowledge={[]} />
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: '开始研究' })).toHaveAttribute('href', '/research/new')
    expect(screen.getByRole('link', { name: '创建知识库' })).toHaveAttribute(
      'href',
      '/knowledge-bases?create=1',
    )
    expect(screen.queryByText(/KPI/i)).not.toBeInTheDocument()
  })
})
