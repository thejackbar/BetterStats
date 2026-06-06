import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  BarChart, Bar, PieChart, Pie, Cell, Legend,
} from 'recharts'
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
  { value: 'page_view', label: 'Pages' },
]

// Multi-select. 'Everyone' is the sentinel for an empty selection.
const ROLE_OPTIONS = [
  { value: 'super_admin', label: 'Super admins' },
  { value: 'club_admin',  label: 'Club admins'  },
  { value: 'anon',        label: 'Anonymous'    },
]

const ROLE_LABEL = {
  super_admin: 'Super',
  club_admin:  'Admin',
  club_member: 'Member',
  anon:        'Anon',
}

// ISO country code → flag emoji. Pure unicode trick: A-Z maps to regional
// indicator symbols at U+1F1E6..U+1F1FF.
function flagFor(cc) {
  if (!cc || cc.length !== 2) return ''
  const codePoints = cc.toUpperCase().split('').map(c => 0x1f1e6 + c.charCodeAt(0) - 65)
  try {
    return String.fromCodePoint(...codePoints)
  } catch {
    return ''
  }
}

// Recharts colour palette built from existing CSS vars so light/dark themes
// just work. Order matters for the rotating Pie cells.
const COLOURS = [
  'var(--pb-accent)',
  '#3b82f6',  // blue
  '#a855f7',  // purple
  '#f59e0b',  // amber
  '#ec4899',  // pink
  '#22d3ee',  // cyan
  '#84cc16',  // lime
  '#ef4444',  // red
  '#64748b',  // slate
]

function fmtTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('en-AU', {
    day: 'numeric', month: 'short',
    hour: 'numeric', minute: '2-digit',
  })
}

function fmtNum(n) {
  if (n == null) return '0'
  if (n >= 10000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k'
  return String(n)
}

function userLabel(row) {
  return row.user_display_name || row.user_email
    || (row.user_id ? row.user_id.slice(0, 8) : 'anon')
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

function RoleBadge({ role }) {
  if (!role) return null
  const label = ROLE_LABEL[role] || role
  const colour = role === 'super_admin' ? 'text-pb-accent'
    : role === 'club_admin' ? 'text-pb-text'
    : role === 'anon' ? 'text-pb-faintest'
    : 'text-pb-faint'
  return (
    <span className={`font-mono text-[9px] uppercase tracking-wide ${colour}`}>
      {label}
    </span>
  )
}

// Format the x-axis label for the time-series chart. Hour bucket for the
// 24h window, day bucket otherwise.
function fmtBucket(iso, bucket) {
  if (!iso) return ''
  const d = new Date(iso)
  if (bucket === 'hour') {
    return d.toLocaleTimeString('en-AU', { hour: 'numeric' })
  }
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-pb-surface border pb-hairline rounded px-3 py-2 text-xs shadow-lg">
      {label && <p className="font-mono text-[10px] text-pb-faint mb-1">{label}</p>}
      {payload.map((p, i) => (
        <p key={i} className="font-mono text-pb-text">
          <span className="inline-block w-2 h-2 rounded-full mr-2 align-middle" style={{ background: p.color || p.fill }} />
          {p.name}: <strong>{fmtNum(p.value)}</strong>
        </p>
      ))}
    </div>
  )
}

export default function AdminUsage() {
  const [days, setDays] = useState(7)
  const [eventType, setEventType] = useState('')
  const [roles, setRoles] = useState([])

  const [summary, setSummary] = useState(null)
  const [visitors, setVisitors] = useState(null)
  const [series, setSeries] = useState({ bucket: 'day', points: [] })
  const [byFeature, setByFeature] = useState([])
  const [byRole, setByRole] = useState([])
  const [byClub, setByClub] = useState([])
  const [byLocation, setByLocation] = useState({ by_country: [], by_city: [] })
  const [topRoutes, setTopRoutes] = useState([])
  const [topUsers, setTopUsers] = useState([])
  const [recent, setRecent] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const toggleRole = useCallback((value) => {
    setRoles(prev => prev.includes(value)
      ? prev.filter(r => r !== value)
      : [...prev, value]
    )
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    const opts = {
      days,
      eventType: eventType || null,
      roles,
    }
    try {
      const [s, vis, ts, feat, brole, bclub, bloc, r, u, e] = await Promise.all([
        api.adminUsageSummary(opts),
        api.adminUsageVisitors({ days, eventType: eventType || null }),
        api.adminUsageTimeseries(opts),
        api.adminUsageByFeature(opts),
        // by-role chart shows the overall split, ignores the role filter
        api.adminUsageByRole({ days, eventType: eventType || null }),
        api.adminUsageByClub(opts),
        api.adminUsageByLocation(opts),
        api.adminUsageTopRoutes({ ...opts, limit: 20 }),
        api.adminUsageTopUsers({ days, roles, limit: 20 }),
        api.adminUsageRecent({ ...opts, limit: 100 }),
      ])
      setSummary(s)
      setVisitors(vis)
      setSeries(ts)
      setByFeature(feat)
      setByRole(brole)
      setByClub(bclub)
      setByLocation(bloc)
      setTopRoutes(r)
      setTopUsers(u)
      setRecent(e)
    } catch (err) {
      setError(err?.message || 'Failed to load usage data')
    } finally {
      setLoading(false)
    }
  }, [days, eventType, roles])

  useEffect(() => { load() }, [load])

  const seriesData = useMemo(() => series.points.map(p => ({
    label: fmtBucket(p.bucket, series.bucket),
    api: p.api_hits,
    pages: p.page_views,
    total: p.total,
  })), [series])

  const featureData = useMemo(() => byFeature.slice(0, 10), [byFeature])
  const roleData = useMemo(() => byRole.map((r, i) => ({
    name: ROLE_LABEL[r.role] || r.role,
    value: r.hits,
    fill: COLOURS[i % COLOURS.length],
  })), [byRole])

  return (
    <AdminLayout>
      <div className="max-w-6xl">
        <h1 className="font-display font-bold text-2xl text-pb-text mb-2">Usage Breadcrumbs</h1>
        <p className="text-pb-faint text-sm mb-5 leading-relaxed">
          What people are doing inside BetterStats — API calls and page views.
          IPs are stored as a truncated hash, never raw.
        </p>

        {/* Filters */}
        <div className="mb-5 space-y-2">
          <div className="flex flex-wrap gap-2 items-center">
            <span className="font-mono text-[10px] text-pb-faint uppercase tracking-wide w-14">Window</span>
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
            <button
              onClick={load}
              className="ml-auto font-mono text-[10px] px-2.5 py-1 rounded border pb-hairline text-pb-faint hover:text-pb-text"
            >
              Refresh
            </button>
          </div>
          <div className="flex flex-wrap gap-2 items-center">
            <span className="font-mono text-[10px] text-pb-faint uppercase tracking-wide w-14">Type</span>
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
          </div>
          <div className="flex flex-wrap gap-2 items-center">
            <span className="font-mono text-[10px] text-pb-faint uppercase tracking-wide w-14">Role</span>
            <button
              onClick={() => setRoles([])}
              className={`font-mono text-[10px] px-2.5 py-1 rounded border pb-hairline transition ${
                roles.length === 0 ? 'bg-pb-accent text-pb-bg' : 'text-pb-faint hover:text-pb-text'
              }`}
            >
              Everyone
            </button>
            {ROLE_OPTIONS.map(opt => {
              const active = roles.includes(opt.value)
              return (
                <button
                  key={opt.value}
                  onClick={() => toggleRole(opt.value)}
                  className={`font-mono text-[10px] px-2.5 py-1 rounded border pb-hairline transition flex items-center gap-1.5 ${
                    active ? 'bg-pb-accent text-pb-bg' : 'text-pb-faint hover:text-pb-text'
                  }`}
                >
                  {active && <span className="text-[9px]">✓</span>}
                  {opt.label}
                </button>
              )
            })}
            {roles.length > 0 && (
              <span className="font-mono text-[9px] text-pb-faintest ml-1">
                {roles.length} selected
              </span>
            )}
          </div>
        </div>

        {error && (
          <div className="mb-4 font-mono text-[11px] text-pb-red bg-pb-red/10 border border-pb-red/30 rounded px-3 py-2">
            {error}
          </div>
        )}

        {/* Summary cards */}
        {summary && (
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-3">
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

        {/* Visitors — new vs returning, derived from the (hashed) IP. */}
        {visitors && (
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
            {[
              { label: 'Visitors', value: visitors.visitors, hint: 'unique IPs' },
              { label: 'Returning', value: visitors.returning, hint: `${visitors.returning_pct}% · seen before` },
              { label: 'New', value: visitors.new, hint: 'first time' },
              { label: 'Multi-day', value: visitors.multi_day, hint: '≥2 days active' },
              { label: 'Hits / visitor', value: visitors.avg_hits, hint: 'avg', raw: true },
            ].map(s => (
              <div key={s.label} className="pb-card px-3 py-2" style={{ background: 'color-mix(in srgb, var(--pb-accent) 5%, transparent)' }}>
                <div className="font-mono text-[9px] uppercase tracking-wide text-pb-faint">{s.label}</div>
                <div className="font-display text-xl text-pb-text">{s.raw ? s.value : fmtNum(s.value)}</div>
                {s.hint && <div className="font-mono text-[9px] text-pb-faintest mt-0.5">{s.hint}</div>}
              </div>
            ))}
          </div>
        )}

        {/* Time series */}
        <div className="pb-card p-4 mb-6">
          <div className="flex items-center justify-between mb-2">
            <h2 className="font-display font-bold text-sm text-pb-text uppercase tracking-wide">Activity over time</h2>
            <span className="font-mono text-[9px] text-pb-faintest">
              {series.bucket === 'hour' ? 'per hour' : 'per day'}
            </span>
          </div>
          <div style={{ width: '100%', height: 220 }}>
            {seriesData.length === 0 ? (
              <div className="h-full flex items-center justify-center font-mono text-[11px] text-pb-faint">
                {loading ? 'Loading…' : 'No data in window.'}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={seriesData} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="apiFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--pb-accent)" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="var(--pb-accent)" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="pagesFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" />
                  <XAxis dataKey="label" tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} />
                  <Tooltip content={<ChartTooltip />} />
                  <Area type="monotone" dataKey="api"   name="API"        stroke="var(--pb-accent)" strokeWidth={2} fill="url(#apiFill)" />
                  <Area type="monotone" dataKey="pages" name="Page views" stroke="#3b82f6"          strokeWidth={2} fill="url(#pagesFill)" />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Feature breakdown + role donut */}
        <div className="grid lg:grid-cols-3 gap-5 mb-6">
          <div className="pb-card p-4 lg:col-span-2">
            <h2 className="font-display font-bold text-sm text-pb-text uppercase tracking-wide mb-2">By feature</h2>
            <div style={{ width: '100%', height: Math.max(240, featureData.length * 28) }}>
              {featureData.length === 0 ? (
                <div className="h-full flex items-center justify-center font-mono text-[11px] text-pb-faint">
                  {loading ? 'Loading…' : 'No data.'}
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={featureData} layout="vertical" margin={{ top: 4, right: 16, left: 4, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" horizontal={false} />
                    <XAxis type="number" tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis type="category" dataKey="feature" width={140} tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--pb-surface2)', opacity: 0.4 }} />
                    <Bar dataKey="hits" name="Hits" fill="var(--pb-accent)" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          <div className="pb-card p-4">
            <h2 className="font-display font-bold text-sm text-pb-text uppercase tracking-wide mb-2">By role</h2>
            <p className="font-mono text-[9px] text-pb-faintest mb-2">
              Overall split — ignores the role filter above.
            </p>
            <div style={{ width: '100%', height: 240 }}>
              {roleData.length === 0 ? (
                <div className="h-full flex items-center justify-center font-mono text-[11px] text-pb-faint">
                  {loading ? 'Loading…' : 'No data.'}
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={roleData} dataKey="value" nameKey="name" innerRadius={40} outerRadius={75} paddingAngle={2}>
                      {roleData.map((entry, i) => (
                        <Cell key={i} fill={entry.fill} />
                      ))}
                    </Pie>
                    <Tooltip content={<ChartTooltip />} />
                    <Legend
                      wrapperStyle={{ fontSize: 10, fontFamily: 'monospace', color: 'var(--pb-faint)' }}
                      iconSize={8}
                    />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>
        </div>

        {/* By club — usage attributed to each club (page views via the slug in
            the URL; everything else lands in "Unattributed"). */}
        <div className="pb-card p-4 mb-6">
          <div className="flex items-center justify-between mb-2">
            <h2 className="font-display font-bold text-sm text-pb-text uppercase tracking-wide">By club</h2>
            <span className="font-mono text-[9px] text-pb-faintest">page views attributed via the public URL</span>
          </div>
          {byClub.length === 0 ? (
            <div className="py-6 text-center font-mono text-[11px] text-pb-faint">{loading ? 'Loading…' : 'No data.'}</div>
          ) : (
            <div className="space-y-1.5">
              {(() => {
                const max = Math.max(1, ...byClub.map(c => c.hits || 0))
                return byClub.slice(0, 15).map((c) => {
                  const pct = Math.round((c.hits / max) * 100)
                  const unattributed = !c.club_id
                  return (
                    <div key={c.club_id || 'none'} className="flex items-center gap-3">
                      <div className="w-40 shrink-0 truncate text-sm" title={c.club_name}>
                        {c.club_slug ? (
                          <span className="text-pb-text">{c.club_name}</span>
                        ) : (
                          <span className="text-pb-faintest italic">{c.club_name}</span>
                        )}
                      </div>
                      <div className="flex-1 h-4 rounded bg-pb-surface2 overflow-hidden">
                        <div className="h-full rounded" style={{ width: `${pct}%`, background: unattributed ? 'var(--pb-faint)' : 'var(--pb-accent)', opacity: unattributed ? 0.4 : 1 }} />
                      </div>
                      <div className="w-28 shrink-0 text-right font-mono text-[10px] text-pb-faint">
                        {fmtNum(c.hits)} · {fmtNum(c.unique_ips)} IPs
                      </div>
                    </div>
                  )
                })
              })()}
            </div>
          )}
        </div>

        {/* Top routes + top users tables */}
        <div className="grid md:grid-cols-2 gap-5 mb-6">
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
                    <div className="text-pb-text text-sm truncate flex items-center gap-2">
                      {userLabel(u)}
                      <RoleBadge role={u.user_role} />
                    </div>
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

        {/* By location */}
        <div className="grid md:grid-cols-2 gap-5 mb-6">
          <div>
            <h2 className="font-display font-bold text-sm text-pb-text mb-2 uppercase tracking-wide">By country</h2>
            <div className="pb-card overflow-hidden">
              {loading && !byLocation.by_country.length && (
                <div className="p-6 text-center font-mono text-[11px] text-pb-faint">Loading…</div>
              )}
              {!loading && !byLocation.by_country.length && (
                <div className="p-6 text-center font-mono text-[11px] text-pb-faint">
                  No geo data yet. Cloudflare populates country on every request — give it a few minutes after deploy.
                </div>
              )}
              {byLocation.by_country.map((row, i) => (
                <div
                  key={row.country || `none-${i}`}
                  className={`flex items-center gap-3 px-4 py-2 ${i > 0 ? 'pb-hairline-t' : ''}`}
                >
                  <span className="text-base shrink-0 w-6">{flagFor(row.country)}</span>
                  <div className="flex-1 min-w-0">
                    <div className="font-mono text-[11px] text-pb-text truncate">
                      {row.country || 'Unknown'}
                    </div>
                    <div className="font-mono text-[9px] text-pb-faintest">
                      {row.unique_ips} unique IPs
                    </div>
                  </div>
                  <div className="font-mono text-[11px] text-pb-text shrink-0">{fmtNum(row.hits)}</div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <h2 className="font-display font-bold text-sm text-pb-text mb-2 uppercase tracking-wide">By city</h2>
            <div className="pb-card overflow-hidden">
              {loading && !byLocation.by_city.length && (
                <div className="p-6 text-center font-mono text-[11px] text-pb-faint">Loading…</div>
              )}
              {!loading && !byLocation.by_city.length && (
                <div className="p-6 text-center font-mono text-[11px] text-pb-faint">
                  City lookups (via ip-api.com) fill in shortly after each visit. Refresh in a minute.
                </div>
              )}
              {byLocation.by_city.map((row, i) => (
                <div
                  key={`${row.city}-${row.region}-${row.country}-${i}`}
                  className={`flex items-center gap-3 px-4 py-2 ${i > 0 ? 'pb-hairline-t' : ''}`}
                >
                  <span className="text-base shrink-0 w-6">{flagFor(row.country)}</span>
                  <div className="flex-1 min-w-0">
                    <div className="font-mono text-[11px] text-pb-text truncate">
                      {row.city}
                      {row.region && <span className="text-pb-faint">, {row.region}</span>}
                    </div>
                    <div className="font-mono text-[9px] text-pb-faintest">
                      {row.unique_ips} unique IPs
                    </div>
                  </div>
                  <div className="font-mono text-[11px] text-pb-text shrink-0">{fmtNum(row.hits)}</div>
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
              <div className="flex-1 min-w-0">
                {r.target_name && r.target_url ? (
                  <a
                    href={r.target_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-pb-accent hover:underline text-[12px] truncate block"
                    title={r.path}
                  >
                    {r.target_name}
                  </a>
                ) : r.event_type === 'page_view' && r.path ? (
                  <a
                    href={r.path}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-mono text-[10px] text-pb-text hover:text-pb-accent hover:underline truncate block"
                  >
                    {r.path}
                  </a>
                ) : (
                  <span className="font-mono text-[10px] text-pb-text truncate block" title={r.path}>
                    {r.path}
                  </span>
                )}
              </div>
              <span
                className="text-xs shrink-0 w-20 text-right truncate"
                title={[r.city, r.region, r.country].filter(Boolean).join(', ') || 'Unknown'}
              >
                {r.country ? (
                  <span className="font-mono text-pb-faint">
                    {flagFor(r.country)} {r.city || r.country}
                  </span>
                ) : (
                  <span className="font-mono text-[10px] text-pb-faintest">—</span>
                )}
              </span>
              <span className="font-mono text-[10px] text-pb-faint shrink-0 w-28 text-right truncate flex items-center justify-end gap-1.5">
                {r.user_id ? (
                  <>
                    <span className="truncate">{userLabel(r)}</span>
                    <RoleBadge role={r.user_role} />
                  </>
                ) : 'anon'}
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
