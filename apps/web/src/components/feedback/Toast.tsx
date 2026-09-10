import type { PropsWithChildren } from 'react'

/**
 * 轻量操作反馈（UIDESIGN §6.13）：顶部居中、单条、自动消失。
 * 成功类反馈以 `--es-success` 图标为前缀；不拦截焦点。
 */
export function Toast({ children }: PropsWithChildren) {
  return (
    <div className="toast" role="status">
      <span className="toast__icon" aria-hidden="true">
        ✓
      </span>
      {children}
    </div>
  )
}
