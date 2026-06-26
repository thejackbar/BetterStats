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

// Recharts colour palette built from existing CSS vars so light/dark themes
// just work. Order matters for the rotating Pie cells.
const COLOURS = [
  'var(--pb-accent)',
  '#3b82f6', '#a855f7', '#f59e0b', '#ec4899',
  '#22d3ee', '#84cc16', '#ef4444', '#64748b',
]

// Traffic source → label + dot colour for the live section.
const SOURCE_STYLE = {
  facebook:  { label: 'Facebook',    dot: '#1877f2' },
  instagram: { label: 'Instagram',   dot: '#e1306c' },
  google:    { label: 'Google',      dot: '#ea4335' },
  bing:      { label: 'Bing',        dot: '#0c8484' },
  email:     { label: 'Email',       dot: '#f59e0b' },
  twitter:   { label: 'X / Twitter', dot: '#1d9bf0' },
  linkedin:  { label: 'LinkedIn',    dot: '#0a66c2' },
  tiktok:    { label: 'TikTok',      dot: '#ff0050' },
  youtube:   { label: 'YouTube',     dot: '#ff0000' },
  whatsapp:  { label: 'WhatsApp',    dot: '#25d366' },
  reddit:    { label: 'Reddit',      dot: '#ff4500' },
  referral:  { label: 'Referral',    dot: '#a855f7' },
  direct:    { label: 'Direct',      dot: 'var(--pb-faint)' },
}
function sourceMeta(s) {
  const key = (s || 'direct').toLowerCase()
  return SOURCE_STYLE[key] || { label: s, dot: 'var(--pb-accent)' }
}

// ISO country code → flag emoji. A-Z maps to regional indicator symbols.
function flagFor(cc) {
  if (!cc || cc.length !== 2) return ''
  const codePoints = cc.toUpperCase().split('').map(c => 0x1f1e6 + c.charCodeAt(0) - 65)
  try { return String.fromCodePoint(...codePoints) } catch { return '' }
}

function fmtTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('en-AU', {
    day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit',
  })
}

function fmtAgo(iso) {
  if (!iso) return ''
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000))
  if (s < 10) return 'now'
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60); if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60); if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24); return `${d}d ago`
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

function deviceIcon(d) {
  switch (d?.type) {
    case 'mobile':  return '📱'
    case 'tablet':  return '📲'
    case 'bot':     return '🤖'
    case 'desktop': return '🖥️'
    default:        return '🌐'
  }
}

function Dot({ on, color = '#10b981', size = 6 }) {
  return (
    <span className={on ? 'animate-pulse' : ''}
      style={{ display: 'inline-block', width: size, height: size, borderRadius: '50%',
               background: on ? color : 'transparent' }} />
  )
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
    <span className={`font-mono text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded border pb-hairline ${
      isPage ? 'text-pb-accent' : 'text-pb-faint'}`}>
      {isPage ? 'page' : 'api'}
    </span>
  )
}

function RoleBadge({ role }) {
  if (!role) return null
  const label = ROLE_LABEL[role] || role
  const colour = role === 'super_admin' ? 'text-pb-accent'
    : role === 'club_admin' ? 'text-pb-text'
    : role === 'anon' ? 'text-pb-faintest' : 'text-pb-faint'
  return <span className={`font-mono text-[9px] uppercase tracking-wide ${colour}`}>{label}</span>
}

// Format the x-axis label for the time-series chart. Hour bucket for 24h, day otherwise.
function fmtBucket(iso, bucket) {
  if (!iso) return ''
  const d = new Date(iso)
  if (bucket === 'hour') return d.toLocaleTimeString('en-AU', { hour: 'numeric' })
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

// Collapsible section. Default open, remembers its state — so nothing is
// hidden unless you choose to tuck it away.
function Panel({ id, title, sub, defaultOpen = true, children }) {
  const [open, setOpen] = useState(() => {
    try {
      const v = localStorage.getItem('uSec:' + id)
      return v == null ? defaultOpen : v === '1'
    } catch { return defaultOpen }
  })
  const toggle = () => setOpen(o => {
    const n = !o
    try { localStorage.setItem('uSec:' + id, n ? '1' : '0') } catch { /* ignore */ }
    return n
  })
  return (
    <div className="mb-6">
      <button onClick={toggle} className="w-full flex items-center gap-2 mb-2 text-left">
        <span className="font-mono text-pb-faint text-[11px] w-3 shrink-0">{open ? '▾' : '▸'}</span>
        <h2 className="font-display font-bold text-sm text-pb-text uppercase tracking-wide">{title}</h2>
        {sub && <span className="font-mono text-[9px] text-pb-faintest">{sub}</span>}
      </button>
      {open && <div>{children}</div>}
    </div>
  )
}

// ─── Live / realtime section (auto-refreshing, anonymous public traffic) ─────

function LiveSection() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [live, setLive] = useState(true)
  const [updatedAt, setUpdatedAt] = useState(null)
  const [, tick] = useState(0)

  const load = useCallback(async () => {
    try {
      const d = await api.adminUsageLive()
      setData(d); setError(null); setUpdatedAt(Date.now())
    } catch (e) {
      setError(e?.message || 'Failed to load')
    }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!live) return
    const id = setInterval(load, 8000)
    return () => clearInterval(id)
  }, [live, load])
  useEffect(() => {
    const id = setInterval(() => tick(n => n + 1), 1000)
    return () => clearInterval(id)
  }, [])

  const A = data?.active
  const recent = data?.recent || []
  const perMinute = data?.per_minute || []
  const pmMax = Math.max(1, ...perMinute.map(p => p.views))
  const sources = data?.sources || []
  const srcMax = Math.max(1, ...sources.map(s => s.visitors))
  const utms = data?.utms || []

  const windows = [
    { key: 'now',   label: 'Active now',  sub: 'last 5 min', live: true },
    { key: 'm30',   label: 'Last 30 min', sub: '' },
    { key: 'today', label: 'Today',       sub: 'last 24h' },
    { key: 'week',  label: 'Last 7 days', sub: '' },
  ]

  return (
    <div className="mb-8">
      <div className="flex items-center gap-2 mb-3">
        <h2 className="font-display font-bold text-sm text-pb-text uppercase tracking-wide">Live</h2>
        <Dot on={live} />
        <span className="font-mono text-[9px] text-pb-faintest">
          {updatedAt ? `updated ${fmtAgo(new Date(updatedAt).toISOString())}` : ''}
        </span>
        <span className="ml-auto flex items-center gap-2">
          <button onClick={() => setLive(l => !l)}
            className="font-mono text-[10px] px-2 py-0.5 rounded border pb-hairline text-pb-faint hover:text-pb-text">
            {live ? 'Pause' : 'Resume'}
          </button>
          <button onClick={load}
            className="font-mono text-[10px] px-2 py-0.5 rounded border pb-hairline text-pb-faint hover:text-pb-text">
            Refresh
          </button>
        </span>
      </div>

      {error && (
        <div className="mb-3 font-mono text-[11px] text-pb-red bg-pb-red/10 border border-pb-red/30 rounded px-3 py-2">{error}</div>
      )}
      {!data && !error && (
        <div className="py-8 text-center font-mono text-[11px] text-pb-faint">Connecting…</div>
      )}

      {data && (
        <>
          {/* Active visitors across windows */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            {windows.map(w => {
              const a = A?.[w.key] || { visitors: 0, views: 0 }
              return (
                <div key={w.key} className="pb-card px-4 py-3"
                  style={w.live ? { background: 'color-mix(in srgb, var(--pb-accent) 8%, transparent)' } : undefined}>
                  <div className="flex items-center gap-1.5">
                    {w.live && <Dot on={live} />}
                    <span className="font-mono text-[10px] uppercase tracking-wide text-pb-faint">{w.label}</span>
                  </div>
                  <div className="font-display text-3xl text-pb-text leading-tight mt-1">{a.visitors}</div>
                  <div className="font-mono text-[10px] text-pb-faintest">
                    {a.visitors === 1 ? 'visitor' : 'visitors'} · {a.views} views{w.sub ? ` · ${w.sub}` : ''}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Page views per minute */}
          <div className="pb-card px-4 py-3 mb-4">
            <div className="flex items-center justify-between mb-2">
              <span className="font-mono text-[10px] uppercase tracking-wide text-pb-faint">Page views per minute</span>
              <span className="font-mono text-[9px] text-pb-faintest">last 30 min · public pages</span>
            </div>
            <div className="flex items-end gap-[3px] h-12">
              {perMinute.map((p, i) => (
                <div key={i} className="flex-1 rounded-t"
                  style={{ height: `${Math.max(3, (p.views / pmMax) * 100)}%`,
                           background: p.views ? 'var(--pb-accent)' : 'var(--pb-surface2)',
                           opacity: p.views ? (0.55 + 0.45 * (p.views / pmMax)) : 1 }}
                  title={`${new Date(p.minute).toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' })} · ${p.views} views`} />
              ))}
            </div>
          </div>

          <div className="grid lg:grid-cols-3 gap-5">
            {/* Live page-view feed */}
            <div className="lg:col-span-2">
              <div className="flex items-center gap-2 mb-2">
                <h3 className="font-display font-bold text-[13px] text-pb-text uppercase tracking-wide">Live page views</h3>
                <Dot on={live} />
                <span className="font-mono text-[9px] text-pb-faintest">anonymous public traffic</span>
              </div>
              <div className="pb-card overflow-hidden">
                {recent.length === 0 && (
                  <div className="py-8 text-center font-mono text-[11px] text-pb-faint">No page views yet.</div>
                )}
                <div className="max-h-[520px] overflow-y-auto">
                  {recent.map((e, i) => {
                    const m = sourceMeta(e.source)
                    const isNew = (Date.now() - new Date(e.created_at).getTime()) < 15000
                    return (
                      <div key={`${e.created_at}-${i}`}
                        className={`flex items-center gap-2.5 px-3 py-2 ${i > 0 ? 'pb-hairline-t' : ''}`}>
                        <Dot on={isNew} />
                        <span className="font-mono text-[10px] text-pb-faintest w-14 shrink-0">{fmtAgo(e.created_at)}</span>
                        <div className="flex-1 min-w-0">
                          <div className="text-[13px] text-pb-text truncate">{e.label}</div>
                          <a href={e.page} target="_blank" rel="noopener noreferrer"
                            className="font-mono text-[10px] text-pb-faint hover:text-pb-accent hover:underline truncate block">
                            {e.page}
                            {e.utm_source && <span className="text-pb-accent"> · {e.utm_source}{e.utm_campaign ? `/${e.utm_campaign}` : ''}</span>}
                          </a>
                        </div>
                        <span className="inline-flex items-center gap-1 shrink-0" title={`Source: ${m.label}`}>
                          <span className="w-2 h-2 rounded-full" style={{ background: m.dot }} />
                          <span className="font-mono text-[9px] text-pb-faint hidden sm:inline">{m.label}</span>
                        </span>
                        <span className="font-mono text-[10px] text-pb-faint w-20 text-right truncate shrink-0"
                          title={[e.city, e.region, e.country].filter(Boolean).join(', ')}>
                          {e.country ? `${flagFor(e.country)} ${e.city || e.country}` : ''}
                        </span>
                        <span className="shrink-0 text-sm" title={[e.device?.os, e.device?.browser].filter(Boolean).join(' ')}>
                          {deviceIcon(e.device)}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>

            {/* Sources + UTM links (24h) */}
            <div className="space-y-5">
              <div>
                <h3 className="font-display font-bold text-[13px] text-pb-text uppercase tracking-wide mb-1">Sources</h3>
                <p className="font-mono text-[9px] text-pb-faintest mb-2">last 24 hours</p>
                <div className="pb-card px-3 py-2">
                  {sources.length === 0 && <div className="py-3 text-center font-mono text-[10px] text-pb-faint">No traffic yet.</div>}
                  {sources.map((s, i) => {
                    const m = sourceMeta(s.source)
                    return (
                      <div key={i} className="flex items-center gap-2 py-1">
                        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: m.dot }} />
                        <div className="w-20 truncate text-[12px] text-pb-text" title={m.label}>{m.label}</div>
                        <div className="flex-1 h-3 bg-pb-surface2 rounded overflow-hidden">
                          <div className="h-full rounded" style={{ width: `${Math.round((s.visitors / srcMax) * 100)}%`, background: m.dot }} />
                        </div>
                        <div className="w-12 text-right font-mono text-[10px] text-pb-faint">{s.visitors}</div>
                      </div>
                    )
                  })}
                </div>
              </div>

              <div>
                <h3 className="font-display font-bold text-[13px] text-pb-text uppercase tracking-wide mb-1">UTM links</h3>
                <p className="font-mono text-[9px] text-pb-faintest mb-2">last 24 hours</p>
                <div className="pb-card px-3 py-2">
                  {utms.length === 0 ? (
                    <div className="py-2 font-mono text-[10px] text-pb-faintest leading-relaxed">
                      No UTM-tagged links in the last 24h. Add <span className="text-pb-faint">?utm_source=…</span> to your share links.
                    </div>
                  ) : utms.map((u, i) => (
                    <div key={i} className="flex items-center gap-2 py-1">
                      <div className="flex-1 min-w-0">
                        <div className="font-mono text-[11px] text-pb-text truncate">
                          {u.utm_source}{u.utm_campaign ? <span className="text-pb-faint"> / {u.utm_campaign}</span> : ''}
                        </div>
                        {u.utm_medium && <div className="font-mono text-[9px] text-pb-faintest">{u.utm_medium}</div>}
                      </div>
                      <div className="text-right shrink-0">
                        <div className="font-mono text-[10px] text-pb-text">{u.visitors} ppl</div>
                        <div className="font-mono text-[9px] text-pb-faintest">{u.views} views</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// ─── Main page ───────────────────────────────────────────────────────────────

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
    setRoles(prev => prev.includes(value) ? prev.filter(r => r !== value) : [...prev, value])
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    const opts = { days, eventType: eventType || null, roles }
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
      setSummary(s); setVisitors(vis); setSeries(ts); setByFeature(feat)
      setByRole(brole); setByClub(bclub); setByLocation(bloc)
      setTopRoutes(r); setTopUsers(u); setRecent(e)
    } catch (err) {
      setError(err?.message || 'Failed to load usage data')
    } finally {
      setLoading(false)
    }
  }, [days, eventType, roles])

  useEffect(() => { load() }, [load])

  const seriesData = useMemo(() => series.points.map(p => ({
    label: fmtBucket(p.bucket, series.bucket),
    api: p.api_hits, pages: p.page_views, total: p.total,
  })), [series])

  const featureData = useMemo(() => byFeature.slice(0, 10), [byFeature])
  const roleData = useMemo(() => byRole.map((r, i) => ({
    name: ROLE_LABEL[r.role] || r.role, value: r.hits, fill: COLOURS[i % COLOURS.length],
  })), [byRole])

  return (
    <AdminLayout>
      <div className="max-w-6xl">
        <h1 className="font-display font-bold text-2xl text-pb-text mb-2">Usage Breadcrumbs</h1>
        <p className="text-pb-faint text-sm mb-5 leading-relaxed">
          Who's on the site right now, and what people are doing across BetterStats.
          IPs are stored as a truncated hash, not the raw address.
        </p>

        {/* Live realtime section (anonymous public traffic, auto-refreshing) */}
        <LiveSection />

        {/* ── Analytics (filtered) ─────────────────────────────────────── */}
        <h2 className="font-display font-bold text-sm text-pb-text uppercase tracking-wide mb-3 pt-2 pb-hairline-t">Analytics</h2>

        {/* Filters */}
        <div className="mb-5 space-y-2">
          <div className="flex flex-wrap gap-2 items-center">
            <span className="font-mono text-[10px] text-pb-faint uppercase tracking-wide w-14">Window</span>
            {WINDOW_OPTIONS.map(opt => (
              <button key={opt.value} onClick={() => setDays(opt.value)}
                className={`font-mono text-[10px] px-2.5 py-1 rounded border pb-hairline transition ${
                  days === opt.value ? 'bg-pb-accent text-pb-bg' : 'text-pb-faint hover:text-pb-text'}`}>
                {opt.label}
              </button>
            ))}
            <button onClick={load}
              className="ml-auto font-mono text-[10px] px-2.5 py-1 rounded border pb-hairline text-pb-faint hover:text-pb-text">
              Refresh
            </button>
          </div>
          <div className="flex flex-wrap gap-2 items-center">
            <span className="font-mono text-[10px] text-pb-faint uppercase tracking-wide w-14">Type</span>
            {EVENT_TYPES.map(opt => (
              <button key={opt.value || 'all'} onClick={() => setEventType(opt.value)}
                className={`font-mono text-[10px] px-2.5 py-1 rounded border pb-hairline transition ${
                  eventType === opt.value ? 'bg-pb-accent text-pb-bg' : 'text-pb-faint hover:text-pb-text'}`}>
                {opt.label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2 items-center">
            <span className="font-mono text-[10px] text-pb-faint uppercase tracking-wide w-14">Role</span>
            <button onClick={() => setRoles([])}
              className={`font-mono text-[10px] px-2.5 py-1 rounded border pb-hairline transition ${
                roles.length === 0 ? 'bg-pb-accent text-pb-bg' : 'text-pb-faint hover:text-pb-text'}`}>
              Everyone
            </button>
            {ROLE_OPTIONS.map(opt => {
              const active = roles.includes(opt.value)
              return (
                <button key={opt.value} onClick={() => toggleRole(opt.value)}
                  className={`font-mono text-[10px] px-2.5 py-1 rounded border pb-hairline transition flex items-center gap-1.5 ${
                    active ? 'bg-pb-accent text-pb-bg' : 'text-pb-faint hover:text-pb-text'}`}>
                  {active && <span className="text-[9px]">✓</span>}
                  {opt.label}
                </button>
              )
            })}
            {roles.length > 0 && (
              <span className="font-mono text-[9px] text-pb-faintest ml-1">{roles.length} selected</span>
            )}
          </div>
        </div>

        {error && (
          <div className="mb-4 font-mono text-[11px] text-pb-red bg-pb-red/10 border border-pb-red/30 rounded px-3 py-2">{error}</div>
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
        <Panel id="timeseries" title="Activity over time" sub={series.bucket === 'hour' ? 'per hour' : 'per day'}>
          <div className="pb-card p-4">
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
        </Panel>

        {/* Feature breakdown + role donut */}
        <Panel id="breakdown" title="Breakdown" sub="by feature & role">
          <div className="grid lg:grid-cols-3 gap-5">
            <div className="pb-card p-4 lg:col-span-2">
              <h3 className="font-display font-bold text-[13px] text-pb-text uppercase tracking-wide mb-2">By feature</h3>
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
              <h3 className="font-display font-bold text-[13px] text-pb-text uppercase tracking-wide mb-2">By role</h3>
              <p className="font-mono text-[9px] text-pb-faintest mb-2">Overall split — ignores the role filter above.</p>
              <div style={{ width: '100%', height: 240 }}>
                {roleData.length === 0 ? (
                  <div className="h-full flex items-center justify-center font-mono text-[11px] text-pb-faint">
                    {loading ? 'Loading…' : 'No data.'}
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={roleData} dataKey="value" nameKey="name" innerRadius={40} outerRadius={75} paddingAngle={2}>
                        {roleData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                      </Pie>
                      <Tooltip content={<ChartTooltip />} />
                      <Legend wrapperStyle={{ fontSize: 10, fontFamily: 'monospace', color: 'var(--pb-faint)' }} iconSize={8} />
                    </PieChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>
          </div>
        </Panel>

        {/* By club */}
        <Panel id="byclub" title="By club" sub="page views attributed via the public URL">
          <div className="pb-card p-4">
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
                          {c.club_slug ? <span className="text-pb-text">{c.club_name}</span>
                            : <span className="text-pb-faintest italic">{c.club_name}</span>}
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
        </Panel>

        {/* Top routes + top users */}
        <Panel id="toproutes" title="Top routes & users">
          <div className="grid md:grid-cols-2 gap-5">
            <div>
              <h3 className="font-display font-bold text-[13px] text-pb-text mb-2 uppercase tracking-wide">Top routes</h3>
              <div className="pb-card overflow-hidden">
                {loading && !topRoutes.length && <div className="p-6 text-center font-mono text-[11px] text-pb-faint">Loading…</div>}
                {!loading && !topRoutes.length && <div className="p-6 text-center font-mono text-[11px] text-pb-faint">No data in window.</div>}
                {topRoutes.map((r, i) => (
                  <div key={`${r.event_type}:${r.route}:${i}`} className={`flex items-center gap-3 px-4 py-2 ${i > 0 ? 'pb-hairline-t' : ''}`}>
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
              <h3 className="font-display font-bold text-[13px] text-pb-text mb-2 uppercase tracking-wide">Top users</h3>
              <div className="pb-card overflow-hidden">
                {loading && !topUsers.length && <div className="p-6 text-center font-mono text-[11px] text-pb-faint">Loading…</div>}
                {!loading && !topUsers.length && <div className="p-6 text-center font-mono text-[11px] text-pb-faint">No data in window.</div>}
                {topUsers.map((u, i) => (
                  <div key={u.user_id || i} className={`flex items-center gap-3 px-4 py-2 ${i > 0 ? 'pb-hairline-t' : ''}`}>
                    <div className="flex-1 min-w-0">
                      <div className="text-pb-text text-sm truncate flex items-center gap-2">
                        {userLabel(u)}
                        <RoleBadge role={u.user_role} />
                      </div>
                      <div className="font-mono text-[9px] text-pb-faintest">{u.unique_routes} routes · last {fmtTime(u.last_hit)}</div>
                    </div>
                    <div className="font-mono text-[11px] text-pb-text shrink-0">{fmtNum(u.hits)}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Panel>

        {/* By location */}
        <Panel id="geo" title="Geography" sub="top countries & cities">
          <div className="grid md:grid-cols-2 gap-5">
            <div>
              <h3 className="font-display font-bold text-[13px] text-pb-text mb-2 uppercase tracking-wide">By country</h3>
              <div className="pb-card overflow-hidden">
                {loading && !byLocation.by_country.length && <div className="p-6 text-center font-mono text-[11px] text-pb-faint">Loading…</div>}
                {!loading && !byLocation.by_country.length && (
                  <div className="p-6 text-center font-mono text-[11px] text-pb-faint">
                    No geo data yet. Cloudflare populates country on every request.
                  </div>
                )}
                {byLocation.by_country.map((row, i) => (
                  <div key={row.country || `none-${i}`} className={`flex items-center gap-3 px-4 py-2 ${i > 0 ? 'pb-hairline-t' : ''}`}>
                    <span className="text-base shrink-0 w-6">{flagFor(row.country)}</span>
                    <div className="flex-1 min-w-0">
                      <div className="font-mono text-[11px] text-pb-text truncate">{row.country || 'Unknown'}</div>
                      <div className="font-mono text-[9px] text-pb-faintest">{row.unique_ips} unique IPs</div>
                    </div>
                    <div className="font-mono text-[11px] text-pb-text shrink-0">{fmtNum(row.hits)}</div>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h3 className="font-display font-bold text-[13px] text-pb-text mb-2 uppercase tracking-wide">By city</h3>
              <div className="pb-card overflow-hidden">
                {loading && !byLocation.by_city.length && <div className="p-6 text-center font-mono text-[11px] text-pb-faint">Loading…</div>}
                {!loading && !byLocation.by_city.length && (
                  <div className="p-6 text-center font-mono text-[11px] text-pb-faint">
                    City lookups (via ip-api.com) fill in shortly after each visit.
                  </div>
                )}
                {byLocation.by_city.map((row, i) => (
                  <div key={`${row.city}-${row.region}-${row.country}-${i}`} className={`flex items-center gap-3 px-4 py-2 ${i > 0 ? 'pb-hairline-t' : ''}`}>
                    <span className="text-base shrink-0 w-6">{flagFor(row.country)}</span>
                    <div className="flex-1 min-w-0">
                      <div className="font-mono text-[11px] text-pb-text truncate">
                        {row.city}{row.region && <span className="text-pb-faint">, {row.region}</span>}
                      </div>
                      <div className="font-mono text-[9px] text-pb-faintest">{row.unique_ips} unique IPs</div>
                    </div>
                    <div className="font-mono text-[11px] text-pb-text shrink-0">{fmtNum(row.hits)}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Panel>

        {/* Recent events */}
        <Panel id="recent" title="Recent events" sub="full event log (matches the filters)">
          <div className="pb-card overflow-hidden">
            {loading && !recent.length && <div className="p-6 text-center font-mono text-[11px] text-pb-faint">Loading…</div>}
            {!loading && !recent.length && <div className="p-6 text-center font-mono text-[11px] text-pb-faint">No events.</div>}
            {recent.map((r, i) => (
              <div key={r.id} className={`flex items-center gap-3 px-4 py-2 ${i > 0 ? 'pb-hairline-t' : ''}`}>
                <TypeBadge type={r.event_type} />
                <span className="font-mono text-[10px] text-pb-faintest shrink-0 w-24">{fmtTime(r.created_at)}</span>
                <StatusBadge status={r.status} />
                <span className="font-mono text-[10px] text-pb-faint shrink-0 w-12">{r.method}</span>
                <div className="flex-1 min-w-0">
                  {r.target_name && r.target_url ? (
                    <a href={r.target_url} target="_blank" rel="noopener noreferrer"
                      className="text-pb-accent hover:underline text-[12px] truncate block" title={r.path}>{r.target_name}</a>
                  ) : r.event_type === 'page_view' && r.path ? (
                    <a href={r.path} target="_blank" rel="noopener noreferrer"
                      className="font-mono text-[10px] text-pb-text hover:text-pb-accent hover:underline truncate block">{r.path}</a>
                  ) : (
                    <span className="font-mono text-[10px] text-pb-text truncate block" title={r.path}>{r.path}</span>
                  )}
                </div>
                <span className="text-xs shrink-0 w-20 text-right truncate"
                  title={[r.city, r.region, r.country].filter(Boolean).join(', ') || 'Unknown'}>
                  {r.country ? (
                    <span className="font-mono text-pb-faint">{flagFor(r.country)} {r.city || r.country}</span>
                  ) : <span className="font-mono text-[10px] text-pb-faintest">—</span>}
                </span>
                <span className="font-mono text-[10px] text-pb-faint shrink-0 w-28 text-right truncate flex items-center justify-end gap-1.5">
                  {r.user_id ? (<><span className="truncate">{userLabel(r)}</span><RoleBadge role={r.user_role} /></>) : 'anon'}
                </span>
                <span className="font-mono text-[9px] text-pb-faintest shrink-0 w-12 text-right">
                  {r.duration_ms != null ? `${r.duration_ms}ms` : ''}
                </span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </AdminLayout>
  )
}
