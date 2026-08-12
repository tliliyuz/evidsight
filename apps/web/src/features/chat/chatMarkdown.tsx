import type { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'

import type { ChatSourceChunk } from '@/features/chat/chatSseParser'

/** 内容里的内联引用标记：`[来源1]`、`[来源2]`（后端注入，编号对应 sources 数组 chunk_index）。 */
const INLINE_CITATION = /\[来源\s*(\d+)\]/g
/** 是否包含内联引用标记：有则来源以内联锚点呈现，不再额外渲染下方来源条。 */
export function hasInlineCitations(content: string): boolean {
  return INLINE_CITATION.test(content)
}

/** 把 `[来源N]` 预处理为 markdown 链接占位 `#cite-N`，再由 a 组件拦截成引用按钮。 */
function prepareContent(content: string): string {
  return content.replace(INLINE_CITATION, (_match, num: string) => `[来源${num}](#cite-${num})`)
}

/**
 * 回答正文 markdown 渲染（react-markdown，CommonMark 兼容）。
 * 后端注入的 `[来源N]` 标记预处理为内联引用按钮，点击打开来源详情抽屉。
 */
export function renderChatMarkdown(
  content: string,
  sources: ChatSourceChunk[],
  onOpenSource: (source: ChatSourceChunk) => void,
): ReactNode {
  return (
    <div className="assistant-answer__md">
      <ReactMarkdown
        components={{
          a({ href, children }) {
            const match = /^#cite-(\d+)$/.exec(href ?? '')
            if (match) {
              const num = Number(match[1])
              const source = sources.find((item) => item.chunk_index === num)
              if (source) {
                return (
                  <button
                    type="button"
                    className="chat-citation chat-citation--inline"
                    aria-label={`引用来源 ${num}`}
                    title={source.doc_name || '未命名文档'}
                    onClick={() => onOpenSource(source)}
                  >
                    {String(num).padStart(2, '0')}
                  </button>
                )
              }
            }
            return <a href={href}>{children}</a>
          },
        }}
      >
        {prepareContent(content)}
      </ReactMarkdown>
    </div>
  )
}
