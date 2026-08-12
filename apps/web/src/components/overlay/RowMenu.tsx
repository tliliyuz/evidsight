import { useEffect, useRef, useState } from 'react'

export type RowMenuAction = {
  label: string
  danger?: boolean
  onSelect: () => void
}

/**
 * 列表行操作溢出菜单：行内只留主操作，次级操作收敛到 `⋮` 触发按钮。
 * 点击外部或 Escape 关闭；菜单项点击后先关闭再执行动作。
 */
export function RowMenu({ label, actions }: { label: string; actions: RowMenuAction[] }) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return undefined
    function handlePointerDown(event: MouseEvent | TouchEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('touchstart', handlePointerDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('touchstart', handlePointerDown)
    }
  }, [open])

  return (
    <div
      className="row-menu"
      ref={rootRef}
      onKeyDown={(event) => {
        if (event.key === 'Escape') setOpen(false)
      }}
    >
      <button
        type="button"
        className="row-menu__trigger"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((opening) => !opening)}
      >
        <span aria-hidden="true">⋮</span>
      </button>
      {open ? (
        <div className="row-menu__panel" role="menu">
          {actions.map((action) => (
            <button
              key={action.label}
              type="button"
              role="menuitem"
              className={action.danger ? 'row-menu__item row-menu__item--danger' : 'row-menu__item'}
              onClick={() => {
                setOpen(false)
                action.onSelect()
              }}
            >
              {action.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}
