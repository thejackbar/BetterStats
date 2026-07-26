import { useState, useEffect, useCallback } from 'react'
import {
  ResponsiveContainer, BarChart, Bar, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip,
} from 'recharts'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

const DEFAULT_BUDGET = 750
const DEFAULT_LENGTH_DAYS = 30

const TREND_RANGES = [
  { label: '7d', days: 7 },
  { label: '14d', days: 14 },
  { label: '30d', days: 30 },
  { label: 'Lifetime', days: 90 },
]

const SEVERITY_STYLE = {
  critical: { dot: 'bg-red-400', border: 'border-red-500/50', text: 'text-red-300' },
  warning: { dot: 'bg-amber-400', border: 'border-amber-500/50', text: 'text-amber-300' },
  info: { dot: 'bg-sky-400', border: 'border-sky-500/50', text: 'text-sky-300' },
  good: { dot: 'bg-emerald-400', border: 'border-emerald-500/50', text: 'text-emerald-300' },
}

const AD_STATUS_STYLE = {
  winner: { label: 'Winner', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40' },
  laggard: { label: 'Laggard', cls: 'bg-red-500/15 text-red-300 border-red-500/40' },
  on_track: { label: 'On track', cls: 'bg-pb-surface2 text-pb-faint border-pb-hairline' },
  paused: { label: 'Paused', cls: 'bg-slate-500/15 text-slate-400 border-slate-500/40' },
}

function fmtMoney(n) {
  if (n == null || Number.isNaN(n)) return 'A$0.00'
  return `A$${Number(n).toFixed(2)}`
}
function fmtNum(n) {
  if (n == null) return '0'
  const v = Number(n)
  if (v >= 10000) return (v / 1000).toFixed(1).replace(/\.0$/, '') + 'k'
  return Math.round(v).toLocaleString('en-AU')
}
function fmtPct(n) {
  if (n == null) return '–'
  return `${Number(n).toFixed(1)}%`
}
function fmtTime(iso) {
  if (!iso) return 'never'
  return new Date(iso).toLocaleString('en-AU', {
    day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit',
    timeZone: 'Australia/Perth',
  }) + ' (Perth)'
}
function fmtDay(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', timeZone: 'Australia/Perth' })
}

function ChartTooltip({ active, payload, label, money }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-pb-surface border pb-hairline rounded px-3 py-2 text-xs shadow-lg">
      {label && <p className="font-mono text-[10px] text-pb-faint mb-1">{fmtDay(label)}</p>}
      {payload.map((p, i) => (
        <p key={i} className="font-mono text-pb-text">
          <span className="inline-block w-2 h-2 rounded-full mr-2 align-middle" style={{ background: p.color }} />
          {p.name}: <strong>{money?.has(p.dataKey) ? fmtMoney(p.value) : p.value}</strong>
        </p>
      ))}
    </div>
  )
}

function Stat({ label, value, hint }) {
  return (
    <div className="pb-card px-3 py-2.5">
      <div className="font-mono text-[9px] uppercase tracking-wide text-pb-faint">{label}</div>
      <div className="font-display text-xl text-pb-text mt-0.5">{value}</div>
      {hint && <div className="font-mono text-[9px] text-pb-faintest mt-0.5">{hint}</div>}
    </div>
  )
}

function InsightRow({ insight }) {
  const style = SEVERITY_STYLE[insight.severity] || SEVERITY_STYLE.info
  return (
    <div className={`flex items-start gap-2.5 py-2 px-3 rounded border-l-2 bg-pb-surface2/30 ${style.border}`}>
      <span className={`shrink-0 mt-1.5 w-1.5 h-1.5 rounded-full ${style.dot}`} />
      <p className="text-xs leading-relaxed">
        <span className={`font-medium ${style.text}`}>{insight.title}.</span>{' '}
        <span className="text-pb-dim">{insight.detail}</span>
      </p>
    </div>
  )
}

function FunnelChart({ stages, title = 'Funnel: impressions to a completed registration' }) {
  if (!stages?.length) return null
  const top = stages[0]?.value || 0
  return (
    <div className="pb-card p-4">
      <div className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-3">
        {title}
      </div>
      <div className="space-y-2.5">
        {stages.map((s, i) => {
          const widthPct = top ? Math.max(2, (s.value / top) * 100) : 0
          const fillOpacity = 0.3 + 0.7 * (top ? s.value / top : 0)
          const dropSevere = i > 0 && s.pct_of_prev < 20 && (stages[i - 1]?.value || 0) >= 2
          return (
            <div key={s.key}>
              {i > 0 && (
                <div className={`font-mono text-[9px] pl-1 mb-1 ${dropSevere ? 'text-red-400' : 'text-pb-faintest'}`}>
                  &darr; {fmtPct(s.pct_of_prev)} continued from &ldquo;{stages[i - 1].label}&rdquo;
                </div>
              )}
              <div className="flex items-center gap-3">
                <div className="w-40 sm:w-52 shrink-0 text-xs text-pb-text truncate" title={s.label}>{s.label}</div>
                <div className="flex-1 h-5 bg-pb-surface2 rounded overflow-hidden">
                  <div
                    className="h-full bg-pb-accent rounded"
                    style={{ width: `${widthPct}%`, opacity: fillOpacity }}
                  />
                </div>
                <div className="w-16 shrink-0 text-right font-mono text-xs text-pb-text">{fmtNum(s.value)}</div>
                <div className="w-14 shrink-0 text-right font-mono text-[10px] text-pb-faint">{fmtPct(s.pct_of_top)}</div>
              </div>
            </div>
          )
        })}
      </div>
      <div className="flex items-center gap-3 mt-1.5 font-mono text-[9px] text-pb-faintest">
        <div className="w-40 sm:w-52 shrink-0" />
        <div className="flex-1" />
        <div className="w-16 shrink-0 text-right">count</div>
        <div className="w-14 shrink-0 text-right">of top</div>
      </div>
    </div>
  )
}

function RangePicker({ value, onChange }) {
  return (
    <div className="inline-flex rounded border border-pb-hairline overflow-hidden">
      {TREND_RANGES.map((r) => (
        <button
          key={r.days}
          onClick={() => onChange(r.days)}
          className={`px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide2 ${
            value === r.days ? 'bg-pb-accent text-white' : 'text-pb-dim hover:bg-pb-surface2'
          }`}
        >
          {r.label}
        </button>
      ))}
    </div>
  )
}

function TrendChart({ title, data, dataKey, kind = 'line', color = '#3b82f6', money }) {
  return (
    <div className="pb-card p-4">
      <div className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-2">{title}</div>
      <div style={{ width: '100%', height: 170 }}>
        {data.length === 0 ? (
          <div className="h-full flex items-center justify-center font-mono text-[11px] text-pb-faint">No data yet.</div>
        ) : kind === 'bar' ? (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" />
              <XAxis dataKey="date" tickFormatter={fmtDay} tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip content={<ChartTooltip money={money} />} />
              <Bar dataKey={dataKey} name={title} fill={color} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" />
              <XAxis dataKey="date" tickFormatter={fmtDay} tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip content={<ChartTooltip money={money} />} />
              <Line type="monotone" dataKey={dataKey} name={title} stroke={color} strokeWidth={2} dot={{ r: 2 }} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}

function AdTrendMini({ adId, days }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')

  useEffect(() => {
    let alive = true
    setLoading(true)
    setErr('')
    api.metaAdsAdHistory(adId, days)
      .then((d) => { if (alive) setRows(d.days || []) })
      .catch((e) => { if (alive) setErr(e.message || "Could not load this ad's trend.") })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [adId, days])

  if (loading) return <p className="text-xs text-pb-faint px-1 py-2">Loading trend&hellip;</p>
  if (err) return <p className="text-xs text-red-400 px-1 py-2">{err}</p>
  if (rows.length === 0) return <p className="text-xs text-pb-faint px-1 py-2">No daily history recorded yet for this ad.</p>

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
      <TrendChart title="Daily spend" data={rows} dataKey="spend" kind="bar" color="var(--pb-accent)" money={new Set(['spend'])} />
      <TrendChart title="Daily link CTR" data={rows} dataKey="link_ctr" kind="line" color="#3b82f6" />
    </div>
  )
}

function AdCard({ ad, maxCostPerLpv, selected, onSelect, trendDays }) {
  const style = AD_STATUS_STYLE[ad.status] || AD_STATUS_STYLE.on_track
  const paused = ad.status === 'paused'
  const barPct = ad.cost_per_lpv && maxCostPerLpv ? Math.min(100, (ad.cost_per_lpv / maxCostPerLpv) * 100) : 0
  const barColor = paused ? 'bg-slate-500' : ad.status === 'winner' ? 'bg-emerald-500' : ad.status === 'laggard' ? 'bg-red-500' : 'bg-pb-accent'

  return (
    <div className={`pb-card border overflow-hidden ${selected ? 'border-pb-accent' : 'border-pb-hairline'} ${paused ? 'opacity-70' : ''}`}>
      <button onClick={onSelect} className="w-full text-left p-3.5 hover:bg-pb-surface2/40">
        <div className="flex items-start justify-between gap-2 mb-1">
          <div className="text-sm font-medium text-pb-text">{ad.name}</div>
          <span className={`shrink-0 px-1.5 py-0.5 rounded-full border text-[9px] font-mono uppercase ${style.cls}`}>
            {style.label}
          </span>
        </div>
        <p className="text-xs text-pb-dim mb-2.5 leading-relaxed">{ad.note}</p>
        <div className="grid grid-cols-3 gap-x-3 gap-y-1 font-mono text-[10px] text-pb-faint mb-2">
          <div>Spend <span className="text-pb-text">{fmtMoney(ad.spend)}</span></div>
          <div>Link CTR <span className="text-pb-text">{fmtPct(ad.link_ctr)}</span></div>
          <div>LPVs <span className="text-pb-text">{fmtNum(ad.landing_page_views)}</span></div>
          <div>Cost/LPV <span className="text-pb-text">{ad.cost_per_lpv != null ? fmtMoney(ad.cost_per_lpv) : '–'}</span></div>
          <div>Leads <span className="text-pb-text">{fmtNum(ad.leads)}</span></div>
          <div>Cost/Lead <span className="text-pb-text">{ad.cost_per_lead != null ? fmtMoney(ad.cost_per_lead) : '–'}</span></div>
        </div>
        {ad.cost_per_lpv != null && (
          <div className="h-1.5 bg-pb-surface2 rounded-full overflow-hidden">
            <div className={`h-full ${barColor}`} style={{ width: `${Math.max(4, barPct)}%` }} />
          </div>
        )}
        <div className="font-mono text-[9px] text-pb-faintest mt-2">
          {selected ? 'Hide trend over time' : 'Click for trend over time'}
        </div>
      </button>
      {selected && (
        <div className="border-t pb-hairline px-3.5 pb-3.5">
          <AdTrendMini adId={ad.ad_id} days={trendDays} />
        </div>
      )}
    </div>
  )
}

export default function SuperMetaAds() {
  const [summary, setSummary] = useState(null)
  const [history, setHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')

  const [adjustments, setAdjustments] = useState([])
  const [adjNote, setAdjNote] = useState('')
  const [adjusting, setAdjusting] = useState(false)
  const [showAdjLog, setShowAdjLog] = useState(false)

  const [attribution, setAttribution] = useState(null)
  const [adSignups, setAdSignups] = useState(null)
  const [registrationFunnel, setRegistrationFunnel] = useState(null)
  const [selectedClubs, setSelectedClubs] = useState(null)

  const [trendDays, setTrendDays] = useState(14)
  const [selectedAdId, setSelectedAdId] = useState(null)
  const [showAllInsights, setShowAllInsights] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    api.metaAdsSummary()
      .then((s) => { setSummary(s); setError('') })
      .catch((e) => setError(e.message || 'Could not load the Meta Ads dashboard.'))
      .finally(() => setLoading(false))
    api.metaAdsLeadAdjustments().then((d) => setAdjustments(d.adjustments || [])).catch(() => {})
    api.adminUsageCampaigns({ days: 30 }).then(setAttribution).catch(() => {})
    api.metaAdsAdSignups().then(setAdSignups).catch(() => {})
    api.metaAdsRegistrationFunnel().then((d) => setRegistrationFunnel(d.funnel || [])).catch(() => {})
    api.metaAdsSelectedClubs().then(setSelectedClubs).catch(() => {})
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    setHistoryLoading(true)
    api.metaAdsHistory(trendDays)
      .then((h) => setHistory(h.days || []))
      .catch(() => {})
      .finally(() => setHistoryLoading(false))
  }, [trendDays])

  const adjustLeads = async (delta) => {
    setAdjusting(true)
    setError('')
    try {
      const data = await api.metaAdsAdjustLeads(delta, adjNote)
      setSummary(data)
      setAdjNote('')
      const d = await api.metaAdsLeadAdjustments()
      setAdjustments(d.adjustments || [])
    } catch (e) {
      setError(e.message || 'Could not adjust the lead count.')
    } finally {
      setAdjusting(false)
    }
  }

  const refresh = async () => {
    setRefreshing(true)
    setError('')
    try {
      const data = await api.metaAdsRefresh()
      if (data.error) {
        setError(data.error.message)
      } else {
        setSummary(data)
        const h = await api.metaAdsHistory(trendDays)
        setHistory(h.days || [])
      }
    } catch (e) {
      setError(e.message || 'Refresh failed.')
    } finally {
      setRefreshing(false)
    }
  }

  const budget = summary?.campaign_budget ?? DEFAULT_BUDGET
  const lengthDays = summary?.campaign_length_days ?? DEFAULT_LENGTH_DAYS

  const header = (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-pb-text">Meta Ads &mdash; Trials Campaign</h1>
        <p className="text-sm text-pb-dim mt-1">BC_AU_Trials_CBO_Aug2026 &middot; ~{lengthDays} days from launch</p>
      </div>
      <div className="flex items-center gap-3">
        <span className="font-mono text-[10px] text-pb-faint">
          Last updated {fmtTime(summary?.last_updated)}
        </span>
        <button
          onClick={refresh}
          disabled={refreshing || loading}
          className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 uppercase border border-pb-accent text-pb-text hover:bg-pb-accent/10 disabled:opacity-50"
        >
          {refreshing ? 'Refreshing…' : 'Refresh now'}
        </button>
      </div>
    </div>
  )

  if (loading) {
    return (
      <AdminLayout>
        <div className="max-w-[1200px] mx-auto p-4 sm:p-6">
          {header}
          <p className="text-sm text-pb-dim">Loading…</p>
        </div>
      </AdminLayout>
    )
  }

  const tokenConfigured = summary?.token_configured
  const campaign = summary?.campaign
  const insights = summary?.insights || []
  const ads = summary?.ads || []
  const maxCostPerLpv = ads.reduce((m, a) => (a.cost_per_lpv != null && a.cost_per_lpv > m ? a.cost_per_lpv : m), 0)

  return (
    <AdminLayout>
      <div className="max-w-[1200px] mx-auto p-4 sm:p-6">
        {header}

        {error && (
          <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 mb-4">{error}</p>
        )}

        {!tokenConfigured ? (
          <div className="pb-card p-8 text-center">
            <p className="text-sm text-pb-text font-medium">Meta access token not configured</p>
            <p className="text-sm text-pb-dim mt-2 max-w-xl mx-auto">
              Add <code className="font-mono text-xs bg-pb-surface2 px-1.5 py-0.5 rounded">META_ACCESS_TOKEN</code> (and
              the other <code className="font-mono text-xs bg-pb-surface2 px-1.5 py-0.5 rounded">META_*</code> vars) to
              the backend&rsquo;s environment, then come back and click Refresh now. See the setup runbook for how to
              generate a system-user token with <code className="font-mono text-xs">ads_read</code> +{' '}
              <code className="font-mono text-xs">read_insights</code>.
            </p>
          </div>
        ) : !campaign ? (
          <div className="pb-card p-8 text-center">
            <p className="text-sm text-pb-dim">
              Campaign is live but hasn&rsquo;t spent yet &mdash; check back after it starts delivering, or click
              Refresh now.
            </p>
          </div>
        ) : (
          <>
            {/* Headlines — short, worst-first, only fires on something worth
                a glance. Capped so this stays a quick scan, not a report. */}
            {insights.length > 0 && (
              <div className="mb-4">
                <div className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-2">
                  Headlines
                </div>
                <div className="space-y-1.5">
                  {(showAllInsights ? insights : insights.slice(0, 3)).map((insight, i) => (
                    <InsightRow key={i} insight={insight} />
                  ))}
                </div>
                {insights.length > 3 && (
                  <button
                    onClick={() => setShowAllInsights((s) => !s)}
                    className="mt-1.5 font-mono text-[9px] text-pb-faint hover:underline"
                  >
                    {showAllInsights ? 'Show fewer' : `+${insights.length - 3} more`}
                  </button>
                )}
              </div>
            )}

            {/* KPI strip */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-1">
              <Stat
                label="Spend"
                value={fmtMoney(campaign.spend)}
                hint={`of ${fmtMoney(budget)} · ${Math.min(100, Math.round((campaign.spend / budget) * 100))}%`}
              />
              <Stat label="Cost per LPV" value={campaign.cost_per_lpv != null ? fmtMoney(campaign.cost_per_lpv) : '–'} />
              <Stat
                label="Cost per registration"
                value={campaign.cost_per_lead != null ? fmtMoney(campaign.cost_per_lead) : '–'}
                hint="spend / actual registrations"
              />

              <div className="pb-card px-3 py-2.5">
                <div className="font-mono text-[9px] uppercase tracking-wide text-pb-faint">Free trial registrations</div>
                <div className="font-display text-xl text-pb-text mt-0.5">{fmtNum(campaign.leads_effective)}</div>
                <div className="font-mono text-[9px] text-pb-faintest mt-0.5">
                  {fmtNum(campaign.registrations)} actual
                  {campaign.leads_adjustment ? `, ${campaign.leads_adjustment > 0 ? '+' : ''}${campaign.leads_adjustment} manual` : ''}
                  {' '}&middot;{' '}
                  <span title="Meta counts this the moment someone picks a club, not when they finish registering, and it can shift on its own. The actual figure above is the real number.">
                    {fmtNum(campaign.leads)} Meta-reported
                  </span>
                </div>
                <div className="flex items-center gap-1 mt-1.5">
                  <button
                    onClick={() => adjustLeads(-1)}
                    disabled={adjusting}
                    title="Remove one registration (e.g. spam or duplicate)"
                    className="w-5 h-5 flex items-center justify-center rounded border border-pb-hairline text-pb-dim hover:bg-pb-surface2 disabled:opacity-50 font-mono text-xs leading-none"
                  >
                    &minus;
                  </button>
                  <button
                    onClick={() => adjustLeads(1)}
                    disabled={adjusting}
                    title="Add one registration our own tracking didn't capture (e.g. a manually onboarded club)"
                    className="w-5 h-5 flex items-center justify-center rounded border border-pb-hairline text-pb-dim hover:bg-pb-surface2 disabled:opacity-50 font-mono text-xs leading-none"
                  >
                    +
                  </button>
                  <button
                    onClick={() => setShowAdjLog((s) => !s)}
                    className="font-mono text-[9px] text-pb-faint hover:underline ml-1"
                  >
                    {showAdjLog ? 'hide log' : `log (${adjustments.length})`}
                  </button>
                </div>
              </div>
            </div>

            {showAdjLog && (
              <div className="pb-card p-3 mb-2">
                <input
                  type="text"
                  value={adjNote}
                  onChange={(e) => setAdjNote(e.target.value)}
                  placeholder="Optional note for the next +/- (e.g. duplicate, spam, converted to a paying club)"
                  className="w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 font-mono text-[11px] text-pb-text mb-2"
                />
                <div className="font-mono text-[9px] uppercase tracking-wide text-pb-faint mb-1">Adjustment history</div>
                {adjustments.length === 0 ? (
                  <p className="text-xs text-pb-faint">No manual adjustments yet.</p>
                ) : (
                  <ul className="space-y-1 max-h-40 overflow-y-auto">
                    {adjustments.map((a, i) => (
                      <li key={i} className="flex flex-wrap items-baseline gap-x-2 text-xs">
                        <span className={a.delta > 0 ? 'text-emerald-400 font-mono' : 'text-red-400 font-mono'}>
                          {a.delta > 0 ? `+${a.delta}` : a.delta}
                        </span>
                        <span className="font-mono text-[10px] text-pb-faintest">{fmtTime(a.created_at)}</span>
                        {a.created_by_email && <span className="text-pb-faint">{a.created_by_email}</span>}
                        {a.note && <span className="text-pb-dim">{a.note}</span>}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            <div className="w-full bg-pb-surface2 rounded-full h-1.5 mb-4 overflow-hidden">
              <div
                className="h-full bg-pb-accent"
                style={{ width: `${Math.min(100, (campaign.spend / budget) * 100)}%` }}
              />
            </div>

            {/* Funnel */}
            <div className="mb-4">
              <FunnelChart stages={campaign.funnel} />
            </div>

            {/* Registration-wizard step breakdown — fills in the gap between
                Meta's own Lead and CompleteRegistration events. */}
            {registrationFunnel?.some((s) => s.value > 0) && (
              <div className="mb-4">
                <FunnelChart
                  stages={registrationFunnel}
                  title="Registration wizard: where visitors drop off (last 30 days)"
                />
              </div>
            )}

            {/* Which clubs are behind the "Club selected" count — named wherever
                we can identify them (beacon metadata, Terms-step name, or a
                completed registration). */}
            {selectedClubs && (selectedClubs.clubs.length > 0 || selectedClubs.anonymous > 0) && (
              <div className="pb-card p-4 mb-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
                  <div className="font-mono text-[10px] uppercase tracking-wide text-pb-faint">
                    Clubs selected in the wizard (last 30 days)
                  </div>
                  <span className="font-mono text-[10px] text-pb-faintest">
                    {selectedClubs.identified} identified
                    {selectedClubs.anonymous > 0 && <> &middot; {selectedClubs.anonymous} not captured</>}
                  </span>
                </div>

                {selectedClubs.clubs.length === 0 ? (
                  <p className="text-xs text-pb-faint">
                    {selectedClubs.anonymous} club selection{selectedClubs.anonymous === 1 ? '' : 's'} in
                    this window, but none can be named yet — they were picked before the club was captured
                    on the selection beacon and never reached the Terms step. New selections from now on
                    will be named here.
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint border-b pb-hairline">
                          <th className="px-2 py-2">Club</th>
                          <th className="px-2 py-2">Furthest step</th>
                          <th className="px-2 py-2">Contact email</th>
                          <th className="px-2 py-2">Last seen</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedClubs.clubs.map((c) => (
                          <tr key={c.name + (c.org_id || '')} className="border-b pb-hairline last:border-0 hover:bg-pb-surface2/40">
                            <td className="px-2 py-2 text-pb-text font-medium whitespace-nowrap">
                              {c.slug ? <a href={`/${c.slug}`} className="hover:underline">{c.name}</a> : c.name}
                            </td>
                            <td className="px-2 py-2">
                              <span className={`inline-block px-1.5 py-0.5 rounded-full border font-mono text-[9px] uppercase ${
                                c.furthest_step === 'Registration completed'
                                  ? 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10'
                                  : c.furthest_step === 'Reached Terms & privacy'
                                    ? 'border-amber-500/40 text-amber-300 bg-amber-500/10'
                                    : 'border-pb-hairline text-pb-faint'
                              }`}>
                                {c.furthest_step}
                              </span>
                            </td>
                            <td className="px-2 py-2 text-pb-dim whitespace-nowrap">{c.email || '–'}</td>
                            <td className="px-2 py-2 text-pb-dim whitespace-nowrap">{fmtTime(c.last_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <p className="font-mono text-[9px] text-pb-faintest mt-3">
                  The step funnel above counts anonymous visitors; this names the clubs behind them. A club
                  is identified from the selection beacon (captured from this release on), the club name on
                  a Terms-step acknowledgement, or a completed registration &mdash; whichever it reached furthest.
                </p>
              </div>
            )}

            {/* Per-ad comparison, with click-to-drill-down trend */}
            <div className="mb-4">
              <div className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-2">
                Ad-by-ad performance
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {ads.map((ad) => (
                  <AdCard
                    key={ad.ad_id}
                    ad={ad}
                    maxCostPerLpv={maxCostPerLpv}
                    selected={selectedAdId === ad.ad_id}
                    onSelect={() => setSelectedAdId((cur) => (cur === ad.ad_id ? null : ad.ad_id))}
                    trendDays={trendDays}
                  />
                ))}
              </div>
            </div>

            {/* Trend charts — true daily figures (not cumulative-to-date), each on its own axis */}
            <div className="mb-4">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                <div className="font-mono text-[10px] uppercase tracking-wide text-pb-faint">
                  Trend {historyLoading && <span className="text-pb-faintest normal-case">loading&hellip;</span>}
                </div>
                <RangePicker value={trendDays} onChange={setTrendDays} />
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                <TrendChart title="Spend per day" data={history} dataKey="spend" kind="bar" color="var(--pb-accent)" money={new Set(['spend'])} />
                <TrendChart title="Link CTR per day" data={history} dataKey="link_ctr" kind="line" color="#3b82f6" />
                <TrendChart title="Cost per LPV per day" data={history} dataKey="cost_per_lpv" kind="line" color="#f59e0b" money={new Set(['cost_per_lpv'])} />
                <TrendChart title="Leads per day (Meta-reported)" data={history} dataKey="leads" kind="bar" color="#a78bfa" />
              </div>
            </div>

            {/* On-site attribution & conversion, from our own visit tracking rather than Meta's numbers */}
            {attribution && (
              <div className="pb-card p-4 mb-4">
                <div className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-3">
                  On-site attribution, last {attribution.days} days
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 mb-4">
                  <Stat label="Meta visitors" value={fmtNum(attribution.meta.visitors)} hint="site-tracked, not Meta's own count" />
                  <Stat label="Facebook" value={fmtNum(attribution.meta.facebook)} />
                  <Stat label="Instagram" value={fmtNum(attribution.meta.instagram)} />
                  <Stat label="Paid clicks" value={fmtNum(attribution.meta.paid)} />
                  <Stat
                    label="Reached pricing/contact"
                    value={fmtNum(attribution.conversion.reached_intent)}
                    hint={`${attribution.conversion.pct}% of Meta visitors`}
                  />
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                  <div>
                    <div className="font-mono text-[9px] uppercase tracking-wide text-pb-faint mb-1.5">Top ad creatives (by visitor)</div>
                    {attribution.creatives.length === 0 ? (
                      <p className="text-xs text-pb-faint">No tagged creatives seen yet.</p>
                    ) : (
                      <table className="w-full text-xs">
                        <tbody>
                          {attribution.creatives.slice(0, 6).map((c, i) => (
                            <tr key={i} className="border-b pb-hairline last:border-0">
                              <td className="py-1.5 pr-2 text-pb-text">{c.content || '(untagged)'}</td>
                              <td className="py-1.5 pr-2 text-pb-faint">{c.campaign || '–'}</td>
                              <td className="py-1.5 text-right text-pb-dim whitespace-nowrap">{fmtNum(c.visitors)} visitors</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                  <div>
                    <div className="font-mono text-[9px] uppercase tracking-wide text-pb-faint mb-1.5">Where Meta clicks land</div>
                    {attribution.landing.length === 0 ? (
                      <p className="text-xs text-pb-faint">No landing pages recorded yet.</p>
                    ) : (
                      <table className="w-full text-xs">
                        <tbody>
                          {attribution.landing.slice(0, 6).map((l, i) => (
                            <tr key={i} className="border-b pb-hairline last:border-0">
                              <td className="py-1.5 pr-2 text-pb-text">{l.label || l.page}</td>
                              <td className="py-1.5 text-right text-pb-dim whitespace-nowrap">{fmtNum(l.visitors)} visitors</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                </div>
                <p className="font-mono text-[9px] text-pb-faintest mt-3">
                  From our own visit tracking (not Meta's), so it independently confirms whether an ad click actually
                  went anywhere on the site. Full breakdown on the{' '}
                  <a href="/admin/usage" className="text-accent hover:underline">Usage</a> page.
                </p>
              </div>
            )}

            {/* Ad-driven self-serve signups joined to their Twenty engagement
                score — which ads produced clubs that actually use the thing. */}
            {adSignups && (
              <div className="pb-card p-4 mb-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
                  <div className="font-mono text-[10px] uppercase tracking-wide text-pb-faint">
                    Self-serve trial signups &rarr; lead score
                  </div>
                  {adSignups.rows.length > 0 && campaign?.spend > 0 && (
                    <span className="font-mono text-[10px] text-pb-faintest">
                      {fmtMoney(campaign.spend / Math.max(1, adSignups.rows.filter((r) => r.signup_source === 'self_serve_ad').length))} per ad-driven signup at current spend
                    </span>
                  )}
                </div>

                {adSignups.rows.length === 0 ? (
                  <p className="text-xs text-pb-faint">
                    No self-serve signups yet. Once the /trial page is live and the campaign is running,
                    every club that registers itself lands here with its ad attribution and Twenty
                    engagement score.
                  </p>
                ) : (
                  <>
                    {adSignups.campaigns.length > 0 && (
                      <div className="flex flex-wrap gap-2 mb-3">
                        {adSignups.campaigns.map((c) => (
                          <span key={c.campaign} className="px-2 py-1 rounded border pb-hairline font-mono text-[10px] text-pb-dim">
                            <span className="text-pb-text">{c.campaign || '(untagged)'}</span>
                            {' '}&middot; {fmtNum(c.signups)} signup{c.signups === 1 ? '' : 's'}
                            {c.converted > 0 && <span className="text-emerald-400"> &middot; {c.converted} paid</span>}
                            {c.avg_engagement != null && <> &middot; avg score {c.avg_engagement}</>}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint border-b pb-hairline">
                            <th className="px-2 py-2">Club</th>
                            <th className="px-2 py-2">Signed up</th>
                            <th className="px-2 py-2">Source</th>
                            <th className="px-2 py-2">Campaign / creative</th>
                            <th className="px-2 py-2">Modules</th>
                            <th className="px-2 py-2 text-right">Lead score</th>
                          </tr>
                        </thead>
                        <tbody>
                          {adSignups.rows.map((r) => (
                            <tr key={r.org_id} className="border-b pb-hairline last:border-0 hover:bg-pb-surface2/40">
                              <td className="px-2 py-2 text-pb-text font-medium whitespace-nowrap">
                                {r.slug ? <a href={`/${r.slug}`} className="hover:underline">{r.name}</a> : r.name}
                              </td>
                              <td className="px-2 py-2 text-pb-dim whitespace-nowrap">{r.signed_up_at ? fmtTime(r.signed_up_at) : '–'}</td>
                              <td className="px-2 py-2">
                                <span className={`inline-block px-1.5 py-0.5 rounded-full border font-mono text-[9px] uppercase ${
                                  r.signup_source === 'self_serve_ad'
                                    ? 'border-violet-500/40 text-violet-300 bg-violet-500/10'
                                    : 'border-pb-hairline text-pb-faint'
                                }`}>
                                  {r.signup_source === 'self_serve_ad' ? (r.click_source || 'ad') : 'organic'}
                                </span>
                              </td>
                              <td className="px-2 py-2 text-pb-dim">
                                {[r.utm_campaign, r.utm_content].filter(Boolean).join(' / ') || '–'}
                              </td>
                              <td className="px-2 py-2 text-pb-dim">
                                {r.converted_to_paid
                                  ? <span className="text-emerald-400">{r.paid_modules.length} paid</span>
                                  : `${r.trial_modules.length} on trial`}
                              </td>
                              <td className="px-2 py-2 text-right">
                                {r.engagement_score == null ? (
                                  <span className="font-mono text-[10px] text-pb-faintest">not yet scored</span>
                                ) : (
                                  <span className={`font-display font-bold ${
                                    r.engagement_score >= 70 ? 'text-red-400'
                                      : r.engagement_score >= 40 ? 'text-amber-400'
                                      : 'text-pb-dim'
                                  }`}>
                                    {r.engagement_score}
                                  </span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <p className="font-mono text-[9px] text-pb-faintest mt-3">
                      Lead score is the cached Twenty engagement score (refreshed daily / via the Club
                      Directory&rsquo;s refresh buttons). A club that registered before Twenty was configured
                      shows &ldquo;not yet scored&rdquo; until it&rsquo;s exported.
                    </p>
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </AdminLayout>
  )
}
