import type { PropsWithChildren } from 'react'

export type BadgeTone = 'neutral' | 'success' | 'processing' | 'warning' | 'danger' | 'knowledge'

/** 小型矩形状态 Badge（对齐 UIDESIGN §6.4）：始终包含状态词，必要时加图标。 */
export function StatusBadge({ tone, children }: PropsWithChildren<{ tone: BadgeTone }>) {
  return (
    <span className={`status-badge status-badge--${tone}`} role="status">
      <span className="status-badge__dot" aria-hidden="true" />
      {children}
    </span>
  )
}
