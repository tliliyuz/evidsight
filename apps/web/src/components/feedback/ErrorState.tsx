/**
 * 错误态（UIDESIGN §6 反馈）。与空态 EmptyState 结构同构：三级标题 + 说明文案 + 主按钮动作，
 * `.error-state` 与 `.empty-state` 共享居中布局（global.css），保证「空知识库/空文档/空对话」
 * 与「暂时无法加载」视觉一致；`requestId` 为安全错误 ID，不暴露堆栈或内部路径。
 */
export function ErrorState({ requestId, onRetry }: { requestId?: string; onRetry?: () => void }) {
  return (
    <section className="error-state" role="alert">
      <h3>暂时无法加载</h3>
      <p>内容仍然安全保留，请稍后重试。</p>
      {requestId ? <small>请求 ID：{requestId}</small> : null}
      {onRetry ? (
        <button type="button" className="btn btn--primary" onClick={onRetry}>
          重试
        </button>
      ) : null}
    </section>
  )
}
