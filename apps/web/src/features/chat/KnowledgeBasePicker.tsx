import { useQuery } from '@tanstack/react-query'
import { useSyncExternalStore, useState } from 'react'

import { knowledgeApi, type KnowledgeBase } from '@/api/knowledge'
import { StatusBadge } from '@/components/feedback/StatusBadge'
import { authSession } from '@/features/auth/authSession'

function useCurrentUser() {
  const auth = useSyncExternalStore(authSession.subscribe, authSession.getSnapshot)
  return auth.user
}

/**
 * 据见问答知识范围选择器（FRONTEND §5.5）。
 *
 * v1.0 只允许单选一个知识库；组件保留多选入口的布局与信息层级，但多选
 * 不可执行，展示「多知识库问答规划中」。发送时只提交一个 knowledge_base_id。
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
  const user = useCurrentUser()

  // 挂载即查询可见知识库，使触发按钮在关闭态也能解析已选名称；
  // 打开后按输入名称过滤重新查询。
  const { data, isPending } = useQuery({
    queryKey: ['knowledge-bases', 'all', query],
    queryFn: () =>
      knowledgeApi.listKnowledgeBases({
        scope: 'all',
        q: query.trim() || undefined,
        page: 1,
        page_size: 20,
      }),
  })

  const items = data?.items ?? []
  const selected = value ? items.find((kb) => kb.uuid === value) : null
  const selectedName = selected?.name ?? (value ? '已选择知识库' : '未选择知识库')

  function pick(kb: KnowledgeBase | null) {
    onSelect(kb)
    setOpen(false)
  }

  return (
    <div className="kb-picker">
      <div className="kb-picker__current">
        <span className="kb-picker__label">知识范围</span>
        <button
          type="button"
          className="kb-picker__trigger"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-haspopup="listbox"
        >
          {selectedName}
        </button>
      </div>
      {open ? (
        <div className="kb-picker__panel" role="listbox" aria-label="选择知识库">
          <label className="kb-picker__search">
            <span className="sr-only">搜索知识库</span>
            <input
              type="search"
              placeholder="搜索知识库名称"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          {isPending ? <p className="kb-picker__hint">正在加载知识库…</p> : null}
          {!isPending && items.length === 0 ? (
            <p className="kb-picker__hint">没有可用的知识库</p>
          ) : null}
          <ul className="kb-picker__list">
            {items.map((kb) => {
              const isMine = user !== null && kb.owner === user.id
              return (
                <li key={kb.uuid}>
                  <button
                    type="button"
                    className="kb-picker__option"
                    role="option"
                    aria-selected={kb.uuid === value}
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
