import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { knowledgeApi, type KnowledgeApi, type KnowledgeScope } from '@/api/knowledge'
import { EmptyState } from '@/components/feedback/EmptyState'
import { ErrorState } from '@/components/feedback/ErrorState'
import { Pagination } from '@/components/feedback/Pagination'
import { Skeleton } from '@/components/feedback/Skeleton'
import { StatusBadge, type BadgeTone } from '@/components/feedback/StatusBadge'
import { formatTimestamp } from '@/features/knowledge/format'
import { KnowledgeBaseFormDialog } from '@/features/knowledge/KnowledgeBaseFormDialog'

/** 列表每页条数（默认 10 条/页，让分页在中等数据量下可见）。 */
const PAGE_SIZE = 10

const SCOPE_LABELS: { value: KnowledgeScope; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'mine', label: '我创建的' },
  { value: 'public', label: '组织公开' },
]

/** 索引状态列（权威聚合索引状态，ADR-007 索引发布锁；不得根据 chunk_count 猜测）。 */
const INDEX_STATES: Record<
  'ready' | 'updating' | 'recovering',
  { label: string; tone: BadgeTone }
> = {
  ready: { label: '可检索', tone: 'success' },
  updating: { label: '索引更新中', tone: 'processing' },
  recovering: { label: '恢复中', tone: 'warning' },
}

function IndexStatusBadge({ status }: { status?: string | null }) {
  if (!status || !(status in INDEX_STATES)) {
    return <span className="index-state index-state--missing">—</span>
  }
  const { label, tone } = INDEX_STATES[status as keyof typeof INDEX_STATES]
  return <StatusBadge tone={tone}>{label}</StatusBadge>
}

type Props = { api?: KnowledgeApi }

export function KnowledgeBaseListPage({ api = knowledgeApi }: Props) {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const scope = (searchParams.get('scope') as KnowledgeScope) ?? 'all'
  const q = searchParams.get('q') ?? ''
  const page = Number(searchParams.get('page') ?? '1')

  const [creating, setCreating] = useState(false)

  const listQuery = useQuery({
    queryKey: ['knowledge-bases', scope, q, page],
    queryFn: () => api.listKnowledgeBases({ scope, q, page, page_size: PAGE_SIZE }),
  })

  function setScope(next: KnowledgeScope) {
    const nextParams = new URLSearchParams(searchParams)
    nextParams.set('scope', next)
    // 切换可见范围时清除名称搜索：搜索关键字可能只匹配某一范围，保持「全部」能看全量
    nextParams.delete('q')
    nextParams.delete('page')
    setSearchParams(nextParams)
  }

  function submitSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const nextQ = String(form.get('q') ?? '').trim()
    const nextParams = new URLSearchParams(searchParams)
    if (nextQ) {
      nextParams.set('q', nextQ)
    } else {
      nextParams.delete('q')
    }
    nextParams.delete('page')
    setSearchParams(nextParams)
  }

  return (
    <main className="route-surface kb-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">知识库</p>
          <h1>知识库</h1>
          <span>每个知识库拥有独立索引；权限在每次问答与研究时重新确认。</span>
        </div>
        <button type="button" className="btn btn--primary" onClick={() => setCreating(true)}>
          新建知识库
        </button>
      </header>

      <div className="list-toolbar" role="toolbar" aria-label="知识库筛选">
        <div className="segmented" role="group" aria-label="可见范围">
          {SCOPE_LABELS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              className={value === scope ? 'active' : ''}
              onClick={() => setScope(value)}
            >
              {label}
            </button>
          ))}
        </div>
        {/* 搜索无按钮：回车提交（对齐原型，只承诺名称搜索） */}
        <form role="search" aria-label="搜索知识库" className="search-form" onSubmit={submitSearch}>
          <input
            type="search"
            name="q"
            aria-label="搜索知识库"
            placeholder="搜索知识库名称"
            defaultValue={q}
          />
        </form>
      </div>

      <div className="ledger kb-ledger">
        <div className="ledger__head" aria-hidden="true">
          <span>知识库 / 描述</span>
          <span>可见性</span>
          <span>文档</span>
          <span>索引状态</span>
          <span>最近更新</span>
          <span>操作</span>
        </div>

        {listQuery.isPending ? (
          <div className="ledger__body">
            <Skeleton rows={5} />
          </div>
        ) : listQuery.isError ? (
          <div className="ledger__body">
            <ErrorState onRetry={() => void listQuery.refetch()} />
          </div>
        ) : listQuery.data.items.length === 0 ? (
          <div className="ledger__body">
            {/* 搜索无匹配时不显示「新建知识库」按钮（页面头部已有主按钮，避免重复） */}
            {q ? (
              <EmptyState
                title="没有匹配的知识库"
                description="换个名称再试，或清除搜索后查看全部知识库。"
              />
            ) : (
              <EmptyState
                title="还没有知识库"
                description="创建第一个知识库，导入需要治理的材料。"
                action={
                  <button
                    type="button"
                    className="btn btn--primary"
                    onClick={() => setCreating(true)}
                  >
                    新建知识库
                  </button>
                }
              />
            )}
          </div>
        ) : (
          <ul className="ledger__body">
            {listQuery.data.items.map((item) => (
              <li key={item.uuid} className="ledger__row">
                <div className="ledger__cell ledger__cell--kb">
                  <b className="ledger__title">{item.name}</b>
                  <small className="ledger__desc">{item.description ?? '（无描述）'}</small>
                </div>
                <div className="ledger__cell">
                  <StatusBadge tone={item.visibility === 'public' ? 'knowledge' : 'neutral'}>
                    {item.visibility === 'public' ? '公开' : '私有'}
                  </StatusBadge>
                </div>
                <div className="ledger__cell ledger__cell--docs">
                  <b>{item.doc_count}</b>
                  <small>文档</small>
                </div>
                <div className="ledger__cell">
                  <IndexStatusBadge status={item.index_status} />
                </div>
                <div className="ledger__cell ledger__cell--updated">
                  {/* 最近更新列与详情同口径用绝对时间戳（formatTimestamp，不用相对时间） */}
                  <span>{formatTimestamp(item.updated_at ?? item.created_at)}</span>
                  {item.owner_username ? <small>{item.owner_username}</small> : null}
                </div>
                {/* 操作列只保留主操作「进入知识库」；编辑/删除知识库在详情页 Hero（权限感知） */}
                <div className="ledger__cell ledger__cell--actions">
                  <Link to={`/knowledge-bases/${item.uuid}`} className="btn">
                    进入知识库
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Pagination
        page={page}
        total={listQuery.data?.total ?? 0}
        pageSize={PAGE_SIZE}
        disabled={listQuery.isPending}
        onPageChange={(next) => {
          const nextParams = new URLSearchParams(searchParams)
          nextParams.set('page', String(next))
          setSearchParams(nextParams)
        }}
      />

      <p className="ledger-footnote">
        <span>说明</span>
        只有已完成或部分完成且具有有效来源的文档会参与检索；失败与等待中的文档不会成为答案依据。
      </p>

      {creating ? (
        <KnowledgeBaseFormDialog
          initial={null}
          api={api}
          onClose={() => setCreating(false)}
          onSaved={() => {
            setCreating(false)
            void queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] })
          }}
        />
      ) : null}
    </main>
  )
}
