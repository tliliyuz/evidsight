import type { ChatSourceChunk } from '@/features/chat/chatSseParser'

/** 消息角色时间戳：本地 `HH:mm`（FRONTEND §5.5 角色名称字号高于元数据）。 */
export function formatChatTimestamp(value?: string): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/**
 * 来源定位展示。技术债：只有 PDF 的 page 是真实页码；docx/md/txt 等的 page 实为段落/切片
 * 序号，按 doc_name 扩展名区分「页 / 段」。
 */
export function sourceLocation(source: ChatSourceChunk): string {
  if (source.page) {
    const ext = (source.doc_name ?? '').split('.').pop()?.toLowerCase()
    return ext === 'pdf' ? `第 ${source.page} 页` : `第 ${source.page} 段`
  }
  if (source.section_path) return source.section_path
  if (source.section_title) return source.section_title
  return '未知'
}
