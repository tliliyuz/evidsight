import { type RefObject, useEffect, useRef } from 'react'

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

type Options = {
  containerRef: RefObject<HTMLElement | null>
  onClose: () => void
  canClose?: boolean
}

/** UIDESIGN §6.6：Overlay 初始焦点、焦点循环、Escape 与关闭后焦点返回。 */
export function useOverlayFocus({ containerRef, onClose, canClose = true }: Options) {
  const onCloseRef = useRef(onClose)
  const canCloseRef = useRef(canClose)

  useEffect(() => {
    onCloseRef.current = onClose
    canCloseRef.current = canClose
  }, [canClose, onClose])

  useEffect(() => {
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const container = containerRef.current

    if (!container) return undefined

    const initial =
      container.querySelector<HTMLElement>('[data-overlay-initial-focus]') ??
      container.querySelector<HTMLElement>(FOCUSABLE_SELECTOR) ??
      container
    initial.focus()

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && canCloseRef.current) {
        event.preventDefault()
        onCloseRef.current()
        return
      }

      if (event.key !== 'Tab') return

      const focusable = Array.from(
        container!.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter((element) => !element.hidden && element.getAttribute('aria-hidden') !== 'true')

      if (focusable.length === 0) {
        event.preventDefault()
        container!.focus()
        return
      }

      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      if (trigger?.isConnected) trigger.focus()
    }
  }, [containerRef])
}
