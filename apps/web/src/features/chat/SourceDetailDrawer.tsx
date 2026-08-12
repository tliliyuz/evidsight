import { useRef, useState } from 'react'

import { Button } from '@/components/actions/Button'
import { HighlightPreview } from '@/components/feedback/HighlightPreview'
import { useOverlayFocus } from '@/components/overlay/useOverlayFocus'
import { sourceLocation } from '@/features/chat/chatFormat'
import { ChunkDrawer } from '@/features/knowledge/ChunkDrawer'
import type { ChatSourceChunk } from '@/features/chat/chatSseParser'

/**
 * 来源详情抽屉（FRONTEND §5.5 / 原型 07-chat `.chat-source-panel`）。
 *
 * 展示标题、知识库、文档、定位、相关度与预览；「进入文档切片」打开知识中心既有
 * `ChunkDrawer`（稳定 `document_uuid`/`segment_id`，实时鉴权，受限态保留元数据）。
 * 来源缺少 `document_uuid`/`segment_id` 时降级展示且不提供切片入口。
 * 两层叠放 Overlay 允许（UIDESIGN §5.5），焦点返回链由 `useOverlayFocus` 管理。
 */
export function SourceDetailDrawer({
  source,
  kbName,
  onClose,
}: {
  source: ChatSourceChunk
  kbName: string
  onClose: () => void
}) {
  const panelRef = useRef<HTMLElement>(null)
  const [sliceOpen, setSliceOpen] = useState(false)
  useOverlayFocus({ containerRef: panelRef, onClose })

  const canOpenSlice = Boolean(source.document_uuid && source.segment_id)

  return (
    <div className="drawer-overlay" role="presentation">
      <aside
        ref={panelRef}
        className="drawer source-detail"
        role="dialog"
        aria-modal="true"
        aria-label="回答依据"
        tabIndex={-1}
      >
        <header className="drawer__header">
          <div>
            <p className="eyebrow">来源 · {source.chunk_index}</p>
            <h2>回答依据</h2>
          </div>
          <button
            type="button"
            className="drawer__close"
            aria-label="关闭来源"
            data-overlay-initial-focus
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <div className="drawer__body source-detail__body">
          <dl className="source-detail__meta">
            <div>
              <dt>知识库</dt>
              <dd>{kbName}</dd>
            </div>
            <div>
              <dt>文档</dt>
              <dd>{source.doc_name || '未命名文档'}</dd>
            </div>
            <div>
              <dt>定位</dt>
              <dd>{sourceLocation(source)}</dd>
            </div>
            <div>
              <dt>相关度</dt>
              <dd>{source.score}</dd>
            </div>
            <div>
              <dt>来源编号</dt>
              <dd>{source.chunk_index}</dd>
            </div>
          </dl>
          {source.preview_text ? (
            <blockquote className="source-detail__preview">
              <HighlightPreview
                preview={source.preview_text}
                highlightStart={source.highlight_start}
                highlightEnd={source.highlight_end}
              />
            </blockquote>
          ) : null}
          {canOpenSlice ? (
            <Button type="button" variant="primary" onClick={() => setSliceOpen(true)}>
              进入文档切片
            </Button>
          ) : (
            <p className="source-detail__degraded" role="note">
              原文切片暂不可用（来源缺少文档切片定位）。
            </p>
          )}
        </div>
      </aside>
      {sliceOpen ? (
        <ChunkDrawer
          documentId={source.document_uuid}
          initialSegmentId={source.segment_id}
          onClose={() => setSliceOpen(false)}
        />
      ) : null}
    </div>
  )
}
