import { useRef, useState } from 'react'

import { Button } from '@/components/actions/Button'

const MAX_GROW_PX = 160

/**
 * 对话输入区（FRONTEND §5.5 输入区与流式交互）。
 *
 * - 输入框无外框：禁止拖拽改变布局（CSS `resize: none`），随内容增长在合理上限内自增高；
 *   聚焦时只保留文本光标，不显示蓝色焦点环；
 * - `Enter` 发送、`Shift+Enter` 换行，中文输入法组合期间（`isComposing`）不误发送；
 * - 底栏左侧「深度思考」开关（当前为前端开关状态，待后端思考模式落地后接入）；
 * - 生成中禁用重复提交并显示「停止生成」，由调用方统一各阶段状态文案。
 */
export function ChatComposer({
  value,
  placeholder,
  onChange,
  onSend,
  onCancel,
  isActive,
  canSend,
}: {
  value: string
  placeholder: string
  onChange: (value: string) => void
  onSend: () => void
  onCancel: () => void
  isActive: boolean
  canSend: boolean
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const composingRef = useRef(false)
  const [deepThink, setDeepThink] = useState(false)

  function handleChange(next: string) {
    onChange(next)
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = `${Math.min(el.scrollHeight, MAX_GROW_PX)}px`
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !composingRef.current) {
      event.preventDefault()
      if (!isActive && value.trim() && canSend) onSend()
    }
  }

  function submit() {
    if (!isActive && value.trim() && canSend) onSend()
  }

  return (
    <form
      className="chat__composer"
      onSubmit={(event) => {
        event.preventDefault()
        submit()
      }}
    >
      <label htmlFor="chat-input" className="sr-only">
        输入问题
      </label>
      <textarea
        ref={textareaRef}
        id="chat-input"
        value={value}
        placeholder={placeholder}
        rows={1}
        disabled={isActive}
        onChange={(event) => handleChange(event.target.value)}
        onCompositionStart={() => {
          composingRef.current = true
        }}
        onCompositionEnd={() => {
          composingRef.current = false
        }}
        onKeyDown={handleKeyDown}
      />
      <footer className="chat__composer-foot">
        <button
          type="button"
          className={
            deepThink ? 'chat__composer-deep chat__composer-deep--on' : 'chat__composer-deep'
          }
          aria-pressed={deepThink}
          onClick={() => setDeepThink((value) => !value)}
        >
          <span className="chat__composer-deep-switch" aria-hidden="true" />
          <span>深度思考</span>
        </button>
        {isActive ? (
          <Button type="button" onClick={onCancel}>
            停止生成
          </Button>
        ) : (
          <Button
            type="submit"
            variant="primary"
            className="chat__composer-send"
            disabled={!value.trim() || !canSend}
          >
            <span>发送</span>
            <span className="chat__composer-send-arrow" aria-hidden="true">
              ↗
            </span>
          </Button>
        )}
      </footer>
    </form>
  )
}
