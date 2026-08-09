import type { ChatSourceChunk } from '@/features/chat/chatSseParser'

function HighlightPreview({
  preview,
  highlightStart,
  highlightEnd,
}: {
  preview: string
  highlightStart: number | null
  highlightEnd: number | null
}) {
  if (
    highlightStart === null ||
    highlightEnd === null ||
    highlightStart < 0 ||
    highlightEnd > preview.length ||
    highlightStart >= highlightEnd
  ) {
    return <>{preview}</>
  }
  return (
    <>
      {preview.slice(0, highlightStart)}
      <mark>{preview.slice(highlightStart, highlightEnd)}</mark>
      {preview.slice(highlightEnd)}
    </>
  )
}

/**
 * 回答来源卡片（FRONTEND §5.5）。
 *
 * 展示 `sources` 事件携带的来源元数据（编号、文档名、置信度、预览与高亮区间）。
 * 通过 `onOpenSlice` 联动知识中心切片抽屉（ChunkDrawer）：以来源的稳定
 * `document_uuid`/`segment_id` 打开对应文档切片并展开引用片段，原文展开时
 * 由抽屉实时鉴权（FRONTEND §5.4）。无 document_uuid（旧来源或解析缺失）时
 * 不提供进入入口。
 */
export function SourceCards({
  sources,
  confidence,
  confidenceNote,
  onOpenSlice,
}: {
  sources: ChatSourceChunk[]
  confidence?: string
  confidenceNote?: string
  onOpenSlice?: (source: ChatSourceChunk) => void
}) {
  if (sources.length === 0) return null
  return (
    <section className="source-cards" aria-label="回答来源">
      {confidence ? (
        <p className="source-cards__confidence">
          <strong>证据置信度：{confidence}</strong>
          {confidenceNote ? <span> {confidenceNote}</span> : null}
        </p>
      ) : null}
      <ul className="source-cards__list">
        {sources.map((source) => (
          <li key={source.chunk_index}>
            <article className="source-card">
              <header className="source-card__head">
                <span className="source-card__index">来源 {source.chunk_index}</span>
                <h4>{source.doc_name || '未命名文档'}</h4>
                <span className="source-card__score">相关度 {source.score}</span>
              </header>
              {source.section_title ? (
                <p className="source-card__section">{source.section_title}</p>
              ) : null}
              {source.preview_text ? (
                <p className="source-card__preview">
                  <HighlightPreview
                    preview={source.preview_text}
                    highlightStart={source.highlight_start}
                    highlightEnd={source.highlight_end}
                  />
                </p>
              ) : null}
              {onOpenSlice && source.document_uuid ? (
                <button
                  type="button"
                  className="source-card__slice"
                  onClick={() => onOpenSlice(source)}
                >
                  进入文档切片
                </button>
              ) : null}
            </article>
          </li>
        ))}
      </ul>
    </section>
  )
}
