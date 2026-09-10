import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { BrandMark } from '@/components/brand/BrandMark'
import { Button } from '@/components/actions/Button'
import { Icon } from '@/components/icons/Icon'

describe('P0 共享视觉基础', () => {
  it('品牌标记使用可复用资产并提供可访问名称', () => {
    const { rerender } = render(<BrandMark label="EvidSight" />)

    expect(screen.getByRole('img', { name: 'EvidSight' })).toBeInTheDocument()

    rerender(<BrandMark decorative />)
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })

  it('图标默认仅作装饰，必要时可以提供语义', () => {
    const { rerender } = render(<Icon name="knowledge" />)
    expect(screen.queryByRole('img')).not.toBeInTheDocument()

    rerender(<Icon name="knowledge" label="知识库" />)
    expect(screen.getByRole('img', { name: '知识库' })).toBeInTheDocument()
  })

  it('按钮统一变体并在忙碌态保留明确动作名称', () => {
    render(
      <Button variant="primary" busy busyLabel="正在保存">
        保存知识库
      </Button>,
    )

    const button = screen.getByRole('button', { name: '正在保存' })
    expect(button).toBeDisabled()
    expect(button).toHaveClass('btn', 'btn--primary')
  })
})
