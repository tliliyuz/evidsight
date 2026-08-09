import { useMutation } from '@tanstack/react-query'
import { useRef, useState } from 'react'

import { knowledgeApi, type KnowledgeApi, type KnowledgeBase } from '@/api/knowledge'
import { Icon } from '@/components/icons/Icon'
import { useOverlayFocus } from '@/components/overlay/useOverlayFocus'

type Props = {
  initial: KnowledgeBase | null
  api?: KnowledgeApi
  onClose: () => void
  onSaved: () => void
}

/** 新建/编辑知识库右侧抽屉（对齐 FRONTEND §5.3 / UIDESIGN §6.6 Drawer）。 */
export function KnowledgeBaseFormDialog({ initial, api = knowledgeApi, onClose, onSaved }: Props) {
  const [name, setName] = useState(initial?.name ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [visibility, setVisibility] = useState<'private' | 'public'>(
    initial?.visibility ?? 'private',
  )
  const [error, setError] = useState<string | null>(null)
  const nameRef = useRef<HTMLInputElement>(null)
  const drawerRef = useRef<HTMLElement>(null)

  const mutation = useMutation({
    mutationFn: () =>
      initial
        ? api.updateKnowledgeBase(initial.uuid, { name, description, visibility })
        : api.createKnowledgeBase({ name, description, visibility }),
    onSuccess: onSaved,
    onError: (err: Error) => {
      setError(err.message)
    },
  })
  useOverlayFocus({ containerRef: drawerRef, onClose, canClose: !mutation.isPending })

  const trimmedName = name.trim()

  return (
    <div className="drawer-overlay" role="presentation">
      <aside
        ref={drawerRef}
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label={initial ? '编辑知识库' : '新建知识库'}
        tabIndex={-1}
      >
        <header className="drawer__header">
          <h2>{initial ? '编辑知识库' : '新建知识库'}</h2>
          <button type="button" className="drawer__close" aria-label="关闭" onClick={onClose}>
            <Icon name="close" />
          </button>
        </header>
        <form
          className="drawer__body"
          onSubmit={(event) => {
            event.preventDefault()
            setError(null)
            if (!trimmedName) {
              setError('请填写知识库名称')
              return
            }
            mutation.mutate()
          }}
        >
          <label>
            知识库名称
            <input
              ref={nameRef}
              data-overlay-initial-focus
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              minLength={2}
              maxLength={128}
            />
          </label>
          <label>
            描述（可选）
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              maxLength={2000}
              rows={4}
            />
          </label>
          <fieldset>
            <legend>可见性</legend>
            <label className="radio-row">
              <input
                type="radio"
                name="visibility"
                value="private"
                checked={visibility === 'private'}
                onChange={() => setVisibility('private')}
              />
              <span>私有</span>
              <small>仅自己与管理员可见</small>
            </label>
            <label className="radio-row">
              <input
                type="radio"
                name="visibility"
                value="public"
                checked={visibility === 'public'}
                onChange={() => setVisibility('public')}
              />
              <span>公开</span>
              <small>组织内所有成员可读</small>
            </label>
          </fieldset>
          {error ? (
            <p className="form-error" role="alert">
              {error}
            </p>
          ) : null}
          <div className="drawer__footer">
            <button type="button" className="btn" onClick={onClose} disabled={mutation.isPending}>
              取消
            </button>
            <button type="submit" className="btn btn--primary" disabled={mutation.isPending}>
              {mutation.isPending ? '提交中…' : '创建'}
            </button>
          </div>
        </form>
      </aside>
    </div>
  )
}
