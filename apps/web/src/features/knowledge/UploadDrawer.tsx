import { useMutation } from '@tanstack/react-query'
import { useRef, useState } from 'react'

import { knowledgeApi, type KnowledgeApi } from '@/api/knowledge'
import { Icon } from '@/components/icons/Icon'
import { useOverlayFocus } from '@/components/overlay/useOverlayFocus'

const ALLOWED_EXTENSIONS = ['pdf', 'docx', 'md', 'txt'] as const
const ALLOWED_DISPLAY = 'PDF、DOCX、Markdown、TXT'

type Props = {
  kbId: string
  api?: KnowledgeApi
  onClose: () => void
  onUploaded: () => void
}

/** 上传文档右侧抽屉（对齐 FRONTEND §5.4 / UIDESIGN §6.6）：校验扩展名，提交后异步入库。 */
export function UploadDrawer({ kbId, api = knowledgeApi, onClose, onUploaded }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [force, setForce] = useState(false)
  const [validationError, setValidationError] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const drawerRef = useRef<HTMLElement>(null)

  const mutation = useMutation({
    mutationFn: () => api.uploadDocument(kbId, file!, force),
    onSuccess: onUploaded,
    onError: (err: Error) => {
      setSubmitError(err.message)
    },
  })
  useOverlayFocus({ containerRef: drawerRef, onClose, canClose: !mutation.isPending })

  function handleFileChange(files: FileList | null) {
    setValidationError(null)
    setSubmitError(null)
    const selected = files?.[0] ?? null
    if (!selected) {
      setFile(null)
      return
    }
    const extension = selected.name.split('.').pop()?.toLowerCase() ?? ''
    if (!ALLOWED_EXTENSIONS.includes(extension as (typeof ALLOWED_EXTENSIONS)[number])) {
      setFile(null)
      setValidationError(`仅支持 ${ALLOWED_DISPLAY} 文件`)
      return
    }
    setFile(selected)
  }

  return (
    <div className="drawer-overlay" role="presentation">
      <aside
        ref={drawerRef}
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label="上传文档"
        tabIndex={-1}
      >
        <header className="drawer__header">
          <h2>上传文档</h2>
          <button type="button" className="drawer__close" aria-label="关闭" onClick={onClose}>
            <Icon name="close" />
          </button>
        </header>
        <form
          className="drawer__body"
          onSubmit={(event) => {
            event.preventDefault()
            setSubmitError(null)
            if (!file) {
              setValidationError(`请先选择一个 ${ALLOWED_DISPLAY} 文件`)
              return
            }
            mutation.mutate()
          }}
        >
          <label>
            选择文件
            <input
              ref={inputRef}
              data-overlay-initial-focus
              type="file"
              accept=".pdf,.docx,.md,.txt"
              onChange={(event) => handleFileChange(event.target.files)}
            />
          </label>
          {file ? (
            <p className="file-picked">
              已选择：{file.name}（{formatSize(file.size)}）
            </p>
          ) : null}
          {validationError ? (
            <p className="form-error" role="alert">
              {validationError}
            </p>
          ) : null}
          <label className="check-row">
            <input
              type="checkbox"
              checked={force}
              onChange={(event) => setForce(event.target.checked)}
            />
            <span>覆盖同名终态文档</span>
          </label>
          {submitError ? (
            <p className="form-error" role="alert">
              {submitError}
            </p>
          ) : null}
          <div className="drawer__footer">
            <button type="button" className="btn" onClick={onClose} disabled={mutation.isPending}>
              取消
            </button>
            <button
              type="submit"
              className="btn btn--primary"
              disabled={mutation.isPending || !file}
            >
              {mutation.isPending ? '上传中…' : '开始上传'}
            </button>
          </div>
        </form>
      </aside>
    </div>
  )
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
