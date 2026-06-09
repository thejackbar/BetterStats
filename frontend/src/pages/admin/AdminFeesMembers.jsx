import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import BetterFeesLayout from '../../components/admin/BetterFeesLayout'
import { PbSpinner } from '../../lib/presskit'

function sortSeasons(seasons) {
  return seasons.filter(s => !s.alias_of).sort((a, b) => (b.year || 0) - (a.year || 0) || (b.name > a.name ? 1 : -1))
}
const money = n => `$${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`

function StatusPill({ status }) {
  if (status === 'financial')
    return <span className="font-mono text-[9px] tracking-wide2 text-green-300 bg-green-900/40 border border-green-600/30 rounded px-1.5 py-0.5">FINANCIAL</span>
  if (status === 'non_financial')
    return <span className="font-mono text-[9px] tracking-wide2 text-pb-amber border border-pb-amber/40 rounded px-1.5 py-0.5">OWES</span>
  if (status === 'needs_tier')
    return <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest border pb-hairline rounded px-1.5 py-0.5">NEEDS TIER</span>
  return null
}

function Kpi({ label, value, accent, warn }) {
  return (
    <div className="pb-card px-4 py-3">
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">{label}</div>
      <div className={`font-display font-bold text-xl ${warn ? 'text-pb-amber' : accent ? '' : 'text-pb-text'}`}
        style={accent && !warn ? { color: 'var(--pb-accent)' } : {}}>{value}</div>
    </div>
  )
}

function AddMemberModal({ seasonId, tiers, onClose, onCreated }) {
  const toast = useToast()
  const [form, setForm] = useState({ full_name: '', email: '', mobile: '', fee_schedule_id: '' })
  const [busy, setBusy] = useState(false)
  const inp = 'w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'

  async function submit() {
    if (!form.full_name.trim()) { toast.error('Name is required'); return }
    setBusy(true)
    try {
      await api.feeCreateMember({
        season_id: seasonId, full_name: form.full_name.trim(),
        email: form.email.trim() || null, mobile: form.mobile.trim() || null,
        fee_schedule_id: form.fee_schedule_id || null,
      })
      toast.success('Member added'); onCreated()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" style={{ backdropFilter: 'blur(2px)' }} onClick={onClose}>
      <div className="bg-pb-surface pb-card w-full max-w-md" onClick={e => e.stopPropagation()}>
        <div className="px-5 py-3.5 border-b pb-hairline-b flex items-center justify-between">
          <h2 className="font-display font-bold text-pb-text">Add member</h2>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text">✕</button>
        </div>
        <div className="p-5 space-y-3">
          <p className="text-pb-faint text-[12px] leading-relaxed">
            For non-playing members (life members, sponsors, ICL). Players who appear in a game are added automatically.
          </p>
          <div>
            <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">FULL NAME</label>
            <input autoFocus className={inp} placeholder="Surname, First" value={form.full_name}
              onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">EMAIL</label>
              <input className={inp} value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
            </div>
            <div>
              <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">MOBILE</label>
              <input className={inp} value={form.mobile} onChange={e => setForm(f => ({ ...f, mobile: e.target.value }))} />
            </div>
          </div>
          <div>
            <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">TIER</label>
            <select className={inp} value={form.fee_schedule_id} onChange={e => setForm(f => ({ ...f, fee_schedule_id: e.target.value }))}>
              <option value="">— Needs tier —</option>
              {tiers.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>
        </div>
        <div className="px-5 py-3.5 border-t pb-hairline-t flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text">CANCEL</button>
          <button onClick={submit} disabled={busy}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50" style={{ background: 'var(--pb-accent)' }}>
            {busy ? 'ADDING…' : 'ADD MEMBER'}
          </button>
        </div>
      </div>
    </div>
  )
}

function BulkTierModal({ seasonId, memberIds, tiers, onClose, onSaved }) {
  const toast = useToast()
  const [tierId, setTierId] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit() {
    setBusy(true)
    try {
      const r = await api.feeBulkSetTier(seasonId, memberIds, tierId || null)
      toast.success(`Tier set on ${r.updated} member${r.updated === 1 ? '' : 's'}`)
      onSaved()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  const inp = 'w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" style={{ backdropFilter: 'blur(2px)' }} onClick={onClose}>
      <div className="bg-pb-surface pb-card w-full max-w-md" onClick={e => e.stopPropagation()}>
        <div className="px-5 py-3.5 border-b pb-hairline-b flex items-center justify-between">
          <h2 className="font-display font-bold text-pb-text">Set tier for {memberIds.length} member{memberIds.length === 1 ? '' : 's'}</h2>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text">✕</button>
        </div>
        <div className="p-5 space-y-3">
          <p className="text-pb-faint text-[12px] leading-relaxed">
            Updates each member's tier for this season — and carries the new tier forward as their default for next season's rollover.
          </p>
          <div>
            <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">TIER</label>
            <select autoFocus className={inp} value={tierId} onChange={e => setTierId(e.target.value)}>
              <option value="">— Clear tier (needs review) —</option>
              {tiers.map(t => <option key={t.id} value={t.id}>{t.name} ({t.payment_type})</option>)}
            </select>
          </div>
        </div>
        <div className="px-5 py-3.5 border-t pb-hairline-t flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text">CANCEL</button>
          <button onClick={submit} disabled={busy}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50" style={{ background: 'var(--pb-accent)' }}>
            {busy ? 'SAVING…' : 'APPLY'}
          </button>
        </div>
      </div>
    </div>
  )
}

function RolloverModal({ seasonId, fromSeason, onClose, onDone }) {
  const toast = useToast()
  const [includeLeft, setIncludeLeft] = useState(false)
  const [busy, setBusy] = useState(false)
  async function go() {
    setBusy(true)
    try {
      const r = await api.feeRollover(seasonId, fromSeason.id, includeLeft)
      toast.success(`Rolled over ${r.created} member${r.created === 1 ? '' : 's'} (${r.skipped_left_club} left-club skipped)`)
      onDone()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" style={{ backdropFilter: 'blur(2px)' }} onClick={onClose}>
      <div className="bg-pb-surface pb-card w-full max-w-md" onClick={e => e.stopPropagation()}>
        <div className="px-5 py-3.5 border-b pb-hairline-b flex items-center justify-between">
          <h2 className="font-display font-bold text-pb-text">Roll over from {fromSeason.name}</h2>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text">✕</button>
        </div>
        <div className="p-5 space-y-3">
          <p className="text-pb-faint text-[12px] leading-relaxed">
            Opens this season for every member that was in {fromSeason.name}. Each member's tier is carried across (matched by name
            against this season's rate card). Make sure you've seeded or copied the rate card first.
          </p>
          <label className="flex items-center gap-2 font-mono text-[11px] text-pb-dim cursor-pointer select-none">
            <input type="checkbox" checked={includeLeft} onChange={e => setIncludeLeft(e.target.checked)} />
            Include "Left Club" tiers (default: skipped)
          </label>
          <p className="font-mono text-[10px] text-pb-faintest leading-relaxed">
            Members who already exist in this season are skipped. Payments stay with the original season.
          </p>
        </div>
        <div className="px-5 py-3.5 border-t pb-hairline-t flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text">CANCEL</button>
          <button onClick={go} disabled={busy}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50" style={{ background: 'var(--pb-accent)' }}>
            {busy ? 'ROLLING OVER…' : 'ROLL OVER'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function AdminFeesMembers() {
  const toast = useToast()
  const [seasons, setSeasons] = useState([])
  const [seasonId, setSeasonId] = useState('')
  const [data, setData] = useState(null)
  const [tiers, setTiers] = useState([])
  const [q, setQ] = useState('')
  const [needsTierOnly, setNeedsTierOnly] = useState(false)
  const [owesOnly, setOwesOnly] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [recomputing, setRecomputing] = useState(false)
  const [selected, setSelected] = useState(() => new Set())
  const [showBulkTier, setShowBulkTier] = useState(false)
  const [showRollover, setShowRollover] = useState(false)

  useEffect(() => {
    api.adminListSeasons()
      .then(s => { const sorted = sortSeasons(s); setSeasons(sorted); if (sorted[0]) setSeasonId(sorted[0].id) })
      .catch(e => toast.error(e.message))
  }, [])

  const load = useCallback(() => {
    if (!seasonId) return
    setData(null)
    setSelected(new Set())
    api.feeListMembers(seasonId).then(setData).catch(e => { toast.error(e.message); setData({ members: [], summary: {} }) })
    api.feeListSchedule(seasonId).then(setTiers).catch(() => setTiers([]))
  }, [seasonId])
  useEffect(() => { load() }, [load])

  // The next-most-recent season is the rollover source when this one is empty.
  const previousSeason = useMemo(() => {
    const idx = seasons.findIndex(s => s.id === seasonId)
    return idx >= 0 && idx + 1 < seasons.length ? seasons[idx + 1] : null
  }, [seasons, seasonId])

  async function recompute() {
    setRecomputing(true)
    try {
      const r = await api.feeRecompute(seasonId)
      toast.success(`Match days rebuilt — ${r.members_created} new members, ${r.entries_upserted} entries`)
      load()
    } catch (e) { toast.error(e.message) } finally { setRecomputing(false) }
  }

  const filtered = useMemo(() => {
    if (!data?.members) return []
    const needle = q.trim().toLowerCase()
    return data.members.filter(m =>
      (!needsTierOnly || m.needs_tier) &&
      (!owesOnly || m.status === 'non_financial') &&
      (!needle || m.full_name.toLowerCase().includes(needle) || (m.tier || '').toLowerCase().includes(needle))
    )
  }, [data, q, needsTierOnly, owesOnly])

  const s = data?.summary || {}
  const inp = 'bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent'

  return (
    <BetterFeesLayout>
      <div className="max-w-5xl">
        <div className="flex flex-wrap items-end justify-between gap-3 mb-4">
          <div>
            <h1 className="font-display font-bold text-2xl text-pb-text mb-1">Members</h1>
            <p className="text-pb-faint text-sm">Membership &amp; match-day fees owed. Days played sync automatically.</p>
          </div>
          <div className="flex items-center gap-2">
            <select value={seasonId} onChange={e => setSeasonId(e.target.value)} className={inp}>
              {seasons.map(se => <option key={se.id} value={se.id}>{se.name}</option>)}
            </select>
            {previousSeason && (
              <button onClick={() => setShowRollover(true)} disabled={!seasonId}
                className="px-3 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-accent transition-colors disabled:opacity-50 whitespace-nowrap">
                ROLL OVER
              </button>
            )}
            <button onClick={() => setShowAdd(true)} disabled={!seasonId}
              className="px-3 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
              + MEMBER
            </button>
          </div>
        </div>

        {data === null ? (
          <PbSpinner message="Loading members…" />
        ) : (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-5">
              <Kpi label="Members" value={s.total_members ?? 0} />
              <Kpi label="Non-Financial" value={s.non_financial ?? 0} warn={(s.non_financial ?? 0) > 0} />
              <Kpi label="Payable" value={money(s.total_payable)} />
              <Kpi label="Paid" value={money(s.total_paid)} />
              <Kpi label="Outstanding" value={money(s.total_outstanding)} accent />
            </div>

            <div className="flex flex-wrap items-center gap-3 mb-3">
              <input className={`${inp} flex-1 min-w-[180px]`} placeholder="Search name or tier…" value={q} onChange={e => setQ(e.target.value)} />
              <label className="flex items-center gap-2 font-mono text-[10px] tracking-wide2 text-pb-faint cursor-pointer select-none">
                <input type="checkbox" checked={needsTierOnly} onChange={e => setNeedsTierOnly(e.target.checked)} />
                NEEDS TIER
              </label>
              <label className="flex items-center gap-2 font-mono text-[10px] tracking-wide2 text-pb-faint cursor-pointer select-none">
                <input type="checkbox" checked={owesOnly} onChange={e => setOwesOnly(e.target.checked)} />
                OWES MONEY
              </label>
              <button onClick={recompute} disabled={recomputing}
                className="px-3 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-accent transition-colors disabled:opacity-50">
                {recomputing ? 'SYNCING…' : 'SYNC MATCH DAYS'}
              </button>
            </div>

            {filtered.length === 0 ? (
              data.members.length === 0 && previousSeason ? (
                // First view of a new season → offer to roll forward from the prior one.
                <div className="pb-card p-6">
                  <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-2">Open Season</p>
                  <p className="text-pb-text text-sm mb-1">No members yet for this season.</p>
                  <p className="text-pb-dim text-sm mb-4 leading-relaxed">
                    Roll forward everyone from <span className="text-pb-text">{previousSeason.name}</span> — each member keeps their tier
                    (so you only bulk-edit the exceptions, e.g. graduating students). Payments stay behind, "Left Club" members are skipped.
                  </p>
                  <div className="flex gap-2">
                    <button onClick={() => setShowRollover(true)}
                      className="px-3 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg" style={{ background: 'var(--pb-accent)' }}>
                      ROLL OVER FROM {previousSeason.name.toUpperCase()}
                    </button>
                    <button onClick={recompute} disabled={recomputing}
                      className="px-3 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-accent transition-colors disabled:opacity-50">
                      {recomputing ? 'SYNCING…' : 'JUST SYNC MATCH DAYS'}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="pb-card p-6 text-center">
                  <p className="text-pb-dim text-sm mb-1">
                    {data.members.length === 0 ? 'No members yet for this season.' : 'No members match your filter.'}
                  </p>
                  {data.members.length === 0 && (
                    <p className="font-mono text-[11px] text-pb-faint">
                      Set up the <Link to="/admin/fees/schedule" className="text-pb-accent underline">Fee Schedule</Link>, then hit “Sync Match Days”.
                    </p>
                  )}
                </div>
              )
            ) : (
              <>
                <p className="font-mono text-[10px] tracking-wide2 text-pb-faint mb-2">
                  Tip: tick rows to bulk-assign a tier (e.g. promote graduating students to Senior in one go).
                </p>
                <div className="pb-card overflow-hidden">
                  <table className="w-full">
                    <thead>
                      <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left bg-pb-surface2/40">
                        <th className="font-medium py-2.5 pl-5 pr-2 w-8">
                          <input type="checkbox"
                            checked={filtered.length > 0 && filtered.every(m => selected.has(m.member_id))}
                            onChange={e => {
                              if (e.target.checked) setSelected(new Set(filtered.map(m => m.member_id)))
                              else setSelected(new Set())
                            }}
                            className="cursor-pointer align-middle" />
                        </th>
                        <th className="font-medium py-2.5 pr-3">NAME</th>
                        <th className="font-medium py-2.5 pr-3">TIER</th>
                        <th className="font-medium py-2.5 pr-3 w-16 text-right">DAYS</th>
                        <th className="font-medium py-2.5 pr-3 w-24 text-right">PAYABLE</th>
                        <th className="font-medium py-2.5 pr-3 w-24 text-right">PAID</th>
                        <th className="font-medium py-2.5 pr-3 w-24 text-right">OWED</th>
                        <th className="font-medium py-2.5 pr-5 w-28 text-right">STATUS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.map(m => {
                        const isSelected = selected.has(m.member_id)
                        return (
                          <tr key={m.member_season_id}
                            className={`pb-hairline-t align-middle ${isSelected ? 'bg-pb-surface2/60' : 'hover:bg-pb-surface2/40'} transition-colors`}>
                            <td className="py-2.5 pl-5 pr-2">
                              <input type="checkbox" checked={isSelected}
                                onChange={e => setSelected(s => {
                                  const n = new Set(s)
                                  if (e.target.checked) n.add(m.member_id); else n.delete(m.member_id)
                                  return n
                                })}
                                className="cursor-pointer align-middle" />
                            </td>
                            <td className="py-2.5 pr-3">
                              <Link to={`/admin/fees/member/${m.member_id}?season=${seasonId}`}
                                className="text-pb-text text-sm hover:text-pb-accent transition-colors inline-flex items-center gap-1.5">
                                {m.full_name}
                                {!m.is_linked && <span className="font-mono text-[8px] tracking-wide2 text-pb-faintest border pb-hairline rounded px-1 py-px">MANUAL</span>}
                              </Link>
                            </td>
                            <td className="py-2.5 pr-3">
                              {m.needs_tier
                                ? <span className="font-mono text-[10px] text-pb-amber">⚠ needs tier</span>
                                : <span className="text-pb-dim text-sm">{m.tier}</span>}
                            </td>
                            <td className="py-2.5 pr-3 text-right font-mono text-[11px] text-pb-dim tabular-nums">{m.match_days || 0}</td>
                            <td className="py-2.5 pr-3 text-right font-mono text-[11px] text-pb-dim tabular-nums">{money(m.total_payable)}</td>
                            <td className="py-2.5 pr-3 text-right font-mono text-[11px] text-pb-dim tabular-nums">{money(m.total_paid)}</td>
                            <td className={`py-2.5 pr-3 text-right font-mono text-[11px] tabular-nums ${m.total_outstanding > 0 ? 'text-pb-text' : 'text-pb-faintest'}`}>
                              {money(m.total_outstanding)}
                            </td>
                            <td className="py-2.5 pr-5 text-right whitespace-nowrap">
                              {m.in_credit && (
                                <span className="font-mono text-[9px] tracking-wide2 text-green-300 bg-green-900/40 border border-green-600/30 rounded px-1.5 py-0.5 mr-1.5"
                                  title="In credit toward future games">+{money(m.credit)}</span>
                              )}
                              <StatusPill status={m.status} />
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            )}
            <p className="font-mono text-[10px] text-pb-faintest mt-3">
              Showing {filtered.length} of {data.members.length}.
            </p>
          </>
        )}
      </div>

      {/* Sticky bulk-action bar — appears when any row is checked. */}
      {selected.size > 0 && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 bg-pb-surface border pb-hairline rounded-lg shadow-2xl px-4 py-3 flex items-center gap-3"
          style={{ borderColor: 'var(--pb-accent)' }}>
          <span className="font-mono text-[11px] text-pb-text">{selected.size} selected</span>
          <button onClick={() => setShowBulkTier(true)}
            className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg" style={{ background: 'var(--pb-accent)' }}>
            SET TIER
          </button>
          <button onClick={() => setSelected(new Set())}
            className="font-mono text-[10px] text-pb-faint hover:text-pb-text">CLEAR</button>
        </div>
      )}

      {showAdd && (
        <AddMemberModal seasonId={seasonId} tiers={tiers}
          onClose={() => setShowAdd(false)}
          onCreated={() => { setShowAdd(false); load() }} />
      )}
      {showBulkTier && (
        <BulkTierModal seasonId={seasonId} memberIds={Array.from(selected)} tiers={tiers}
          onClose={() => setShowBulkTier(false)}
          onSaved={() => { setShowBulkTier(false); setSelected(new Set()); load() }} />
      )}
      {showRollover && previousSeason && (
        <RolloverModal seasonId={seasonId} fromSeason={previousSeason}
          onClose={() => setShowRollover(false)}
          onDone={() => { setShowRollover(false); load() }} />
      )}
    </BetterFeesLayout>
  )
}
