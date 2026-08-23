import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import BetterFeesLayout from '../../components/admin/BetterFeesLayout'
import { PbSpinner } from '../../lib/presskit'
import { formatSeason } from '../../lib/cricketFormat'

const money = n => `$${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`

function sortSeasons(seasons) {
  return seasons.filter(s => !s.alias_of).sort((a, b) => (b.year || 0) - (a.year || 0) || (b.name > a.name ? 1 : -1))
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
function fmtMonth(key) {
  if (!key || key === 'unknown') return 'No date'
  const [y, m] = key.split('-')
  return `${MONTHS[Number(m) - 1] || m} ${y}`
}

function Kpi({ label, value, accent, warn, sky }) {
  return (
    <div className={`pb-card px-4 py-3 ${accent ? 'border-pb-accent/40' : ''}`}>
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">{label}</div>
      <div className={`font-display font-bold text-xl ${warn ? 'text-pb-amber' : sky ? 'text-sky-300' : 'text-pb-text'}`}
        style={accent && !warn ? { color: 'var(--pb-accent)' } : {}}>{value}</div>
    </div>
  )
}

function CashflowBars({ series }) {
  const max = Math.max(1, ...series.map(s => s.total))
  return (
    <div className="space-y-1.5">
      {series.map(s => (
        <div key={s.month} className="grid grid-cols-[120px_1fr_120px] items-center gap-3">
          <span className="font-mono text-[10px] tracking-wide2 text-pb-faint">{fmtMonth(s.month)}</span>
          <div className="relative h-6 bg-pb-surface2/40 rounded overflow-hidden flex">
            <div className="h-full" style={{ width: `${(s.membership / max) * 100}%`, background: 'var(--pb-accent)', opacity: 0.85 }} title={`Membership ${money(s.membership)}`} />
            <div className="h-full bg-pb-text/40" style={{ width: `${(s.match_day / max) * 100}%` }} title={`Match Day ${money(s.match_day)}`} />
          </div>
          <span className="font-mono text-[11px] text-pb-text text-right">{money(s.total)}</span>
        </div>
      ))}
      <div className="flex items-center gap-4 pt-2 font-mono text-[10px] text-pb-faintest">
        <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-2 rounded-sm" style={{ background: 'var(--pb-accent)', opacity: 0.85 }} /> Membership</span>
        <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-2 rounded-sm bg-pb-text/40" /> Match day</span>
      </div>
    </div>
  )
}

export default function AdminFeeReports() {
  const toast = useToast()
  const [seasons, setSeasons] = useState([])
  const [seasonId, setSeasonId] = useState('')
  const [summary, setSummary] = useState(null)
  const [followUps, setFollowUps] = useState(null)
  const [cashflow, setCashflow] = useState(null)

  useEffect(() => {
    api.adminListSeasons()
      .then(s => { const sorted = sortSeasons(s); setSeasons(sorted); if (sorted[0]) setSeasonId(sorted[0].id) })
      .catch(e => toast.error(e.message))
  }, [])

  const load = useCallback(() => {
    if (!seasonId) return
    setSummary(null); setFollowUps(null); setCashflow(null)
    Promise.all([
      api.feeReportSummary(seasonId).then(setSummary),
      api.feeReportNonFinancial(seasonId).then(setFollowUps),
      api.feeReportCashflow(seasonId).then(setCashflow),
    ]).catch(e => toast.error(e.message))
  }, [seasonId])
  useEffect(() => { load() }, [load])

  const overall = summary?.overall || {}
  const totalCash = useMemo(() =>
    (cashflow || []).reduce((acc, m) => acc + (m.total || 0), 0)
  , [cashflow])

  function exportCsv() {
    if (!seasonId) return
    window.open(api.feeReportExportUrl(seasonId), '_blank')
  }
  const inp = 'bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent'

  return (
    <BetterFeesLayout>
      <div className="max-w-5xl">
        <div className="flex flex-wrap items-end justify-between gap-3 mb-4">
          <div>
            <h1 className="font-display font-bold text-2xl text-pb-text mb-1">Reports</h1>
            <p className="text-pb-faint text-sm">Season summary, follow-up list, and monthly cashflow. Export the full ledger for the bookkeeper.</p>
          </div>
          <div className="flex items-center gap-2">
            <select value={seasonId} onChange={e => setSeasonId(e.target.value)} className={inp}>
              {seasons.map(s => <option key={s.id} value={s.id}>{formatSeason(s)}</option>)}
            </select>
            <button onClick={exportCsv} disabled={!seasonId}
              className="px-3 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50" style={{ background: 'var(--pb-accent)' }}>
              EXPORT CSV
            </button>
          </div>
        </div>

        {/* KPIs */}
        {summary === null ? <PbSpinner message="Loading summary…" /> : (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3 mb-6">
              <Kpi label="Members" value={overall.members ?? 0} />
              <Kpi label="Financial" value={overall.financial ?? 0} />
              <Kpi label="Non-Financial" value={overall.non_financial ?? 0} warn={(overall.non_financial ?? 0) > 0} />
              <Kpi label="Payable" value={money(overall.total_payable)} />
              <Kpi label="Paid" value={money(overall.total_paid)} />
              <Kpi label="Waived" value={money(overall.match_fee_waived)} sky />
              <Kpi label="Outstanding" value={money(overall.total_outstanding)} accent />
            </div>

            {/* By payment type */}
            {summary?.by_payment_type?.length > 0 && (
              <div className="pb-card overflow-hidden mb-8">
                <table className="w-full">
                  <thead>
                    <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left bg-pb-surface2/40">
                      <th className="font-medium py-2.5 pl-5 pr-3">PAYMENT TYPE</th>
                      <th className="font-medium py-2.5 pr-3 w-20 text-right">MEMBERS</th>
                      <th className="font-medium py-2.5 pr-3 w-28 text-right">PAYABLE</th>
                      <th className="font-medium py-2.5 pr-3 w-28 text-right">PAID</th>
                      <th className="font-medium py-2.5 pr-3 w-24 text-right">WAIVED</th>
                      <th className="font-medium py-2.5 pr-5 w-32 text-right">OUTSTANDING</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.by_payment_type.map(b => (
                      <tr key={b.payment_type} className="pb-hairline-t align-middle">
                        <td className="py-2.5 pl-5 pr-3 text-pb-text text-sm capitalize">{b.payment_type.replace('_', ' ')}</td>
                        <td className="py-2.5 pr-3 text-right font-mono text-[11px] text-pb-dim tabular-nums">{b.members}</td>
                        <td className="py-2.5 pr-3 text-right font-mono text-[11px] text-pb-dim tabular-nums">{money(b.payable)}</td>
                        <td className="py-2.5 pr-3 text-right font-mono text-[11px] text-pb-dim tabular-nums">{money(b.paid)}</td>
                        <td className={`py-2.5 pr-3 text-right font-mono text-[11px] tabular-nums ${b.waived > 0 ? 'text-sky-300/90' : 'text-pb-faintest'}`}>{money(b.waived)}</td>
                        <td className={`py-2.5 pr-5 text-right font-mono text-[11px] tabular-nums ${b.outstanding > 0 ? 'text-pb-text' : 'text-pb-faintest'}`}>{money(b.outstanding)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Follow-up list */}
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2 uppercase">
              Non-Financial Follow-Up <span className="text-pb-faintest">({(followUps || []).length})</span>
            </p>
            <p className="text-pb-dim text-sm mb-3 leading-relaxed">
              Members who currently owe money, sorted biggest first. Contact details are pulled from each member's profile.
            </p>
            {followUps === null ? <PbSpinner /> : followUps.length === 0 ? (
              <div className="pb-card p-6 text-center text-pb-dim text-sm mb-8">Everyone’s financial. 🎉</div>
            ) : (
              <div className="pb-card overflow-hidden mb-8">
                <table className="w-full">
                  <thead>
                    <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left bg-pb-surface2/40">
                      <th className="font-medium py-2.5 pl-5 pr-3">NAME</th>
                      <th className="font-medium py-2.5 pr-3">TIER</th>
                      <th className="font-medium py-2.5 pr-3 w-24 text-right">M’SHIP</th>
                      <th className="font-medium py-2.5 pr-3 w-24 text-right">MATCH</th>
                      <th className="font-medium py-2.5 pr-3 w-24 text-right">TOTAL</th>
                      <th className="font-medium py-2.5 pr-5 w-52 text-right">CONTACT</th>
                    </tr>
                  </thead>
                  <tbody>
                    {followUps.map(r => (
                      <tr key={r.member_season_id} className="pb-hairline-t align-middle hover:bg-pb-surface2/40">
                        <td className="py-2.5 pl-5 pr-3">
                          <Link to={`/admin/fees/member/${r.member_id}?season=${seasonId}`}
                            className="text-pb-text text-sm hover:text-pb-accent transition-colors">{r.full_name}</Link>
                        </td>
                        <td className="py-2.5 pr-3 text-pb-dim text-sm">{r.tier || '—'}</td>
                        <td className="py-2.5 pr-3 text-right font-mono text-[11px] text-pb-dim tabular-nums whitespace-nowrap">{money(r.membership_outstanding)}</td>
                        <td className="py-2.5 pr-3 text-right font-mono text-[11px] text-pb-dim tabular-nums whitespace-nowrap">{money(r.match_fee_outstanding)}</td>
                        <td className="py-2.5 pr-3 text-right font-mono text-[11px] tabular-nums whitespace-nowrap" style={{ color: 'var(--pb-accent)' }}>{money(r.total_outstanding)}</td>
                        <td className="py-2.5 pr-5 text-right font-mono text-[10px] text-pb-faintest truncate max-w-0">
                          {r.email || r.mobile || '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Cashflow */}
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2 uppercase">
              Monthly Cashflow <span className="text-pb-faintest">. Total received {money(totalCash)}</span>
            </p>
            <p className="text-pb-dim text-sm mb-3 leading-relaxed">
              Payments by month. Membership and match-day kept separate so you can see when each cash stream lands.
            </p>
            {cashflow === null ? <PbSpinner /> : cashflow.length === 0 ? (
              <div className="pb-card p-6 text-center text-pb-dim text-sm">No payments logged yet for this season.</div>
            ) : (
              <div className="pb-card p-5"><CashflowBars series={cashflow} /></div>
            )}
          </>
        )}
      </div>
    </BetterFeesLayout>
  )
}
