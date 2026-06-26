import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  BarChart, Bar, PieChart, Pie, Cell, Legend,
} from 'recharts'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

// Visitors & Leads — reoriented around the people on the site, not the request
// log. Default view is the last 24h of anonymous page views; the noisier
// telemetry (API hits, charts, geography, raw log) is tucked into collapsible
// sections that stay shut until you open them.

const WINDOW_OPTIONS = [
  { value: 1,   label: '24h' },
  { value: 7,   label: '7d'  },
  { value: 30,  label: '30d' },
  { value: 90,  label: '90d' },
]

const ROLE_LABEL = {
  super_admin: 'Super', club_admin: 'Admin', club_member: 'Member', anon: 'Anon',
}

// Source bucket → display label + dot colour. Falls back to the raw value.
const SOURCE_STYLE = {
  facebook:    { label: 'Facebook',     dot: '#1877f2' },
  instagram:   { label: 'Instagram',    dot: '#e1306c' },
  google:      { label: 'Google',       dot: '#ea4335' },
  bing:        { label: 'Bing',         dot: '#0c8484' },
  email:       { label: 'Email',        dot: '#f59e0b' },
  twitter:     { label: 'X / Twitter',  dot: '#1d9bf0' },
  linkedin:    { label: 'LinkedIn',     dot: '#0a66c2' },
  tiktok:      { label: 'TikTok',       dot: '#ff0050' },
  youtube:     { label: 'YouTube',      dot: '#ff0000' },
  whatsapp:    { label: 'WhatsApp',     dot: '#25d366' },
  reddit:      { label: 'Reddit',       dot: '#ff4500' },
  playhq:      { label: 'PlayHQ',       dot: '#7c3aed' },
  playcricket: { label: 'Play-Cricket', dot: '#1e9e57' },
  direct:      { label: 'Direct',       dot: 'var(--pb-faint)' },
}

function sourceMeta(s) {
  const key = (s || 'direct').toLowerCase()
  return SOURCE_STYLE[key] || { label: s, dot: 'var(--pb-accent)' }
}

const COLOURS = [
  'var(--pb-accent)', '#3b82f6', '#a855f7', '#f59e0b', '#ec4899',
  '#22d3ee', '#84cc16', '#ef4444', '#64748b',
]

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
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  const m = s / 60; if (m < 60) return `${Math.floor(m)}m ago`
  const h = m / 60; if (h < 24) return `${Math.floor(h)}h ago`
  const d = h / 24; if (d < 30) return `${Math.floor(d)}d ago`
  return new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })
}

function fmtNum(n) {
  if (n == null) return '0'
  if (n >= 10000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k'
  return String(n)
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

function deviceLabel(d) {
  if (!d) return ''
  return [d.os, d.browser].filter(Boolean).join(' · ')
}

function locationLabel(row) {
  const bits = [row.city, row.region].filter(Boolean)
  const place = bits.length ? bits[0] : (row.country || '')
  return `${flagFor(row.country)} ${place}`.trim()
}

// ─── Small badges ────────────────────────────────────────────────────────────

function Pill({ children, tone = 'faint', title }) {
  const cls = {
    accent: 'text-pb-accent', amber: 'text-pb-amber', red: 'text-pb-red',
    text: 'text-pb-text', faint: 'text-pb-faint', faintest: 'text-pb-faintest',
  }[tone] || 'text-pb-faint'
  return (
    <span title={title}
      className={`font-mono text-[8px] uppercase tracking-wide px-1.5 py-0.5 rounded border pb-hairline ${cls}`}>
      {children}
    </span>
  )
}

function ReturningBadge({ returning }) {
  return returning
    ? <Pill tone="accent" title="Seen before this window">returning</Pill>
    : <Pill tone="faintest" title="First seen in this window">new</Pill>
}

function IntentBadges({ contact, pricing }) {
  if (!contact && !pricing) return null
  return (
    <>
      {pricing && <Pill tone="amber" title="Viewed the pricing page">pricing</Pill>}
      {contact && <Pill tone="accent" title="Viewed the contact page">contact</Pill>}
    </>
  )
}

function SourceBadge({ source }) {
  const m = sourceMeta(source)
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-[10px] text-pb-faint" title={`Source: ${m.label}`}>
      <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ background: m.dot }} />
      {m.label}
    </span>
  )
}

function ClubChip({ club }) {
  if (!club) return <span className="font-mono text-[10px] text-pb-faintest">club unknown</span>
  const conf = club.source === 'utm'
    ? 'via UTM'
    : club.confidence != null ? `${club.confidence}%` : ''
  return (
    <span className="inline-flex items-center gap-1.5 min-w-0" title={club.source === 'utm'
      ? `Matched their UTM code to ${club.name}`
      : `${club.confidence}% of their club page views were ${club.name}`}>
      <span className="truncate text-pb-text text-[12px]">{club.name}</span>
      {conf && <span className="font-mono text-[9px] text-pb-faintest shrink-0">{conf}</span>}
    </span>
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

const LEAD_STATUS_TONE = {
  new: 'accent', contacted: 'amber', onboarded: 'text', closed: 'faintest',
}

// ─── Collapsible, lazy-loading section ───────────────────────────────────────

function usePersistentOpen(id, defaultOpen) {
  const [open, setOpen] = useState(() => {
    try {
      const v = localStorage.getItem('bsUsageSec:' + id)
      return v == null ? defaultOpen : v === '1'
    } catch { return defaultOpen }
  })
  const toggle = useCallback(() => setOpen(o => {
    const n = !o
    try { localStorage.setItem('bsUsageSec:' + id, n ? '1' : '0') } catch { /* ignore */ }
    return n
  }), [id])
  return [open, toggle]
}

// Renders a collapsible card. The loader only runs while the section is open,
// and re-runs when `deps` change (the window/filters) — so collapsed sections
// cost nothing and the default lead view stays fast.
function Section({ id, title, subtitle, defaultOpen = false, deps = [], load, right, children }) {
  const [open, toggle] = usePersistentOpen(id, defaultOpen)
  const [state, setState] = useState({ data: null, loading: false, error: null })
  const depKey = JSON.stringify(deps)
  useEffect(() => {
    if (!open || !load) return
    let alive = true
    setState(s => ({ data: s.data, loading: true, error: null }))
    Promise.resolve().then(load)
      .then(d => { if (alive) setState({ data: d, loading: false, error: null }) })
      .catch(e => { if (alive) setState({ data: null, loading: false, error: e?.message || 'Failed to load' }) })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, depKey])

  return (
    <div className="pb-card mb-3 overflow-hidden">
      <button onClick={toggle}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-pb-surface2/30 transition">
        <span className="font-mono text-pb-faint text-xs w-3 shrink-0">{open ? '▾' : '▸'}</span>
        <div className="flex-1 min-w-0">
          <h2 className="font-display font-bold text-sm text-pb-text uppercase tracking-wide">{title}</h2>
          {subtitle && <p className="font-mono text-[10px] text-pb-faintest mt-0.5">{subtitle}</p>}
        </div>
        {state.loading && <span className="font-mono text-[9px] text-pb-faintest shrink-0">loading…</span>}
        {right}
      </button>
      {open && (
        <div className="px-4 pb-4 pt-1 pb-hairline-t">
          {state.error
            ? <div className="py-4 font-mono text-[11px] text-pb-red">{state.error}</div>
            : children(state)}
        </div>
      )}
    </div>
  )
}

function Empty({ loading, children = 'No data in window.' }) {
  return <div className="py-6 text-center font-mono text-[11px] text-pb-faint">{loading ? 'Loading…' : children}</div>
}

// ─── Visitor row (shared by the Visitors + Warm lists) ───────────────────────

function VisitorRow({ v, onOpen }) {
  return (
    <button onClick={() => onOpen(v.vkey)}
      className="w-full text-left px-3 py-2.5 pb-hairline-t first:border-t-0 hover:bg-pb-surface2/40 transition">
      <div className="flex items-center gap-2.5">
        <span className="text-base shrink-0" title={deviceLabel(v.device)}>{deviceIcon(v.device)}</span>
        <div className="flex-1 min-w-0">
          {/* Line 1: club + intent + returning */}
          <div className="flex items-center gap-2 min-w-0">
            <span className="min-w-0 flex-1"><ClubChip club={v.club} /></span>
            <span className="flex items-center gap-1 shrink-0">
              <IntentBadges contact={v.hit_contact} pricing={v.hit_pricing} />
              <ReturningBadge returning={v.returning} />
            </span>
          </div>
          {/* Line 2: source · location · activity */}
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <SourceBadge source={v.traffic_source} />
            {v.utm_campaign && (
              <span className="font-mono text-[9px] text-pb-faintest truncate max-w-[140px]" title={`Campaign: ${v.utm_campaign}`}>
                ✦ {v.utm_campaign}
              </span>
            )}
            {(v.city || v.country) && (
              <span className="font-mono text-[9px] text-pb-faint truncate max-w-[140px]">{locationLabel(v)}</span>
            )}
            <span className="font-mono text-[9px] text-pb-faintest">
              👁 {fmtNum(v.page_views)} {v.page_views === 1 ? 'page' : 'pages'}
              {v.sessions > 1 ? ` · ${v.sessions} visits` : ''}
              {v.active_days > 1 ? ` · ${v.active_days}d` : ''}
            </span>
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div className="font-mono text-[10px] text-pb-faint">{fmtAgo(v.last_seen)}</div>
          {!v.is_known_visitor && (
            <div className="font-mono text-[8px] text-pb-faintest" title="Identified by IP hash only (older visit)">ip-only</div>
          )}
        </div>
      </div>
    </button>
  )
}

// ─── Visitor drill-down modal ────────────────────────────────────────────────

function VisitorModal({ vkey, onClose }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    setLoading(true); setError(null); setData(null)
    api.adminUsageVisitorDetail(vkey)
      .then(d => { if (alive) setData(d) })
      .catch(e => { if (alive) setError(e?.message || 'Failed to load visitor') })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [vkey])

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const s = data?.summary

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50" />
      <div className="relative w-full max-w-lg h-full bg-pb-bg border-l pb-hairline overflow-y-auto shadow-2xl"
        onClick={e => e.stopPropagation()}>
        <div className="sticky top-0 bg-pb-bg/95 backdrop-blur border-b pb-hairline px-4 py-3 flex items-center gap-3 z-10">
          <span className="text-lg">{deviceIcon(s?.device)}</span>
          <div className="flex-1 min-w-0">
            <h3 className="font-display font-bold text-sm text-pb-text">Visitor profile</h3>
            <p className="font-mono text-[9px] text-pb-faintest truncate">
              {s?.is_known_visitor ? vkey : `${vkey} (IP-only)`}
            </p>
          </div>
          <button onClick={onClose}
            className="font-mono text-[11px] text-pb-faint hover:text-pb-text px-2 py-1 rounded border pb-hairline">
            Close
          </button>
        </div>

        <div className="p-4 space-y-4">
          {error && <div className="font-mono text-[11px] text-pb-red">{error}</div>}
          {loading && <Empty loading>Loading visitor…</Empty>}

          {s && (
            <>
              {/* Summary grid */}
              <div className="grid grid-cols-2 gap-2">
                {[
                  { label: 'Page views', value: fmtNum(s.page_views) },
                  { label: 'First seen', value: fmtTime(s.first_seen) },
                  { label: 'Last seen', value: fmtAgo(s.last_seen) },
                  { label: 'Source', value: sourceMeta(s.traffic_source).label },
                  { label: 'Device', value: [s.device?.type, s.device?.os, s.device?.browser].filter(Boolean).join(' · ') || '—' },
                  { label: 'Location', value: [s.city, s.region, s.country].filter(Boolean).join(', ') || '—' },
                ].map(c => (
                  <div key={c.label} className="pb-card px-3 py-2">
                    <div className="font-mono text-[8px] uppercase tracking-wide text-pb-faint">{c.label}</div>
                    <div className="text-[12px] text-pb-text truncate" title={String(c.value)}>{c.value}</div>
                  </div>
                ))}
              </div>

              {(s.utm_source || s.utm_campaign || s.click_id || s.landing_path) && (
                <div className="pb-card px-3 py-2 space-y-1">
                  <div className="font-mono text-[8px] uppercase tracking-wide text-pb-faint mb-1">Acquisition</div>
                  {s.landing_path && <Row k="Landed on" v={s.landing_path} />}
                  {s.utm_source && <Row k="utm_source" v={s.utm_source} />}
                  {s.utm_medium && <Row k="utm_medium" v={s.utm_medium} />}
                  {s.utm_campaign && <Row k="utm_campaign" v={s.utm_campaign} />}
                  {s.click_id && <Row k="click id" v={s.click_id} />}
                </div>
              )}

              {/* Linked enquiry — "have we talked to them?" */}
              {data.leads?.length > 0 && (
                <div>
                  <h4 className="font-display font-bold text-[11px] uppercase tracking-wide text-pb-accent mb-1.5">
                    Enquiry on file
                  </h4>
                  <div className="space-y-2">
                    {data.leads.map(ld => (
                      <div key={ld.id} className="pb-card px-3 py-2"
                        style={{ background: 'color-mix(in srgb, var(--pb-accent) 6%, transparent)' }}>
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-pb-text text-sm font-medium">{ld.name}</span>
                          <Pill tone={LEAD_STATUS_TONE[ld.status] || 'faint'}>{ld.status}</Pill>
                          <Pill tone="faintest" title={ld.match === 'id' ? 'Matched by visitor id' : 'Matched by device fingerprint'}>
                            {ld.match === 'id' ? 'linked' : 'likely'}
                          </Pill>
                          <span className="font-mono text-[9px] text-pb-faintest ml-auto">{fmtAgo(ld.created_at)}</span>
                        </div>
                        <div className="font-mono text-[10px] text-pb-faint space-y-0.5">
                          <div>{ld.club}{ld.association ? ` · ${ld.association}` : ''}</div>
                          <div>{ld.email}{ld.phone ? ` · ${ld.phone}` : ''}</div>
                          {ld.message && <div className="text-pb-faintest italic mt-1">“{ld.message}”</div>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Clubs browsed */}
              {data.clubs?.length > 0 && (
                <div>
                  <h4 className="font-display font-bold text-[11px] uppercase tracking-wide text-pb-text mb-1.5">
                    Clubs browsed
                  </h4>
                  <div className="space-y-1">
                    {data.clubs.map(c => (
                      <div key={c.club_slug} className="flex items-center gap-2 text-[12px]">
                        <a href={`/${c.club_slug}`} target="_blank" rel="noopener noreferrer"
                          className="text-pb-accent hover:underline flex-1 truncate">{c.club_name}</a>
                        <span className="font-mono text-[9px] text-pb-faintest">
                          {fmtNum(c.page_views)} views · {fmtAgo(c.last_seen)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Journey */}
              <div>
                <h4 className="font-display font-bold text-[11px] uppercase tracking-wide text-pb-text mb-1.5">
                  Page journey <span className="text-pb-faintest font-mono normal-case">({data.events.length})</span>
                </h4>
                <div className="pb-card overflow-hidden">
                  {data.events.length === 0 && <Empty>No page views.</Empty>}
                  {data.events.map((e, i) => (
                    <div key={e.id} className={`flex items-start gap-2 px-3 py-1.5 ${i > 0 ? 'pb-hairline-t' : ''}`}>
                      <span className="font-mono text-[9px] text-pb-faintest shrink-0 w-16 pt-0.5">{fmtAgo(e.created_at)}</span>
                      <div className="flex-1 min-w-0">
                        {e.target_name && e.target_url ? (
                          <a href={e.target_url} target="_blank" rel="noopener noreferrer"
                            className="text-pb-accent hover:underline text-[12px] truncate block" title={e.path}>
                            {e.target_name}
                          </a>
                        ) : (
                          <a href={e.path} target="_blank" rel="noopener noreferrer"
                            className="font-mono text-[10px] text-pb-text hover:text-pb-accent hover:underline truncate block">
                            {e.path}
                          </a>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function Row({ k, v }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="font-mono text-[9px] text-pb-faintest shrink-0 w-20">{k}</span>
      <span className="font-mono text-[10px] text-pb-text truncate" title={String(v)}>{v}</span>
    </div>
  )
}

// ─── Charts (secondary sections) ─────────────────────────────────────────────

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

function fmtBucket(iso, bucket) {
  if (!iso) return ''
  const d = new Date(iso)
  if (bucket === 'hour') return d.toLocaleTimeString('en-AU', { hour: 'numeric' })
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })
}

// ─── Main page ───────────────────────────────────────────────────────────────

export default function AdminUsage() {
  const [days, setDays] = useState(1)        // default 24h
  const [anonOnly, setAnonOnly] = useState(true)
  const [nonce, setNonce] = useState(0)
  const [drillVkey, setDrillVkey] = useState(null)

  // KPI strip (always visible).
  const [kpi, setKpi] = useState({ summary: null, visitors: null })
  const [kpiLoading, setKpiLoading] = useState(true)

  const roles = useMemo(() => (anonOnly ? ['anon'] : []), [anonOnly])

  useEffect(() => {
    let alive = true
    setKpiLoading(true)
    Promise.all([
      api.adminUsageVisitors({ days, eventType: 'page_view', anonOnly }),
      api.adminUsageSummary({ days, roles, eventType: 'page_view' }),
    ]).then(([visitors, summary]) => {
      if (alive) setKpi({ visitors, summary })
    }).catch(() => {
      if (alive) setKpi({ summary: null, visitors: null })
    }).finally(() => { if (alive) setKpiLoading(false) })
    return () => { alive = false }
  }, [days, anonOnly, roles, nonce])

  const refresh = () => setNonce(n => n + 1)

  const v = kpi.visitors
  const kpiCards = v ? [
    { label: 'Visitors', value: fmtNum(v.visitors), hint: 'unique people' },
    { label: 'Returning', value: fmtNum(v.returning), hint: `${v.returning_pct}% seen before` },
    { label: 'New', value: fmtNum(v.new), hint: 'first time' },
    { label: 'High intent', value: fmtNum(v.high_intent), hint: 'contact / pricing', accent: true },
    { label: 'Multi-day', value: fmtNum(v.multi_day), hint: '≥2 days active' },
    { label: 'Page views', value: fmtNum(kpi.summary?.page_views ?? 0), hint: 'this window' },
  ] : []

  return (
    <AdminLayout>
      <div className="max-w-6xl">
        <h1 className="font-display font-bold text-2xl text-pb-text mb-1">Visitors &amp; Leads</h1>
        <p className="text-pb-faint text-sm mb-4 leading-relaxed">
          See who's been on the site, where they came from, and the club they're likely tied to.
          The default view is anonymous page views from the last 24 hours, the lead-capture lens.
          IPs are hashed before they're stored.
        </p>

        {/* Filter bar */}
        <div className="mb-4 flex flex-wrap gap-2 items-center">
          <span className="font-mono text-[10px] text-pb-faint uppercase tracking-wide">Window</span>
          {WINDOW_OPTIONS.map(opt => (
            <button key={opt.value} onClick={() => setDays(opt.value)}
              className={`font-mono text-[10px] px-2.5 py-1 rounded border pb-hairline transition ${
                days === opt.value ? 'bg-pb-accent text-pb-bg' : 'text-pb-faint hover:text-pb-text'}`}>
              {opt.label}
            </button>
          ))}
          <span className="w-px h-4 bg-pb-hairline mx-1" />
          <button onClick={() => setAnonOnly(a => !a)}
            className={`font-mono text-[10px] px-2.5 py-1 rounded border pb-hairline transition flex items-center gap-1.5 ${
              anonOnly ? 'bg-pb-accent text-pb-bg' : 'text-pb-faint hover:text-pb-text'}`}
            title="Hide logged-in admins/members; show only anonymous visitors">
            {anonOnly && <span className="text-[9px]">✓</span>}
            Anonymous only
          </button>
          <button onClick={refresh}
            className="ml-auto font-mono text-[10px] px-2.5 py-1 rounded border pb-hairline text-pb-faint hover:text-pb-text">
            Refresh
          </button>
        </div>

        {/* KPI strip */}
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 mb-5">
          {(kpiCards.length ? kpiCards : Array.from({ length: 6 }, (_, i) => ({ label: '—', value: '—', key: i }))).map(c => (
            <div key={c.label === '—' ? c.key : c.label} className="pb-card px-3 py-2"
              style={c.accent ? { background: 'color-mix(in srgb, var(--pb-accent) 8%, transparent)' } : undefined}>
              <div className="font-mono text-[9px] uppercase tracking-wide text-pb-faint">{c.label}</div>
              <div className="font-display text-xl text-pb-text">{kpiLoading && !v ? '·' : c.value}</div>
              {c.hint && <div className="font-mono text-[9px] text-pb-faintest mt-0.5">{c.hint}</div>}
            </div>
          ))}
        </div>

        {/* ── Leads (enquiries) ─────────────────────────────────────────── */}
        <Section id="leads" title="Leads — onboarding enquiries" defaultOpen
          subtitle="Contact-form enquiries, newest first, with the browsing behind each. Last 90 days."
          deps={[nonce]}
          load={() => api.adminUsageLeads({ days: 90, limit: 200 })}>
          {({ data, loading }) => <LeadsPanel data={data} loading={loading} onOpen={setDrillVkey} />}
        </Section>

        {/* ── Warm visitors (intent, longer window) ─────────────────────── */}
        <Section id="warm" title="Warm visitors — viewed pricing or contact" defaultOpen
          subtitle="Anonymous visitors who showed buying intent but haven't enquired yet. Last 30 days."
          deps={[Math.max(days, 30), nonce]}
          load={() => api.adminUsageVisitorsList({ days: Math.max(days, 30), anonOnly: true, intentOnly: true, sort: 'recent', limit: 60 })}>
          {({ data, loading }) => (
            <VisitorList data={data} loading={loading} onOpen={setDrillVkey}
              empty="No pricing or contact views yet in this window." />
          )}
        </Section>

        {/* ── Visitors (main table) ─────────────────────────────────────── */}
        <Section id="visitors" title="Visitors" defaultOpen
          subtitle="Everyone on the site in the window with their likely club, source and returning status. Click a row for the full journey."
          deps={[days, anonOnly, nonce]}
          load={() => api.adminUsageVisitorsList({ days, anonOnly, sort: 'intent', limit: 150 })}>
          {({ data, loading }) => <VisitorList data={data} loading={loading} onOpen={setDrillVkey} />}
        </Section>

        {/* ── Traffic sources ───────────────────────────────────────────── */}
        <Section id="sources" title="Traffic sources" defaultOpen
          subtitle="Where visitors come from (first touch) and the UTM campaigns driving them."
          deps={[days, anonOnly, nonce]}
          load={() => api.adminUsageSources({ days, anonOnly })}>
          {({ data, loading }) => <SourcesPanel data={data} loading={loading} />}
        </Section>

        {/* ── Secondary: collapsed by default ───────────────────────────── */}

        <Section id="timeseries" title="Activity over time"
          subtitle="Page views per bucket."
          deps={[days, anonOnly, nonce]}
          load={() => api.adminUsageTimeseries({ days, roles, eventType: 'page_view' })}>
          {({ data, loading }) => <TimeseriesPanel series={data} loading={loading} />}
        </Section>

        <Section id="byclub" title="By club"
          subtitle="Page views attributed to each club via the public URL."
          deps={[days, anonOnly, nonce]}
          load={() => api.adminUsageByClub({ days, roles, eventType: 'page_view' })}>
          {({ data, loading }) => <ByClubPanel rows={data} loading={loading} />}
        </Section>

        <Section id="pages" title="Top pages"
          subtitle="Most-viewed pages and feature areas."
          deps={[days, anonOnly, nonce]}
          load={() => Promise.all([
            api.adminUsageTopRoutes({ days, roles, eventType: 'page_view', limit: 20 }),
            api.adminUsageByFeature({ days, roles, eventType: 'page_view' }),
          ]).then(([routes, feature]) => ({ routes, feature }))}>
          {({ data, loading }) => <PagesPanel data={data} loading={loading} />}
        </Section>

        <Section id="geo" title="Geography"
          subtitle="Top countries and cities."
          deps={[days, anonOnly, nonce]}
          load={() => api.adminUsageByLocation({ days, roles, eventType: 'page_view' })}>
          {({ data, loading }) => <GeoPanel data={data} loading={loading} />}
        </Section>

        <Section id="people" title="Signed-in users &amp; roles"
          subtitle="Role split and the most active logged-in users."
          deps={[days, nonce]}
          load={() => Promise.all([
            api.adminUsageByRole({ days, eventType: 'page_view' }),
            api.adminUsageTopUsers({ days, roles: [], limit: 20 }),
          ]).then(([byRole, topUsers]) => ({ byRole, topUsers }))}>
          {({ data, loading }) => <PeoplePanel data={data} loading={loading} />}
        </Section>

        <Section id="raw" title="Raw event log"
          subtitle="The unrolled breadcrumb stream (API + pages)."
          deps={[nonce]}
          load={() => api.adminUsageRecent({ limit: 100 })}>
          {({ data, loading }) => <RawLogPanel rows={data} loading={loading} />}
        </Section>
      </div>

      {drillVkey && <VisitorModal vkey={drillVkey} onClose={() => setDrillVkey(null)} />}
    </AdminLayout>
  )
}

// ─── Panels ──────────────────────────────────────────────────────────────────

function VisitorList({ data, loading, onOpen, empty }) {
  if (!data?.length) return <Empty loading={loading}>{empty || 'No visitors in window.'}</Empty>
  return (
    <div className="-mx-1">
      {data.map(v => <VisitorRow key={v.vkey} v={v} onOpen={onOpen} />)}
    </div>
  )
}

function LeadsPanel({ data, loading, onOpen }) {
  const [filter, setFilter] = useState('all')
  if (!data?.leads) return <Empty loading={loading}>No enquiries.</Empty>
  const counts = data.status_counts || {}
  const total = data.leads.length
  const shown = filter === 'all' ? data.leads : data.leads.filter(l => l.status === filter)
  const chips = [
    { value: 'all', label: `All ${total}` },
    { value: 'new', label: `New ${counts.new || 0}` },
    { value: 'contacted', label: `Contacted ${counts.contacted || 0}` },
    { value: 'onboarded', label: `Onboarded ${counts.onboarded || 0}` },
    { value: 'closed', label: `Closed ${counts.closed || 0}` },
  ]
  return (
    <div>
      <div className="flex flex-wrap gap-1.5 mb-3">
        {chips.map(c => (
          <button key={c.value} onClick={() => setFilter(c.value)}
            className={`font-mono text-[10px] px-2 py-0.5 rounded border pb-hairline transition ${
              filter === c.value ? 'bg-pb-accent text-pb-bg' : 'text-pb-faint hover:text-pb-text'}`}>
            {c.label}
          </button>
        ))}
        <a href="/admin/super/onboarding"
          className="ml-auto font-mono text-[10px] px-2 py-0.5 rounded border pb-hairline text-pb-faint hover:text-pb-text">
          Manage →
        </a>
      </div>
      {shown.length === 0
        ? <Empty>No enquiries with this status.</Empty>
        : <div className="space-y-2">{shown.map(l => <LeadCard key={l.id} lead={l} onOpen={onOpen} />)}</div>}
    </div>
  )
}

function LeadCard({ lead, onOpen }) {
  const [open, setOpen] = useState(false)
  const b = lead.browsing
  return (
    <div className="pb-card overflow-hidden">
      <div className="px-3 py-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-pb-text text-sm font-medium">{lead.name}</span>
          <Pill tone={LEAD_STATUS_TONE[lead.status] || 'faint'}>{lead.status}</Pill>
          {b?.hit_pricing && <Pill tone="amber">viewed pricing</Pill>}
          <span className="font-mono text-[9px] text-pb-faintest ml-auto">{fmtAgo(lead.created_at)}</span>
        </div>
        <div className="font-mono text-[10px] text-pb-faint mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
          <span className="text-pb-text">{lead.club}</span>
          {lead.association && <span>{lead.association}</span>}
          <a href={`mailto:${lead.email}`} className="text-pb-accent hover:underline">{lead.email}</a>
          {lead.phone && <span>{lead.phone}</span>}
        </div>
        {/* Browsing summary — the cross-reference to anonymous activity */}
        <div className="mt-1.5 flex items-center gap-2 flex-wrap">
          {b ? (
            <>
              <SourceBadge source={b.traffic_source} />
              <span className="font-mono text-[9px] text-pb-faintest">
                👁 {fmtNum(b.page_views)} pages · {b.distinct_paths} unique
                {b.active_days > 1 ? ` · ${b.active_days}d` : ''}
              </span>
              {b.browsed_club && b.browsed_club !== lead.club && (
                <span className="font-mono text-[9px] text-pb-amber" title="The club they browsed differs from the club they typed">
                  browsed {b.browsed_club}
                </span>
              )}
              <button onClick={() => onOpen(b.vkey)}
                className="font-mono text-[9px] text-pb-accent hover:underline">view journey →</button>
            </>
          ) : (
            <span className="font-mono text-[9px] text-pb-faintest italic">
              {lead.has_visitor ? 'Browsing not found in window' : 'No browsing linked (pre-dates visitor tracking)'}
            </span>
          )}
          {(lead.message || lead.interests || lead.timeline) && (
            <button onClick={() => setOpen(o => !o)}
              className="font-mono text-[9px] text-pb-faint hover:text-pb-text ml-auto">
              {open ? 'less' : 'details'}
            </button>
          )}
        </div>
      </div>
      {open && (
        <div className="px-3 py-2 pb-hairline-t font-mono text-[10px] text-pb-faint space-y-1 bg-pb-surface2/30">
          {lead.role && <Row k="Role" v={lead.role} />}
          {lead.grades && <Row k="Grades" v={lead.grades} />}
          {lead.timeline && <Row k="Timeline" v={lead.timeline} />}
          {lead.interests && <Row k="Interests" v={lead.interests} />}
          {lead.heard_about && <Row k="Heard via" v={lead.heard_about} />}
          {lead.message && <div className="text-pb-faintest italic pt-1">“{lead.message}”</div>}
        </div>
      )}
    </div>
  )
}

function SourcesPanel({ data, loading }) {
  if (!data) return <Empty loading={loading} />
  const sources = data.by_source || []
  const campaigns = data.by_campaign || []
  const max = Math.max(1, ...sources.map(s => s.visitors || 0))
  return (
    <div className="grid lg:grid-cols-2 gap-5">
      <div>
        <h3 className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-2">By source</h3>
        {sources.length === 0 ? <Empty>No source data.</Empty> : (
          <div className="space-y-1.5">
            {sources.map(s => {
              const m = sourceMeta(s.source)
              const pct = Math.round((s.visitors / max) * 100)
              return (
                <div key={s.source} className="flex items-center gap-2.5">
                  <div className="w-24 shrink-0 flex items-center gap-1.5 min-w-0">
                    <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ background: m.dot }} />
                    <span className="text-[12px] text-pb-text truncate" title={m.label}>{m.label}</span>
                  </div>
                  <div className="flex-1 h-4 rounded bg-pb-surface2 overflow-hidden">
                    <div className="h-full rounded" style={{ width: `${pct}%`, background: m.dot }} />
                  </div>
                  <div className="w-24 shrink-0 text-right font-mono text-[9px] text-pb-faint">
                    {fmtNum(s.visitors)} ppl
                    {s.intent_visitors > 0 && <span className="text-pb-amber"> · {s.intent_visitors}🔥</span>}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
      <div>
        <h3 className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-2">UTM campaigns</h3>
        {campaigns.length === 0 ? (
          <Empty>No tagged campaigns yet. Add <span className="font-mono">?utm_source=…</span> to share links.</Empty>
        ) : (
          <div className="pb-card overflow-hidden">
            {campaigns.map((c, i) => (
              <div key={i} className={`flex items-center gap-2 px-3 py-1.5 ${i > 0 ? 'pb-hairline-t' : ''}`}>
                <div className="flex-1 min-w-0">
                  <div className="font-mono text-[11px] text-pb-text truncate">
                    {c.utm_source}{c.utm_campaign ? ` / ${c.utm_campaign}` : ''}
                  </div>
                  {c.club_name && (
                    <div className="font-mono text-[9px] text-pb-accent truncate" title="Resolved from the club's UTM code">
                      → {c.club_name}
                    </div>
                  )}
                </div>
                <div className="font-mono text-[10px] text-pb-faint shrink-0 text-right">
                  {fmtNum(c.visitors)} ppl
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function TimeseriesPanel({ series, loading }) {
  const data = useMemo(() => (series?.points || []).map(p => ({
    label: fmtBucket(p.bucket, series?.bucket),
    pages: p.page_views,
  })), [series])
  if (!data.length) return <Empty loading={loading} />
  return (
    <div style={{ width: '100%', height: 220 }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
          <defs>
            <linearGradient id="pagesFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--pb-accent)" stopOpacity={0.4} />
              <stop offset="100%" stopColor="var(--pb-accent)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" />
          <XAxis dataKey="label" tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} />
          <Tooltip content={<ChartTooltip />} />
          <Area type="monotone" dataKey="pages" name="Page views" stroke="var(--pb-accent)" strokeWidth={2} fill="url(#pagesFill)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

function ByClubPanel({ rows, loading }) {
  if (!rows?.length) return <Empty loading={loading} />
  const max = Math.max(1, ...rows.map(c => c.hits || 0))
  return (
    <div className="space-y-1.5">
      {rows.slice(0, 15).map(c => {
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
      })}
    </div>
  )
}

function PagesPanel({ data, loading }) {
  if (!data) return <Empty loading={loading} />
  const routes = data.routes || []
  const feature = (data.feature || []).slice(0, 10)
  return (
    <div className="grid lg:grid-cols-2 gap-5">
      <div>
        <h3 className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-2">Top routes</h3>
        <div className="pb-card overflow-hidden">
          {routes.length === 0 && <Empty>No data.</Empty>}
          {routes.map((r, i) => (
            <div key={`${r.route}:${i}`} className={`flex items-center gap-3 px-3 py-1.5 ${i > 0 ? 'pb-hairline-t' : ''}`}>
              <TypeBadge type={r.event_type} />
              <div className="flex-1 min-w-0">
                <div className="font-mono text-[11px] text-pb-text truncate">{r.route || '—'}</div>
                <div className="font-mono text-[9px] text-pb-faintest">{r.unique_ips} IPs · last {fmtAgo(r.last_hit)}</div>
              </div>
              <div className="font-mono text-[11px] text-pb-text shrink-0">{fmtNum(r.hits)}</div>
            </div>
          ))}
        </div>
      </div>
      <div>
        <h3 className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-2">By feature</h3>
        <div style={{ width: '100%', height: Math.max(200, feature.length * 28) }}>
          {feature.length === 0 ? <Empty /> : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={feature} layout="vertical" margin={{ top: 4, right: 16, left: 4, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" horizontal={false} />
                <XAxis type="number" tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="feature" width={130} tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--pb-surface2)', opacity: 0.4 }} />
                <Bar dataKey="hits" name="Views" fill="var(--pb-accent)" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  )
}

function GeoPanel({ data, loading }) {
  if (!data) return <Empty loading={loading} />
  const countries = data.by_country || []
  const cities = data.by_city || []
  return (
    <div className="grid md:grid-cols-2 gap-5">
      <div>
        <h3 className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-2">By country</h3>
        <div className="pb-card overflow-hidden">
          {countries.length === 0 && <Empty>No geo data yet.</Empty>}
          {countries.map((row, i) => (
            <div key={row.country || `none-${i}`} className={`flex items-center gap-3 px-3 py-1.5 ${i > 0 ? 'pb-hairline-t' : ''}`}>
              <span className="text-base shrink-0 w-6">{flagFor(row.country)}</span>
              <div className="flex-1 min-w-0 font-mono text-[11px] text-pb-text truncate">{row.country || 'Unknown'}</div>
              <div className="font-mono text-[11px] text-pb-text shrink-0">{fmtNum(row.hits)}</div>
            </div>
          ))}
        </div>
      </div>
      <div>
        <h3 className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-2">By city</h3>
        <div className="pb-card overflow-hidden">
          {cities.length === 0 && <Empty>City lookups fill in shortly after each visit.</Empty>}
          {cities.map((row, i) => (
            <div key={`${row.city}-${i}`} className={`flex items-center gap-3 px-3 py-1.5 ${i > 0 ? 'pb-hairline-t' : ''}`}>
              <span className="text-base shrink-0 w-6">{flagFor(row.country)}</span>
              <div className="flex-1 min-w-0 font-mono text-[11px] text-pb-text truncate">
                {row.city}{row.region && <span className="text-pb-faint">, {row.region}</span>}
              </div>
              <div className="font-mono text-[11px] text-pb-text shrink-0">{fmtNum(row.hits)}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function PeoplePanel({ data, loading }) {
  if (!data) return <Empty loading={loading} />
  const roleData = (data.byRole || []).map((r, i) => ({
    name: ROLE_LABEL[r.role] || r.role, value: r.hits, fill: COLOURS[i % COLOURS.length],
  }))
  const topUsers = data.topUsers || []
  return (
    <div className="grid md:grid-cols-2 gap-5">
      <div>
        <h3 className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-2">By role</h3>
        <div style={{ width: '100%', height: 220 }}>
          {roleData.length === 0 ? <Empty /> : (
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={roleData} dataKey="value" nameKey="name" innerRadius={36} outerRadius={70} paddingAngle={2}>
                  {roleData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                </Pie>
                <Tooltip content={<ChartTooltip />} />
                <Legend wrapperStyle={{ fontSize: 10, fontFamily: 'monospace', color: 'var(--pb-faint)' }} iconSize={8} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
      <div>
        <h3 className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-2">Most active users</h3>
        <div className="pb-card overflow-hidden">
          {topUsers.length === 0 && <Empty>No signed-in activity.</Empty>}
          {topUsers.map((u, i) => (
            <div key={u.user_id || i} className={`flex items-center gap-3 px-3 py-1.5 ${i > 0 ? 'pb-hairline-t' : ''}`}>
              <div className="flex-1 min-w-0">
                <div className="text-pb-text text-sm truncate flex items-center gap-2">
                  {u.user_display_name || u.user_email || (u.user_id ? u.user_id.slice(0, 8) : 'anon')}
                  <RoleBadge role={u.user_role} />
                </div>
                <div className="font-mono text-[9px] text-pb-faintest">{u.unique_routes} routes · last {fmtAgo(u.last_hit)}</div>
              </div>
              <div className="font-mono text-[11px] text-pb-text shrink-0">{fmtNum(u.hits)}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function RawLogPanel({ rows, loading }) {
  if (!rows?.length) return <Empty loading={loading}>No events.</Empty>
  return (
    <div className="pb-card overflow-hidden -mx-1">
      {rows.map((r, i) => (
        <div key={r.id} className={`flex items-center gap-3 px-3 py-1.5 ${i > 0 ? 'pb-hairline-t' : ''}`}>
          <TypeBadge type={r.event_type} />
          <span className="font-mono text-[10px] text-pb-faintest shrink-0 w-20">{fmtAgo(r.created_at)}</span>
          <StatusBadge status={r.status} />
          <span className="font-mono text-[10px] text-pb-faint shrink-0 w-10">{r.method}</span>
          <div className="flex-1 min-w-0">
            {r.target_name && r.target_url ? (
              <a href={r.target_url} target="_blank" rel="noopener noreferrer"
                className="text-pb-accent hover:underline text-[12px] truncate block" title={r.path}>{r.target_name}</a>
            ) : (
              <span className="font-mono text-[10px] text-pb-text truncate block" title={r.path}>{r.path}</span>
            )}
          </div>
          <span className="text-xs shrink-0 w-20 text-right truncate font-mono text-pb-faint"
            title={[r.city, r.region, r.country].filter(Boolean).join(', ') || 'Unknown'}>
            {r.country ? `${flagFor(r.country)} ${r.city || r.country}` : '—'}
          </span>
        </div>
      ))}
    </div>
  )
}
