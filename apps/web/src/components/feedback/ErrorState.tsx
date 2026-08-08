export function ErrorState({ requestId, onRetry }: { requestId?: string; onRetry?: () => void }) {
  return (
    <section className="error-state" role="alert">
      <h2>暂时无法加载</h2>
      <p>内容仍然安全保留，请稍后重试。</p>
      {requestId ? <small>请求 ID：{requestId}</small> : null}
      {onRetry ? (
        <button type="button" onClick={onRetry}>
          重试
        </button>
      ) : null}
    </section>
  )
}
