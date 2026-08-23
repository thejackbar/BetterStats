import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import BetterFeesLayout from '../../components/admin/BetterFeesLayout'
import { Button, Select, SearchInput, StatCard, Badge, Empty } from '../../components/admin/ui'
import { usePeopleFilters } from '../../components/admin/clubmanager/peopleFilters'
import { PbSpinner } from '../../lib/presskit'
import { formatSeason } from '../../lib/cricketFormat'

const money = n => `$${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`

function sortSeasons(seasons) {
  return seasons.filter(s => !s.alias_of).sort((a, b) => (b.year || 0) - (a.year || 0) || (b.name > a.name ? 1 : -1))
}

const KIND_LABEL = { membership: "M'ship", match_day: 'Match' }

export default function AdminFeePayments() {
  // The Directory's People filters (see peopleFilters.jsx) — matched on the
  // segments that service computes, so this screen never re-derives them.
  const people = usePeopleFilters({ seg: true })
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
      // The Directory's People filters, so a payment run can be scoped to a
      // group of people rather than only searched by name.
      people.matches(p.member_id) &&
      (!needle || (p.full_name || '').toLowerCase().includes(needle) ||
                  (p.bank_ref || '').toLowerCase().includes(needle) ||
                  (p.method || '').toLowerCase().includes(needle))
    )
  }, [payments, q, kindFilter, people.anyOn, people.matches])

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

  // Title, live count, filters and the two actions all belong to the shell's
  // sticky header, the same as the Directory — so the page-level <h1> and the
  // paragraph under it are gone rather than drawn a second time in the body.
  const header = {
    title: 'Payments',
    caption: `The season's full ledger · ${filtered.length} of ${payments?.length ?? 0} shown`,
    // The search sits under the heading, on the same line as Bookmarks — the
    // one place every Committee screen and the Directory carry theirs.
    twoRow: true,
    // WHO you are looking at sits on the title line, centred, in Committee's
    // own segmented control — the same three menus the Directory carries, so a
    // money job can be scoped to a group of people ("every Junior Player") from
    // here. The search and the kind filter stay underneath.
    tabs: people.menus,
    filters: (
      <div className="flex items-center gap-2 flex-wrap">
        <SearchInput wide value={q} onChange={setQ} placeholder="Search name, bank ref, method…" />
        {people.chips}
        <Select value={kindFilter} onChange={e => setKindFilter(e.target.value)} className="!w-auto">
          <option value="">All kinds</option>
          <option value="membership">Membership only</option>
          <option value="match_day">Match day only</option>
        </Select>
      </div>
    ),
    actions: (
      <>
        <Select value={seasonId} onChange={e => setSeasonId(e.target.value)} className="!w-auto max-w-[190px]">
          {seasons.map(s => <option key={s.id} value={s.id}>{formatSeason(s)}</option>)}
        </Select>
        <Button as={Link} to={`/admin/fees/payments/bulk${seasonId ? `?season=${seasonId}` : ''}`}>Bulk payment</Button>
        <Button as={Link} to="/admin/fees/payments/import" variant="primary">Import bank CSV</Button>
      </>
    ),
  }

  return (
    <BetterFeesLayout {...header}>
      <div className="max-w-5xl">
        {payments === null ? <PbSpinner message="Loading payments…" /> : (
          <>
            <div className="grid grid-cols-3 gap-2 mb-4">
              <StatCard label="Payments" value={filtered.length} ink="var(--pb-text)" />
              <StatCard label="Membership" value={money(total.membership)} ink="var(--pb-text)" />
              <StatCard label="Total" value={money(total.total)} accent />
            </div>

            {filtered.length === 0 ? (
              <div className="pb-card">
                <Empty>
                  {(payments || []).length === 0
                    ? 'No payments logged yet. Add them from the member page.'
                    : 'No payments match your filter.'}
                </Empty>
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
                        <td className="py-2.5 pr-3 whitespace-nowrap"><Badge>{KIND_LABEL[p.kind]}</Badge></td>
                        <td className="py-2.5 pr-3 text-right font-mono text-[11px] text-pb-text tabular-nums whitespace-nowrap">{money(p.amount)}</td>
                        <td className="py-2.5 pr-3 font-mono text-[10px] text-pb-dim whitespace-nowrap">{p.method || '—'}</td>
                        <td className="py-2.5 pr-3 text-pb-faint text-[12px] truncate max-w-0">
                          {p.bank_ref || ''}
                          {p.notes && <span className="text-pb-faintest"> · {p.notes}</span>}
                        </td>
                        <td className="py-2.5 pr-5 text-right">
                          <Button size="sm" variant="danger" onClick={() => del(p.id)}>Delete</Button>
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
    </BetterFeesLayout>
  )
}
