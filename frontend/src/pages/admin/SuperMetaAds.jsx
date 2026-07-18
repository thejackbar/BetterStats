import { useState, useEffect, useCallback } from 'react'
import {
  ResponsiveContainer, AreaChart, Area, LineChart, Line, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip,
} from 'recharts'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

const CAMPAIGN_WINDOW = 'BC_AU_SelfServe_Aug2026 · ~30 days from launch'
const CAMPAIGN_BUDGET = 520  // the campaign's lifetime spend cap

const REC_STYLE = {
  keep_going: {
    label: 'Keep going',
    box: 'bg-emerald-500/10 border-emerald-500/40',
    text: 'text-emerald-300',
    badge: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
  },
  watch: {
    label: 'Watch',
    box: 'bg-amber-500/10 border-amber-500/40',
    text: 'text-amber-300',
    badge: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
  },
  action_needed: {
    label: 'Action needed',
    box: 'bg-red-500/10 border-red-500/40',
    text: 'text-red-300',
    badge: 'bg-red-500/15 text-red-300 border-red-500/40',
  },
}

const AD_STATUS_STYLE = {
  winner:   { label: 'Winner',   cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40' },
  laggard:  { label: 'Laggard',  cls: 'bg-red-500/15 text-red-300 border-red-500/40' },
  on_track: { label: 'On track', cls: 'bg-pb-surface2 text-pb-faint border-pb-hairline' },
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
  return `${Number(n).toFixed(2)}%`
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
      {label && <p className="font-mono text-[10px] text-pb-faint mb-1">{label}</p>}
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

export default function SuperMetaAds() {
  const [summary, setSummary] = useState(null)
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')

  const [adjustments, setAdjustments] = useState([])
  const [adjNote, setAdjNote] = useState('')
  const [adjusting, setAdjusting] = useState(false)
  const [showAdjLog, setShowAdjLog] = useState(false)

  const [attribution, setAttribution] = useState(null)
  const [adSignups, setAdSignups] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([api.metaAdsSummary(), api.metaAdsHistory(14)])
      .then(([s, h]) => { setSummary(s); setHistory(h.days || []); setError('') })
      .catch((e) => setError(e.message || 'Could not load the Meta Ads dashboard.'))
      .finally(() => setLoading(false))
    api.metaAdsLeadAdjustments().then((d) => setAdjustments(d.adjustments || [])).catch(() => {})
    api.adminUsageCampaigns({ days: 30 }).then(setAttribution).catch(() => {})
    api.metaAdsAdSignups().then(setAdSignups).catch(() => {})
  }, [])

  useEffect(() => { load() }, [load])

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
        const h = await api.metaAdsHistory(14)
        setHistory(h.days || [])
      }
    } catch (e) {
      setError(e.message || 'Refresh failed.')
    } finally {
      setRefreshing(false)
    }
  }

  const header = (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-pb-text">Meta Ads &mdash; Self-Serve Trial Campaign</h1>
        <p className="text-sm text-pb-dim mt-1">{CAMPAIGN_WINDOW}</p>
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
            {/* Recommendation banner */}
            <div className={`pb-card border p-4 mb-4 ${REC_STYLE[summary.recommendation_status]?.box || ''}`}>
              <div className="flex items-center gap-2 mb-1">
                <span className={`px-2 py-0.5 rounded-full border text-[10px] font-mono uppercase tracking-wide2 ${REC_STYLE[summary.recommendation_status]?.badge || ''}`}>
                  {REC_STYLE[summary.recommendation_status]?.label || summary.recommendation_status}
                </span>
              </div>
              <p className={`text-sm ${REC_STYLE[summary.recommendation_status]?.text || 'text-pb-text'}`}>
                {summary.recommendation}
              </p>
            </div>

            {/* KPI cards */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 mb-1">
              <Stat
                label="Spend"
                value={fmtMoney(campaign.spend)}
                hint={`of ${fmtMoney(CAMPAIGN_BUDGET)} · ${Math.min(100, Math.round((campaign.spend / CAMPAIGN_BUDGET) * 100))}%`}
              />
              <Stat label="Landing page views" value={fmtNum(campaign.landing_page_views)} />
              <Stat label="Link CTR" value={fmtPct(campaign.link_ctr)} />
              <Stat label="Cost per LPV" value={campaign.cost_per_lpv != null ? fmtMoney(campaign.cost_per_lpv) : '–'} />
              <Stat
                label="Cost per lead"
                value={campaign.cost_per_lead != null ? fmtMoney(campaign.cost_per_lead) : '–'}
                hint="spend / effective leads"
              />

              <div className="pb-card px-3 py-2.5">
                <div className="font-mono text-[9px] uppercase tracking-wide text-pb-faint">Meta-attributed conversions</div>
                <div className="font-display text-xl text-pb-text mt-0.5">{fmtNum(campaign.leads_effective)}</div>
                <div className="font-mono text-[9px] text-pb-faintest mt-0.5">
                  {fmtNum(campaign.leads)} from Meta
                  {campaign.leads_adjustment ? `, ${campaign.leads_adjustment > 0 ? '+' : ''}${campaign.leads_adjustment} manual` : ''}
                </div>
                <div className="flex items-center gap-1 mt-1.5">
                  <button
                    onClick={() => adjustLeads(-1)}
                    disabled={adjusting}
                    title="Remove one lead (e.g. spam or duplicate)"
                    className="w-5 h-5 flex items-center justify-center rounded border border-pb-hairline text-pb-dim hover:bg-pb-surface2 disabled:opacity-50 font-mono text-xs leading-none"
                  >
                    &minus;
                  </button>
                  <button
                    onClick={() => adjustLeads(1)}
                    disabled={adjusting}
                    title="Add one lead Meta didn't capture (e.g. a direct enquiry)"
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
                style={{ width: `${Math.min(100, (campaign.spend / CAMPAIGN_BUDGET) * 100)}%` }}
              />
            </div>

            {/* Trend charts */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mb-4">
              <div className="pb-card p-4">
                <div className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-2">Spend over time</div>
                <div style={{ width: '100%', height: 200 }}>
                  {history.length === 0 ? (
                    <div className="h-full flex items-center justify-center font-mono text-[11px] text-pb-faint">No data yet.</div>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={history} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                        <defs>
                          <linearGradient id="spendFill" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="var(--pb-accent)" stopOpacity={0.4} />
                            <stop offset="100%" stopColor="var(--pb-accent)" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" />
                        <XAxis dataKey="date" tickFormatter={fmtDay} tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} />
                        <YAxis tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} />
                        <Tooltip content={<ChartTooltip money={new Set(['spend'])} />} labelFormatter={fmtDay} />
                        <Area type="monotone" dataKey="spend" name="Spend" stroke="var(--pb-accent)" strokeWidth={2} fill="url(#spendFill)" />
                      </AreaChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>
              <div className="pb-card p-4">
                <div className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-2">CTR &amp; cost per LPV</div>
                <div style={{ width: '100%', height: 200 }}>
                  {history.length === 0 ? (
                    <div className="h-full flex items-center justify-center font-mono text-[11px] text-pb-faint">No data yet.</div>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={history} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" />
                        <XAxis dataKey="date" tickFormatter={fmtDay} tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} />
                        <YAxis yAxisId="ctr" tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} />
                        <YAxis yAxisId="cost" orientation="right" tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} />
                        <Tooltip content={<ChartTooltip money={new Set(['cost_per_lpv'])} />} labelFormatter={fmtDay} />
                        <Line yAxisId="ctr" type="monotone" dataKey="link_ctr" name="Link CTR %" stroke="#3b82f6" strokeWidth={2} dot={false} />
                        <Line yAxisId="cost" type="monotone" dataKey="cost_per_lpv" name="Cost per LPV" stroke="#f59e0b" strokeWidth={2} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>
              <div className="pb-card p-4">
                <div className="font-mono text-[10px] uppercase tracking-wide text-pb-faint mb-2">Leads per day (Meta-reported)</div>
                <div style={{ width: '100%', height: 200 }}>
                  {history.length === 0 ? (
                    <div className="h-full flex items-center justify-center font-mono text-[11px] text-pb-faint">No data yet.</div>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={history} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" />
                        <XAxis dataKey="date" tickFormatter={fmtDay} tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} />
                        <YAxis tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} allowDecimals={false} />
                        <Tooltip content={<ChartTooltip />} labelFormatter={fmtDay} />
                        <Bar dataKey="leads" name="Leads" fill="#a78bfa" radius={[3, 3, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>
            </div>

            {/* Per-ad table */}
            <div className="pb-card overflow-x-auto mb-4">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint border-b pb-hairline">
                    <th className="px-3 py-2.5">Ad</th>
                    <th className="px-3 py-2.5">Destination</th>
                    <th className="px-3 py-2.5">Spend</th>
                    <th className="px-3 py-2.5">Link CTR</th>
                    <th className="px-3 py-2.5">LPVs</th>
                    <th className="px-3 py-2.5">Cost/LPV</th>
                    <th className="px-3 py-2.5">Leads</th>
                    <th className="px-3 py-2.5">Cost/Lead</th>
                    <th className="px-3 py-2.5">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(summary.ads || []).map((ad) => (
                    <tr key={ad.ad_id} className="border-b pb-hairline hover:bg-pb-surface2/40">
                      <td className="px-3 py-2.5 font-medium text-pb-text">{ad.name}</td>
                      <td className="px-3 py-2.5 text-pb-dim">{ad.destination || '–'}</td>
                      <td className="px-3 py-2.5 text-pb-dim whitespace-nowrap">{fmtMoney(ad.spend)}</td>
                      <td className="px-3 py-2.5 text-pb-dim">{fmtPct(ad.link_ctr)}</td>
                      <td className="px-3 py-2.5 text-pb-dim">{fmtNum(ad.landing_page_views)}</td>
                      <td className="px-3 py-2.5 text-pb-dim whitespace-nowrap">{ad.cost_per_lpv != null ? fmtMoney(ad.cost_per_lpv) : '–'}</td>
                      <td className="px-3 py-2.5 text-pb-dim">{fmtNum(ad.leads)}</td>
                      <td className="px-3 py-2.5 text-pb-dim whitespace-nowrap">{ad.cost_per_lead != null ? fmtMoney(ad.cost_per_lead) : '–'}</td>
                      <td className="px-3 py-2.5">
                        <span className={`inline-block px-2 py-0.5 rounded-full border text-[10px] font-mono uppercase ${AD_STATUS_STYLE[ad.status]?.cls || ''}`}>
                          {AD_STATUS_STYLE[ad.status]?.label || ad.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
                                {r.archived && <span className="text-pb-faintest font-mono text-[9px] ml-1">ARCHIVED</span>}
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

            {/* Footer note */}
            <p className="text-xs text-pb-faint">
              Meta&rsquo;s Lead number is indicative &mdash; the real conversions are the request-access enquiries in
              Formspree and the{' '}
              <a href="/admin/super/onboarding" className="text-accent hover:underline">onboarding list</a>.
            </p>
          </>
        )}
      </div>
    </AdminLayout>
  )
}
