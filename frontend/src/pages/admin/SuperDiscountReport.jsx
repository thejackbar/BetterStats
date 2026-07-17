import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

// Super-Admin rollup of every discount actually paid out — see
// routers/billing.py::discount_report. Sourced from billing_invoices (what a
// club was actually charged), not discount_coupons_redemptions (which only
// records that a code was applied, not its dollar value on any one invoice).

const INPUT_CLS = 'bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
const LABEL_CLS = 'font-mono text-[10px] text-pb-faint block mb-1'

const fmt = (cents) => `$${((cents || 0) / 100).toFixed(2)}`

function SummaryCard({ label, value, sub }) {
  return (
    <div className="pb-card p-4">
      <p className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint">{label}</p>
      <p className="text-2xl font-display font-bold text-pb-text mt-1">{value}</p>
      {sub && <p className="font-mono text-[10px] text-pb-faintest mt-1">{sub}</p>}
    </div>
  )
}

export default function SuperDiscountReport() {
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    setError('')
    api.superDiscountReport(dateFrom || undefined, dateTo || undefined)
      .then(setReport)
      .catch((e) => setError(e.message || 'Could not load the discount report'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <AdminLayout>
      <div className="max-w-[1200px] mx-auto p-4 sm:p-6">
        <div className="mb-5">
          <h1 className="text-xl font-semibold text-pb-text">Discount report</h1>
          <p className="text-sm text-pb-dim mt-1">
            Bundle and coupon-code discounts actually paid out, per club and platform-wide.
          </p>
        </div>

        <div className="pb-card p-4 mb-5 flex flex-wrap items-end gap-3">
          <div>
            <label className={LABEL_CLS}>From</label>
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className={INPUT_CLS} />
          </div>
          <div>
            <label className={LABEL_CLS}>Until</label>
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className={INPUT_CLS} />
          </div>
          <button onClick={load}
            className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded font-semibold text-pb-bg"
            style={{ background: 'var(--pb-accent)' }}>
            APPLY
          </button>
          {(dateFrom || dateTo) && (
            <button onClick={() => { setDateFrom(''); setDateTo(''); }}
              className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded border pb-hairline text-pb-faint hover:text-pb-text">
              CLEAR
            </button>
          )}
        </div>

        {error && <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 mb-4">{error}</p>}

        {loading ? (
          <p className="text-sm text-pb-dim">Loading…</p>
        ) : !report ? null : (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
              <SummaryCard label="Bundle discount total" value={fmt(report.bundle.total_cents)} sub={`${report.bundle.total_count} invoice${report.bundle.total_count === 1 ? '' : 's'}`} />
              <SummaryCard label="Bundle — clubs" value={report.bundle.by_club.length} />
              <SummaryCard label="Coupon discount total" value={fmt(report.coupons.total_cents)} sub={`${report.coupons.total_count} invoice${report.coupons.total_count === 1 ? '' : 's'}`} />
              <SummaryCard label="Coupon codes used" value={report.coupons.by_code.length} />
            </div>

            <div className="mb-6">
              <h2 className="font-display font-bold text-pb-text mb-2">Bundle discount by club</h2>
              <div className="pb-card overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint border-b pb-hairline">
                      <th className="px-3 py-2.5">Club</th>
                      <th className="px-3 py-2.5">Invoices</th>
                      <th className="px-3 py-2.5">Total discount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.bundle.by_club.length === 0 ? (
                      <tr><td colSpan={3} className="px-3 py-4 text-pb-faint font-mono text-[11px]">No bundle discounts in this range.</td></tr>
                    ) : report.bundle.by_club.map((r) => (
                      <tr key={r.organisation_id} className="border-b pb-hairline hover:bg-pb-surface2/40">
                        <td className="px-3 py-2 text-pb-text">{r.organisation_name}</td>
                        <td className="px-3 py-2 text-pb-dim">{r.count}</td>
                        <td className="px-3 py-2 text-pb-text font-mono">{fmt(r.total_cents)}</td>
                      </tr>
                    ))}
                  </tbody>
                  {report.bundle.by_club.length > 0 && (
                    <tfoot>
                      <tr className="border-t pb-hairline font-semibold">
                        <td className="px-3 py-2 text-pb-text">All clubs</td>
                        <td className="px-3 py-2 text-pb-text">{report.bundle.total_count}</td>
                        <td className="px-3 py-2 text-pb-text font-mono">{fmt(report.bundle.total_cents)}</td>
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
            </div>

            <div className="mb-6">
              <h2 className="font-display font-bold text-pb-text mb-2">Coupon discounts by code (all clubs)</h2>
              <div className="pb-card overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint border-b pb-hairline">
                      <th className="px-3 py-2.5">Code</th>
                      <th className="px-3 py-2.5">Clubs</th>
                      <th className="px-3 py-2.5">Invoices</th>
                      <th className="px-3 py-2.5">Total discount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.coupons.by_code.length === 0 ? (
                      <tr><td colSpan={4} className="px-3 py-4 text-pb-faint font-mono text-[11px]">No coupon discounts in this range.</td></tr>
                    ) : report.coupons.by_code.map((r) => (
                      <tr key={r.coupon_code} className="border-b pb-hairline hover:bg-pb-surface2/40">
                        <td className="px-3 py-2 font-mono text-pb-text">{r.coupon_code}</td>
                        <td className="px-3 py-2 text-pb-dim">{r.club_count}</td>
                        <td className="px-3 py-2 text-pb-dim">{r.count}</td>
                        <td className="px-3 py-2 text-pb-text font-mono">{fmt(r.total_cents)}</td>
                      </tr>
                    ))}
                  </tbody>
                  {report.coupons.by_code.length > 0 && (
                    <tfoot>
                      <tr className="border-t pb-hairline font-semibold">
                        <td className="px-3 py-2 text-pb-text">All codes</td>
                        <td className="px-3 py-2"></td>
                        <td className="px-3 py-2 text-pb-text">{report.coupons.total_count}</td>
                        <td className="px-3 py-2 text-pb-text font-mono">{fmt(report.coupons.total_cents)}</td>
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
            </div>

            <div>
              <h2 className="font-display font-bold text-pb-text mb-2">Coupon discounts by club</h2>
              <div className="pb-card overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint border-b pb-hairline">
                      <th className="px-3 py-2.5">Club</th>
                      <th className="px-3 py-2.5">Code</th>
                      <th className="px-3 py-2.5">Invoices</th>
                      <th className="px-3 py-2.5">Total discount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.coupons.by_club.length === 0 ? (
                      <tr><td colSpan={4} className="px-3 py-4 text-pb-faint font-mono text-[11px]">No coupon discounts in this range.</td></tr>
                    ) : report.coupons.by_club.map((r) => (
                      <tr key={`${r.organisation_id}-${r.coupon_code}`} className="border-b pb-hairline hover:bg-pb-surface2/40">
                        <td className="px-3 py-2 text-pb-text">{r.organisation_name}</td>
                        <td className="px-3 py-2 font-mono text-pb-dim">{r.coupon_code}</td>
                        <td className="px-3 py-2 text-pb-dim">{r.count}</td>
                        <td className="px-3 py-2 text-pb-text font-mono">{fmt(r.total_cents)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>
    </AdminLayout>
  )
}
