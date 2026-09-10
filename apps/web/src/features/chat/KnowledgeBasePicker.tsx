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
 * 据见问答知识范围选择器（FRONTEND §5.5）。
 *
 * v1.0 只允许单选一个知识库；组件保留多选入口的布局与信息层级，但多选不可执行，
 * 展示「多知识库问答规划中」。发送时只提交一个 knowledge_base_id。
 *
 * 触发按钮为原型 scope-trigger 样式：「已选知识库」+ 已选数量徽章（v1 单选为 0/1）；
 * 所选知识库名称由页面级 scope-summary 承载（FRONTEND §5.5）。
 * 可达性：打开后焦点移入搜索框；`Escape` 或点击浮层外部关闭，关闭后焦点返回触发按钮；
 * `↑`/`↓`/`Home`/`End` 移动候选、`Enter` 确认选择。
 */
export function KnowledgeBasePicker({
  value,
  onSelect,
}: {
  value: string | null
  onSelect: (kb: KnowledgeBase | null) => void
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

  // 打开后按「作用域 + 名称」查询；每类最多平铺 5 条、按更新时间倒序（服务端默认）。
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
  // v1 单选：已选知识库数量为 0 或 1
  const selectedCount = value ? 1 : 0

  // 打开：重置搜索与活动项，聚焦搜索框；关闭：焦点返回触发按钮
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

  // 点击浮层外部关闭
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

  function pick(kb: KnowledgeBase | null) {
    onSelect(kb)
    setOpen(false)
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
          pick(active)
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
    activeIndex >= 0 && items[activeIndex] ? `kb-option-${items[activeIndex].uuid}` : undefined

  return (
    <div className="kb-picker" ref={rootRef}>
      <div className="kb-picker__current">
        <button
          ref={triggerRef}
          type="button"
          className="kb-picker__trigger"
          onClick={toggleOpen}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls="kb-listbox"
        >
          <span className="kb-picker__trigger-label">已选知识库</span>
          <b className="kb-picker__count">{selectedCount}</b>
        </button>
      </div>
      {open ? (
        <div className="kb-picker__panel" id="kb-listbox" role="listbox" aria-label="选择知识库">
          <label className="kb-picker__search">
            <span className="sr-only">搜索知识库</span>
            <input
              ref={searchRef}
              type="search"
              role="combobox"
              aria-expanded={open}
              aria-controls="kb-listbox"
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
              return (
                <li key={kb.uuid}>
                  <button
                    type="button"
                    id={`kb-option-${kb.uuid}`}
                    className="kb-picker__option"
                    role="option"
                    aria-selected={kb.uuid === value}
                    aria-current={index === activeIndex ? 'true' : undefined}
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => pick(kb)}
                  >
                    <span className="kb-picker__name">{kb.name}</span>
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
            <li>
              <button
                type="button"
                className="kb-picker__option kb-picker__option--disabled"
                role="option"
                disabled
                title="多知识库问答规划中"
              >
                <span className="kb-picker__name">多知识库问答</span>
                <span className="kb-picker__meta">规划中，暂不可用</span>
              </button>
            </li>
          </ul>
        </div>
      ) : null}
    </div>
  )
}
