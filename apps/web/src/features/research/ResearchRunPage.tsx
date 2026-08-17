import { useMutation } from '@tanstack/react-query'
import { useState, type CSSProperties } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'

import { researchApi } from '@/api/research'
import type { ResearchTaskStatus } from '@/api/research'
import { Button } from '@/components/actions/Button'
import { ConfirmDialog } from '@/components/feedback/ConfirmDialog'
import { ErrorState } from '@/components/feedback/ErrorState'
import { Skeleton } from '@/components/feedback/Skeleton'
import { StatusBadge } from '@/components/feedback/StatusBadge'
import { useAppToast } from '@/components/feedback/toastContext'
import {
  RESEARCH_STATUS_LABELS,
  RESEARCH_STATUS_TONES,
  RESEARCH_STRATEGY_NAMES,
  RESEARCH_TASK_TYPE_LABELS,
  RESEARCH_PHASE_ORDER,
  researchPhaseLabel,
} from '@/features/research/researchPhases'
import { useResearchSse } from '@/features/research/useResearchSse'

const TERMINAL_STATUSES: ReadonlySet<ResearchTaskStatus> = new Set([
  'completed',
  'failed',
  'canceled',
  'partially_completed',
])

function isTerminal(status: ResearchTaskStatus | null | undefined): boolean {
  return status != null && TERMINAL_STATUSES.has(status)
}

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

function elapsedLabel(
  startedAt: string | null,
  createdAt: string,
  now: Date,
  terminal: boolean,
  completedAt: string | null,
): string {
  // 终态取 completed_at → started_at 的实际耗时，不随当前时间增长；
  // 非终态按 started_at → 当前时刻显示「已运行」。
  const from = startedAt ? new Date(startedAt).getTime() : new Date(createdAt).getTime()
  const to = terminal && completedAt ? new Date(completedAt).getTime() : now.getTime()
  const diff = Math.max(0, to - from)
  const minutes = Math.floor(diff / 60_000)
  const seconds = Math.floor((diff % 60_000) / 1000)
  const prefix = terminal ? '运行' : '已运行'
  return minutes >= 1 ? `${prefix} ${minutes} 分 ${pad(seconds)} 秒` : `${prefix} ${seconds} 秒`
}

function clock(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function phaseState(phase: string, current: string | null): 'done' | 'active' | 'pending' {
  if (phase === current) return 'active'
  if (!current) return 'pending'
  const currentIndex = RESEARCH_PHASE_ORDER.indexOf(
    current as (typeof RESEARCH_PHASE_ORDER)[number],
  )
  if (currentIndex === -1) return 'pending'
  return RESEARCH_PHASE_ORDER.indexOf(phase as (typeof RESEARCH_PHASE_ORDER)[number]) < currentIndex
    ? 'done'
    : 'pending'
}

/**
 * 研究运行态（FRONTEND §5.9 / UIDESIGN §5.6：Route Surface，执行主列 + Context Rail）。
 *
 * - 数据流：先 GET /state 取持久快照（LoadingSnapshot → Subscribing），再订阅 Research SSE
 *   （Subscribing → Live）；断线 Reconnecting 自动重连带 Last-Event-ID；终态以快照为准（FRONTEND §8）；
 * - 只展示可公开的动作摘要/数量/耗时/重试/降级，不展示模型隐藏推理（事件流不渲染
 *   step.updated 的 arguments/observation/output 原始内容）；
 * - 取消是「请求」：具名确认 → POST cancel，任务在后台持续运行；
 * - 信息栏只显示 API 字段（当前证据）+ 创建表单经导航 state 临时传入的
 *   研究类型/来源策略/知识库（刷新后降级，待裁决记录）；预算不展示（服务端推导、DTO 未暴露）。
 */
export function ResearchRunPage() {
  const { taskId } = useParams<{ taskId: string }>()
  const location = useLocation()
  const { show } = useAppToast()
  const navState = location.state as {
    kbNames?: string[]
    taskType?: string
    strategy?: string
  } | null
  const { snapshot, retry } = useResearchSse(taskId)
  const [cancelOpen, setCancelOpen] = useState(false)

  const task = snapshot.task
  const topic = task?.topic ?? ''
  const now = new Date()

  const cancelMutation = useMutation({
    mutationFn: () => researchApi.cancelResearchTask(taskId ?? ''),
    onSuccess: () => {
      setCancelOpen(false)
      show('已请求取消研究任务')
    },
  })

  const resumeMutation = useMutation({
    mutationFn: () => researchApi.resumeResearchTask(taskId ?? ''),
    onSuccess: () => {
      show('已继续研究任务')
      retry() // 恢复后任务回到运行态，重新拉快照并订阅 SSE
    },
  })

  const terminal = isTerminal(task?.status)
  const recoverable = task?.status === 'failed' && task.error?.recoverable === true

  let connectionLabel: string | null = null
  if (snapshot.phase === 'live') connectionLabel = '实时连接正常'
  else if (snapshot.phase === 'reconnecting') connectionLabel = '正在重连…'
  else if (snapshot.phase === 'subscribing' || snapshot.phase === 'loadingSnapshot')
    connectionLabel = '连接中…'
  else if (snapshot.phase === 'subscriptionEnded') connectionLabel = '等待重连…'

  return (
    <main className="route-surface research-run">
      <header className="research-header">
        <div className="research-header__main">
          <Link to="/research" className="back-link">
            ← 研究任务
          </Link>
          <p className="eyebrow">研究任务</p>
          <h1>{topic || '…'}</h1>
          {!terminal ? <p>任务在后台持续运行，关闭页面不会中止研究。</p> : null}
        </div>
        <div className="research-actions">
          {terminal ? (
            <StatusBadge tone={RESEARCH_STATUS_TONES[task?.status ?? 'pending']}>
              {RESEARCH_STATUS_LABELS[task?.status ?? 'pending']}
            </StatusBadge>
          ) : null}
          {recoverable ? (
            <Button
              variant="primary"
              busy={resumeMutation.isPending}
              busyLabel="正在继续…"
              onClick={() => resumeMutation.mutate()}
            >
              继续任务
            </Button>
          ) : null}
          {!terminal && !snapshot.cancelRequested ? (
            <Button
              variant="ghost"
              className="btn--danger-ghost"
              onClick={() => setCancelOpen(true)}
            >
              取消任务
            </Button>
          ) : null}
          {snapshot.cancelRequested ? <span className="research-canceled">已请求取消</span> : null}
          {connectionLabel ? (
            <span
              className={`research-connection${
                snapshot.phase === 'reconnecting' ? ' research-connection--reconnecting' : ''
              }`}
            >
              <span />
              {connectionLabel}
            </span>
          ) : null}
        </div>
      </header>

      {snapshot.phase === 'loadingSnapshot' && !task ? (
        snapshot.error ? (
          <ErrorState onRetry={retry} />
        ) : (
          <div className="research-run__loading">
            <Skeleton rows={4} />
          </div>
        )
      ) : task ? (
        <>
          <section className="overall-progress" aria-label="整体进度">
            <div>
              <span>整体进度</span>
              <b>{Math.round(task.progress.progress * 100)}%</b>
            </div>
            <i>
              <em
                style={
                  { '--progress': `${Math.round(task.progress.progress * 100)}%` } as CSSProperties
                }
              />
            </i>
            <small>
              已完成 {task.progress.completed_steps}/{task.progress.total_steps} 步 ·{' '}
              {elapsedLabel(task.started_at, task.created_at, now, terminal, task.completed_at)}
            </small>
          </section>

          <div className="research-layout">
            <div className="execution-column">
              <ol className="pipeline" aria-label="研究阶段">
                {RESEARCH_PHASE_ORDER.map((phase, index) => (
                  <li key={phase} className={phaseState(phase, task.current_phase)}>
                    <span>{pad(index + 1)}</span>
                    <b>{researchPhaseLabel(phase)}</b>
                  </li>
                ))}
              </ol>

              <section className="activity-stream">
                <header>
                  <p className="eyebrow">事件流</p>
                </header>
                {snapshot.timeline.length === 0 ? (
                  <p className="activity-stream__empty">等待事件…</p>
                ) : (
                  <div className="activity-stream__list">
                    {snapshot.timeline.map((item, index) => (
                      <div
                        className={`event event--${item.kind}`}
                        key={item.eventId !== null ? item.eventId : `event-${index}`}
                      >
                        <time>{clock(item.timestamp)}</time>
                        <i aria-hidden="true" />
                        <div>
                          <b>{item.title}</b>
                          {item.detail ? <p>{item.detail}</p> : null}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </div>

            <aside className="task-context">
              <p className="eyebrow">任务信息</p>
              <dl>
                {navState?.taskType ? (
                  <div>
                    <dt>研究类型</dt>
                    <dd>{RESEARCH_TASK_TYPE_LABELS[navState.taskType] ?? navState.taskType}</dd>
                  </div>
                ) : null}
                {navState?.strategy ? (
                  <div>
                    <dt>来源策略</dt>
                    <dd>
                      {RESEARCH_STRATEGY_NAMES[
                        navState.strategy as keyof typeof RESEARCH_STRATEGY_NAMES
                      ] ?? navState.strategy}
                    </dd>
                  </div>
                ) : null}
                {navState?.kbNames && navState.kbNames.length > 0 ? (
                  <div>
                    <dt>知识库</dt>
                    <dd>
                      {navState.kbNames.map((name) => (
                        <span className="task-context__kb" key={name}>
                          {name}
                        </span>
                      ))}
                    </dd>
                  </div>
                ) : null}
                <div>
                  <dt>当前证据</dt>
                  <dd>{task.stats.total_evidence} 项</dd>
                </div>
              </dl>
              <p className="privacy-note">只显示动作和结果，不展示模型隐藏思维链。</p>
            </aside>
          </div>

          {task.status === 'failed' && task.error ? (
            <p className="research-error research-run__failure" role="alert">
              {task.error.error_message}
            </p>
          ) : null}

          {terminal && task.report_id ? (
            <div className="research-run__report">
              <Link to={`/reports/${task.report_id}`} className="btn btn--primary">
                查看报告
              </Link>
            </div>
          ) : null}
        </>
      ) : null}

      {cancelOpen ? (
        <ConfirmDialog
          title="取消研究任务"
          description={`确定取消研究任务「${topic}」？已完成的业务结果不会丢失。`}
          confirmLabel="确认取消"
          tone="danger"
          pending={cancelMutation.isPending}
          busyLabel="正在取消…"
          onCancel={() => setCancelOpen(false)}
          onConfirm={() => cancelMutation.mutate()}
        />
      ) : null}
    </main>
  )
}
