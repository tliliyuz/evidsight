import { useEffect, useRef } from 'react'

type Props = {
  title: string
  description: string
  confirmLabel: string
  tone?: 'default' | 'danger'
  pending?: boolean
  onCancel: () => void
  onConfirm: () => void
}

/** 具名确认对话框（对齐 UIDESIGN §6.6 / FRONTEND §10）：危险操作必须具名，不用模糊的“确定/取消”。 */
export function ConfirmDialog({
  title,
  description,
  confirmLabel,
  tone = 'default',
  pending = false,
  onCancel,
  onConfirm,
}: Props) {
  const cancelRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    cancelRef.current?.focus()
  }, [])

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && !pending) {
        onCancel()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onCancel, pending])

  return (
    <div className="dialog-overlay" role="presentation">
      <div className="dialog" role="dialog" aria-modal="true" aria-label={title}>
        <h2>{title}</h2>
        <p>{description}</p>
        <div className="dialog__actions">
          <button
            ref={cancelRef}
            type="button"
            className="btn"
            disabled={pending}
            onClick={onCancel}
          >
            取消
          </button>
          <button
            type="button"
            className={tone === 'danger' ? 'btn btn--danger' : 'btn btn--primary'}
            disabled={pending}
            onClick={onConfirm}
          >
            {pending ? '处理中…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
