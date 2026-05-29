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
        <h1 className="font-display font-bold text-2xl text-pb-text mb-1">Payments</h1>
        <p className="text-pb-faint text-sm mb-5">
          The full ledger for one season. Log payments from the individual member page; this view is for searching, reconciling,
          and removing mistakes.
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
                <div className="grid grid-cols-[auto_1.4fr_auto_auto_auto_1fr_auto] gap-3 px-5 py-2.5 bg-pb-surface2/40 font-mono text-[10px] tracking-wide3 text-pb-faint">
                  <span className="w-20">DATE</span><span>MEMBER</span>
                  <span className="w-16">KIND</span><span className="w-20 text-right">AMOUNT</span>
                  <span className="w-14">METHOD</span><span>REF / NOTES</span><span></span>
                </div>
                {filtered.map((p, i) => (
                  <div key={p.id} className={`grid grid-cols-[auto_1.4fr_auto_auto_auto_1fr_auto] items-center gap-3 px-5 py-2.5 ${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2/40`}>
                    <span className="font-mono text-[10px] text-pb-faintest w-20">{p.paid_at || '—'}</span>
                    <Link to={`/admin/fees/member/${p.member_id}?season=${seasonId}`} className="text-pb-text text-sm truncate hover:text-pb-accent transition-colors">
                      {p.full_name}
                    </Link>
                    <span className="font-mono text-[10px] text-pb-faint w-16">{KIND_LABEL[p.kind]}</span>
                    <span className="font-mono text-[11px] text-pb-text w-20 text-right">{money(p.amount)}</span>
                    <span className="font-mono text-[10px] text-pb-dim w-14">{p.method || '—'}</span>
                    <span className="text-pb-faint text-[12px] truncate">
                      {p.bank_ref || ''}
                      {p.notes && <span className="text-pb-faintest"> · {p.notes}</span>}
                    </span>
                    <button onClick={() => del(p.id)}
                      className="font-mono text-[9px] text-pb-red/50 hover:text-pb-red transition-colors">DEL</button>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </AdminLayout>
  )
}
