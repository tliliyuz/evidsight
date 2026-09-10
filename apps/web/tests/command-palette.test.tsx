import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CommandPalette } from '@/components/command/CommandPalette'

const navigateMock = vi.fn()

// 仅 mock useNavigate，Link/MemoryRouter 保持真实
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => navigateMock }
})

beforeEach(() => {
  navigateMock.mockReset()
})

function renderPalette() {
  const onClose = vi.fn()
  render(
    <MemoryRouter>
      <CommandPalette onClose={onClose} />
    </MemoryRouter>,
  )
  return { onClose }
}

describe('命令面板', () => {
  it('打开时聚焦搜索框且不显示命令列表，输入后才弹出', () => {
    renderPalette()

    expect(screen.getByLabelText('搜索命令')).toHaveFocus()
    // 空输入不显示下拉列表
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(screen.queryByText('工作台')).not.toBeInTheDocument()
  })

  it('输入按名称/说明过滤命令', async () => {
    const user = userEvent.setup()
    renderPalette()

    await user.type(screen.getByLabelText('搜索命令'), '知识')
    expect(screen.getByText('知识库')).toBeInTheDocument()
    expect(screen.getByText('创建知识库')).toBeInTheDocument()
    expect(screen.queryByText('工作台')).not.toBeInTheDocument()
  })

  it('↑/↓ 移动，Enter 执行当前项并导航', async () => {
    const user = userEvent.setup()
    const { onClose } = renderPalette()

    const input = screen.getByLabelText('搜索命令')
    // 「知识库」唯一命中 知识库/创建知识库 两项（「知识」会连带命中 据见问答 的说明）
    await user.type(input, '知识库')
    // 首项 = 知识库；↓ 到 创建知识库（fireEvent 直击 input + waitFor 刷新重渲染），再 Enter 执行
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    await waitFor(() => {
      expect(screen.getByText('创建知识库').closest('li')).toHaveClass('is-active')
    })
    fireEvent.keyDown(input, { key: 'Enter' })

    expect(navigateMock).toHaveBeenCalledWith('/knowledge-bases?create=1')
    expect(onClose).toHaveBeenCalled()
  })

  it('无匹配时展示「无匹配命令」', async () => {
    const user = userEvent.setup()
    renderPalette()

    await user.type(screen.getByLabelText('搜索命令'), '不存在的命令xyz')
    expect(screen.getByText('无匹配命令')).toBeInTheDocument()
  })

  it('Escape 关闭并调用 onClose', async () => {
    const user = userEvent.setup()
    const { onClose } = renderPalette()

    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })
})
