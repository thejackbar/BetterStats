import { useState, useEffect, useCallback } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

const WINDOW_OPTIONS = [
  { value: 1,   label: '24h' },
  { value: 7,   label: '7d'  },
  { value: 30,  label: '30d' },
  { value: 90,  label: '90d' },
]

const EVENT_TYPES = [
  { value: '',          label: 'All' },
  { value: 'api',       label: 'API' },
  { value: 'page_view', label: 'Page views' },
]

function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('en-AU', {
    day: 'numeric', month: 'short',
    hour: 'numeric', minute: '2-digit',
  })
}

function fmtNum(n) {
  if (n == null) return '0'
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k'
  return String(n)
}

function userLabel(row) {
  return row.user_display_name || row.user_email || (row.user_id ? row.user_id.slice(0, 8) : 'anon')
}

function StatusBadge({ status }) {
  let cls = 'text-pb-faint'
  if (status >= 500) cls = 'text-pb-red'
  else if (status >= 400) cls = 'text-pb-amber'
  else if (status >= 200 && status < 300) cls = 'text-pb-text'
  return <span className={`font-mono text-[10px] ${cls}`}>{status || '—'}</span>
}

function TypeBadge({ type }) {
  const isPage = type === 'page_view'
  return (
    <span
      className={`font-mono text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded border pb-hairline ${
        isPage ? 'text-pb-accent' : 'text-pb-faint'
      }`}
    >
      {isPage ? 'page' : 'api'}
    </span>
  )
}

export default function AdminUsage() {
  const [days, setDays] = useState(7)
  const [eventType, setEventType] = useState('')
  const [summary, setSummary] = useState(null)
  const [topRoutes, setTopRoutes] = useState([])
  const [topUsers, setTopUsers] = useState([])
  const [recent, setRecent] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [s, r, u, e] = await Promise.all([
        api.adminUsageSummary({ days }),
        api.adminUsageTopRoutes({ days, limit: 25, eventType: eventType || null }),
        api.adminUsageTopUsers({ days, limit: 25 }),
        api.adminUsageRecent({ limit: 100, eventType: eventType || null }),
      ])
      setSummary(s)
      setTopRoutes(r)
      setTopUsers(u)
      setRecent(e)
    } catch (err) {
      setError(err?.message || 'Failed to load usage data')
    } finally {
      setLoading(false)
    }
  }, [days, eventType])

  useEffect(() => { load() }, [load])

  return (
    <AdminLayout>
      <div className="max-w-5xl">
        <h1 className="font-display font-bold text-2xl text-pb-text mb-2">Usage Breadcrumbs</h1>
        <p className="text-pb-faint text-sm mb-5 leading-relaxed">
          What people are doing inside BetterStats — API calls and page views.
          Each row is a single hit. IPs are stored as a truncated hash, never raw.
        </p>

        {/* Filters */}
        <div className="mb-5 flex flex-wrap gap-2 items-center">
          <span className="font-mono text-[10px] text-pb-faint uppercase tracking-wide">Window</span>
          {WINDOW_OPTIONS.map(opt => (
            <button
              key={opt.value}
              onClick={() => setDays(opt.value)}
              className={`font-mono text-[10px] px-2.5 py-1 rounded border pb-hairline transition ${
                days === opt.value ? 'bg-pb-accent text-pb-bg' : 'text-pb-faint hover:text-pb-text'
              }`}
            >
              {opt.label}
            </button>
          ))}
          <span className="ml-3 font-mono text-[10px] text-pb-faint uppercase tracking-wide">Type</span>
          {EVENT_TYPES.map(opt => (
            <button
              key={opt.value || 'all'}
              onClick={() => setEventType(opt.value)}
              className={`font-mono text-[10px] px-2.5 py-1 rounded border pb-hairline transition ${
                eventType === opt.value ? 'bg-pb-accent text-pb-bg' : 'text-pb-faint hover:text-pb-text'
              }`}
            >
              {opt.label}
            </button>
          ))}
          <button
            onClick={load}
            className="ml-auto font-mono text-[10px] px-2.5 py-1 rounded border pb-hairline text-pb-faint hover:text-pb-text"
          >
            Refresh
          </button>
        </div>

        {error && (
          <div className="mb-4 font-mono text-[11px] text-pb-red bg-pb-red/10 border border-pb-red/30 rounded px-3 py-2">
            {error}
          </div>
        )}

        {/* Summary cards */}
        {summary && (
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
            {[
              { label: 'Total events', value: summary.total },
              { label: 'API hits',     value: summary.api_hits },
              { label: 'Page views',   value: summary.page_views },
              { label: 'Unique users', value: summary.unique_users },
              { label: 'Unique IPs',   value: summary.unique_ips },
            ].map(s => (
              <div key={s.label} className="pb-card px-3 py-2">
                <div className="font-mono text-[9px] uppercase tracking-wide text-pb-faint">{s.label}</div>
                <div className="font-display text-xl text-pb-text">{fmtNum(s.value)}</div>
              </div>
            ))}
          </div>
        )}

        <div className="grid md:grid-cols-2 gap-5 mb-6">
          {/* Top routes */}
          <div>
            <h2 className="font-display font-bold text-sm text-pb-text mb-2 uppercase tracking-wide">Top routes</h2>
            <div className="pb-card overflow-hidden">
              {loading && !topRoutes.length && (
                <div className="p-6 text-center font-mono text-[11px] text-pb-faint">Loading…</div>
              )}
              {!loading && !topRoutes.length && (
                <div className="p-6 text-center font-mono text-[11px] text-pb-faint">No data in window.</div>
              )}
              {topRoutes.map((r, i) => (
                <div
                  key={`${r.event_type}:${r.route}:${i}`}
                  className={`flex items-center gap-3 px-4 py-2 ${i > 0 ? 'pb-hairline-t' : ''}`}
                >
                  <TypeBadge type={r.event_type} />
                  <div className="flex-1 min-w-0">
                    <div className="font-mono text-[11px] text-pb-text truncate">{r.route || '—'}</div>
                    <div className="font-mono text-[9px] text-pb-faintest">
                      {r.unique_users} users · {r.unique_ips} IPs · last {fmtTime(r.last_hit)}
                    </div>
                  </div>
                  <div className="font-mono text-[11px] text-pb-text shrink-0">{fmtNum(r.hits)}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Top users */}
          <div>
            <h2 className="font-display font-bold text-sm text-pb-text mb-2 uppercase tracking-wide">Top users</h2>
            <div className="pb-card overflow-hidden">
              {loading && !topUsers.length && (
                <div className="p-6 text-center font-mono text-[11px] text-pb-faint">Loading…</div>
              )}
              {!loading && !topUsers.length && (
                <div className="p-6 text-center font-mono text-[11px] text-pb-faint">No data in window.</div>
              )}
              {topUsers.map((u, i) => (
                <div
                  key={u.user_id || i}
                  className={`flex items-center gap-3 px-4 py-2 ${i > 0 ? 'pb-hairline-t' : ''}`}
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-pb-text text-sm truncate">{userLabel(u)}</div>
                    <div className="font-mono text-[9px] text-pb-faintest">
                      {u.unique_routes} routes · last {fmtTime(u.last_hit)}
                    </div>
                  </div>
                  <div className="font-mono text-[11px] text-pb-text shrink-0">{fmtNum(u.hits)}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Recent events */}
        <h2 className="font-display font-bold text-sm text-pb-text mb-2 uppercase tracking-wide">Recent events</h2>
        <div className="pb-card overflow-hidden">
          {loading && !recent.length && (
            <div className="p-6 text-center font-mono text-[11px] text-pb-faint">Loading…</div>
          )}
          {!loading && !recent.length && (
            <div className="p-6 text-center font-mono text-[11px] text-pb-faint">No events.</div>
          )}
          {recent.map((r, i) => (
            <div
              key={r.id}
              className={`flex items-center gap-3 px-4 py-2 ${i > 0 ? 'pb-hairline-t' : ''}`}
            >
              <TypeBadge type={r.event_type} />
              <span className="font-mono text-[10px] text-pb-faintest shrink-0 w-24">
                {fmtTime(r.created_at)}
              </span>
              <StatusBadge status={r.status} />
              <span className="font-mono text-[10px] text-pb-faint shrink-0 w-12">{r.method}</span>
              <span className="font-mono text-[10px] text-pb-text flex-1 min-w-0 truncate">
                {r.path}
              </span>
              <span className="font-mono text-[10px] text-pb-faint shrink-0 w-24 text-right truncate">
                {r.user_id ? userLabel(r) : 'anon'}
              </span>
              <span className="font-mono text-[9px] text-pb-faintest shrink-0 w-12 text-right">
                {r.duration_ms != null ? `${r.duration_ms}ms` : ''}
              </span>
            </div>
          ))}
        </div>
      </div>
    </AdminLayout>
  )
}
