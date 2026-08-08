import { Link } from 'react-router-dom'

import { EmptyState } from '@/components/feedback/EmptyState'

type RecentItem = { id: string; title: string }

export function WorkbenchPage({
  recentResearch = [],
  recentKnowledge = [],
}: {
  recentResearch?: RecentItem[]
  recentKnowledge?: RecentItem[]
}) {
  return (
    <main className="workbench">
      <header className="page-heading">
        <div>
          <p>Workspace overview</p>
          <h1>工作台</h1>
          <span>从问题出发，回到可以复核的证据。</span>
        </div>
      </header>
      <section className="workbench__actions" aria-label="快速开始">
        <Link to="/chat">
          <strong>快速提问</strong>
          <span>在一个知识库范围内获得带来源的回答</span>
        </Link>
        <Link to="/research/new">
          <strong>深度研究</strong>
          <span>选择内部、外部或混合来源并持续追踪进度</span>
        </Link>
      </section>
      <div className="workbench__columns">
        <section>
          <h2>RECENT RESEARCH</h2>
          {recentResearch.length ? (
            <ul>{recentResearch.map((item) => <li key={item.id}>{item.title}</li>)}</ul>
          ) : (
            <EmptyState
              title="还没有研究任务"
              description="明确研究范围，系统会持续保存任务事实。"
              action={<Link to="/research/new">开始研究</Link>}
            />
          )}
        </section>
        <section>
          <h2>RECENT KNOWLEDGE</h2>
          {recentKnowledge.length ? (
            <ul>{recentKnowledge.map((item) => <li key={item.id}>{item.title}</li>)}</ul>
          ) : (
            <EmptyState
              title="还没有知识库"
              description="先导入可治理的材料，再开始问答或研究。"
              action={<Link to="/knowledge-bases?create=1">创建知识库</Link>}
            />
          )}
        </section>
      </div>
    </main>
  )
}
