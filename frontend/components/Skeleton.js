// Plassholdere som vises mens data lastes. De har omtrent samme form som
// innholdet som kommer, så siden ikke hopper når dataene er på plass.

export function TableSkeleton({ rows = 8, cols = 6, label = 'Laster...' }) {
  return (
    <div className="skeleton-table" role="status" aria-label={label} style={{ '--cols': cols - 1 }}>
      <div className="skeleton-row skeleton-head">
        {Array.from({ length: cols }, (_, c) => <span key={c} className="skeleton skeleton-cell" />)}
      </div>
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} className="skeleton-row" style={{ '--i': r }}>
          <span className="skeleton-product">
            <span className="skeleton skeleton-line" />
            <span className="skeleton skeleton-line skeleton-line-short" />
          </span>
          {Array.from({ length: cols - 1 }, (_, c) => <span key={c} className="skeleton skeleton-cell" />)}
        </div>
      ))}
    </div>
  )
}

export function ChartSkeleton({ count = 2, height = 260 }) {
  return (
    <div className="charts-grid table-charts" role="status" aria-label="Laster grafer">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="chart-card">
          <span className="skeleton skeleton-title" />
          <span className="skeleton skeleton-line skeleton-line-short" />
          <span className="skeleton skeleton-chart" style={{ height }} />
        </div>
      ))}
    </div>
  )
}
