import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type CSSProperties } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { EmptyState } from '@/components/feedback/EmptyState'
import { ErrorState } from '@/components/feedback/ErrorState'
import { Pagination } from '@/components/feedback/Pagination'
import { Skeleton } from '@/components/feedback/Skeleton'
import { StatusBadge } from '@/components/feedback/StatusBadge'
import { ConfirmDialog } from '@/components/feedback/ConfirmDialog'
import { useAppToast } from '@/components/feedback/toastContext'
import { RowMenu } from '@/components/overlay/RowMenu'
import {
  researchApi,
  type ResearchApi,
  type ResearchTaskListItem,
  type ResearchTaskStatus,
} from '@/api/research'
import { formatTimestamp } from '@/features/knowledge/format'
import {
  RESEARCH_STATUS_LABELS,
  RESEARCH_STATUS_TONES,
  RESEARCH_STRATEGY_LABELS,
  RESEARCH_TASK_TYPE_LABELS,
} from '@/features/research/researchPhases'

const PAGE_SIZE = 10

const STATUS_TABS: { value: string; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'running', label: '进行中' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '异常' },
]

const TERMINAL_STATUSES: ReadonlySet<ResearchTaskStatus> = new Set([
  'completed',
  'failed',
  'canceled',
  'partially_completed',
])

function continueTarget(item: ResearchTaskListItem): { to: string; label: string } {
  // 正在运行的任务提供「进入研究现场」，不得重新创建任务
  if (item.status === 'running') return { to: `/research/${item.task_id}`, label: '进入现场' }
  if ((item.status === 'completed' || item.status === 'partially_completed') && item.report_id) {
    return { to: `/reports/${item.report_id}`, label: '查看报告' }
  }
  return { to: `/research/${item.task_id}`, label: '查看' }
}

/**
 * 研究任务列表（FRONTEND §5.8 / UIDESIGN §5.6：Route Surface，筛选工具栏 + Ledger）。
 *
 * - 状态标签（全部/进行中/已完成/异常）与关键词搜索走后端 `status`/`keyword` 参数；
 *   来源策略筛选后端暂无 `source_strategy` 参数，本轮不做（负责人 2026-08-12 裁决，待裁决记录）；
 * - 行操作：运行中「进入现场」、已完成且含报告「查看报告」、其余「查看」；
 *   `recoverable` 不在列表 DTO，可恢复任务的「继续任务」由运行态页提供（待裁决记录）；
 * - 删除只允许终态任务（运行中不可删除），具名确认后从缓存剔除 + 页码回退 + 全局反馈；
 * - 不虚构数量/耗时（列表 DTO 无这些字段）。
 */
export function ResearchTaskListPage({ api = researchApi }: { api?: ResearchApi }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const { show } = useAppToast()
  const queryClient = useQueryClient()
  const [deletingTarget, setDeletingTarget] = useState<ResearchTaskListItem | null>(null)

  const statusParam = searchParams.get('status') ?? ''
  const keyword = searchParams.get('keyword') ?? ''
  const page = Math.max(1, Number(searchParams.get('page') ?? '1'))

  const listQuery = useQuery({
    queryKey: ['research-tasks', statusParam, keyword, page],
    queryFn: () =>
      api.listResearchTasks({
        status: statusParam ? (statusParam as ResearchTaskStatus) : undefined,
        keyword: keyword || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
  })

  function setFilter(changes: Record<string, string | undefined>) {
    const next = new URLSearchParams(searchParams)
    for (const [key, value] of Object.entries(changes)) {
      if (value === undefined || value === '') {
        next.delete(key)
      } else {
        next.set(key, value)
      }
    }
    setSearchParams(next)
  }

  const deleteMutation = useMutation({
    mutationFn: (target: ResearchTaskListItem) => api.deleteResearchTask(target.task_id),
    onSuccess: (_data, target) => {
      // 从列表缓存就地剔除该行（与后端删除一致，不假装成功）
      queryClient.setQueriesData<{ items: { task_id: string }[] }>(
        { queryKey: ['research-tasks'] },
        (old) =>
          old
            ? { ...old, items: old.items.filter((item) => item.task_id !== target.task_id) }
            : old,
      )
      // 删除当前页最后一项且 page>1 时回退页码，避免停留在空页
      if (page > 1 && (listQuery.data?.items.length ?? 0) === 1) {
        setFilter({ page: undefined })
      }
      void queryClient.invalidateQueries({ queryKey: ['research-tasks'] })
      setDeletingTarget(null)
      show(`已删除研究任务「${target.topic}」`)
    },
  })

  const items = listQuery.data?.items ?? []
  const isFiltered = keyword !== ''

  return (
    <main className="route-surface research-tasks-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">研究任务</p>
          <h1>研究任务</h1>
          <span>查看运行状态、继续研究现场，或管理已经结束的任务。</span>
        </div>
        <Link to="/research/new" className="btn btn--primary">
          新建研究
        </Link>
      </header>

      <div className="list-toolbar" role="toolbar" aria-label="研究任务筛选">
        <div className="segmented" role="group" aria-label="任务状态">
          {STATUS_TABS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              className={value === statusParam ? 'active' : ''}
              onClick={() => setFilter({ status: value || undefined, page: undefined })}
            >
              {label}
            </button>
          ))}
        </div>
        <form
          role="search"
          aria-label="搜索研究主题"
          className="search-form"
          onSubmit={(event) => {
            event.preventDefault()
            const formData = new FormData(event.currentTarget)
            setFilter({
              keyword: String(formData.get('q') ?? '').trim() || undefined,
              page: undefined,
            })
          }}
        >
          <input
            type="search"
            name="q"
            aria-label="搜索研究主题"
            placeholder="搜索研究主题"
            defaultValue={keyword}
          />
        </form>
      </div>

      <div className="ledger research-ledger">
        <div className="ledger__head" aria-hidden="true">
          <span>研究任务</span>
          <span>来源</span>
          <span>状态</span>
          <span>最近更新</span>
          <span>操作</span>
        </div>
        {listQuery.isPending ? (
          <div className="ledger__body">
            <Skeleton rows={5} />
          </div>
        ) : listQuery.isError ? (
          <div className="ledger__body">
            <ErrorState onRetry={() => void listQuery.refetch()} />
          </div>
        ) : items.length === 0 ? (
          <div className="ledger__body">
            <EmptyState
              title={isFiltered ? '没有匹配的研究任务' : '还没有研究任务'}
              description={
                isFiltered
                  ? '换个关键词，或切到「全部」状态查看。'
                  : '创建一项深度研究，任务会在后台独立运行并生成报告。'
              }
              action={
                !isFiltered ? (
                  <Link to="/research/new" className="btn btn--primary">
                    新建研究
                  </Link>
                ) : undefined
              }
            />
          </div>
        ) : (
          <ul className="ledger__body">
            {items.map((item) => {
              const target = continueTarget(item)
              const progress = Math.round(item.progress * 100)
              return (
                <li className="ledger__row" key={item.task_id}>
                  <div className="ledger__cell ledger__cell--task">
                    <b className="ledger__title">{item.topic}</b>
                    <small className="ledger__desc">
                      {RESEARCH_TASK_TYPE_LABELS[item.task_type] ?? item.task_type}
                    </small>
                  </div>
                  <div className="ledger__cell ledger__cell--source">
                    <em className={`channel channel--${item.source_strategy}`}>
                      {RESEARCH_STRATEGY_LABELS[item.source_strategy]}
                    </em>
                  </div>
                  <div className="ledger__cell ledger__cell--status">
                    <StatusBadge tone={RESEARCH_STATUS_TONES[item.status]}>
                      {RESEARCH_STATUS_LABELS[item.status]}
                    </StatusBadge>
                    {item.status === 'running' ? (
                      <span className="row-progress" aria-label={`进度 ${progress}%`}>
                        <i style={{ '--progress': `${progress}%` } as CSSProperties} />
                        <em>{progress}%</em>
                      </span>
                    ) : null}
                  </div>
                  <div className="ledger__cell ledger__cell--updated">
                    <b>{formatTimestamp(item.created_at)}</b>
                  </div>
                  <div className="ledger__cell ledger__cell--actions">
                    <Link to={target.to} className="btn">
                      {target.label}
                    </Link>
                    {TERMINAL_STATUSES.has(item.status) ? (
                      <RowMenu
                        label={`研究任务操作 ${item.topic}`}
                        actions={[
                          {
                            label: '删除研究任务',
                            danger: true,
                            onSelect: () => setDeletingTarget(item),
                          },
                        ]}
                      />
                    ) : null}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      <Pagination
        page={page}
        total={listQuery.data?.total ?? 0}
        pageSize={PAGE_SIZE}
        disabled={listQuery.isPending}
        onPageChange={(next) => setFilter({ page: next === 1 ? undefined : String(next) })}
      />

      <p className="ledger-footnote">
        <span>说明</span>
        运行中的任务可在研究现场取消，但不能直接删除；已结束任务可删除，报告内容保持不可变。
      </p>

      {deletingTarget ? (
        <ConfirmDialog
          title="删除研究任务"
          description={`确定删除研究任务「${deletingTarget.topic}」？删除后无法恢复。`}
          confirmLabel="确认删除"
          tone="danger"
          pending={deleteMutation.isPending}
          busyLabel="正在删除…"
          onCancel={() => setDeletingTarget(null)}
          onConfirm={() => deleteMutation.mutate(deletingTarget)}
        />
      ) : null}
    </main>
  )
}
