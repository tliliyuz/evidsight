import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { conversationsApi } from '@/api/conversations'
import type { KnowledgeBase } from '@/api/knowledge'
import { ConfirmDialog } from '@/components/feedback/ConfirmDialog'
import { ChunkDrawer } from '@/features/knowledge/ChunkDrawer'
import { KnowledgeBasePicker } from '@/features/chat/KnowledgeBasePicker'
import { SourceCards } from '@/features/chat/SourceCards'
import { useChatGeneration } from '@/features/chat/useChatGeneration'
import type { ChatSourceChunk } from '@/features/chat/chatSseParser'
import type { ChatGenerationSnapshot } from '@/features/chat/chatGenerationMachine'

function statusLabel(phase: ChatGenerationSnapshot['phase']): string | null {
  switch (phase) {
    case 'connecting':
      return '正在连接…'
    case 'streaming':
    case 'awaitingSources':
      return '生成中'
    case 'canceling':
      return '正在停止'
    case 'canceled':
      return '已中止'
    default:
      return null
  }
}

type DisplayMessage = {
  key: string
  role: 'user' | 'assistant'
  content: string
  status?: string | null
  error?: ChatGenerationSnapshot['error']
  sources?: ChatGenerationSnapshot['sources']
  confidence?: string
  confidenceNote?: string
}

/**
 * 据见问答页面（FRONTEND §5.5 / §7）。
 *
 * - 打开历史会话（?conversation=:id）恢复消息与知识库范围；
 * - 新会话通过知识库选择器单选一个 KB 后发送；
 * - 只消费 Chat v1 canonical SSE，未完成输出显示「生成中/已中止」，
 *   不伪装完整答案；done 后才视为成功终态；
 * - 完成一轮后以服务端回读（会话详情）确认消息已持久化，切换知识库会开启新会话。
 */
export function ChatPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const conversationId = searchParams.get('conversation')
  // 从知识库详情「用它提问」进入时预选知识库（FRONTEND §5.5）
  const kbParam = searchParams.get('kb')
  const queryClient = useQueryClient()
  const { snapshot, send, cancel, isActive } = useChatGeneration()
  const [selectedKbId, setSelectedKbId] = useState<string | null>(kbParam ?? null)
  // 同一路由内 ?kb= 变化（如从另一知识库再次「用它提问」）时在渲染期同步预选，
  // 使用 React 官方「props 变化时调整 state」模式（避免 set-state-in-effect）；
  // ?kb= 清空（发送后写入 ?conversation=）时不覆盖用户已选知识库。
  const [prevKbParam, setPrevKbParam] = useState<string | null>(kbParam ?? null)
  if (kbParam !== null && kbParam !== prevKbParam) {
    setPrevKbParam(kbParam)
    setSelectedKbId(kbParam)
  }
  const [question, setQuestion] = useState('')
  const [activeQuestion, setActiveQuestion] = useState<string | null>(null)
  const [pendingKbSwitch, setPendingKbSwitch] = useState<KnowledgeBase | null>(null)
  const [sliceSource, setSliceSource] = useState<ChatSourceChunk | null>(null)

  const { data: conversation } = useQuery({
    queryKey: ['conversation', conversationId],
    queryFn: () =>
      conversationId ? conversationsApi.detail(conversationId) : Promise.resolve(null),
    enabled: conversationId !== null,
  })

  const activeKbId = selectedKbId ?? conversation?.kb_uuid ?? null
  const historyContainsDone =
    conversation?.messages.some((message) => message.id === snapshot.doneMessageId) ?? false
  const showLiveAssistant =
    snapshot.phase !== 'idle' && !(snapshot.phase === 'completed' && historyContainsDone)
  const showLiveUser = activeQuestion !== null && showLiveAssistant

  // 完成一轮：以服务端回读确认持久化；新会话写入 URL 以便刷新可恢复。
  // 实时气泡在历史回读到 done 消息后自动隐藏（showLiveAssistant 关闭），无需在此清状态。
  useEffect(() => {
    if (snapshot.phase !== 'completed') return
    const id = snapshot.conversationId
    if (id) {
      if (id !== conversationId) {
        setSearchParams({ conversation: id }, { replace: true })
      }
      void queryClient.invalidateQueries({ queryKey: ['conversation', id] })
    }
  }, [snapshot.phase, snapshot.conversationId, conversationId, queryClient, setSearchParams])

  const history: DisplayMessage[] = (conversation?.messages ?? []).map((message) => {
    const attached = snapshot.completedSources[message.id]
    return {
      key: `history-${message.id}`,
      role: message.role === 'user' ? 'user' : 'assistant',
      content: message.content,
      sources: attached?.sources,
      confidence: attached?.confidence,
      confidenceNote: attached?.confidenceNote,
    }
  })

  const live: DisplayMessage[] = []
  if (showLiveAssistant) {
    if (showLiveUser) {
      live.push({ key: 'live-user', role: 'user', content: activeQuestion as string })
    }
    live.push({
      key: 'live-assistant',
      role: 'assistant',
      content: snapshot.text,
      status: statusLabel(snapshot.phase),
      error: snapshot.error,
      sources: snapshot.sources ?? undefined,
      confidence: snapshot.confidence,
      confidenceNote: snapshot.confidenceNote,
    })
  }

  const messages = [...history, ...live]

  function handlePickKb(kb: KnowledgeBase | null) {
    const kbId = kb?.uuid ?? null
    if (conversation && kbId && kbId === conversation.kb_uuid) {
      // 保持当前会话范围
      setSelectedKbId(null)
      return
    }
    // 切换知识库会改变会话范围：存在会话时先明确提示（FRONTEND §5.5）
    if (conversation && kbId) {
      setPendingKbSwitch(kb)
      return
    }
    applyKbSwitch(kbId)
  }

  function applyKbSwitch(kbId: string | null) {
    setSelectedKbId(kbId)
    setSearchParams({}, { replace: true })
    setPendingKbSwitch(null)
  }

  async function handleSend() {
    const trimmed = question.trim()
    if (!trimmed || activeKbId === null || isActive) return
    // 完成新会话后、详情回读完成前，conversation 尚未加载；回退到 URL 参数，
    // 避免以 conversation_id=null 重复创建新会话（取消竞态之外的发送竞态）
    const sendConversationId = conversation?.uuid ?? conversationId
    setActiveQuestion(trimmed)
    setQuestion('')
    await send({
      conversationId: sendConversationId,
      knowledgeBaseId: activeKbId,
      question: trimmed,
    })
  }

  return (
    <main className="chat">
      <header className="page-heading chat__heading">
        <div>
          <p>Q&A</p>
          <h1>据见问答</h1>
          <span>在一个知识库范围内获得带来源的回答。</span>
        </div>
        <Link to="/chat/history">问答历史</Link>
      </header>

      <KnowledgeBasePicker value={activeKbId} onSelect={handlePickKb} />

      <section className="chat__thread" aria-label="对话内容" aria-live="polite">
        {messages.length === 0 ? (
          <p className="chat__empty">
            {activeKbId === null ? '请先选择知识库，再开始问答。' : '输入问题，获得带来源的回答。'}
          </p>
        ) : (
          <ol className="chat__messages">
            {messages.map((message) => (
              <li key={message.key} className={`chat__message chat__message--${message.role}`}>
                <div className="chat__bubble">
                  <p>{message.content || (message.role === 'assistant' ? '…' : '')}</p>
                  {message.status ? (
                    <span className="chat__status" aria-live="polite">
                      {message.status}
                    </span>
                  ) : null}
                  {message.error ? (
                    <p className="chat__error" role="alert">
                      {message.error.message || '回答生成失败'}
                    </p>
                  ) : null}
                  {message.sources && message.sources.length > 0 ? (
                    <SourceCards
                      sources={message.sources}
                      confidence={message.confidence}
                      confidenceNote={message.confidenceNote}
                      onOpenSlice={setSliceSource}
                    />
                  ) : null}
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>

      <form
        className="chat__composer"
        onSubmit={(event) => {
          event.preventDefault()
          void handleSend()
        }}
      >
        <label htmlFor="chat-input" className="sr-only">
          输入问题
        </label>
        <textarea
          id="chat-input"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={activeKbId === null ? '选择知识库后可提问' : '输入问题…'}
          rows={3}
          disabled={isActive}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              void handleSend()
            }
          }}
        />
        <div className="chat__composer-actions">
          {isActive ? (
            <button type="button" className="chat__stop" onClick={cancel}>
              停止生成
            </button>
          ) : (
            <button
              type="submit"
              className="chat__send"
              disabled={!question.trim() || activeKbId === null}
            >
              发送
            </button>
          )}
        </div>
      </form>

      {pendingKbSwitch ? (
        <ConfirmDialog
          title="切换知识库"
          description={`切换知识库将开启新的问答会话，当前会话「${conversation?.title ?? '新对话'}」的范围会变化。确定切换到「${pendingKbSwitch.name}」吗？`}
          confirmLabel="切换"
          onCancel={() => setPendingKbSwitch(null)}
          onConfirm={() => applyKbSwitch(pendingKbSwitch.uuid)}
        />
      ) : null}

      {sliceSource ? (
        <ChunkDrawer
          documentId={sliceSource.document_uuid}
          initialSegmentId={sliceSource.segment_id || null}
          onClose={() => setSliceSource(null)}
        />
      ) : null}
    </main>
  )
}
