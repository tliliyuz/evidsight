import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { conversationsApi, type Conversation } from '@/api/conversations'
import { apiErrorMessage } from '@/api/errors'
import { Button } from '@/components/actions/Button'
import { ConfirmDialog } from '@/components/feedback/ConfirmDialog'
import { EmptyState } from '@/components/feedback/EmptyState'
import { ErrorState } from '@/components/feedback/ErrorState'
import { Pagination } from '@/components/feedback/Pagination'
import { RenameDialog } from '@/components/feedback/RenameDialog'
import { Skeleton } from '@/components/feedback/Skeleton'
import { useAppToast } from '@/components/feedback/toastContext'
import { RowMenu } from '@/components/overlay/RowMenu'
import { useDebouncedValue } from '@/features/chat/useDebouncedValue'
import { formatTimestamp } from '@/features/knowledge/format'

type SortOrder = 'desc' | 'asc'
type TimeRange = 'all' | 'today' | 'week'

const PAGE_SIZE = 10
const SEARCH_DEBOUNCE_MS = 300

const TIME_RANGES: { value: TimeRange; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'today', label: '今天' },
  { value: 'week', label: '本周' },
]

/** 本地「今天/本周」范围判定（周一为本周起点）。 */
function inTimeRange(value: string | null | undefined, range: TimeRange): boolean {
  if (range === 'all') return true
  if (!value) return false
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return false
  const now = new Date()
  if (range === 'today') return date.toDateString() === now.toDateString()
  const day = now.getDay()
  const monday = new Date(now)
  monday.setDate(now.getDate() - (day === 0 ? 6 : day - 1))
  monday.setHours(0, 0, 0, 0)
  return date >= monday
}

/**
 * 问答历史页面（FRONTEND §5.6 / API.md §7）。
 *
 * 台账列表结构；搜索（`q` 仅匹配会话标题）、排序（`sort_by=last_message_at` + `order`）与
 * 分页均由服务端执行，参数同步到 URL（`q`/`sort`/`page`），前端不得以一次性拉取全量在
 * 浏览器内替代服务端搜索排序。重命名、删除具名二次确认；删除当前页最后一项后回退页码。
 */
export function ConversationHistoryPage() {
  const queryClient = useQueryClient()
  const { show } = useAppToast()
  const [searchParams, setSearchParams] = useSearchParams()

  const rawQ = searchParams.get('q') ?? ''
  const sort: SortOrder = searchParams.get('sort') === 'asc' ? 'asc' : 'desc'
  const page = Math.max(1, Number(searchParams.get('page') ?? '1') || 1)
  // 搜索防抖：URL 立即同步，查询以防抖后的值驱动，避免逐键触发服务端请求
  const q = useDebouncedValue(rawQ, SEARCH_DEBOUNCE_MS).trim()

  const [timeRange, setTimeRange] = useState<TimeRange>('all')
  const [renameTarget, setRenameTarget] = useState<Conversation | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Conversation | null>(null)

  function updateParams(patch: Record<string, string | undefined>) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        for (const [key, value] of Object.entries(patch)) {
          if (!value) next.delete(key)
          else next.set(key, value)
        }
        return next
      },
      { replace: true },
    )
  }

  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ['conversations', { q, order: sort, page }],
    queryFn: () =>
      conversationsApi.list({
        q: q || undefined,
        sort_by: 'last_message_at',
        order: sort,
        page,
        page_size: PAGE_SIZE,
      }),
  })

  const renameMutation = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      conversationsApi.rename(id, title),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['conversations'] })
      setRenameTarget(null)
    },
    onError: (error) => {
      show(apiErrorMessage(error, '重命名失败，请稍后重试'))
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => conversationsApi.remove(id),
    onSuccess: () => {
      // 删除当前页最后一项（page>1 且仅一条）后回退一页，避免落在空页
      if (page > 1 && (data?.items.length ?? 0) === 1) {
        updateParams({ page: String(page - 1) })
      }
      void queryClient.invalidateQueries({ queryKey: ['conversations'] })
      setDeleteTarget(null)
    },
    onError: (error) => {
      show(apiErrorMessage(error, '删除失败，请稍后重试'))
    },
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const hasSearch = q !== ''
  // 「今天/本周」分类：对服务端返回的当前页按 last_message_at 前端筛选。
  // 后端列表接口暂无时间范围参数，计数与分页仍按「全部」口径；需要按分类精确统计时须后端支持。
  const visibleItems = items.filter((conversation) =>
    inTimeRange(conversation.last_message_at ?? conversation.updated_at, timeRange),
  )
  const filteredByTime = timeRange !== 'all' && visibleItems.length === 0 && items.length > 0

  function handleSearchChange(value: string) {
    updateParams({ q: value || undefined, page: undefined })
  }

  function handleSortToggle() {
    updateParams({ sort: sort === 'desc' ? 'asc' : 'desc', page: undefined })
  }

  function handlePageChange(nextPage: number) {
    updateParams({ page: String(nextPage) })
  }

  let content: React.ReactNode
  if (isPending) {
    content = <Skeleton rows={4} />
  } else if (isError) {
    content = <ErrorState onRetry={() => void refetch()} />
  } else if (filteredByTime) {
    content = (
      <EmptyState
        title="该时间范围没有会话"
        description="换个分类或清除搜索，查看其它时间范围的会话。"
      />
    )
  } else if (items.length === 0) {
    content = hasSearch ? (
      <EmptyState
        title="没有匹配的会话"
        description="换个关键词试试，或清除搜索查看全部会话。"
        action={
          <Button type="button" onClick={() => updateParams({ q: undefined, page: undefined })}>
            清除搜索
          </Button>
        }
      />
    ) : (
      <EmptyState
        title="还没有问答历史"
        description="在一个知识库范围内提问后，会话会出现在这里。"
        action={
          <Link to="/chat" className="btn btn--primary">
            开始问答
          </Link>
        }
      />
    )
  } else {
    content = (
      <>
        <div className="ledger chat-history-ledger">
          <div className="ledger__head" aria-hidden="true">
            <span>对话</span>
            <span>知识库</span>
            <span>消息</span>
            <span>最近更新</span>
            <span>操作</span>
          </div>
          <ul className="ledger__body">
            {visibleItems.map((conversation) => (
              <li key={conversation.uuid} className="ledger__row">
                <span className="ledger__cell">
                  <Link
                    className="conversation-row__open"
                    to={`/chat?conversation=${conversation.uuid}`}
                  >
                    {conversation.title || '新对话'}
                  </Link>
                </span>
                <span className="ledger__cell">{conversation.kb_name ?? '知识库已删除'}</span>
                <span className="ledger__cell">{conversation.message_count} 条消息</span>
                <span className="ledger__cell">
                  {formatTimestamp(conversation.last_message_at ?? conversation.updated_at)}
                </span>
                {/* 行内只留主操作「打开对话」；重命名/删除收敛到 ⋮ 溢出菜单，避免三按钮挤列 */}
                <span className="ledger__cell ledger__cell--actions">
                  <Link className="btn" to={`/chat?conversation=${conversation.uuid}`}>
                    打开对话
                  </Link>
                  <RowMenu
                    label={`会话操作 ${conversation.title || '新对话'}`}
                    actions={[
                      { label: '重命名', onSelect: () => setRenameTarget(conversation) },
                      {
                        label: '删除',
                        danger: true,
                        onSelect: () => setDeleteTarget(conversation),
                      },
                    ]}
                  />
                </span>
              </li>
            ))}
          </ul>
        </div>
        {total > PAGE_SIZE ? (
          <Pagination
            page={page}
            total={total}
            pageSize={PAGE_SIZE}
            onPageChange={handlePageChange}
          />
        ) : null}
      </>
    )
  }

  return (
    <main className="chat-history route-surface">
      <header className="page-heading chat-history__heading">
        <div>
          <p className="eyebrow">问答历史</p>
          <h1>问答历史</h1>
          <span>搜索、排序并打开此前的问答会话。</span>
        </div>
        <div className="chat-history__heading-actions">
          <Link to="/chat" className="btn btn--primary">
            新建对话
          </Link>
        </div>
      </header>

      <div className="list-toolbar chat-history__toolbar" role="toolbar" aria-label="会话筛选">
        <div className="segmented" role="group" aria-label="时间范围">
          {TIME_RANGES.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              className={value === timeRange ? 'active' : ''}
              onClick={() => setTimeRange(value)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="chat-history__toolbar-right">
          <label className="chat-history__search">
            <span className="sr-only">搜索会话</span>
            <input
              type="search"
              placeholder="搜索会话名称"
              maxLength={128}
              value={rawQ}
              onChange={(event) => handleSearchChange(event.target.value)}
            />
          </label>
          <Button type="button" onClick={handleSortToggle} aria-pressed={sort === 'asc'}>
            更新时间 {sort === 'desc' ? '↓' : '↑'}
          </Button>
        </div>
      </div>

      {content}

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
