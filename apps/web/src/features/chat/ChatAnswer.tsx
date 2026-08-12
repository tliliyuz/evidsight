import { useState } from 'react'

import { formatChatTimestamp } from '@/features/chat/chatFormat'
import { hasInlineCitations, renderChatMarkdown } from '@/features/chat/chatMarkdown'
import type { ChatSourceChunk } from '@/features/chat/chatSseParser'
import type { ChatGenerationSnapshot } from '@/features/chat/chatGenerationMachine'

export type DisplayMessage = {
  key: string
  role: 'user' | 'assistant'
  content: string
  createdAt?: string
  status?: string | null
  error?: ChatGenerationSnapshot['error']
  sources?: ChatSourceChunk[]
  confidence?: string
  confidenceNote?: string
}

/**
 * 系统回答正文（FRONTEND §5.5 / 原型 07-chat）。
 *
 * - 正文阅读区：左对齐，宽度、字号、行高与段落间距按原型，移除通用气泡感；
 * - 内容以轻量 markdown 渲染（粗体/列表/标题/代码/段落）；后端注入的 `[来源N]` 标记
 *   转换为内联引用按钮，点击打开来源详情抽屉；内容无内联标记时回退到正文下方的来源条；
 * - 底部信息栏「使用 N 个知识库 · M 个来源」+ 「复制回答」；
 * - 实时状态与错误分别以 `role="status"` / `role="alert"` 呈现（收窄 aria-live）。
 */
export function ChatAnswer({
  message,
  onOpenSource,
  knowledgeBaseCount = 0,
}: {
  message: DisplayMessage
  onOpenSource: (source: ChatSourceChunk) => void
  knowledgeBaseCount?: number
}) {
  const sources = message.sources ?? []
  const [copied, setCopied] = useState(false)
  const inlineCitations = hasInlineCitations(message.content)

  // 有来源时至少用了一个知识库（v1 单 KB；计数取会话实际知识库数量）
  const kbUsed = sources.length > 0 ? Math.max(knowledgeBaseCount, 1) : knowledgeBaseCount

  async function handleCopy() {
    const text = message.content
    if (!text) return
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      // 剪贴板不可用时静默失败，不打断阅读
    }
  }

  return (
    <div className="chat__answer">
      <span className="message-role">
        EvidSight
        {message.createdAt ? ` · ${formatChatTimestamp(message.createdAt)}` : ''}
      </span>
      <div className="assistant-answer">
        {inlineCitations ? (
          <div className="assistant-answer__md">
            {renderChatMarkdown(message.content, sources, onOpenSource)}
          </div>
        ) : (
          <p>{message.content || (message.status ? '' : '…')}</p>
        )}
        {!inlineCitations && sources.length > 0 ? (
          <>
            <span className="chat-citations" aria-label="回答依据">
              {sources.map((source) => (
                <button
                  key={source.chunk_index}
                  type="button"
                  className="chat-citation"
                  aria-label={`引用来源 ${source.chunk_index}`}
                  title={source.doc_name || '未命名文档'}
                  onClick={() => onOpenSource(source)}
                >
                  {String(source.chunk_index).padStart(2, '0')}
                </button>
              ))}
            </span>
            <small className="answer-sources__note">回答依据来源，按检索相关度排序</small>
          </>
        ) : null}
      </div>
      {message.status ? (
        <span className="chat__status" role="status">
          {message.status}
        </span>
      ) : null}
      {message.error ? (
        <p className="chat__error" role="alert">
          {message.error.message || '回答生成失败'}
        </p>
      ) : null}
      {sources.length > 0 ? (
        <p className="answer-foot">
          <span className="answer-foot__meta">
            使用 {kbUsed} 个知识库 · {sources.length} 个来源
          </span>
          <button type="button" className="answer-foot__copy" onClick={() => void handleCopy()}>
            {copied ? '已复制' : '复制回答'}
          </button>
        </p>
      ) : null}
    </div>
  )
}
