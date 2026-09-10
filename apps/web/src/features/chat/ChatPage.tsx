import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { conversationsApi } from '@/api/conversations'
import { apiErrorMessage } from '@/api/errors'
import { knowledgeApi } from '@/api/knowledge'
import type { KnowledgeBase } from '@/api/knowledge'
import { Button } from '@/components/actions/Button'
import { ConfirmDialog } from '@/components/feedback/ConfirmDialog'
import { RenameDialog } from '@/components/feedback/RenameDialog'
import { useAppToast } from '@/components/feedback/toastContext'
import { ChatAnswer, type DisplayMessage } from '@/features/chat/ChatAnswer'
import { formatChatTimestamp } from '@/features/chat/chatFormat'
import { ChatComposer } from '@/features/chat/ChatComposer'
import { KnowledgeBasePicker } from '@/features/chat/KnowledgeBasePicker'
import { SourceDetailDrawer } from '@/features/chat/SourceDetailDrawer'
import { useChatGeneration } from '@/features/chat/useChatGeneration'
import { useChatAutoScroll } from '@/features/chat/useChatAutoScroll'
import { chatSourceToChunks } from '@/features/chat/chatSourceAdapter'
import type { ChatSourceChunk } from '@/features/chat/chatSseParser'
import type { ChatGenerationSnapshot } from '@/features/chat/chatGenerationMachine'

/** 空会话态的一键问答提示词：3-2-1 倒三角布局，点击预填输入框，减少大面积留白。 */
const QUESTION_PROMPT_ROWS = [
  ['梳理这个知识库的核心主题与结论', '找出文档中相互矛盾的观点', '总结最近更新的内容要点'],
  ['用一句话概括主要结论', '列出最重要的三点发现'],
  ['帮我起草一份要点摘要'],
]

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

/**
 * 据见问答页面（FRONTEND §5.5 / §7）。
 *
 * - 页头展示真实会话标题与「← 问答历史」入口；角色标识 + 消息时间（created_at）；
 * - 打开历史会话（?conversation=:id）恢复消息与知识库范围；
 * - 只消费 Chat v1 canonical SSE，未完成输出显示「生成中/已中止」，done 后才视为成功终态；
 * - 来源编号/引用标记打开来源详情抽屉，可继续进入既有切片抽屉（实时鉴权）；
 * - 历史来源合并优先级：持久化 Message.sources 优先，内存快照仅作回读前瞬时兜底；
 * - aria-live 仅覆盖状态行（role="status"）与错误（role="alert"）。
 */
export function ChatPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const conversationId = searchParams.get('conversation')
  // 从知识库详情「用它提问」进入时预选知识库（FRONTEND §5.5）
  const kbParam = searchParams.get('kb')
  const queryClient = useQueryClient()
  const { show } = useAppToast()
  const { snapshot, send, cancel, isActive } = useChatGeneration()
  const threadRef = useRef<HTMLElement>(null)
  const [selectedKbId, setSelectedKbId] = useState<string | null>(kbParam ?? null)
  const [selectedKbName, setSelectedKbName] = useState<string | null>(null)
  const [renameOpen, setRenameOpen] = useState(false)
  const [liveStartedAt, setLiveStartedAt] = useState<string | null>(null)
  const [sourceDetail, setSourceDetail] = useState<ChatSourceChunk | null>(null)
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

  const { data: conversation } = useQuery({
    queryKey: ['conversation', conversationId],
    queryFn: () =>
      conversationId ? conversationsApi.detail(conversationId) : Promise.resolve(null),
    enabled: conversationId !== null,
  })

  // 从知识库详情「用它提问」进入（?kb=）时解析知识库名称供 scope-summary 展示
  const { data: kbFromParam } = useQuery({
    queryKey: ['knowledge-base', kbParam],
    queryFn: () => (kbParam ? knowledgeApi.getKnowledgeBase(kbParam) : Promise.resolve(null)),
    enabled: kbParam !== null,
  })

  const renameMutation = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      conversationsApi.rename(id, title),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['conversation', conversationId] })
      setRenameOpen(false)
    },
    onError: (error) => {
      show(apiErrorMessage(error, '重命名失败，请稍后重试'))
    },
  })

  const activeKbId = selectedKbId ?? conversation?.kb_uuid ?? null
  // 当前会话的知识库名称：用户在会话内新选（selectedKbName 非空且 ≠ 会话既有 kb_uuid）时
  // 优先显示所选名称；其余按「会话回读 kb_name → ?kb= 详情 → 选择器名称」解析。
  const scopeName =
    selectedKbName !== null && selectedKbId !== conversation?.kb_uuid
      ? selectedKbName
      : (conversation?.kb_name ?? kbFromParam?.name ?? selectedKbName)
  const scopeSummary =
    activeKbId !== null
      ? scopeName
        ? `本对话已选择「${scopeName}」；每轮提问会重新确认访问权限。`
        : '本对话已选择知识库；每轮提问会重新确认访问权限。'
      : null
  // 孤儿会话：知识库已被删除或权限不足（kb_status 非 active）时，提示更换知识库并禁发
  const orphanConversation = conversation != null && conversation.kb_status !== 'active'
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

  // 合并优先级（FRONTEND §5.5）：持久化 Message.sources 非空时为权威；内存 completedSources
  // 仅作「done 后、服务端回读前」的瞬时兜底，并承载不随来源持久化的 transient confidence。
  const history: DisplayMessage[] = (conversation?.messages ?? []).map((message) => {
    const attached = snapshot.completedSources[message.id]
    const persisted = message.sources?.length ? chatSourceToChunks(message.sources) : []
    const sources = persisted.length > 0 ? persisted : (attached?.sources ?? [])
    const confidence = persisted.length > 0 ? undefined : attached?.confidence
    const confidenceNote = persisted.length > 0 ? undefined : attached?.confidenceNote
    return {
      key: `history-${message.id}`,
      role: message.role === 'user' ? 'user' : 'assistant',
      content: message.content,
      createdAt: message.created_at,
      sources,
      confidence,
      confidenceNote,
    }
  })

  const live: DisplayMessage[] = []
  if (showLiveAssistant) {
    if (showLiveUser) {
      live.push({
        key: 'live-user',
        role: 'user',
        content: activeQuestion as string,
        createdAt: liveStartedAt ?? undefined,
      })
    }
    live.push({
      key: 'live-assistant',
      role: 'assistant',
      content: snapshot.text,
      createdAt: liveStartedAt ?? undefined,
      status: statusLabel(snapshot.phase),
      error: snapshot.error,
      sources: snapshot.sources ?? undefined,
      confidence: snapshot.confidence,
      confidenceNote: snapshot.confidenceNote,
    })
  }

  const messages = [...history, ...live]
  useChatAutoScroll(threadRef, [messages.length, snapshot.text, snapshot.phase])

  function handlePickKb(kb: KnowledgeBase | null) {
    const kbId = kb?.uuid ?? null
    if (conversation && kbId && kbId === conversation.kb_uuid) {
      // 保持当前会话范围
      setSelectedKbId(null)
      setSelectedKbName(null)
      return
    }
    // 切换知识库会改变会话范围：存在会话时先明确提示（FRONTEND §5.5）
    if (conversation && kbId) {
      setPendingKbSwitch(kb)
      return
    }
    applyKbSwitch(kbId, kb?.name ?? null)
  }

  function applyKbSwitch(kbId: string | null, kbName: string | null = null) {
    setSelectedKbId(kbId)
    setSelectedKbName(kbName)
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
    setLiveStartedAt(new Date().toISOString())
    setQuestion('')
    await send({
      conversationId: sendConversationId,
      knowledgeBaseId: activeKbId,
      question: trimmed,
    })
  }

  return (
    <main className="chat route-surface">
      <header className="chat-header">
        <div className="chat-header__main">
          <div className="chat-title-row">
            <Link className="history-trigger" to="/chat/history">
              ← 问答历史
            </Link>
            <div className="chat-title-col">
              <h1>{conversation?.title ?? '新对话'}</h1>
              {scopeSummary ? <p className="scope-summary">{scopeSummary}</p> : null}
            </div>
          </div>
        </div>
        <div className="chat-header-actions">
          {activeKbId === null ? (
            <span className="chat-header__kb-hint">请先选择知识库，再开始问答。</span>
          ) : null}
          <KnowledgeBasePicker value={activeKbId} onSelect={handlePickKb} />
          <Button type="button" disabled={!conversation} onClick={() => setRenameOpen(true)}>
            重命名
          </Button>
        </div>
      </header>

      <section ref={threadRef} className="chat__thread" aria-label="对话内容">
        {messages.length === 0 ? (
          <div className="chat__empty">
            <p className="chat__empty-greeting">你好，我是 EvidSight，有什么我能帮你的吗？</p>
            <div className="chat__prompts" role="group" aria-label="一键问答提示词">
              {QUESTION_PROMPT_ROWS.map((row) => (
                <div key={row.join('')} className="chat__prompt-row">
                  {row.map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      className="chat__prompt"
                      onClick={() => setQuestion(prompt)}
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              ))}
            </div>
          </div>
        ) : (
          <ol className="chat__messages">
            {messages.map((message) => (
              <li key={message.key} className={`chat__message chat__message--${message.role}`}>
                {message.role === 'user' ? (
                  <div className="chat__user">
                    <span className="message-role chat__user-role">
                      你{message.createdAt ? ` · ${formatChatTimestamp(message.createdAt)}` : ''}
                    </span>
                    <div className="chat__bubble chat__bubble--user">
                      <p>{message.content}</p>
                    </div>
                  </div>
                ) : (
                  <ChatAnswer
                    message={message}
                    knowledgeBaseCount={activeKbId !== null ? 1 : 0}
                    onOpenSource={setSourceDetail}
                  />
                )}
              </li>
            ))}
          </ol>
        )}
      </section>

      {orphanConversation ? (
        <p className="chat__orphan-warning" role="alert">
          这个会话的知识库已被删除或暂无权限，请选择其他知识库继续提问。
        </p>
      ) : null}

      <ChatComposer
        value={question}
        placeholder={activeKbId === null ? '选择知识库后可提问' : '输入问题…'}
        onChange={setQuestion}
        onSend={() => void handleSend()}
        onCancel={cancel}
        isActive={isActive}
        canSend={activeKbId !== null && !orphanConversation}
      />

      {pendingKbSwitch ? (
        <ConfirmDialog
          title="切换知识库"
          description={`切换知识库将开启新的问答会话，当前会话「${conversation?.title ?? '新对话'}」的范围会变化。确定切换到「${pendingKbSwitch.name}」吗？`}
          confirmLabel="切换"
          onCancel={() => setPendingKbSwitch(null)}
          onConfirm={() => applyKbSwitch(pendingKbSwitch.uuid, pendingKbSwitch.name)}
        />
      ) : null}

      {renameOpen && conversation ? (
        <RenameDialog
          initialTitle={conversation.title}
          pending={renameMutation.isPending}
          onCancel={() => setRenameOpen(false)}
          onConfirm={(title) => {
            void renameMutation.mutate({ id: conversation.uuid, title })
          }}
        />
      ) : null}

      {sourceDetail ? (
        <SourceDetailDrawer
          source={sourceDetail}
          kbName={conversation?.kb_name ?? '知识库已删除'}
          onClose={() => setSourceDetail(null)}
        />
      ) : null}
    </main>
  )
}
