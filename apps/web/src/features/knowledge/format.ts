/** 绝对时间戳文案（本地时区 `YYYY-MM-DD HH:mm`，对齐原型「2026-07-31 12:18 更新」口径；不接受相对时间推断）。 */
export function formatTimestamp(value: string | Date | null): string {
  if (value == null) return '—'
  const date = typeof value === 'string' ? new Date(value) : value
  if (Number.isNaN(date.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}
