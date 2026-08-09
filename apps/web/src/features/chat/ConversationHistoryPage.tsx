import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { conversationsApi, type Conversation } from '@/api/conversations'
import { ConfirmDialog } from '@/components/feedback/ConfirmDialog'
import { EmptyState } from '@/components/feedback/EmptyState'
import { Skeleton } from '@/components/feedback/Skeleton'
import { useOverlayFocus } from '@/components/overlay/useOverlayFocus'

type SortOrder = 'desc' | 'asc'

function formatTime(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function RenameDialog({
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
          <button type="button" className="btn" disabled={pending} onClick={onCancel}>
            取消
          </button>
          <button
            type="button"
            className="btn btn--primary"
            disabled={pending || !title.trim()}
            onClick={() => onConfirm(title.trim())}
          >
            {pending ? '保存中…' : '保存'}
          </button>
        </div>
      </div>
    </div>
  )
}

/**
 * 问答历史页面（FRONTEND §5.6）。
 *
 * 独立列表页，不与对话页叠加第二条侧边栏；支持名称搜索、更新时间排序、
 * 重命名、具名二次确认删除与「打开对话」。删除成功后经服务端回读确认，
 * 不直接篡改列表项为成功终态。
 */
export function ConversationHistoryPage() {
  const queryClient = useQueryClient()
  const [searchQuery, setSearchQuery] = useState('')
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc')
  const [renameTarget, setRenameTarget] = useState<Conversation | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Conversation | null>(null)

  const { data, isPending } = useQuery({
    queryKey: ['conversations'],
    queryFn: () => conversationsApi.list({ page: 1, page_size: 100 }),
  })

  const renameMutation = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      conversationsApi.rename(id, title),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['conversations'] })
      setRenameTarget(null)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => conversationsApi.remove(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['conversations'] })
      setDeleteTarget(null)
    },
  })

  const conversations = useMemo(() => {
    const items = data?.items ?? []
    const keyword = searchQuery.trim().toLowerCase()
    const filtered = keyword
      ? items.filter(
          (item) =>
            item.title.toLowerCase().includes(keyword) ||
            (item.kb_name ?? '').toLowerCase().includes(keyword),
        )
      : items
    const sorted = [...filtered].sort((a, b) => {
      const at = a.last_message_at ?? a.updated_at ?? ''
      const bt = b.last_message_at ?? b.updated_at ?? ''
      const diff = new Date(at).getTime() - new Date(bt).getTime()
      return sortOrder === 'desc' ? -diff : diff
    })
    return sorted
  }, [data?.items, searchQuery, sortOrder])

  return (
    <main className="chat-history">
      <header className="page-heading chat-history__heading">
        <div>
          <p>History</p>
          <h1>问答历史</h1>
          <span>搜索、排序并打开此前的问答会话。</span>
        </div>
        <Link to="/chat">返回问答</Link>
      </header>

      <div className="chat-history__toolbar">
        <label className="chat-history__search">
          <span className="sr-only">搜索会话</span>
          <input
            type="search"
            placeholder="搜索会话名称或知识库"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
          />
        </label>
        <button
          type="button"
          className="btn"
          onClick={() => setSortOrder((order) => (order === 'desc' ? 'asc' : 'desc'))}
          aria-pressed={sortOrder === 'asc'}
        >
          更新时间 {sortOrder === 'desc' ? '↓' : '↑'}
        </button>
      </div>

      {isPending ? (
        <Skeleton rows={4} />
      ) : conversations.length === 0 ? (
        <EmptyState
          title="还没有问答历史"
          description="在一个知识库范围内提问后，会话会出现在这里。"
          action={<Link to="/chat">开始问答</Link>}
        />
      ) : (
        <ul className="chat-history__list">
          {conversations.map((conversation) => (
            <li key={conversation.uuid} className="chat-history__row">
              <Link className="chat-history__open" to={`/chat?conversation=${conversation.uuid}`}>
                <strong>{conversation.title || '新对话'}</strong>
                <span className="chat-history__meta">
                  {conversation.kb_name ?? '知识库已删除'}
                  {' · '}
                  {conversation.message_count} 条消息
                  {' · '}
                  {formatTime(conversation.last_message_at ?? conversation.updated_at)}
                </span>
              </Link>
              <div className="chat-history__actions">
                <button type="button" className="btn" onClick={() => setRenameTarget(conversation)}>
                  重命名
                </button>
                <button
                  type="button"
                  className="btn btn--danger"
                  onClick={() => setDeleteTarget(conversation)}
                >
                  删除
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {renameTarget ? (
        <RenameDialog
          initialTitle={renameTarget.title}
          pending={renameMutation.isPending}
          onCancel={() => setRenameTarget(null)}
          onConfirm={(title) => {
            void renameMutation.mutate({ id: renameTarget.uuid, title })
          }}
        />
      ) : null}

      {deleteTarget ? (
        <ConfirmDialog
          title="删除问答会话"
          description={`确定删除会话「${deleteTarget.title || '新对话'}」吗？该操作不可恢复。`}
          confirmLabel="删除会话"
          tone="danger"
          pending={deleteMutation.isPending}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => {
            void deleteMutation.mutate(deleteTarget.uuid)
          }}
        />
      ) : null}
    </main>
  )
}
