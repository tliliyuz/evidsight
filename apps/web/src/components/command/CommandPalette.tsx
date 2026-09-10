import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useOverlayFocus } from '@/components/overlay/useOverlayFocus'

/**
 * 命令面板（FRONTEND §3.4 / UIDESIGN §7.22）。
 *
 * 命令入口按钮在原位展开为搜索输入框（combobox）：不弹出独立面板，直接在触发框输入。
 * 空输入不显示命令列表，输入有匹配后才在输入框下方弹出过滤后的命令列表。
 * ↑/↓ 移动、Enter 执行、Escape 或点击外部关闭并返回命令入口按钮。
 * 承载页面导航与明确创建动作，不执行任意指令、不跨数据源全文搜索。
 */

type Command = {
  id: string
  label: string
  hint: string
  to: string
}

const COMMANDS: Command[] = [
  { id: 'workbench', label: '工作台', hint: '回到工作台', to: '/workbench' },
  { id: 'chat', label: '据见问答', hint: '向企业知识提问', to: '/chat' },
  { id: 'history', label: '问答历史', hint: '查看最近会话', to: '/chat/history' },
  { id: 'knowledge', label: '知识库', hint: '管理企业知识', to: '/knowledge-bases' },
  { id: 'research-new', label: '深度研究', hint: '发起新的研究任务', to: '/research/new' },
  { id: 'research', label: '研究任务', hint: '查看运行状态', to: '/research' },
  {
    id: 'kb-create',
    label: '创建知识库',
    hint: '新建知识库并导入材料',
    to: '/knowledge-bases?create=1',
  },
]

const LIST_ID = 'command-list'

type Props = {
  onClose: () => void
}

export function CommandPalette({ onClose }: Props) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const panelRef = useRef<HTMLDivElement>(null)

  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    if (!keyword) return COMMANDS
    return COMMANDS.filter((command) =>
      `${command.label}${command.hint}`.toLowerCase().includes(keyword),
    )
  }, [query])

  const expanded = query.trim().length > 0
  const activeCommand = expanded ? filtered[activeIndex] : undefined

  useOverlayFocus({ containerRef: panelRef, onClose, canClose: true })

  // 点击输入框外部关闭（原位输入，不做全屏遮罩）
  useEffect(() => {
    function handlePointerDown(event: MouseEvent | TouchEvent) {
      if (!panelRef.current?.contains(event.target as Node)) onClose()
    }
    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('touchstart', handlePointerDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('touchstart', handlePointerDown)
    }
  }, [onClose])

  function run(command: Command) {
    onClose()
    navigate(command.to)
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      if (expanded) setActiveIndex((index) => Math.min(index + 1, filtered.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      if (expanded) setActiveIndex((index) => Math.max(index - 1, 0))
    } else if (event.key === 'Enter') {
      event.preventDefault()
      if (activeCommand) run(activeCommand)
    }
  }

  return (
    <div ref={panelRef} className="command-palette">
      <input
        type="text"
        className="command-palette__input"
        role="combobox"
        aria-label="搜索命令"
        aria-expanded={expanded}
        aria-controls={LIST_ID}
        aria-autocomplete="list"
        aria-activedescendant={activeCommand ? `${LIST_ID}-${activeCommand.id}` : undefined}
        placeholder="搜索或执行指令…"
        value={query}
        onChange={(event) => {
          // 输入变化时重置当前项到首项，避免旧索引越界
          setQuery(event.target.value)
          setActiveIndex(0)
        }}
        onKeyDown={handleKeyDown}
        data-overlay-initial-focus
      />
      {expanded ? (
        filtered.length > 0 ? (
          <ul id={LIST_ID} className="command-list" role="listbox" aria-label="命令列表">
            {filtered.map((command, index) => (
              <li
                key={command.id}
                id={`${LIST_ID}-${command.id}`}
                role="option"
                aria-selected={index === activeIndex}
                className={`command-list__item${index === activeIndex ? ' is-active' : ''}`}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => run(command)}
              >
                <span className="command-list__label">{command.label}</span>
                <small className="command-list__hint">{command.hint}</small>
              </li>
            ))}
          </ul>
        ) : (
          <p className="command-palette__empty">无匹配命令</p>
        )
      ) : null}
    </div>
  )
}
