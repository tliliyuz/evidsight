import { useQuery } from '@tanstack/react-query'
import { useSyncExternalStore, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'

import { knowledgeApi, type KnowledgeApi } from '@/api/knowledge'
import {
  researchApi,
  type ResearchApi,
  type ResearchTaskListItem,
  type ResearchTaskStatus,
} from '@/api/research'
import { EmptyState } from '@/components/feedback/EmptyState'
import { ErrorState } from '@/components/feedback/ErrorState'
import { Skeleton } from '@/components/feedback/Skeleton'
import { StatusBadge, type BadgeTone } from '@/components/feedback/StatusBadge'
import { authSession } from '@/features/auth/authSession'

export type WorkbenchApi = {
  listResearchTasks: ResearchApi['listResearchTasks']
  listKnowledgeBases: KnowledgeApi['listKnowledgeBases']
}

const defaultApi: WorkbenchApi = {
  listResearchTasks: researchApi.listResearchTasks,
  listKnowledgeBases: knowledgeApi.listKnowledgeBases,
}

const STATUS_LABELS: Record<ResearchTaskStatus, string> = {
  pending: '排队中',
  running: '进行中',
  completed: '已完成',
  partially_completed: '部分完成',
  failed: '运行失败',
  canceled: '已取消',
  paused: '已暂停',
}

const STATUS_TONES: Record<ResearchTaskStatus, BadgeTone> = {
  pending: 'neutral',
  running: 'processing',
  completed: 'success',
  partially_completed: 'warning',
  failed: 'danger',
  canceled: 'neutral',
  paused: 'warning',
}

const CHANNEL_LABELS: Record<ResearchTaskListItem['source_strategy'], string> = {
  knowledge: '内部',
  web: '公开',
  hybrid: '混合',
}

function greeting(hour: number): string {
  if (hour < 6) return '凌晨好'
  if (hour < 12) return '早上好'
  if (hour < 18) return '下午好'
  return '晚上好'
}

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

function relativeTime(iso: string | null, now: Date): string {
  if (!iso) return '刚刚'
  const diff = now.getTime() - new Date(iso).getTime()
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  return `${Math.floor(diff / 86_400_000)} 天前`
}

function continueTarget(item: ResearchTaskListItem): { to: string; label: string } {
  // 正在运行的任务提供「进入研究现场」，不得重新创建任务
  if (item.status === 'running') return { to: `/research/${item.task_id}`, label: '进入现场' }
  if ((item.status === 'completed' || item.status === 'partially_completed') && item.report_id) {
    return { to: `/reports/${item.report_id}`, label: '查看报告' }
  }
  return { to: `/research/${item.task_id}`, label: '查看' }
}

/**
 * 工作台（FRONTEND §5.2 / UIDESIGN §7.1）。
 *
 * 行动入口而非统计仪表盘：Launcher 主区 + 主列/右侧上下文列；RECENT RESEARCH
 * 使用连续 Hairline 列表展示来源类型/状态/进度/继续入口；RECENT KNOWLEDGE 放入
 * 右侧紧凑列表；正在运行的任务只提供「进入研究现场」，不重新创建任务。
 * 全部数据来自真实 API（/api/v1/research/tasks 与 /api/v1/knowledge-bases），
 * 不使用虚构 KPI、虚构任务或原型 Mock 数据填充页面。
 */
export function WorkbenchPage({ api = defaultApi }: { api?: WorkbenchApi }) {
  const auth = useSyncExternalStore(authSession.subscribe, authSession.getSnapshot)
  const username = auth.user?.username ?? ''
  const now = new Date()

  const researchQuery = useQuery({
    queryKey: ['workbench', 'research'],
    queryFn: () => api.listResearchTasks({ page: 1, page_size: 5 }),
  })
  const runningQuery = useQuery({
    queryKey: ['workbench', 'research', 'running'],
    queryFn: () => api.listResearchTasks({ status: 'running', page: 1, page_size: 1 }),
  })
  const knowledgeQuery = useQuery({
    queryKey: ['workbench', 'knowledge'],
    queryFn: () => api.listKnowledgeBases({ scope: 'all', page: 1, page_size: 5 }),
  })

  const research = researchQuery.data?.items ?? []
  const knowledge = knowledgeQuery.data?.items ?? []
  const runningTask = runningQuery.data?.items[0] ?? null

  return (
    <main className="workbench route-surface">
      <header className="page-heading workbench__heading">
        <div>
          <p className="eyebrow">
            工作台 · {pad(now.getMonth() + 1)}/{pad(now.getDate())}
          </p>
          <h1>
            {greeting(now.getHours())}，{username || '朋友'}
          </h1>
          <span>从一个问题开始，或继续正在形成的结论。</span>
        </div>
        <span className="workbench__updated">
          今天 {pad(now.getHours())}:{pad(now.getMinutes())} 更新
        </span>
      </header>

      <div className="workbench-grid">
        <div className="workbench__primary">
          <section className="workbench-launcher" aria-label="快速开始">
            <p className="eyebrow">开始</p>
            <h2>今天要看清什么？</h2>
            <p>快速询问已有知识，或启动一项可恢复、可追踪的深度研究。</p>
            <div className="workbench-launcher__actions">
              <Link to="/chat">
                <span className="launcher-card__copy">
                  <small>快速提问</small>
                  <b>向企业知识提问</b>
                </span>
                <span className="launcher-card__action">进入问答 →</span>
              </Link>
              <Link to="/research/new">
                <span className="launcher-card__copy">
                  <small>深度研究</small>
                  <b>发起新的研究任务</b>
                </span>
                <span className="launcher-card__action">定义范围 →</span>
              </Link>
            </div>
          </section>

          <section className="recent-section" aria-label="最近研究">
            <header className="recent-section__header">
              <p className="eyebrow">最近研究</p>
              <Link to="/research">查看全部</Link>
            </header>
            {researchQuery.isPending ? (
              <Skeleton />
            ) : researchQuery.isError ? (
              <ErrorState onRetry={() => void researchQuery.refetch()} />
            ) : research.length === 0 ? (
              <EmptyState
                title="还没有研究任务"
                description="明确研究范围，系统会持续保存任务事实。"
                actionAlign="beside"
                action={
                  <Link to="/research/new" className="btn btn--primary">
                    开始研究
                  </Link>
                }
              />
            ) : (
              <ol className="task-list">
                {research.map((item) => {
                  const target = continueTarget(item)
                  const progress = Math.round(item.progress * 100)
                  return (
                    <li key={item.task_id} className="task-row">
                      <span className={`channel channel--${item.source_strategy}`}>
                        {CHANNEL_LABELS[item.source_strategy] ?? item.source_strategy}
                      </span>
                      <span className="task-copy">
                        <b>{item.topic}</b>
                        <small>
                          {STATUS_LABELS[item.status]} ·{' '}
                          {relativeTime(item.completed_at ?? item.created_at, now)} 更新
                        </small>
                      </span>
                      {item.status === 'running' ? (
                        <span className="row-progress" aria-label={`进度 ${progress}%`}>
                          <i style={{ '--progress': `${progress}%` } as CSSProperties} />
                          <em>{progress}%</em>
                        </span>
                      ) : (
                        <StatusBadge tone={STATUS_TONES[item.status]}>
                          {STATUS_LABELS[item.status]}
                        </StatusBadge>
                      )}
                      <Link className="row-cta" to={target.to}>
                        {target.label}
                      </Link>
                    </li>
                  )
                })}
              </ol>
            )}
          </section>
        </div>

        <aside className="workbench__context">
          {/* 进行中的研究卡片始终渲染：RECENT KNOWLEDGE 固定在卡片下方，无运行任务时显示占位 */}
          <section className="active-mission" aria-label="进行中的研究">
            {runningTask ? (
              <>
                <p className="eyebrow">
                  进行中的研究 <span className="live-dot" aria-hidden="true" />
                </p>
                <h3>{runningTask.topic}</h3>
                <p>
                  {STATUS_LABELS[runningTask.status]} · {Math.round(runningTask.progress * 100)}%
                </p>
                <div className="thin-progress">
                  <i
                    style={
                      {
                        '--progress': `${Math.round(runningTask.progress * 100)}%`,
                      } as CSSProperties
                    }
                  />
                </div>
                <Link to={`/research/${runningTask.task_id}`}>进入研究现场 →</Link>
              </>
            ) : (
              <>
                <p className="eyebrow">进行中的研究</p>
                <p>暂无进行中的研究。从一个问题开始，或继续最近的研究。</p>
                <Link to="/research/new">开始研究 →</Link>
              </>
            )}
          </section>

          <section className="knowledge-quick" aria-label="最近知识库">
            <header className="recent-section__header">
              <p className="eyebrow">最近知识库</p>
              <Link to="/knowledge-bases">查看全部</Link>
            </header>
            {knowledgeQuery.isPending ? (
              <Skeleton />
            ) : knowledgeQuery.isError ? (
              <ErrorState onRetry={() => void knowledgeQuery.refetch()} />
            ) : knowledge.length === 0 ? (
              <EmptyState
                title="还没有知识库"
                description="先导入可治理的材料，再开始问答或研究。"
                action={
                  <Link to="/knowledge-bases?create=1" className="btn btn--primary">
                    创建知识库
                  </Link>
                }
              />
            ) : (
              <ul className="knowledge-quick__list">
                {knowledge.map((item) => (
                  <li key={item.uuid}>
                    <Link to={`/knowledge-bases/${item.uuid}`}>
                      <b>{item.name}</b>
                      <small>
                        {item.doc_count} 个文档 · {relativeTime(item.updated_at, now)} 更新
                      </small>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </aside>
      </div>
    </main>
  )
}
