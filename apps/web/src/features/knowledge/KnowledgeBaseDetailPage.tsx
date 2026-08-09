import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useParams } from 'react-router-dom'

import { knowledgeApi, type DocumentStatus, type KnowledgeApi } from '@/api/knowledge'
import { ChunkDrawer } from '@/features/knowledge/ChunkDrawer'
import { ConfirmDialog } from '@/components/feedback/ConfirmDialog'
import { EmptyState } from '@/components/feedback/EmptyState'
import { ErrorState } from '@/components/feedback/ErrorState'
import { Skeleton } from '@/components/feedback/Skeleton'
import { StatusBadge, type BadgeTone } from '@/components/feedback/StatusBadge'
import { UploadDrawer } from '@/features/knowledge/UploadDrawer'

const DOCUMENT_STATUS: Record<DocumentStatus, { label: string; tone: BadgeTone; action?: string }> =
  {
    queued: { label: '等待处理', tone: 'processing' },
    processing: { label: '处理中', tone: 'processing' },
    completed: { label: '可检索', tone: 'success', action: '查看切片' },
    partial: { label: '部分可用', tone: 'warning', action: '查看说明' },
    failed: { label: '处理失败', tone: 'danger', action: '查看安全错误' },
    deleting: { label: '删除中', tone: 'neutral' },
  }

type Props = { api?: KnowledgeApi }

export function KnowledgeBaseDetailPage({ api = knowledgeApi }: Props) {
  const { kbId = '' } = useParams<{ kbId: string }>()
  const queryClient = useQueryClient()

  const [uploading, setUploading] = useState(false)
  const [deleting, setDeleting] = useState<{ uuid: string; filename: string } | null>(null)
  const [chunkDoc, setChunkDoc] = useState<string | null>(null)

  const kbQuery = useQuery({
    queryKey: ['knowledge-base', kbId],
    queryFn: () => api.getKnowledgeBase(kbId),
  })

  const docsQuery = useQuery({
    queryKey: ['knowledge-base', kbId, 'documents'],
    queryFn: () => api.listDocuments(kbId, { page: 1, page_size: 20 }),
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
      void queryClient.invalidateQueries({ queryKey: ['knowledge-base', kbId, 'documents'] })
      void queryClient.invalidateQueries({ queryKey: ['knowledge-base', kbId] })
      setDeleting(null)
    },
  })

  const canUpload = kbQuery.data?.status === 'active' && kbQuery.data?.visibility === 'private'

  return (
    <main className="knowledge-detail">
      {kbQuery.isPending ? (
        <Skeleton />
      ) : kbQuery.isError ? (
        <ErrorState onRetry={() => void kbQuery.refetch()} />
      ) : (
        <header className="page-heading">
          <div>
            <p>Knowledge base</p>
            <h1>{kbQuery.data.name}</h1>
            <span>{kbQuery.data.description ?? '（无描述）'}</span>
          </div>
          <div className="page-heading__meta">
            <StatusBadge tone={kbQuery.data.visibility === 'public' ? 'knowledge' : 'neutral'}>
              {kbQuery.data.visibility === 'public' ? '公开' : '私有'}
            </StatusBadge>
            <StatusBadge tone={kbQuery.data.status === 'active' ? 'success' : 'danger'}>
              {kbQuery.data.status === 'active' ? '可用' : '删除中'}
            </StatusBadge>
          </div>
        </header>
      )}

      <section className="documents-section">
        <header className="documents-section__header">
          <h2>文档</h2>
          {canUpload ? (
            <button type="button" className="btn btn--primary" onClick={() => setUploading(true)}>
              上传文档
            </button>
          ) : null}
        </header>

        {docsQuery.isPending ? (
          <Skeleton />
        ) : docsQuery.isError ? (
          <ErrorState onRetry={() => void docsQuery.refetch()} />
        ) : docsQuery.data.items.length === 0 ? (
          <EmptyState
            title="还没有文档"
            description="上传 PDF、DOCX、Markdown 或 TXT，入库后即可被检索。"
          />
        ) : (
          <ul className="doc-list">
            {docsQuery.data.items.map((item) => {
              const status = DOCUMENT_STATUS[item.status]
              const retryable = item.status === 'partial' || item.status === 'failed'
              return (
                <li key={item.uuid} className="doc-row">
                  <div className="doc-row__main">
                    <h3>{item.filename}</h3>
                    <dl className="doc-row__meta">
                      <div>
                        <dt>大小</dt>
                        <dd>{formatSize(item.file_size)}</dd>
                      </div>
                      <div>
                        <dt>切片</dt>
                        <dd>{item.chunk_count}</dd>
                      </div>
                      <div>
                        <dt>更新时间</dt>
                        <dd>{formatDateTime(item.updated_at ?? item.created_at)}</dd>
                      </div>
                    </dl>
                    {item.error_msg ? <p className="doc-row__error">{item.error_msg}</p> : null}
                  </div>
                  <div className="doc-row__right">
                    <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
                    <div className="doc-row__actions">
                      {item.status === 'completed' ? (
                        <button
                          type="button"
                          className="btn"
                          onClick={() => setChunkDoc(item.uuid)}
                        >
                          查看切片
                        </button>
                      ) : null}
                      {retryable ? (
                        <button
                          type="button"
                          className="btn"
                          disabled={retryMutation.isPending}
                          onClick={() => retryMutation.mutate(item.uuid)}
                        >
                          {retryMutation.isPending ? '重试中…' : '重试'}
                        </button>
                      ) : null}
                      <button
                        type="button"
                        className="btn btn--danger-ghost"
                        onClick={() => setDeleting({ uuid: item.uuid, filename: item.filename })}
                      >
                        删除文档
                      </button>
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      {uploading ? (
        <UploadDrawer
          kbId={kbId}
          api={api}
          onClose={() => setUploading(false)}
          onUploaded={() => {
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

function formatSize(bytes: number | null): string {
  if (bytes == null) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
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
