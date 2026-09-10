import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'

import { ConfirmDialog } from '@/components/feedback/ConfirmDialog'

function DialogHarness({ pending = false }: { pending?: boolean }) {
  const [open, setOpen] = useState(false)

  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        删除知识库
      </button>
      {open ? (
        <ConfirmDialog
          title="删除知识库"
          description="删除后不可恢复。"
          confirmLabel="删除知识库"
          pending={pending}
          onCancel={() => setOpen(false)}
          onConfirm={() => undefined}
        />
      ) : null}
    </>
  )
}

describe('Overlay 焦点门禁', () => {
  it('打开后进入 Overlay，Tab 在内部循环，Escape 关闭并返回触发器', async () => {
    const user = userEvent.setup()
    render(<DialogHarness />)

    const trigger = screen.getByRole('button', { name: '删除知识库' })
    await user.click(trigger)

    const cancel = screen.getByRole('button', { name: '取消' })
    const confirm = screen.getAllByRole('button', { name: '删除知识库' })[1]
    expect(cancel).toHaveFocus()

    await user.tab({ shift: true })
    expect(confirm).toHaveFocus()

    await user.tab()
    expect(cancel).toHaveFocus()

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('提交期间禁止 Escape 关闭', async () => {
    const user = userEvent.setup()
    render(<DialogHarness pending />)

    await user.click(screen.getByRole('button', { name: '删除知识库' }))
    await user.keyboard('{Escape}')

    expect(screen.getByRole('dialog', { name: '删除知识库' })).toBeInTheDocument()
  })
})
