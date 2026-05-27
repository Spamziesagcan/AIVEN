import { useEffect, useMemo, useState } from 'react'

export default function ObservabilityDashboard() {
  const [metrics, setMetrics] = useState(null)
  const [status, setStatus] = useState('Loading')

  useEffect(() => {
    let mounted = true

    async function loadMetrics() {
      try {
        const response = await fetch(`${getApiBase()}/api/observability/metrics`)
        if (!response.ok) throw new Error('Failed to load metrics')
        const data = await response.json()
        if (!mounted) return
        setMetrics(data)
        setStatus('Live')
      } catch {
        if (!mounted) return
        setStatus('Offline')
      }
    }

    loadMetrics()
    const interval = setInterval(loadMetrics, 15000)

    function handleRefreshEvent() {
      loadMetrics()
    }

    window.addEventListener('observability:refresh', handleRefreshEvent)

    return () => {
      mounted = false
      clearInterval(interval)
      window.removeEventListener('observability:refresh', handleRefreshEvent)
    }
  }, [])

  const summary = metrics?.summary || {}
  const series = metrics?.series || []
  const recentErrors = metrics?.recent_errors || []
  const maxRequests = useMemo(() => Math.max(1, ...series.map((entry) => entry.requests || 0)), [series])

  return (
    <section className="observability-panel">
      <div className="observability-header">
        <div>
          <p className="eyebrow">Observability</p>
          <h3>Latency, throughput, and errors</h3>
          <p className="observability-copy">
            Live request health from the `inference_logs` table, refreshed automatically while you chat.
          </p>
        </div>
        <span className={`dashboard-status ${status.toLowerCase()}`}>{status}</span>
      </div>

      <div className="observability-metrics">
        <MetricCard label="Avg latency" value={formatMs(summary.avg_latency_ms)} tone="mint" />
        <MetricCard label="P95 latency" value={formatMs(summary.p95_latency_ms)} tone="violet" />
        <MetricCard label="Throughput" value={`${summary.throughput_rpm ?? 0} rpm`} tone="blue" />
        <MetricCard label="Error rate" value={`${summary.error_rate_pct ?? 0}%`} tone="rose" />
      </div>

      <div className="observability-grid">
        <div className="observability-card chart-card">
          <div className="card-heading">
            <div>
              <p className="card-kicker">Throughput</p>
              <h4>Hourly request volume</h4>
            </div>
            <span>{summary.total_requests ?? 0} requests</span>
          </div>

          <div className="throughput-chart">
            {series.map((entry) => (
              <div className="throughput-row" key={entry.label}>
                <span className="throughput-label">{entry.label}</span>
                <div className="throughput-track">
                  <div
                    className="throughput-fill"
                    style={{ width: `${Math.max(6, (entry.requests / maxRequests) * 100)}%` }}
                  />
                  {entry.errors > 0 ? <div className="throughput-error-mark" style={{ width: `${Math.max(6, (entry.errors / maxRequests) * 100)}%` }} /> : null}
                </div>
                <span className="throughput-metric">{entry.requests}</span>
                <span className="throughput-latency">{entry.avg_latency_ms} ms</span>
              </div>
            ))}
          </div>
        </div>

        <div className="observability-card error-card">
          <div className="card-heading">
            <div>
              <p className="card-kicker">Errors</p>
              <h4>Recent failures</h4>
            </div>
            <span>{summary.error_count ?? 0} total</span>
          </div>

          {recentErrors.length === 0 ? (
            <div className="empty-observability">No errors in the current window.</div>
          ) : (
            <div className="error-list">
              {recentErrors.map((error, index) => (
                <div className="error-item" key={`${error.request_id || index}-${index}`}>
                  <div className="error-topline">
                    <strong>{error.model || 'unknown model'}</strong>
                    <span>{formatTime(error.received_at)}</span>
                  </div>
                  <p>{error.error}</p>
                  <div className="error-meta">
                    <span>{error.conversation_id || 'no conversation'}</span>
                    <span>{error.request_id || 'no request id'}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

function MetricCard({ label, value, tone }) {
  return (
    <div className={`metric-card ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function formatMs(value) {
  if (value === null || value === undefined) return '0 ms'
  return `${value} ms`
}

function formatTime(timestamp) {
  if (!timestamp) return ''
  return new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(timestamp))
}

function getApiBase() {
  return process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000'
}