import { useState, useEffect, useCallback } from 'react'
import { useParams, useSearchParams, Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import AdminLayout from '../../components/admin/AdminLayout'
import { PbSpinner } from '../../lib/presskit'

const money = n => `$${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`
const PAY_METHODS = ['', 'EFT', 'Cash', 'PlayHQ', 'Comp', 'Other']
const FORMAT_LABEL = { two_day: 'Two Day', one_day: 'One Day', t20: 'T20', women: "Women's" }
const inp = 'w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'

function MatchDayRow({ row, onSaved }) {
  const toast = useToast()
  const [days, setDays] = useState(String(row.days_played))
  const [reason, setReason] = useState(row.override_reason || '')
  const [busy, setBusy] = useState(false)
  useEffect(() => { setDays(String(row.days_played)); setReason(row.override_reason || '') }, [row.id, row.days_played])

  const dirty = Number(days) !== Number(row.days_played) || (reason || '') !== (row.override_reason || '')
  async function save() {
    setBusy(true)
    try {
      await api.feePatchMatchDay(row.id, { days_played: Number(days) || 0, override_reason: reason.trim() || null })
      toast.success('Match day updated'); onSaved()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="grid grid-cols-[auto_1fr_auto_auto_auto] items-center gap-3 px-5 py-2.5 pb-hairline-t hover:bg-pb-surface2/40">
      <span className="font-mono text-[10px] text-pb-faintest w-20">{row.played_at || '—'}</span>
      <span className="text-pb-dim text-sm truncate">
        {row.match || row.grade || '—'}
        {row.grade && row.match && <span className="text-pb-faintest"> · {row.grade}</span>}
      </span>
      <span className="font-mono text-[10px] text-pb-faint w-16">{FORMAT_LABEL[row.fee_format] || row.fee_format}</span>
      <div className="flex items-center gap-1.5 w-24">
        <input type="number" min="0" max="5" step="0.5" value={days} onChange={e => setDays(e.target.value)}
          className="w-14 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-sm text-right focus:outline-none focus:border-pb-accent" />
        <span className="font-mono text-[9px] text-pb-faintest">{row.auto_derived ? 'auto' : 'edited'}</span>
      </div>
      <div className="flex items-center gap-2 justify-end">
        <input value={reason} onChange={e => setReason(e.target.value)} placeholder="reason"
          className="w-28 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-[11px] focus:outline-none focus:border-pb-accent" />
        <button onClick={save} disabled={!dirty || busy}
          className="px-2.5 py-1 rounded font-mono text-[9px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-30" style={{ background: 'var(--pb-accent)' }}>SAVE</button>
      </div>
    </div>
  )
}

export default function AdminFeeMemberDetail() {
  const { memberId } = useParams()
  const [params] = useSearchParams()
  const toast = useToast()
  const [seasonId, setSeasonId] = useState(params.get('season') || '')
  const [data, setData] = useState(null)
  const [tiers, setTiers] = useState([])
  const [contact, setContact] = useState({ full_name: '', email: '', mobile: '', notes: '' })
  const [tierForm, setTierForm] = useState({ fee_schedule_id: '', is_new_registration: false, membership_payment_method: '' })
  const [savingContact, setSavingContact] = useState(false)
  const [savingTier, setSavingTier] = useState(false)

  // Resolve a season if it wasn't passed in the URL.
  useEffect(() => {
    if (seasonId) return
    api.adminListSeasons().then(s => {
      const sorted = s.filter(x => !x.alias_of).sort((a, b) => (b.year || 0) - (a.year || 0))
      if (sorted[0]) setSeasonId(sorted[0].id)
    }).catch(() => {})
  }, [seasonId])

  const load = useCallback(() => {
    if (!seasonId) return
    setData(null)
    api.feeGetMember(memberId, seasonId).then(d => {
      setData(d)
      setContact({
        full_name: d.member.full_name || '', email: d.member.email || '',
        mobile: d.member.mobile || '', notes: d.member.notes || '',
      })
      setTierForm({
        fee_schedule_id: d.member_season?.fee_schedule_id || '',
        is_new_registration: d.member_season?.is_new_registration || false,
        membership_payment_method: d.member_season?.membership_payment_method || '',
      })
    }).catch(e => toast.error(e.message))
    api.feeListSchedule(seasonId).then(setTiers).catch(() => setTiers([]))
  }, [memberId, seasonId])
  useEffect(() => { load() }, [load])

  async function saveContact() {
    setSavingContact(true)
    try { await api.feePatchMember(memberId, contact); toast.success('Saved'); load() }
    catch (e) { toast.error(e.message) } finally { setSavingContact(false) }
  }
  async function saveTier() {
    setSavingTier(true)
    try {
      await api.feePatchMemberSeason(memberId, {
        season_id: seasonId,
        fee_schedule_id: tierForm.fee_schedule_id || null,
        is_new_registration: tierForm.is_new_registration,
        membership_payment_method: tierForm.membership_payment_method || null,
      })
      toast.success('Tier saved'); load()
    } catch (e) { toast.error(e.message) } finally { setSavingTier(false) }
  }

  if (data === null) return <AdminLayout><PbSpinner message="Loading member…" /></AdminLayout>

  const f = data.financials
  const member = data.member

  return (
    <AdminLayout>
      <div className="max-w-3xl">
        <Link to={`/admin/fees?season=${seasonId}`} className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">← MEMBERS</Link>
        <div className="flex items-center gap-2 mt-2 mb-1">
          <h1 className="font-display font-bold text-2xl text-pb-text">{member.full_name}</h1>
          {member.is_linked
            ? <Link to={`/players/${member.player_id}`} className="font-mono text-[9px] tracking-wide2 text-pb-accent border border-pb-accent/40 rounded px-1.5 py-0.5">LINKED PLAYER</Link>
            : <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest border pb-hairline rounded px-1.5 py-0.5">MANUAL</span>}
        </div>
        <p className="text-pb-faint text-sm mb-5">{data.season.name}</p>

        {/* Balance strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          {[
            ['Match Days', f.match_days || 0],
            ['Membership', money(f.membership_payable)],
            ['Match Fees', money(f.match_fee_payable)],
            ['Total Owed', money(f.total_payable)],
          ].map(([label, val], i) => (
            <div key={label} className="pb-card px-4 py-3">
              <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">{label}</div>
              <div className="font-display font-bold text-lg" style={i === 3 ? { color: 'var(--pb-accent)' } : { color: 'var(--pb-text)' }}>{val}</div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mb-8">
          {/* Tier panel */}
          <div className="pb-card p-5">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">Membership Tier</p>
            {f.needs_tier && <p className="font-mono text-[11px] text-pb-amber mb-3">⚠ No tier assigned — fees won’t calculate.</p>}
            <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">TIER</label>
            <select className={`${inp} mb-3`} value={tierForm.fee_schedule_id}
              onChange={e => setTierForm(t => ({ ...t, fee_schedule_id: e.target.value }))}>
              <option value="">— Needs tier —</option>
              {tiers.map(t => <option key={t.id} value={t.id}>{t.name} ({t.payment_type})</option>)}
            </select>
            <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">MEMBERSHIP PAYMENT METHOD</label>
            <select className={`${inp} mb-3`} value={tierForm.membership_payment_method}
              onChange={e => setTierForm(t => ({ ...t, membership_payment_method: e.target.value }))}>
              {PAY_METHODS.map(m => <option key={m} value={m}>{m || '—'}</option>)}
            </select>
            <label className="flex items-center gap-2 font-mono text-[11px] text-pb-dim cursor-pointer select-none mb-4">
              <input type="checkbox" checked={tierForm.is_new_registration}
                onChange={e => setTierForm(t => ({ ...t, is_new_registration: e.target.checked }))} />
              New registration this season
            </label>
            <button onClick={saveTier} disabled={savingTier}
              className="w-full py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50" style={{ background: 'var(--pb-accent)' }}>
              {savingTier ? 'SAVING…' : 'SAVE TIER'}
            </button>
          </div>

          {/* Contact panel */}
          <div className="pb-card p-5">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">Contact &amp; Notes</p>
            <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">NAME</label>
            <input className={`${inp} mb-3`} value={contact.full_name} onChange={e => setContact(c => ({ ...c, full_name: e.target.value }))} />
            <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">EMAIL</label>
            <input className={`${inp} mb-3`} value={contact.email} onChange={e => setContact(c => ({ ...c, email: e.target.value }))} />
            <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">MOBILE</label>
            <input className={`${inp} mb-3`} value={contact.mobile} onChange={e => setContact(c => ({ ...c, mobile: e.target.value }))} />
            <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">NOTES</label>
            <textarea rows={2} className={`${inp} mb-4`} value={contact.notes} onChange={e => setContact(c => ({ ...c, notes: e.target.value }))} />
            <button onClick={saveContact} disabled={savingContact}
              className="w-full py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-text hover:border-pb-accent disabled:opacity-50">
              {savingContact ? 'SAVING…' : 'SAVE CONTACT'}
            </button>
          </div>
        </div>

        {/* Match days */}
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2 uppercase">
          Match Days <span className="text-pb-faintest">({data.match_days.length})</span>
        </p>
        <p className="text-pb-dim text-sm mb-3 leading-relaxed">
          Auto-derived from appearances. Two-day games default to 2 days — drop to 1 if they only played one day.
          Editing flags the row so it won’t be overwritten by the next sync.
        </p>
        {data.match_days.length === 0 ? (
          <p className="font-mono text-[11px] text-pb-faint pb-card p-5">No match days recorded this season.</p>
        ) : (
          <div className="pb-card overflow-hidden">
            <div className="grid grid-cols-[auto_1fr_auto_auto_auto] gap-3 px-5 py-2.5 bg-pb-surface2/40 font-mono text-[10px] tracking-wide3 text-pb-faint">
              <span className="w-20">DATE</span><span>MATCH</span><span className="w-16">FORMAT</span><span className="w-24">DAYS</span><span className="text-right">OVERRIDE</span>
            </div>
            {data.match_days.map(row => <MatchDayRow key={row.id} row={row} onSaved={load} />)}
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
