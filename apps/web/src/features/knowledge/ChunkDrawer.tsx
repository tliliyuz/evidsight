import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import { knowledgeApi, type KnowledgeApi } from '@/api/knowledge'
import { ErrorState } from '@/components/feedback/ErrorState'
import { Skeleton } from '@/components/feedback/Skeleton'

type Props = {
  documentId: string
  api?: KnowledgeApi
  onClose: () => void
}

type LocationError = Error & { response?: { status?: number } }

/**
 * 文档切片抽屉（对齐 FRONTEND §5.4 / UIDESIGN §6.6）。
 * 分块列表以稳定 segment_id 定位；展开原文时按当前用户与 KB 权限实时鉴权
 * （GET /api/v1/documents/{document_id}/locations/{location_id}）。
 * 权限撤销（403/E5005）或来源不可用（E2015）时立即清除已显示正文并展示受限态。
 */
export function ChunkDrawer({ documentId, api = knowledgeApi, onClose }: Props) {
  const queryClient = useQueryClient()
  const closeRef = useRef<HTMLButtonElement>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    closeRef.current?.focus()
  }, [])

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const chunksQuery = useQuery({
    queryKey: ['document', documentId, 'chunks'],
    queryFn: () => api.getDocumentChunks(documentId, { page: 1, page_size: 50 }),
  })

  const locationMutation = useMutation({
    mutationFn: (segmentId: string) => api.getDocumentLocation(documentId, segmentId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['document', documentId, 'chunks'] })
    },
  })

  function openSegment(segmentId: string) {
    setExpanded(segmentId)
    locationMutation.mutate(segmentId)
  }

  const data = locationMutation.data
  const locationError = locationMutation.error as LocationError | null
  const restricted =
    locationError?.response?.status === 403 || locationError?.response?.status === 404

  return (
    <div className="drawer-overlay" role="presentation">
      <aside className="drawer drawer--wide" role="dialog" aria-modal="true" aria-label="文档切片">
        <header className="drawer__header">
          <h2>文档切片</h2>
          <button
            ref={closeRef}
            type="button"
            className="drawer__close"
            aria-label="关闭"
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <div className="drawer__body">
          {chunksQuery.isPending ? (
            <Skeleton />
          ) : chunksQuery.isError ? (
            <ErrorState onRetry={() => void chunksQuery.refetch()} />
          ) : (
            <ol className="chunk-list">
              {chunksQuery.data.items.map((chunk) => (
                <li key={chunk.segment_id} className="chunk-item">
                  <button
                    type="button"
                    className="chunk-item__expand"
                    aria-expanded={expanded === chunk.segment_id}
                    aria-label={
                      expanded === chunk.segment_id
                        ? '收起'
                        : `展开第${toChineseNumber(chunk.chunk_index + 1)}段`
                    }
                    onClick={() => openSegment(chunk.segment_id)}
                  >
                    <span className="chunk-item__preview">
                      {expanded === chunk.segment_id
                        ? '收起'
                        : `展开第${toChineseNumber(chunk.chunk_index + 1)}段`}
                    </span>
                    <span className="chunk-item__meta">
                      位置 {formatLocation(chunk.metadata)} · <span>{chunk.token_count}</span> Token
                    </span>
                  </button>
                  <div className="chunk-item__preview-text">{chunk.preview}</div>

                  {expanded === chunk.segment_id ? (
                    locationMutation.isPending ? (
                      <div className="chunk-item__body">
                        <Skeleton />
                      </div>
                    ) : restricted ? (
                      <div className="chunk-item__body chunk-item__body--restricted" role="alert">
                        <p>原文已不可访问</p>
                        <small>你的访问权限已被撤销，或该来源已失效。预览与元数据仍保留。</small>
                      </div>
                    ) : locationMutation.isError ? (
                      <div className="chunk-item__body" role="alert">
                        <p>原文加载失败</p>
                        <small>请稍后重试。</small>
                      </div>
                    ) : data ? (
                      <div className="chunk-item__body">
                        <blockquote>{data.minimal_excerpt}</blockquote>
                        <small>
                          位置：
                          {data.location.page_number
                            ? `第 ${data.location.page_number} 页`
                            : (data.location.section_path?.join(' / ') ?? '未知')}
                        </small>
                      </div>
                    ) : null
                  ) : null}
                </li>
              ))}
            </ol>
          )}
        </div>
      </aside>
    </div>
  )
}

function formatLocation(metadata: Record<string, unknown> | null | undefined): string {
  if (!metadata) return '未知'
  if (typeof metadata.page === 'number') return `第 ${metadata.page} 页`
  return '未知'
}

function toChineseNumber(value: number): string {
  const digits = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九']
  return String(value)
    .split('')
    .map((char) => digits[Number(char)] ?? char)
    .join('')
}
