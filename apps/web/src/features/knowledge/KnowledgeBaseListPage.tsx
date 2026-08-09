import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { knowledgeApi, type KnowledgeApi, type KnowledgeScope } from '@/api/knowledge'
import { EmptyState } from '@/components/feedback/EmptyState'
import { ErrorState } from '@/components/feedback/ErrorState'
import { Skeleton } from '@/components/feedback/Skeleton'
import { StatusBadge } from '@/components/feedback/StatusBadge'
import { KnowledgeBaseFormDialog } from '@/features/knowledge/KnowledgeBaseFormDialog'
import { ConfirmDialog } from '@/components/feedback/ConfirmDialog'

const SCOPE_LABELS: { value: KnowledgeScope; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'mine', label: '我创建的' },
  { value: 'public', label: '组织公开' },
]

type Props = { api?: KnowledgeApi }

export function KnowledgeBaseListPage({ api = knowledgeApi }: Props) {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const scope = (searchParams.get('scope') as KnowledgeScope) ?? 'all'
  const q = searchParams.get('q') ?? ''
  const page = Number(searchParams.get('page') ?? '1')

  const [creating, setCreating] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<{
    uuid: string
    name: string
  } | null>(null)

  const listQuery = useQuery({
    queryKey: ['knowledge-bases', scope, q, page],
    queryFn: () => api.listKnowledgeBases({ scope, q, page, page_size: 20 }),
  })

  const editing = listQuery.data?.items.find((item) => item.uuid === editingId) ?? null

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteKnowledgeBase(deleting!.uuid),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] })
      setDeleting(null)
    },
  })

  function setScope(next: KnowledgeScope) {
    const nextParams = new URLSearchParams(searchParams)
    nextParams.set('scope', next)
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
    <main className="knowledge-page">
      <header className="page-heading">
        <div>
          <p>Knowledge base</p>
          <h1>知识库</h1>
          <span>导入可治理的材料，供问答与研究使用。</span>
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
        <form role="search" aria-label="搜索知识库" className="search-form" onSubmit={submitSearch}>
          <input
            type="search"
            name="q"
            aria-label="搜索知识库"
            placeholder="搜索知识库名称"
            defaultValue={q}
          />
          <button type="submit" className="btn">
            搜索
          </button>
        </form>
      </div>

      {listQuery.isPending ? (
        <Skeleton />
      ) : listQuery.isError ? (
        <ErrorState onRetry={() => void listQuery.refetch()} />
      ) : listQuery.data.items.length === 0 ? (
        <EmptyState
          title="还没有知识库"
          description="创建第一个知识库，导入需要治理的材料。"
          action={
            <button type="button" className="btn btn--primary" onClick={() => setCreating(true)}>
              新建知识库
            </button>
          }
        />
      ) : (
        <ul className="kb-list">
          {listQuery.data.items.map((item) => (
            <li key={item.uuid} className="kb-row">
              <div className="kb-row__main">
                <div className="kb-row__title">
                  <h2>{item.name}</h2>
                  <StatusBadge
                    tone={
                      item.visibility === 'public'
                        ? 'knowledge'
                        : item.status === 'deleting'
                          ? 'danger'
                          : 'neutral'
                    }
                  >
                    {item.visibility === 'public' ? '公开' : '私有'}
                  </StatusBadge>
                </div>
                <p className="kb-row__desc">{item.description ?? '（无描述）'}</p>
                <dl className="kb-row__meta">
                  <div>
                    <dt>文档</dt>
                    <dd>{item.doc_count}</dd>
                  </div>
                  <div>
                    <dt>索引片段</dt>
                    <dd>{item.chunk_count}</dd>
                  </div>
                  <div>
                    <dt>更新时间</dt>
                    <dd>{formatDateTime(item.updated_at ?? item.created_at)}</dd>
                  </div>
                </dl>
              </div>
              <div className="kb-row__actions">
                <Link to={`/knowledge-bases/${item.uuid}`} className="btn">
                  进入知识库
                </Link>
                <button type="button" className="btn" onClick={() => setEditingId(item.uuid)}>
                  编辑
                </button>
                <button
                  type="button"
                  className="btn btn--danger-ghost"
                  onClick={() => setDeleting({ uuid: item.uuid, name: item.name })}
                >
                  删除知识库
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="pagination">
        <button
          type="button"
          className="btn"
          disabled={page <= 1 || listQuery.isPending}
          onClick={() => {
            const nextParams = new URLSearchParams(searchParams)
            nextParams.set('page', String(page - 1))
            setSearchParams(nextParams)
          }}
        >
          上一页
        </button>
        <span>
          第 {listQuery.data?.page ?? page} /{' '}
          {listQuery.data ? Math.max(1, Math.ceil(listQuery.data.total / 20)) : 1} 页
        </span>
        <button
          type="button"
          className="btn"
          disabled={!listQuery.data || page * 20 >= listQuery.data.total || listQuery.isPending}
          onClick={() => {
            const nextParams = new URLSearchParams(searchParams)
            nextParams.set('page', String(page + 1))
            setSearchParams(nextParams)
          }}
        >
          下一页
        </button>
      </div>

      {creating || editing ? (
        <KnowledgeBaseFormDialog
          initial={editing}
          api={api}
          onClose={() => {
            setCreating(false)
            setEditingId(null)
          }}
          onSaved={() => {
            setCreating(false)
            setEditingId(null)
            void queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] })
          }}
        />
      ) : null}

      {deleting ? (
        <ConfirmDialog
          title={`确定删除知识库「${deleting.name}」？`}
          description="删除后文档与索引将异步清理，此操作不可撤销。"
          confirmLabel="确认删除"
          tone="danger"
          pending={deleteMutation.isPending}
          onCancel={() => setDeleting(null)}
          onConfirm={() => deleteMutation.mutate()}
        />
      ) : null}
    </main>
  )
}

function formatDateTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
