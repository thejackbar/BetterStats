import { useState, useEffect, useCallback } from 'react'
import {
  ResponsiveContainer, AreaChart, Area, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip,
} from 'recharts'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

const CAMPAIGN_WINDOW = '28 Jun – 12 Jul 2026'
const CAMPAIGN_BUDGET = 200

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

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([api.metaAdsSummary(), api.metaAdsHistory(14)])
      .then(([s, h]) => { setSummary(s); setHistory(h.days || []); setError('') })
      .catch((e) => setError(e.message || 'Could not load the Meta Ads dashboard.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

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
        <h1 className="text-xl font-semibold text-pb-text">Meta Ads &mdash; Early Bird Campaign</h1>
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
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 mb-2">
              <Stat
                label="Spend"
                value={fmtMoney(campaign.spend)}
                hint={`of ${fmtMoney(CAMPAIGN_BUDGET)} · ${Math.min(100, Math.round((campaign.spend / CAMPAIGN_BUDGET) * 100))}%`}
              />
              <Stat label="Landing page views" value={fmtNum(campaign.landing_page_views)} />
              <Stat label="Link CTR" value={fmtPct(campaign.link_ctr)} />
              <Stat label="Cost per LPV" value={campaign.cost_per_lpv != null ? fmtMoney(campaign.cost_per_lpv) : '–'} />
              <Stat
                label="Meta-attributed leads"
                value={fmtNum(campaign.leads)}
                hint="indicative — see onboarding list"
              />
            </div>
            <div className="w-full bg-pb-surface2 rounded-full h-1.5 mb-4 overflow-hidden">
              <div
                className="h-full bg-pb-accent"
                style={{ width: `${Math.min(100, (campaign.spend / CAMPAIGN_BUDGET) * 100)}%` }}
              />
            </div>

            {/* Trend charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-4">
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
