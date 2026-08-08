export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="skeleton" aria-label="正在加载" aria-busy="true">
      {Array.from({ length: rows }, (_, index) => (
        <span key={index} />
      ))}
    </div>
  )
}
