import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import type { UserSummary } from '@/api/auth'
import { knowledgeApi, type DocumentStatus, type KnowledgeApi } from '@/api/knowledge'
import { ChunkDrawer } from '@/features/knowledge/ChunkDrawer'
import { ConfirmDialog } from '@/components/feedback/ConfirmDialog'
import { EmptyState } from '@/components/feedback/EmptyState'
import { ErrorState } from '@/components/feedback/ErrorState'
import { Pagination } from '@/components/feedback/Pagination'
import { Skeleton } from '@/components/feedback/Skeleton'
import { StatusBadge, type BadgeTone } from '@/components/feedback/StatusBadge'
import { useAppToast } from '@/components/feedback/toastContext'
import { UploadDrawer } from '@/features/knowledge/UploadDrawer'
import { useCurrentUser } from '@/features/auth/useCurrentUser'
import { formatTimestamp } from '@/features/knowledge/format'
import { canManageKb, canUploadToKb, isOwner } from '@/features/knowledge/permissions'

const DOCUMENT_STATUS: Record<DocumentStatus, { label: string; tone: BadgeTone }> = {
  queued: { label: '等待处理', tone: 'neutral' },
  processing: { label: '处理中', tone: 'processing' },
  completed: { label: '可检索', tone: 'success' },
  partial: { label: '部分可用', tone: 'warning' },
  failed: { label: '处理失败', tone: 'danger' },
  deleting: { label: '删除中', tone: 'neutral' },
}

/** 文档每页条数（默认 10 条/页，让分页在中等数据量下可见）。 */
const PAGE_SIZE = 10

/** 非终态文档状态：轮询直至全部进入终态（completed/partial/failed）。 */
const NON_TERMINAL_STATUSES = new Set<DocumentStatus>(['queued', 'processing', 'deleting'])

/** 状态筛选：严格映射六值，逐值复用后端单值 status 查询参数（不做后端不支持的分组假能力）。 */
const STATUS_FILTERS: { value: DocumentStatus | ''; label: string }[] = [
  { value: '', label: '全部状态' },
  { value: 'queued', label: '等待处理' },
  { value: 'processing', label: '处理中' },
  { value: 'completed', label: '可检索' },
  { value: 'partial', label: '部分可用' },
  { value: 'failed', label: '处理失败' },
  { value: 'deleting', label: '删除中' },
]

type Props = { api?: KnowledgeApi; currentUser?: UserSummary | null }

export function KnowledgeBaseDetailPage({ api = knowledgeApi, currentUser }: Props) {
  const user = useCurrentUser(currentUser)
  const { kbId = '' } = useParams<{ kbId: string }>()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const status = searchParams.get('status') ?? ''
  const q = searchParams.get('q') ?? ''
  const page = Number(searchParams.get('page') ?? '1')

  const [uploading, setUploading] = useState(false)
  const [deleting, setDeleting] = useState<{ uuid: string; filename: string } | null>(null)
  const [chunkDoc, setChunkDoc] = useState<string | null>(null)
  const { show: showToast } = useAppToast()

  const kbQuery = useQuery({
    queryKey: ['knowledge-base', kbId],
    queryFn: () => api.getKnowledgeBase(kbId),
  })

  const docsQuery = useQuery({
    queryKey: ['knowledge-base', kbId, 'documents', status, q, page],
    queryFn: () =>
      api.listDocuments(kbId, {
        status: status || undefined,
        filename: q || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    // 文档状态轮询：存在排队/处理/删除中的非终态文档时每 5s 自动刷新，全部进入终态后停止
    refetchInterval: (query) => {
      const items = query.state.data?.items
      return items?.some((d) => NON_TERMINAL_STATUSES.has(d.status)) ? 5000 : false
    },
  })

  const retryMutation = useMutation({
    mutationFn: (documentId: string) => api.reprocessDocument(documentId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['knowledge-base', kbId, 'documents'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteDocument(deleting!.uuid),
    onSuccess: () => {
      if (deleting) showToast(`已删除文档「${deleting.filename}」`)
      void queryClient.invalidateQueries({ queryKey: ['knowledge-base', kbId, 'documents'] })
      void queryClient.invalidateQueries({ queryKey: ['knowledge-base', kbId] })
      setDeleting(null)
    },
  })

  function setFilter(next: Partial<Record<'status' | 'q' | 'page', string>>) {
    const nextParams = new URLSearchParams(searchParams)
    for (const [key, value] of Object.entries(next)) {
      if (value) {
        nextParams.set(key, value)
      } else {
        nextParams.delete(key)
      }
    }
    setSearchParams(nextParams)
  }

  function submitSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const nextQ = String(form.get('q') ?? '').trim()
    setFilter({ q: nextQ, page: '1' })
  }

  const kb = kbQuery.data
  const canUpload = kb ? canUploadToKb(kb, user) : false
  // 文档删除：Owner 或管理员治理（知识库编辑/删除已收敛到列表 ⋮ 菜单，不在此 Hero 提供）
  const canManage = kb ? canManageKb(kb, user) : false
  const ownerCanRetry = kb ? isOwner(kb, user) : false
  // Hero owner 展示名：优先后端权威 owner_username；字段缺失时当前用户恰为 owner 则回退到 /me 用户名
  //（owner 恒应看到自己的用户名，不依赖后端响应是否携带该字段）
  const ownerName = kb?.owner_username ?? (kb && isOwner(kb, user) ? user?.username : undefined)

  return (
    <main className="route-surface kb-page">
      <Link className="back-link" to="/knowledge-bases">
        ← 返回知识库
      </Link>

      {kbQuery.isPending ? (
        <Skeleton />
      ) : kbQuery.isError ? (
        <ErrorState onRetry={() => void kbQuery.refetch()} />
      ) : (
        <header className="detail-hero">
          <div className="detail-hero__main">
            <p className="eyebrow">知识库</p>
            {/* 名称单行截断：128 字上限恶意填满也不撑高 Hero，hover 显示全名 */}
            <h1 title={kb!.name}>{kb!.name}</h1>
            {/* 描述保留在名称下方左侧：限宽 + 三行截断，2000 字恶意填满不撑高 Hero */}
            <p className="detail-hero__desc">{kb!.description ?? '（无描述）'}</p>
          </div>
          <div className="detail-hero__side">
            <div className="detail-hero__actions">
              {/* 用它提问：跳转问答页并预选当前知识库（FRONTEND §5.5），所有可见用户可用 */}
              <Link to={`/chat?kb=${kb!.uuid}`} className="btn btn--primary">
                用它提问
              </Link>
              {canUpload ? (
                <button type="button" className="btn" onClick={() => setUploading(true)}>
                  上传文档
                </button>
              ) : null}
            </div>
            {/* 状态行在右侧动作区下方：owner 创建（可见性徽章左侧）→ 可见性徽章 → 绝对时间戳 */}
            <dl className="detail-hero__meta">
              {ownerName ? <span>{ownerName} 创建</span> : null}
              <StatusBadge tone={kb!.visibility === 'public' ? 'knowledge' : 'neutral'}>
                {kb!.visibility === 'public' ? '公开' : '私有'}
              </StatusBadge>
              <span>{formatTimestamp(kb!.updated_at ?? kb!.created_at)} 更新</span>
            </dl>
          </div>
        </header>
      )}

      {/* 摘要卡片（Metric Strip）：文档总数/分块总数/创建时间均来自 KB 响应权威字段，置于「文档与索引状态」上方 */}
      {kb ? (
        <section className="metric-strip" aria-label="知识库摘要">
          <div className="metric-strip__item">
            <span className="metric-strip__label">文档总数</span>
            <b className="metric-strip__value">{kb.doc_count}</b>
            <span className="metric-strip__hint">已入库</span>
          </div>
          <div className="metric-strip__item">
            <span className="metric-strip__label">分块总数</span>
            <b className="metric-strip__value">{kb.chunk_count}</b>
            <span className="metric-strip__hint">有效片段</span>
          </div>
          <div className="metric-strip__item">
            <span className="metric-strip__label">创建时间</span>
            <b className="metric-strip__value">{formatTimestamp(kb.created_at)}</b>
            <span className="metric-strip__hint">知识库建立</span>
          </div>
        </section>
      ) : null}

      <section className="documents-section">
        <header className="documents-section__header">
          <h2>文档与索引状态</h2>
        </header>

        <div className="list-toolbar" role="toolbar" aria-label="文档筛选">
          <label className="status-filter">
            <span className="sr-only">状态筛选</span>
            <select
              aria-label="状态筛选"
              value={status}
              onChange={(event) => setFilter({ status: event.target.value, page: '1' })}
            >
              {STATUS_FILTERS.map(({ value, label }) => (
                <option key={value || 'all'} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {/* 文件名搜索无按钮：回车提交（复用 filename 查询参数） */}
          <form role="search" aria-label="搜索文档" className="search-form" onSubmit={submitSearch}>
            <input
              type="search"
              name="q"
              aria-label="搜索文档"
              placeholder="搜索文件名"
              defaultValue={q}
            />
          </form>
        </div>

        <div className="ledger doc-ledger">
          <div className="ledger__head" aria-hidden="true">
            <span>文档</span>
            <span>状态</span>
            <span>有效片段</span>
            <span>更新时间</span>
            <span>操作</span>
          </div>

          {docsQuery.isPending ? (
            <div className="ledger__body">
              <Skeleton rows={5} />
            </div>
          ) : docsQuery.isError ? (
            <div className="ledger__body">
              <ErrorState onRetry={() => void docsQuery.refetch()} />
            </div>
          ) : docsQuery.data.items.length === 0 ? (
            <div className="ledger__body">
              {/* 搜索/筛选无匹配时不提示「上传」（owner 可上传，但此处是筛选空态，不是空库） */}
              {q || status ? (
                <EmptyState title="没有匹配的文档" description="调整状态筛选或文件名搜索后重试。" />
              ) : (
                <EmptyState
                  title="还没有文档"
                  description="上传 PDF、DOCX、Markdown 或 TXT，入库后即可被检索。"
                />
              )}
            </div>
          ) : (
            <ul className="ledger__body">
              {docsQuery.data.items.map((item) => {
                const state = DOCUMENT_STATUS[item.status]
                const hasSegments = item.status === 'completed' || item.status === 'partial'
                const retryable = item.status === 'partial' || item.status === 'failed'
                return (
                  <li key={item.uuid} className="ledger__row">
                    <div className="ledger__cell ledger__cell--doc">
                      <b className="ledger__title">{item.filename}</b>
                      <small className="ledger__desc">
                        {fileTypeLabel(item.file_type)} · {formatSize(item.file_size)}
                      </small>
                    </div>
                    <div className="ledger__cell ledger__cell--state">
                      <StatusBadge tone={state.tone}>{state.label}</StatusBadge>
                      {item.error_msg ? (
                        <small className="doc-state-reason">{item.error_msg}</small>
                      ) : null}
                    </div>
                    <div className="ledger__cell ledger__cell--segments">
                      {hasSegments ? item.chunk_count : '—'}
                    </div>
                    <div className="ledger__cell ledger__cell--updated">
                      {formatTimestamp(item.updated_at ?? item.created_at)}
                    </div>
                    <div className="ledger__cell ledger__cell--actions">
                      {item.status === 'completed' ? (
                        <button
                          type="button"
                          className="btn"
                          onClick={() => setChunkDoc(item.uuid)}
                        >
                          查看切片
                        </button>
                      ) : null}
                      {retryable && ownerCanRetry ? (
                        <button
                          type="button"
                          className="btn"
                          disabled={retryMutation.isPending}
                          onClick={() => retryMutation.mutate(item.uuid)}
                        >
                          {retryMutation.isPending ? '重试中…' : '重试'}
                        </button>
                      ) : null}
                      {canManage ? (
                        <button
                          type="button"
                          className="btn btn--danger-ghost"
                          onClick={() => setDeleting({ uuid: item.uuid, filename: item.filename })}
                        >
                          删除文档
                        </button>
                      ) : null}
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        <Pagination
          page={page}
          total={docsQuery.data?.total ?? 0}
          pageSize={PAGE_SIZE}
          disabled={docsQuery.isPending}
          onPageChange={(next) => setFilter({ page: String(next) })}
        />

        <p className="ledger-footnote">
          <span>说明</span>
          上传完成后即可离开此页。文档解析、分块与索引在后台继续进行，不依赖当前浏览器连接。
        </p>
      </section>

      {uploading ? (
        <UploadDrawer
          kbId={kbId}
          api={api}
          onClose={() => setUploading(false)}
          onUploaded={() => {
            // 上传完成返回详情页：关闭抽屉并刷新文档列表；文档解析状态随后由轮询自动推进
            setUploading(false)
            void queryClient.invalidateQueries({ queryKey: ['knowledge-base', kbId, 'documents'] })
          }}
        />
      ) : null}

      {deleting ? (
        <ConfirmDialog
          title={`确定删除文档「${deleting.filename}」？`}
          description="文档及其索引将被标记删除并异步清理，此操作不可撤销。"
          confirmLabel="确认删除"
          tone="danger"
          pending={deleteMutation.isPending}
          busyLabel="删除中…"
          onCancel={() => setDeleting(null)}
          onConfirm={() => deleteMutation.mutate()}
        />
      ) : null}

      {chunkDoc ? (
        <ChunkDrawer documentId={chunkDoc} api={api} onClose={() => setChunkDoc(null)} />
      ) : null}
    </main>
  )
}

function fileTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    pdf: 'PDF',
    docx: 'DOCX',
    md: 'Markdown',
    txt: 'TXT',
  }
  return labels[type] ?? type.toUpperCase()
}

function formatSize(bytes: number | null): string {
  if (bytes == null) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
