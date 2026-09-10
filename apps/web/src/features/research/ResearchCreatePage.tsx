import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Button } from '@/components/actions/Button'
import type { KnowledgeBase } from '@/api/knowledge'
import {
  researchApi,
  type ResearchApi,
  type ResearchSourceStrategy,
  type ResearchTaskCreate,
} from '@/api/research'
import { ResearchKbPicker } from '@/features/research/ResearchKbPicker'

const TASK_TYPE_OPTIONS: {
  value: ResearchTaskCreate['requirements']['task_type']
  label: string
}[] = [
  { value: 'comparison', label: '对比研究' },
  { value: 'explainer', label: '解释型' },
  { value: 'analysis', label: '影响分析' },
]

const STRATEGY_OPTIONS: { value: ResearchSourceStrategy; label: string }[] = [
  { value: 'knowledge', label: '内部知识' },
  { value: 'web', label: '公开网络' },
  { value: 'hybrid', label: '混合研究' },
]

type CreateError = { code: string; message: string; retryable: boolean }

function extractError(err: unknown): CreateError {
  const axiosErr = err as {
    response?: {
      status?: number
      data?: { error?: { error_code?: string; message?: string; retryable?: boolean } }
    }
  }
  const envelope = axiosErr?.response?.data?.error
  return {
    code: envelope?.error_code ?? 'UNKNOWN',
    message: envelope?.message ?? '创建研究失败，请稍后重试。',
    retryable: envelope?.retryable === true || axiosErr?.response?.status === 429,
  }
}

/**
 * 创建深度研究（FRONTEND §5.7 / UIDESIGN §5.6：Route Surface，表单主列 + Context Rail）。
 *
 * - 研究主题 + 研究类型（comparison/explainer/analysis）+ 来源策略（knowledge/web/hybrid）；
 *   knowledge/hybrid 必须选择至少一个知识库，web 不携带内部知识库；
 * - `ResearchTaskCreate` 为 additionalProperties:false，只发送契约字段（无预算/期望输出）；
 * - `Idempotency-Key` 用 useRef 缓存：重试复用同 Key 同载荷命中服务端幂等，成功后重置；
 * - 429（并发/队列上限）展示限制 + 「前往任务列表」替代入口（FRONTEND §9.2）；
 * - 不展示「预计 X 分钟」（禁止虚构，deadline 由服务端推导）。
 */
export function ResearchCreatePage({ api = researchApi }: { api?: ResearchApi }) {
  const navigate = useNavigate()
  const [topic, setTopic] = useState('')
  const [taskType, setTaskType] =
    useState<ResearchTaskCreate['requirements']['task_type']>('comparison')
  const [strategy, setStrategy] = useState<ResearchSourceStrategy>('hybrid')
  const [selectedKbs, setSelectedKbs] = useState<KnowledgeBase[]>([])
  const [topicError, setTopicError] = useState<string | null>(null)
  const [kbError, setKbError] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<CreateError | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const idempotencyRef = useRef<string | null>(null)

  const needsKb = strategy === 'knowledge' || strategy === 'hybrid'

  function getOrCreateIdempotencyKey(): string {
    if (!idempotencyRef.current) {
      idempotencyRef.current = crypto.randomUUID()
    }
    return idempotencyRef.current
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setTopicError(null)
    setKbError(null)
    setSubmitError(null)

    const trimmedTopic = topic.trim()
    if (!trimmedTopic) {
      setTopicError('请输入研究主题')
      return
    }
    if (needsKb && selectedKbs.length === 0) {
      setKbError('请至少选择一个知识库')
      return
    }

    const key = getOrCreateIdempotencyKey()
    setSubmitting(true)
    try {
      const result = await api.createResearchTask(
        {
          topic: trimmedTopic,
          requirements: { task_type: taskType, depth: 'quick', max_sources: 10, language: 'zh' },
          source_strategy: strategy,
          knowledge_base_ids: selectedKbs.map((kb) => kb.uuid),
        },
        key,
      )
      idempotencyRef.current = null // 成功创建后重置，下一轮新 Key
      // 任务 DTO（ResearchTask/State）不含 source_strategy 与 requirements，研究类型/
      // 来源策略/知识库通过导航 state 临时传递，刷新后信息栏降级为只显示 API 字段（待裁决记录）
      navigate(`/research/${result.task_id}`, {
        state: {
          kbNames: selectedKbs.map((kb) => kb.name),
          taskType,
          strategy,
        },
      })
    } catch (err) {
      setSubmitError(extractError(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="route-surface research-create">
      <header className="page-heading">
        <div>
          <p className="eyebrow">研究</p>
          <h1>创建研究</h1>
          <span>定义研究主题、类型与来源范围，提交后任务在后台独立运行。</span>
        </div>
        <Link to="/research" className="btn btn--ghost">
          查看研究任务 →
        </Link>
      </header>

      <div className="research-create-grid">
        <form className="research-brief" onSubmit={handleSubmit}>
          <label className="research-field">
            <span>研究主题</span>
            <textarea
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              placeholder="例如：对比三家主流 AI Agent 平台的企业级落地路径…"
              rows={5}
              maxLength={500}
            />
            {topicError ? (
              <p className="research-error research-error--field" role="alert">
                {topicError}
              </p>
            ) : null}
          </label>

          <div className="brief-row">
            <div className="research-field">
              <span>研究类型</span>
              <div className="segmented" role="group" aria-label="研究类型">
                {TASK_TYPE_OPTIONS.map(({ value, label }) => (
                  <button
                    key={value}
                    type="button"
                    className={value === taskType ? 'active' : ''}
                    aria-pressed={value === taskType}
                    onClick={() => setTaskType(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <div className="research-field">
              <span>来源策略</span>
              <div className="segmented research-strategy" role="group" aria-label="来源策略">
                {STRATEGY_OPTIONS.map(({ value, label }) => (
                  <button
                    key={value}
                    type="button"
                    className={value === strategy ? 'active' : ''}
                    aria-pressed={value === strategy}
                    onClick={() => setStrategy(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {needsKb ? (
            <div className="research-field">
              <span>内部知识范围</span>
              <ResearchKbPicker value={selectedKbs} onChange={setSelectedKbs} />
              {kbError ? (
                <p className="research-error research-error--field" role="alert">
                  {kbError}
                </p>
              ) : null}
            </div>
          ) : null}

          {submitError ? (
            <div className="research-error" role="alert">
              <p>{submitError.message}</p>
              {submitError.retryable ? (
                <Link to="/research" className="research-error__action">
                  前往任务列表
                </Link>
              ) : null}
            </div>
          ) : null}

          <footer className="research-brief__footer">
            <p>任务创建后可离开页面，研究在后台持续运行。</p>
            <Button type="submit" variant="primary" busy={submitting} busyLabel="正在启动…">
              启动深度研究
            </Button>
          </footer>
        </form>

        <aside className="research-principles">
          <p className="eyebrow">研究约定</p>
          <ol>
            <li>
              <span>01</span>
              <div>
                <b>范围明确</b>
                <p>混合与内部研究必须选择当前可读知识库。</p>
              </div>
            </li>
            <li>
              <span>02</span>
              <div>
                <b>过程可见</b>
                <p>展示阶段、动作与结果，不展示隐藏思维链。</p>
              </div>
            </li>
            <li>
              <span>03</span>
              <div>
                <b>结论有据</b>
                <p>关键判断必须关联当前仍可访问的来源。</p>
              </div>
            </li>
          </ol>
        </aside>
      </div>
    </main>
  )
}
