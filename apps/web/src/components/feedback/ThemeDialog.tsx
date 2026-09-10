import { useRef, useState } from 'react'

import type { Theme } from '@/state/theme'
import { useOverlayFocus } from '@/components/overlay/useOverlayFocus'

type Props = {
  current: Theme
  onPick: (theme: Theme) => void
  onClose: () => void
}

const OPTIONS: ReadonlyArray<{
  theme: Theme
  label: string
  description: string
  swatch: 'light' | 'dark'
}> = [
  { theme: 'light', label: '浅色', description: '白色背景 · 明亮办公', swatch: 'light' },
  { theme: 'dark', label: '深色', description: '深色背景 · 暗光环境', swatch: 'dark' },
]

function optionLabel(theme: Theme): string {
  return OPTIONS.find((option) => option.theme === theme)?.label ?? theme
}

/**
 * 主题选择与确认（对齐 FRONTEND §3.3 与跟踪版原型 theme-dialog/theme-confirm）。
 * 确认卡片叠加在选择卡片之上（选择卡片保持可见、inert 不参与交互）：
 * 点击主题只进入确认，确认后才应用并持久化。
 */
export function ThemeDialog({ current, onPick, onClose }: Props) {
  const [pending, setPending] = useState<Theme | null>(null)
  const selectionRef = useRef<HTMLDivElement>(null)
  const confirmRef = useRef<HTMLDivElement>(null)
  useOverlayFocus({ containerRef: pending ? confirmRef : selectionRef, onClose, canClose: true })

  return (
    <>
      <div className="dialog-overlay" role="presentation" inert={pending ? true : undefined}>
        <div
          ref={selectionRef}
          className="dialog theme-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="theme-title"
          tabIndex={-1}
        >
          <p className="eyebrow">外观设置</p>
          <h2 id="theme-title">选择界面主题</h2>
          <p className="theme-dialog__intro">
            浅色适合明亮办公环境，深色适合暗光环境；选择后需确认切换。
          </p>
          <div className="theme-options" role="radiogroup" aria-label="界面主题">
            {OPTIONS.map((option) => {
              const selected = option.theme === current
              return (
                <button
                  key={option.theme}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  data-overlay-initial-focus={selected ? '' : undefined}
                  className={selected ? 'theme-option selected' : 'theme-option'}
                  onClick={() => {
                    // 已在当前主题：点击无反应，只有点击未选中的主题才进入确认
                    if (option.theme !== current) setPending(option.theme)
                  }}
                >
                  <span
                    className={`theme-swatch theme-swatch--${option.swatch}`}
                    aria-hidden="true"
                  />
                  <span className="theme-option__copy">
                    <b>{option.label}</b>
                    <small>{option.description}</small>
                  </span>
                  <i className="theme-check" aria-hidden="true">
                    ✓
                  </i>
                </button>
              )
            })}
          </div>
          <div className="theme-actions">
            <button type="button" className="btn" onClick={onClose}>
              取消
            </button>
          </div>
        </div>
      </div>
      {pending ? (
        <div className="dialog-overlay" role="presentation">
          <div
            ref={confirmRef}
            className="dialog theme-confirm"
            role="dialog"
            aria-modal="true"
            aria-labelledby="theme-confirm-title"
            tabIndex={-1}
          >
            <h2 id="theme-confirm-title">切换主题？</h2>
            <p className="theme-confirm__text">
              确定切换到{optionLabel(pending)}主题吗？切换会立即生效。
            </p>
            <div className="theme-actions">
              <button
                type="button"
                className="btn"
                data-overlay-initial-focus
                onClick={() => setPending(null)}
              >
                取消
              </button>
              <button type="button" className="btn btn--primary" onClick={() => onPick(pending)}>
                确认切换
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}
