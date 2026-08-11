import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ErrorState } from '@/components/feedback/ErrorState'

/**
 * 错误态与空态（EmptyState）结构同构：三级标题 + 说明文案 + 主按钮动作，
 * CSS 上 `.error-state` 与 `.empty-state` 共享居中布局（global.css），
 * 保证「空知识库/空文档/空对话」与「暂时无法加载」视觉一致。
 */
describe('ErrorState 错误态', () => {
  it('标题为三级标题（与 EmptyState 同构）并展示安全说明', () => {
    render(<ErrorState onRetry={vi.fn()} />)

    expect(screen.getByRole('heading', { level: 3, name: '暂时无法加载' })).toBeInTheDocument()
    expect(screen.getByText('内容仍然安全保留，请稍后重试。')).toBeInTheDocument()
  })

  it('重试按钮使用主按钮样式（对齐空态动作按钮）', () => {
    render(<ErrorState onRetry={vi.fn()} />)

    const retry = screen.getByRole('button', { name: '重试' })
    expect(retry.className).toContain('btn')
    expect(retry.className).toContain('btn--primary')
  })

  it('未传 onRetry 时不渲染重试按钮', () => {
    render(<ErrorState />)

    expect(screen.queryByRole('button', { name: '重试' })).not.toBeInTheDocument()
  })

  it('展示安全错误请求 ID（不暴露堆栈或内部路径）', () => {
    render(<ErrorState requestId="req-8f3a" onRetry={vi.fn()} />)

    expect(screen.getByText('请求 ID：req-8f3a')).toBeInTheDocument()
  })
})
