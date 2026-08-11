import { useRef, useState } from 'react'

import { apiErrorMessage } from '@/api/errors'
import { knowledgeApi, type KnowledgeApi } from '@/api/knowledge'
import { Icon } from '@/components/icons/Icon'
import { useOverlayFocus } from '@/components/overlay/useOverlayFocus'

const ALLOWED_EXTENSIONS = ['pdf', 'docx', 'md', 'txt'] as const
const ALLOWED_DISPLAY = 'PDF、DOCX、Markdown、TXT'
/** 与后端 settings.UPLOAD_MAX_SIZE 对齐（50 MB，单文件）。 */
const MAX_SIZE_MB = 50

type QueueItem = { id: string; file: File }
type UploadState =
  { status: 'ready' | 'uploading' | 'done' | 'cancelled' } | { status: 'error'; message: string }

let nextItemId = 0
function createItemId(): string {
  nextItemId += 1
  return `upload-item-${nextItemId}`
}

type Props = {
  kbId: string
  api?: KnowledgeApi
  onClose: () => void
  onUploaded: () => void
}

const STATUS_TEXT: Record<UploadState['status'], string> = {
  ready: '就绪',
  uploading: '上传中',
  done: '已完成',
  error: '失败',
  cancelled: '已取消',
}

/** 上传文档右侧抽屉（对齐 FRONTEND §5.4 / UIDESIGN §6.6）：
    多文件队列（客户端批量，逐文件复用单文件 API），Drop Zone 拖入/点击多选；
    上传中可「取消上传」中止进行中的批次（AbortController），不关闭抽屉。 */
export function UploadDrawer({ kbId, api = knowledgeApi, onClose, onUploaded }: Props) {
  const [queue, setQueue] = useState<QueueItem[]>([])
  const [states, setStates] = useState<Record<string, UploadState>>({})
  const [force, setForce] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [validationError, setValidationError] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const drawerRef = useRef<HTMLElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  // 上传中禁止关闭（Escape/焦点循环），只能通过「取消上传」中止批次
  useOverlayFocus({ containerRef: drawerRef, onClose, canClose: !uploading })

  function addFiles(files: FileList | File[] | null) {
    setValidationError(null)
    setSubmitError(null)
    const incoming = Array.from(files ?? [])
    if (incoming.length === 0) return
    const existingNames = new Set(queue.map((item) => item.file.name))
    const accepted: QueueItem[] = []
    for (const file of incoming) {
      const extension = file.name.split('.').pop()?.toLowerCase() ?? ''
      if (!ALLOWED_EXTENSIONS.includes(extension as (typeof ALLOWED_EXTENSIONS)[number])) {
        setValidationError(`仅支持 ${ALLOWED_DISPLAY} 文件，已忽略「${file.name}」`)
        continue
      }
      if (existingNames.has(file.name)) {
        setValidationError(`已选择「${file.name}」，同名文件被忽略`)
        continue
      }
      existingNames.add(file.name)
      accepted.push({ id: createItemId(), file })
    }
    if (accepted.length > 0) {
      setQueue((prev) => [...prev, ...accepted])
    }
  }

  function removeFile(itemId: string) {
    if (uploading) return
    setQueue((prev) => prev.filter((item) => item.id !== itemId))
    setStates((prev) => {
      const next = { ...prev }
      delete next[itemId]
      return next
    })
  }

  async function handleSubmit() {
    if (uploading || queue.length === 0) {
      if (queue.length === 0) setValidationError(`请先选择 ${ALLOWED_DISPLAY} 文件`)
      return
    }
    setSubmitError(null)
    setUploading(true)
    const controller = new AbortController()
    abortRef.current = controller

    const next = { ...states }
    let anySucceeded = false
    for (const item of queue) {
      if (controller.signal.aborted) break
      next[item.id] = { status: 'uploading' }
      setStates({ ...next })
      try {
        await api.uploadDocument(kbId, item.file, force, controller.signal)
        if (controller.signal.aborted) {
          next[item.id] = { status: 'cancelled' }
          break
        }
        anySucceeded = true
        next[item.id] = { status: 'done' }
      } catch (error) {
        if (controller.signal.aborted) {
          next[item.id] = { status: 'cancelled' }
          break
        }
        next[item.id] = {
          status: 'error',
          message: apiErrorMessage(error, '上传失败，请稍后重试。'),
        }
      }
      setStates({ ...next })
    }
    // 取消：把尚未开始的排队项一并标记为已取消
    if (controller.signal.aborted) {
      for (const item of queue) {
        if (next[item.id]?.status === 'ready') {
          next[item.id] = { status: 'cancelled' }
        }
      }
    }
    setStates({ ...next })
    abortRef.current = null
    setUploading(false)
    if (anySucceeded) onUploaded()
  }

  function handleCancel() {
    abortRef.current?.abort()
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
          {/* 上传中禁用右上角关闭：中止批次只能通过「取消上传」 */}
          <button
            type="button"
            className="drawer__close"
            aria-label="关闭"
            disabled={uploading}
            onClick={onClose}
          >
            <Icon name="close" />
          </button>
        </header>
        <form
          className="drawer__body"
          onSubmit={(event) => {
            event.preventDefault()
            void handleSubmit()
          }}
        >
          {/* 视觉隐藏的原生文件输入（多选）：由 Drop Zone / 继续添加触发；aria-label 供辅助技术与测试定位 */}
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".pdf,.docx,.md,.txt"
            aria-label="选择文件"
            className="sr-only"
            tabIndex={-1}
            disabled={uploading}
            onChange={(event) => {
              addFiles(event.target.files)
              event.target.value = ''
            }}
          />
          {/* Drop Zone 常驻：选中后下方追加文件列表，选择区样式保持不变（可继续拖入/多选） */}
          <button
            type="button"
            className={`drop-zone${dragging ? ' drop-zone--drag' : ''}`}
            data-overlay-initial-focus
            disabled={uploading}
            onClick={() => inputRef.current?.click()}
            onDragOver={(event) => {
              event.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault()
              setDragging(false)
              addFiles(event.dataTransfer.files)
            }}
          >
            <b>拖入文件，或从设备选择</b>
            <span>PDF · DOCX · Markdown · TXT</span>
            <small>单文件不超过 {MAX_SIZE_MB} MB，可多选</small>
          </button>
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
            <span>覆盖同名文档</span>
          </label>
          {queue.length > 0 ? (
            <ul className="upload-queue" aria-label="待上传文件">
              {queue.map((item) => {
                const state = states[item.id] ?? { status: 'ready' as const }
                return (
                  <li key={item.id} className="upload-queue__row">
                    <span className="upload-queue__name">
                      <b>{item.file.name}</b>
                      <small>{formatSize(item.file.size)}</small>
                      {state.status === 'error' ? (
                        <small className="upload-queue__error">{state.message}</small>
                      ) : null}
                    </span>
                    <em className={`upload-queue__status upload-queue__status--${state.status}`}>
                      {STATUS_TEXT[state.status]}
                    </em>
                    <button
                      type="button"
                      className="upload-queue__remove"
                      aria-label={`移除 ${item.file.name}`}
                      disabled={uploading}
                      onClick={() => removeFile(item.id)}
                    >
                      <Icon name="close" />
                    </button>
                  </li>
                )
              })}
            </ul>
          ) : null}
          {submitError ? (
            <p className="form-error" role="alert">
              {submitError}
            </p>
          ) : null}
          <div className="drawer__footer">
            {/* 空闲时无「取消」按钮（关闭走右上角 ×）；上传中「取消上传」中止批次，不退出抽屉 */}
            {uploading ? (
              <button type="button" className="btn" onClick={handleCancel}>
                取消上传
              </button>
            ) : null}
            <button
              type="submit"
              className="btn btn--primary"
              disabled={uploading || queue.length === 0}
            >
              {uploading ? '上传中…' : '开始上传'}
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
