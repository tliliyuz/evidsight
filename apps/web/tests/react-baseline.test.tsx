import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { App } from '@/app/App'

describe('React 工程基线', () => {
  it('以单一 React 根节点渲染 EvidSight', () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: 'EvidSight' })).toBeInTheDocument()
    expect(document.documentElement.dataset.theme).toBe('light')
  })
})
