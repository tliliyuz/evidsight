import { useQuery } from '@tanstack/react-query'
import { useSyncExternalStore, useEffect, useRef, useState } from 'react'

import { knowledgeApi, type KnowledgeBase, type KnowledgeScope } from '@/api/knowledge'
import { StatusBadge } from '@/components/feedback/StatusBadge'
import { authSession } from '@/features/auth/authSession'

function useCurrentUser() {
  const auth = useSyncExternalStore(authSession.subscribe, authSession.getSnapshot)
  return auth.user
}

const KB_SCOPE_TABS: { value: KnowledgeScope; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'mine', label: '我的知识库' },
  { value: 'public', label: '公共知识库' },
]

/**
 * 创建研究「内部知识范围」多选选择器（FRONTEND §5.7，多选 1–50）。
 *
 * 复用知识中心/问答的 `kb-picker__*` 浮层结构（搜索 + 作用域 + 候选列表），
 * 语义改为多选：点击候选切换选中，触发按钮显示已选数量徽章，触发按钮下方平铺
 * 已选知识库名称 chip 并可逐个移除。单选组件 `KnowledgeBasePicker` 保持不动。
 * 可达性：打开后焦点移入搜索框；`Escape`/点击外部关闭；方向键移动、`Enter` 切换。
 */
export function ResearchKbPicker({
  value,
  onChange,
}: {
  value: KnowledgeBase[]
  onChange: (next: KnowledgeBase[]) => void
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [pickerScope, setPickerScope] = useState<KnowledgeScope>('all')
  const [activeIndex, setActiveIndex] = useState(-1)
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const prevOpenRef = useRef(false)
  const user = useCurrentUser()

  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ['knowledge-bases', 'all', pickerScope, query],
    queryFn: () =>
      knowledgeApi.listKnowledgeBases({
        scope: pickerScope,
        q: query.trim() || undefined,
        page: 1,
        page_size: 5,
      }),
  })

  const items = data?.items ?? []

  useEffect(() => {
    if (open) {
      searchRef.current?.focus()
    } else if (prevOpenRef.current) {
      triggerRef.current?.focus()
    }
    prevOpenRef.current = open
  }, [open])

  function toggleOpen() {
    if (!open) {
      setQuery('')
      setPickerScope('all')
      setActiveIndex(-1)
    }
    setOpen((opening) => !opening)
  }

  function changeScope(next: KnowledgeScope) {
    setPickerScope(next)
    setActiveIndex(-1)
  }

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

  function isSelected(kb: KnowledgeBase): boolean {
    return value.some((item) => item.uuid === kb.uuid)
  }

  function toggle(kb: KnowledgeBase) {
    onChange(isSelected(kb) ? value.filter((item) => item.uuid !== kb.uuid) : [...value, kb])
  }

  function remove(uuid: string) {
    onChange(value.filter((item) => item.uuid !== uuid))
  }

  function handleSearchKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault()
        setActiveIndex((index) => (items.length === 0 ? -1 : (index + 1) % items.length))
        break
      case 'ArrowUp':
        event.preventDefault()
        setActiveIndex((index) =>
          items.length === 0 ? -1 : index <= 0 ? items.length - 1 : index - 1,
        )
        break
      case 'Home':
        event.preventDefault()
        setActiveIndex(items.length > 0 ? 0 : -1)
        break
      case 'End':
        event.preventDefault()
        setActiveIndex(items.length > 0 ? items.length - 1 : -1)
        break
      case 'Enter': {
        const active = activeIndex >= 0 ? items[activeIndex] : null
        if (active) {
          event.preventDefault()
          toggle(active)
        }
        break
      }
      case 'Escape':
        event.preventDefault()
        setOpen(false)
        break
      case 'Tab':
        setOpen(false)
        break
    }
  }

  const activeId =
    activeIndex >= 0 && items[activeIndex]
      ? `research-kb-option-${items[activeIndex].uuid}`
      : undefined

  return (
    <div className="kb-picker research-kb-picker" ref={rootRef}>
      <div className="kb-picker__current">
        <button
          ref={triggerRef}
          type="button"
          className="kb-picker__trigger"
          onClick={toggleOpen}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls="research-kb-listbox"
        >
          <span className="kb-picker__trigger-label">内部知识范围</span>
          <b className="kb-picker__count">{value.length}</b>
        </button>
      </div>
      {value.length > 0 ? (
        <ul className="research-kb-picker__selected" aria-label="已选知识库">
          {value.map((kb) => (
            <li key={kb.uuid} className="research-kb-picker__chip">
              <span>{kb.name}</span>
              <button type="button" aria-label={`移除 ${kb.name}`} onClick={() => remove(kb.uuid)}>
                ×
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {open ? (
        <div
          className="kb-picker__panel"
          id="research-kb-listbox"
          role="listbox"
          aria-label="选择知识库"
        >
          <label className="kb-picker__search">
            <span className="sr-only">搜索知识库</span>
            <input
              ref={searchRef}
              type="search"
              role="combobox"
              aria-expanded={open}
              aria-controls="research-kb-listbox"
              aria-activedescendant={activeId}
              placeholder="搜索知识库名称"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value)
                setActiveIndex(-1)
              }}
              onKeyDown={handleSearchKeyDown}
            />
          </label>
          <div className="segmented kb-picker__scope" role="group" aria-label="知识库范围">
            {KB_SCOPE_TABS.map(({ value: scopeValue, label }) => (
              <button
                key={scopeValue}
                type="button"
                className={scopeValue === pickerScope ? 'active' : ''}
                onClick={() => changeScope(scopeValue)}
              >
                {label}
              </button>
            ))}
          </div>
          {isPending ? <p className="kb-picker__hint">正在加载知识库…</p> : null}
          {isError ? (
            <p className="kb-picker__hint">
              加载失败
              <button type="button" className="kb-picker__retry" onClick={() => void refetch()}>
                重试
              </button>
            </p>
          ) : null}
          {!isPending && !isError && items.length === 0 ? (
            <p className="kb-picker__hint">没有可用的知识库</p>
          ) : null}
          <ul className="kb-picker__list">
            {items.map((kb, index) => {
              const isMine = user !== null && kb.owner === user.id
              const selected = isSelected(kb)
              return (
                <li key={kb.uuid}>
                  <button
                    type="button"
                    id={`research-kb-option-${kb.uuid}`}
                    className="kb-picker__option"
                    role="option"
                    aria-selected={selected}
                    aria-current={index === activeIndex ? 'true' : undefined}
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => toggle(kb)}
                  >
                    <span className="kb-picker__name">
                      {selected ? '✓ ' : ''}
                      {kb.name}
                    </span>
                    <span className="kb-picker__meta">
                      <StatusBadge tone={kb.visibility === 'public' ? 'knowledge' : 'neutral'}>
                        {kb.visibility === 'public' ? '公开' : '私有'}
                      </StatusBadge>
                      <span>{isMine ? '我创建的' : '组织公开'}</span>
                      <span>{kb.doc_count} 文档</span>
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
