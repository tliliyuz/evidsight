import type { ReactNode } from 'react'

/**
 * 空态（UIDESIGN §6 反馈 / §7.2 工作台）。
 *
 * `actionAlign="below"`（默认）：动作按钮位于说明文案下方；
 * `actionAlign="beside"`：动作按钮与说明文案处于同一行、右对齐，
 * 用于「查看全部」下方右侧的动作布局（如工作台 RECENT RESEARCH 空态）。
 */
export function EmptyState({
  title,
  description,
  action,
  actionAlign = 'below',
}: {
  title: string
  description: string
  action?: ReactNode
  actionAlign?: 'below' | 'beside'
}) {
  if (actionAlign === 'beside') {
    return (
      <section className="empty-state empty-state--beside">
        <h3>{title}</h3>
        <div className="empty-state__action-row">
          <p>{description}</p>
          {action}
        </div>
      </section>
    )
  }
  return (
    <section className="empty-state">
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </section>
  )
}
