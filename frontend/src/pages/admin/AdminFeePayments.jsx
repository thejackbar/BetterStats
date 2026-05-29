import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import AdminLayout from '../../components/admin/AdminLayout'
import { PbSpinner } from '../../lib/presskit'

const money = n => `$${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`

function sortSeasons(seasons) {
  return seasons.filter(s => !s.alias_of).sort((a, b) => (b.year || 0) - (a.year || 0) || (b.name > a.name ? 1 : -1))
}

const KIND_LABEL = { membership: "M'ship", match_day: 'Match' }

export default function AdminFeePayments() {
  const toast = useToast()
  const [seasons, setSeasons] = useState([])
  const [seasonId, setSeasonId] = useState('')
  const [payments, setPayments] = useState(null)
  const [q, setQ] = useState('')
  const [kindFilter, setKindFilter] = useState('')

  useEffect(() => {
    api.adminListSeasons()
      .then(s => { const sorted = sortSeasons(s); setSeasons(sorted); if (sorted[0]) setSeasonId(sorted[0].id) })
      .catch(e => toast.error(e.message))
  }, [])

  const load = useCallback(() => {
    if (!seasonId) return
    setPayments(null)
    api.feeListPayments({ seasonId }).then(setPayments).catch(e => { toast.error(e.message); setPayments([]) })
  }, [seasonId])
  useEffect(() => { load() }, [load])

  const filtered = useMemo(() => {
    if (!payments) return []
    const needle = q.trim().toLowerCase()
    return payments.filter(p =>
      (!kindFilter || p.kind === kindFilter) &&
      (!needle || (p.full_name || '').toLowerCase().includes(needle) ||
                  (p.bank_ref || '').toLowerCase().includes(needle) ||
                  (p.method || '').toLowerCase().includes(needle))
    )
  }, [payments, q, kindFilter])

  const total = useMemo(() =>
    filtered.reduce((acc, p) => {
      acc.total += p.amount
      acc[p.kind] = (acc[p.kind] || 0) + p.amount
      return acc
    }, { total: 0, membership: 0, match_day: 0 }),
    [filtered]
  )

  async function del(id) {
    if (!confirm('Delete this payment?')) return
    try { await api.feeDeletePayment(id); toast.success('Payment deleted'); load() }
    catch (e) { toast.error(e.message) }
  }

  const inp = 'bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent'

  return (
    <AdminLayout>
      <div className="max-w-5xl">
        <div className="flex flex-wrap items-start justify-between gap-3 mb-1">
          <h1 className="font-display font-bold text-2xl text-pb-text">Payments</h1>
          <div className="flex items-center gap-2">
            <Link to={`/admin/fees/payments/bulk${seasonId ? `?season=${seasonId}` : ''}`}
              className="px-3 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-accent transition-colors whitespace-nowrap">
              + BULK PAYMENT
            </Link>
            <Link to="/admin/fees/payments/import"
              className="px-3 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
              + IMPORT BANK CSV
            </Link>
          </div>
        </div>
        <p className="text-pb-faint text-sm mb-5">
          The full ledger for one season. Log payments from the individual member page (or bulk-import from a bank-statement CSV);
          this view is for searching, reconciling, and removing mistakes.
        </p>

        <div className="flex flex-wrap items-center gap-3 mb-5">
          <select value={seasonId} onChange={e => setSeasonId(e.target.value)} className={inp}>
            {seasons.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <input className={`${inp} flex-1 min-w-[180px]`} placeholder="Search name, bank ref, method…" value={q} onChange={e => setQ(e.target.value)} />
          <select value={kindFilter} onChange={e => setKindFilter(e.target.value)} className={inp}>
            <option value="">All kinds</option>
            <option value="membership">Membership only</option>
            <option value="match_day">Match day only</option>
          </select>
        </div>

        {payments === null ? <PbSpinner message="Loading payments…" /> : (
          <>
            <div className="grid grid-cols-3 gap-3 mb-4">
              <div className="pb-card px-4 py-3">
                <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">Payments</div>
                <div className="font-display font-bold text-xl text-pb-text">{filtered.length}</div>
              </div>
              <div className="pb-card px-4 py-3">
                <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">Membership</div>
                <div className="font-display font-bold text-xl text-pb-text">{money(total.membership)}</div>
              </div>
              <div className="pb-card px-4 py-3" style={{ borderColor: 'var(--pb-accent)', borderOpacity: 0.4 }}>
                <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">Total</div>
                <div className="font-display font-bold text-xl" style={{ color: 'var(--pb-accent)' }}>{money(total.total)}</div>
              </div>
            </div>

            {filtered.length === 0 ? (
              <div className="pb-card p-6 text-center text-pb-dim text-sm">
                {(payments || []).length === 0
                  ? 'No payments logged yet. Add them from the member page.'
                  : 'No payments match your filter.'}
              </div>
            ) : (
              <div className="pb-card overflow-hidden">
                <table className="w-full">
                  <thead>
                    <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left bg-pb-surface2/40">
                      <th className="font-medium py-2.5 pl-5 pr-3 w-24">DATE</th>
                      <th className="font-medium py-2.5 pr-3">MEMBER</th>
                      <th className="font-medium py-2.5 pr-3 w-20">KIND</th>
                      <th className="font-medium py-2.5 pr-3 w-24 text-right">AMOUNT</th>
                      <th className="font-medium py-2.5 pr-3 w-20">METHOD</th>
                      <th className="font-medium py-2.5 pr-3">REF / NOTES</th>
                      <th className="font-medium py-2.5 pr-5 w-12 text-right"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map(p => (
                      <tr key={p.id} className="pb-hairline-t align-middle hover:bg-pb-surface2/40">
                        <td className="py-2.5 pl-5 pr-3 font-mono text-[10px] text-pb-faintest whitespace-nowrap">{p.paid_at || '—'}</td>
                        <td className="py-2.5 pr-3">
                          <Link to={`/admin/fees/member/${p.member_id}?season=${seasonId}`}
                            className="text-pb-text text-sm hover:text-pb-accent transition-colors">{p.full_name}</Link>
                        </td>
                        <td className="py-2.5 pr-3 font-mono text-[10px] text-pb-faint whitespace-nowrap">{KIND_LABEL[p.kind]}</td>
                        <td className="py-2.5 pr-3 text-right font-mono text-[11px] text-pb-text tabular-nums whitespace-nowrap">{money(p.amount)}</td>
                        <td className="py-2.5 pr-3 font-mono text-[10px] text-pb-dim whitespace-nowrap">{p.method || '—'}</td>
                        <td className="py-2.5 pr-3 text-pb-faint text-[12px] truncate max-w-0">
                          {p.bank_ref || ''}
                          {p.notes && <span className="text-pb-faintest"> · {p.notes}</span>}
                        </td>
                        <td className="py-2.5 pr-5 text-right">
                          <button onClick={() => del(p.id)}
                            className="font-mono text-[9px] text-pb-red/50 hover:text-pb-red transition-colors">DEL</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </AdminLayout>
  )
}
