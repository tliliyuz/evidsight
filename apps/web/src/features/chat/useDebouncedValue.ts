import { useEffect, useState } from 'react'

/**
 * 防抖值：输入变化后延迟 `delayMs` 才更新返回值。
 * 用于历史页搜索输入——URL 立即同步，但查询以防抖后的值驱动，避免逐键触发服务端请求。
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs)
    return () => window.clearTimeout(timer)
  }, [value, delayMs])

  return debounced
}
