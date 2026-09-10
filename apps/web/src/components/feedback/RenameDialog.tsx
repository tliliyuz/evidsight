import { useRef, useState } from 'react'

import { Button } from '@/components/actions/Button'
import { useOverlayFocus } from '@/components/overlay/useOverlayFocus'

/**
 * 具名重命名对话框（FRONTEND §5.6 / 知识库详情复用）。
 * 提交中禁用关闭（canClose=false），失败时保持打开；成功由调用方关闭。
 */
export function RenameDialog({
  initialTitle,
  pending,
  onCancel,
  onConfirm,
}: {
  initialTitle: string
  pending: boolean
  onCancel: () => void
  onConfirm: (title: string) => void
}) {
  const [title, setTitle] = useState(initialTitle)
  const dialogRef = useRef<HTMLDivElement>(null)
  useOverlayFocus({ containerRef: dialogRef, onClose: onCancel, canClose: !pending })
  return (
    <div className="dialog-overlay" role="presentation">
      <div
        ref={dialogRef}
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-label="重命名会话"
        tabIndex={-1}
      >
        <h2>重命名会话</h2>
        <label className="dialog__field">
          <span>会话名称</span>
          <input
            value={title}
            data-overlay-initial-focus
            onChange={(event) => setTitle(event.target.value)}
            maxLength={256}
          />
        </label>
        <div className="dialog__actions">
          <Button type="button" disabled={pending} onClick={onCancel}>
            取消
          </Button>
          <Button
            type="button"
            variant="primary"
            busy={pending}
            disabled={!title.trim()}
            onClick={() => onConfirm(title.trim())}
          >
            保存
          </Button>
        </div>
      </div>
    </div>
  )
}
