import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'default' | 'primary' | 'danger' | 'ghost'
  busy?: boolean
  busyLabel?: ReactNode
}

/** P0 共享按钮：统一既有视觉变体，并让忙碌态保留明确动作名称。 */
export function Button({
  variant = 'default',
  busy = false,
  busyLabel = '处理中…',
  className,
  disabled,
  children,
  ...props
}: Props) {
  const classes = ['btn', variant === 'default' ? null : `btn--${variant}`, className]
    .filter(Boolean)
    .join(' ')

  return (
    <button
      {...props}
      className={classes}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
    >
      {busy ? busyLabel : children}
    </button>
  )
}
