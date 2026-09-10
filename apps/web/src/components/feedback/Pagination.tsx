type Props = {
  page: number
  total: number
  pageSize: number
  disabled?: boolean
  onPageChange: (page: number) => void
}

/**
 * 分页（对齐原型：默认 10 条/页，显示页码按钮 + 省略号 + 上一页/下一页）。
 * 后端列表接口返回 `total/page/page_size`（API.md §4），前端据 total 计算总页数。
 */
export function Pagination({ page, total, pageSize, disabled = false, onPageChange }: Props) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const pages = buildPageWindow(page, totalPages)

  return (
    <nav className="pagination" aria-label="分页">
      <button
        type="button"
        className="btn"
        disabled={disabled || page <= 1}
        onClick={() => onPageChange(page - 1)}
      >
        上一页
      </button>
      {pages.map((entry, index) =>
        entry === '…' ? (
          <span key={`ellipsis-${index}`} className="pagination__ellipsis">
            …
          </span>
        ) : (
          <button
            key={entry}
            type="button"
            className="btn"
            aria-current={entry === page ? 'page' : undefined}
            disabled={disabled}
            onClick={() => onPageChange(entry)}
          >
            {entry}
          </button>
        ),
      )}
      <button
        type="button"
        className="btn"
        disabled={disabled || page >= totalPages}
        onClick={() => onPageChange(page + 1)}
      >
        下一页
      </button>
      <span>
        第 {page} / {totalPages} 页
      </span>
    </nav>
  )
}

/** 生成页码窗口（首尾固定、当前页 ±2、间隙用省略号），最多约 7 个数字位。 */
function buildPageWindow(current: number, totalPages: number): (number | '…')[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1)
  }
  const start = Math.max(2, current - 2)
  const end = Math.min(totalPages - 1, current + 2)
  const pages: (number | '…')[] = [1]
  if (start > 2) pages.push('…')
  for (let p = start; p <= end; p += 1) pages.push(p)
  if (end < totalPages - 1) pages.push('…')
  pages.push(totalPages)
  return pages
}
