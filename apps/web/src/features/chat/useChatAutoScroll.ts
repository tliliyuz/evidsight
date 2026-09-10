import { type DependencyList, type RefObject, useEffect, useRef } from 'react'

const NEAR_BOTTOM_PX = 48

/**
 * 对话线程自动滚动（FRONTEND §5.5 输入区与流式交互）：
 * - 新消息与流式内容自动滚动到底部；
 * - 用户主动上滚后不强制抢回滚动位置（仅当接近底部时跟随）。
 */
export function useChatAutoScroll(
  containerRef: RefObject<HTMLElement | null>,
  deps: DependencyList,
) {
  const nearBottomRef = useRef(true)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return undefined

    function handleScroll() {
      const target = containerRef.current
      if (!target) return
      nearBottomRef.current =
        target.scrollHeight - target.scrollTop - target.clientHeight < NEAR_BOTTOM_PX
    }
    el.addEventListener('scroll', handleScroll, { passive: true })
    if (nearBottomRef.current) el.scrollTop = el.scrollHeight
    return () => el.removeEventListener('scroll', handleScroll)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return nearBottomRef
}
