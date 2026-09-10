/**
 * 来源预览高亮：按 `highlight_start`/`highlight_end` 区间把命中片段包进 `<mark>`。
 * 区间非法（越界/倒置）时原样返回预览文本。供来源卡片与来源详情抽屉复用。
 */
export function HighlightPreview({
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
