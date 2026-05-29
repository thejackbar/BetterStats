import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import AdminLayout from '../../components/admin/AdminLayout'
import { PbSpinner } from '../../lib/presskit'

function sortSeasons(seasons) {
  return seasons.filter(s => !s.alias_of).sort((a, b) => (b.year || 0) - (a.year || 0) || (b.name > a.name ? 1 : -1))
}
const money = n => `$${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`

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

export default function AdminFeesMembers() {
  const toast = useToast()
  const [seasons, setSeasons] = useState([])
  const [seasonId, setSeasonId] = useState('')
  const [data, setData] = useState(null)
  const [tiers, setTiers] = useState([])
  const [q, setQ] = useState('')
  const [needsTierOnly, setNeedsTierOnly] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [recomputing, setRecomputing] = useState(false)

  useEffect(() => {
    api.adminListSeasons()
      .then(s => { const sorted = sortSeasons(s); setSeasons(sorted); if (sorted[0]) setSeasonId(sorted[0].id) })
      .catch(e => toast.error(e.message))
  }, [])

  const load = useCallback(() => {
    if (!seasonId) return
    setData(null)
    api.feeListMembers(seasonId).then(setData).catch(e => { toast.error(e.message); setData({ members: [], summary: {} }) })
    api.feeListSchedule(seasonId).then(setTiers).catch(() => setTiers([]))
  }, [seasonId])
  useEffect(() => { load() }, [load])

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
      (!needle || m.full_name.toLowerCase().includes(needle) || (m.tier || '').toLowerCase().includes(needle))
    )
  }, [data, q, needsTierOnly])

  const s = data?.summary || {}
  const inp = 'bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent'

  return (
    <AdminLayout>
      <div className="max-w-5xl">
        <div className="flex flex-wrap items-end justify-between gap-3 mb-4">
          <div>
            <h1 className="font-display font-bold text-2xl text-pb-text mb-1">Members</h1>
            <p className="text-pb-faint text-sm">Membership &amp; match-day fees owed. Days played sync from PlayHQ automatically.</p>
          </div>
          <div className="flex items-center gap-2">
            <select value={seasonId} onChange={e => setSeasonId(e.target.value)} className={inp}>
              {seasons.map(se => <option key={se.id} value={se.id}>{se.name}</option>)}
            </select>
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
              <Kpi label="Needs Tier" value={s.needs_tier ?? 0} warn={(s.needs_tier ?? 0) > 0} />
              <Kpi label="Membership" value={money(s.membership_payable)} />
              <Kpi label="Match Fees" value={money(s.match_fee_payable)} />
              <Kpi label="Total Owed" value={money(s.total_payable)} accent />
            </div>

            <div className="flex flex-wrap items-center gap-3 mb-3">
              <input className={`${inp} flex-1 min-w-[180px]`} placeholder="Search name or tier…" value={q} onChange={e => setQ(e.target.value)} />
              <label className="flex items-center gap-2 font-mono text-[10px] tracking-wide2 text-pb-faint cursor-pointer select-none">
                <input type="checkbox" checked={needsTierOnly} onChange={e => setNeedsTierOnly(e.target.checked)} />
                NEEDS TIER ONLY
              </label>
              <button onClick={recompute} disabled={recomputing}
                className="px-3 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-accent transition-colors disabled:opacity-50">
                {recomputing ? 'SYNCING…' : 'SYNC MATCH DAYS'}
              </button>
            </div>

            {filtered.length === 0 ? (
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
            ) : (
              <div className="pb-card overflow-hidden">
                <div className="grid grid-cols-[1.6fr_1.2fr_auto_auto_auto_auto] font-mono text-[10px] tracking-wide3 text-pb-faint px-5 py-2.5 bg-pb-surface2/40">
                  <span>NAME</span><span>TIER</span>
                  <span className="text-right">DAYS</span><span className="text-right">M’SHIP</span>
                  <span className="text-right">MATCH</span><span className="text-right pl-4">TOTAL</span>
                </div>
                {filtered.map((m, i) => (
                  <Link key={m.member_season_id} to={`/admin/fees/member/${m.member_id}?season=${seasonId}`}
                    className={`grid grid-cols-[1.6fr_1.2fr_auto_auto_auto_auto] items-center px-5 py-2.5 ${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2 transition-colors`}>
                    <span className="text-pb-text text-sm truncate pr-2 flex items-center gap-1.5">
                      {m.full_name}
                      {!m.is_linked && <span className="font-mono text-[8px] tracking-wide2 text-pb-faintest border pb-hairline rounded px-1 py-px">MANUAL</span>}
                    </span>
                    <span className="truncate pr-2">
                      {m.needs_tier
                        ? <span className="font-mono text-[10px] text-pb-amber">⚠ needs tier</span>
                        : <span className="text-pb-dim text-sm">{m.tier}</span>}
                    </span>
                    <span className="font-mono text-[11px] text-pb-dim text-right">{m.match_days || 0}</span>
                    <span className="font-mono text-[11px] text-pb-dim text-right">{money(m.membership_payable)}</span>
                    <span className="font-mono text-[11px] text-pb-dim text-right">{money(m.match_fee_payable)}</span>
                    <span className="font-mono text-[11px] text-pb-text text-right pl-4">{money(m.total_payable)}</span>
                  </Link>
                ))}
              </div>
            )}
            <p className="font-mono text-[10px] text-pb-faintest mt-3">
              Showing {filtered.length} of {data.members.length}. Payments &amp; financial status arrive in Phase 2.
            </p>
          </>
        )}
      </div>

      {showAdd && (
        <AddMemberModal seasonId={seasonId} tiers={tiers}
          onClose={() => setShowAdd(false)}
          onCreated={() => { setShowAdd(false); load() }} />
      )}
    </AdminLayout>
  )
}
