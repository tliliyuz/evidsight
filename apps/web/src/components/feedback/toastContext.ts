import { createContext, useContext } from 'react'

/**
 * 全局操作反馈上下文（UIDESIGN §6.13）。
 * 与 `ToastProvider` 分离：本文件只导出 hook 与 context，供组件触发跨页面存活的 Toast。
 */
export type ToastContextValue = { show: (message: string) => void }

export const ToastContext = createContext<ToastContextValue>({ show: () => {} })

export function useAppToast(): ToastContextValue {
  return useContext(ToastContext)
}
