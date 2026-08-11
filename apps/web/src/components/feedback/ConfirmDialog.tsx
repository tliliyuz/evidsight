import { useRef } from 'react'

import { Button } from '@/components/actions/Button'
import { useOverlayFocus } from '@/components/overlay/useOverlayFocus'

type Props = {
  title: string
  description: string
  confirmLabel: string
  tone?: 'default' | 'danger'
  pending?: boolean
  /** 阻塞态按钮文案（如「删除中…」），缺省「处理中…」 */
  busyLabel?: string
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
  busyLabel = '处理中…',
  onCancel,
  onConfirm,
}: Props) {
  const dialogRef = useRef<HTMLDivElement>(null)
  useOverlayFocus({ containerRef: dialogRef, onClose: onCancel, canClose: !pending })

  return (
    <div className="dialog-overlay" role="presentation">
      <div
        ref={dialogRef}
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
      >
        <h2>{title}</h2>
        <p>{description}</p>
        <div className="dialog__actions">
          <Button type="button" data-overlay-initial-focus disabled={pending} onClick={onCancel}>
            取消
          </Button>
          <Button
            type="button"
            variant={tone === 'danger' ? 'danger' : 'primary'}
            busy={pending}
            busyLabel={busyLabel}
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}
