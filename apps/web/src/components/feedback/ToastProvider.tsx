import { useEffect, useRef, useState, type PropsWithChildren } from 'react'

import { Toast } from '@/components/feedback/Toast'
import { ToastContext } from '@/components/feedback/toastContext'

/**
 * 全局操作反馈（UIDESIGN §6.13）：挂在路由之上，Toast 跨页面导航存活
 * （删除知识库后返回列表仍能看见「已删除」反馈）。同一时间只显示一条，
 * 新反馈替换旧反馈并重置自动消失计时。
 */
export function ToastProvider({ children }: PropsWithChildren) {
  const [message, setMessage] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  function show(next: string): void {
    if (timerRef.current) clearTimeout(timerRef.current)
    setMessage(next)
    timerRef.current = setTimeout(() => setMessage(null), 2600)
  }

  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    },
    [],
  )

  return (
    <ToastContext.Provider value={{ show }}>
      {children}
      {message ? <Toast>{message}</Toast> : null}
    </ToastContext.Provider>
  )
}
