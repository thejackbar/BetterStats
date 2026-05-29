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

function StatusBadge({ status }) {
  if (status === 'financial')
    return <span className="font-mono text-[9px] tracking-wide2 text-green-300 bg-green-900/40 border border-green-600/30 rounded px-1.5 py-0.5">FINANCIAL</span>
  if (status === 'non_financial')
    return <span className="font-mono text-[9px] tracking-wide2 text-pb-amber border border-pb-amber/40 rounded px-1.5 py-0.5">OWES</span>
  if (status === 'needs_tier')
    return <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest border pb-hairline rounded px-1.5 py-0.5">NEEDS TIER</span>
  return null
}

function BalanceCard({ label, payable, paid, owed, footer, highlight }) {
  const rowCss = 'flex justify-between font-mono text-[10px] tracking-wide2'
  return (
    <div className={`pb-card px-4 py-3 ${highlight ? 'border-pb-accent/40' : ''}`}>
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-2">{label}</div>
      <div className="space-y-1">
        <div className={rowCss}><span className="text-pb-faint">Payable</span><span className="text-pb-dim">{money(payable)}</span></div>
        <div className={rowCss}><span className="text-pb-faint">Paid</span><span className="text-pb-dim">{money(paid)}</span></div>
        <div className={`${rowCss} pt-1 border-t pb-hairline-t mt-1`}>
          <span className="text-pb-text">Outstanding</span>
          <span className={`font-display font-bold text-base ${owed > 0 ? '' : 'text-pb-dim'}`}
            style={owed > 0 && highlight ? { color: 'var(--pb-accent)' } : owed > 0 ? { color: 'var(--pb-text)' } : {}}>
            {money(owed)}
          </span>
        </div>
      </div>
      {footer && <div className="font-mono text-[10px] text-pb-faintest mt-2">{footer}</div>}
    </div>
  )
}

function PaymentForm({ memberSeasonId, defaultKind = 'membership', defaultMethod = 'EFT', onCreated }) {
  const toast = useToast()
  const [form, setForm] = useState({
    amount: '', kind: defaultKind, paid_at: new Date().toISOString().slice(0, 10),
    method: defaultMethod, bank_ref: '', notes: '',
  })
  const [busy, setBusy] = useState(false)
  async function submit() {
    if (!Number(form.amount)) { toast.error('Amount is required'); return }
    setBusy(true)
    try {
      await api.feeCreatePayment({
        member_season_id: memberSeasonId,
        amount: Number(form.amount), kind: form.kind,
        paid_at: form.paid_at || null,
        method: form.method || null, bank_ref: form.bank_ref || null, notes: form.notes || null,
      })
      toast.success('Payment logged')
      setForm(f => ({ ...f, amount: '', bank_ref: '', notes: '' }))
      onCreated()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  const cell = 'bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
  return (
    <div className="grid grid-cols-1 sm:grid-cols-[auto_120px_120px_120px_1fr_auto] gap-2 items-end p-4 bg-pb-surface2/30">
      <div>
        <label className="font-mono text-[9px] tracking-wide3 text-pb-faint mb-1 block">DATE</label>
        <input type="date" className={`${cell} w-36`} value={form.paid_at} onChange={e => setForm(f => ({ ...f, paid_at: e.target.value }))} />
      </div>
      <div>
        <label className="font-mono text-[9px] tracking-wide3 text-pb-faint mb-1 block">KIND</label>
        <select className={`${cell} w-full`} value={form.kind} onChange={e => setForm(f => ({ ...f, kind: e.target.value }))}>
          <option value="membership">Membership</option>
          <option value="match_day">Match Day</option>
        </select>
      </div>
      <div>
        <label className="font-mono text-[9px] tracking-wide3 text-pb-faint mb-1 block">AMOUNT</label>
        <input type="number" min="0" step="0.01" className={`${cell} w-full text-right`} placeholder="0.00"
          value={form.amount} onChange={e => setForm(f => ({ ...f, amount: e.target.value }))} />
      </div>
      <div>
        <label className="font-mono text-[9px] tracking-wide3 text-pb-faint mb-1 block">METHOD</label>
        <select className={`${cell} w-full`} value={form.method} onChange={e => setForm(f => ({ ...f, method: e.target.value }))}>
          {PAY_METHODS.filter(Boolean).map(m => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>
      <div>
        <label className="font-mono text-[9px] tracking-wide3 text-pb-faint mb-1 block">BANK REF / NOTE</label>
        <input className={`${cell} w-full`} value={form.bank_ref} onChange={e => setForm(f => ({ ...f, bank_ref: e.target.value }))} />
      </div>
      <button onClick={submit} disabled={busy}
        className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
        {busy ? '…' : 'LOG'}
      </button>
    </div>
  )
}

function PaymentRow({ payment, onDeleted }) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  async function del() {
    if (!confirm('Delete this payment?')) return
    setBusy(true)
    try { await api.feeDeletePayment(payment.id); toast.success('Payment deleted'); onDeleted() }
    catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  return (
    <div className="grid grid-cols-[auto_auto_auto_auto_1fr_auto] items-center gap-3 px-5 py-2.5 pb-hairline-t hover:bg-pb-surface2/40">
      <span className="font-mono text-[10px] text-pb-faintest w-20">{payment.paid_at || '—'}</span>
      <span className="font-mono text-[10px] text-pb-faint w-20">{payment.kind === 'membership' ? 'M’SHIP' : 'MATCH'}</span>
      <span className="font-mono text-[11px] text-pb-text w-20 text-right">{money(payment.amount)}</span>
      <span className="font-mono text-[10px] text-pb-dim w-14">{payment.method || '—'}</span>
      <span className="text-pb-faint text-[12px] truncate">
        {payment.bank_ref || ''}
        {payment.notes && <span className="text-pb-faintest"> · {payment.notes}</span>}
      </span>
      <button onClick={del} disabled={busy}
        className="font-mono text-[9px] text-pb-red/50 hover:text-pb-red transition-colors disabled:opacity-50">DEL</button>
    </div>
  )
}

function MatchDayRow({ row, rate, onSaved }) {
  const toast = useToast()
  const [days, setDays] = useState(String(row.days_played))
  const [busy, setBusy] = useState(false)
  useEffect(() => { setDays(String(row.days_played)) }, [row.id, row.days_played])

  const daysDirty = Number(days) !== Number(row.days_played)
  const dayCharge = Number(rate || 0) * Number(row.days_played || 0)

  async function saveDays() {
    setBusy(true)
    try {
      await api.feePatchMatchDay(row.id, { days_played: Number(days) || 0 })
      toast.success('Days updated'); onSaved()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  async function markPaid() {
    setBusy(true)
    try {
      await api.feeMarkMatchDayPaid(row.id, {})
      toast.success('Match day marked paid'); onSaved()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  async function unmark() {
    setBusy(true)
    try {
      await api.feeUnmarkMatchDayPaid(row.id)
      toast.success('Marked unpaid'); onSaved()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <tr className="pb-hairline-t align-middle hover:bg-pb-surface2/40">
      <td className="py-2 pl-5 pr-3 font-mono text-[10px] text-pb-faintest whitespace-nowrap">{row.played_at || '—'}</td>
      <td className="py-2 pr-3 text-pb-dim text-sm">
        <div className="truncate">{row.match || row.grade || '—'}</div>
        {row.grade && row.match && <div className="font-mono text-[10px] text-pb-faintest truncate">{row.grade}</div>}
      </td>
      <td className="py-2 pr-3 font-mono text-[10px] text-pb-faint whitespace-nowrap">{FORMAT_LABEL[row.fee_format] || row.fee_format}</td>
      <td className="py-2 pr-3 text-right whitespace-nowrap">
        <input type="number" min="0" max="5" step="0.5" value={days} onChange={e => setDays(e.target.value)}
          disabled={row.is_paid || busy}
          className="w-14 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-sm text-right focus:outline-none focus:border-pb-accent disabled:opacity-40" />
        {daysDirty && (
          <button onClick={saveDays} disabled={busy}
            className="ml-1.5 px-2 py-1 rounded font-mono text-[9px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-30" style={{ background: 'var(--pb-accent)' }}>SAVE</button>
        )}
      </td>
      <td className="py-2 pr-3 text-right font-mono text-[11px] text-pb-dim whitespace-nowrap">{money(dayCharge)}</td>
      <td className="py-2 pr-3 text-right whitespace-nowrap">
        {row.is_paid
          ? <span className="font-mono text-[9px] tracking-wide2 text-green-300 bg-green-900/40 border border-green-600/30 rounded px-1.5 py-0.5">PAID</span>
          : <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest border pb-hairline rounded px-1.5 py-0.5">UNPAID</span>}
      </td>
      <td className="py-2 pr-5 text-right whitespace-nowrap">
        {row.is_paid
          ? <button onClick={unmark} disabled={busy}
              className="font-mono text-[9px] tracking-wide2 border pb-hairline rounded px-2 py-1 text-pb-faint hover:text-pb-text transition-colors disabled:opacity-50">UNMARK</button>
          : <button onClick={markPaid} disabled={busy || !rate}
              title={!rate ? 'Member has no tier or $0 match-day rate' : 'Log a payment for this day'}
              className="px-2 py-1 rounded font-mono text-[9px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-40" style={{ background: 'var(--pb-accent)' }}>MARK PAID</button>}
      </td>
    </tr>
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
        <div className="flex items-center gap-2 mb-5">
          <span className="text-pb-faint text-sm">{data.season.name}</span>
          <StatusBadge status={f.status} />
        </div>

        {/* Balance strip: payable / paid / outstanding for membership + match-day */}
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 mb-6">
          <BalanceCard label="Membership" payable={f.membership_payable} paid={f.membership_paid} owed={f.membership_outstanding} />
          <BalanceCard label="Match Fees" payable={f.match_fee_payable} paid={f.match_fee_paid} owed={f.match_fee_outstanding}
            footer={`${f.match_days || 0} day${f.match_days === 1 ? '' : 's'} × ${money(f.match_day_rate || 0)}`} />
          <BalanceCard label="Total" payable={f.total_payable} paid={f.total_paid} owed={f.total_outstanding} highlight />
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

        {/* Payments */}
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2 uppercase">
          Payments <span className="text-pb-faintest">({data.payments?.length || 0})</span>
        </p>
        <p className="text-pb-dim text-sm mb-3 leading-relaxed">
          Log each payment as you reconcile it against the bank statement. Membership and match-day are tracked separately so the
          Outstanding column above stays honest.
        </p>
        <div className="pb-card overflow-hidden mb-8">
          {data.member_season ? (
            <PaymentForm
              memberSeasonId={data.member_season.id}
              defaultMethod={data.member_season.membership_payment_method || 'EFT'}
              onCreated={load}
            />
          ) : (
            <div className="p-4 font-mono text-[11px] text-pb-faint">Assign a tier first to log payments.</div>
          )}
          {data.payments && data.payments.length > 0 && (
            <div>
              <div className="grid grid-cols-[auto_auto_auto_auto_1fr_auto] gap-3 px-5 py-2.5 bg-pb-surface2/40 font-mono text-[10px] tracking-wide3 text-pb-faint pb-hairline-t">
                <span className="w-20">DATE</span><span className="w-20">KIND</span>
                <span className="w-20 text-right">AMOUNT</span><span className="w-14">METHOD</span>
                <span>REF / NOTES</span><span></span>
              </div>
              {data.payments.map(p => <PaymentRow key={p.id} payment={p} onDeleted={load} />)}
            </div>
          )}
        </div>

        {/* Match days */}
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2 uppercase">
          Match Days <span className="text-pb-faintest">({data.match_days.length})</span>
        </p>
        <p className="text-pb-dim text-sm mb-3 leading-relaxed">
          Auto-derived from appearances. Two-day games default to 2 days — drop to 1 if they only played one day.
          Hit <span className="text-pb-text">Mark Paid</span> to log the day’s fee as a payment in one click.
        </p>
        {data.match_days.length === 0 ? (
          <p className="font-mono text-[11px] text-pb-faint pb-card p-5">No match days recorded this season.</p>
        ) : (
          <div className="pb-card overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left bg-pb-surface2/40">
                  <th className="font-medium py-2.5 pl-5 pr-3 w-24">DATE</th>
                  <th className="font-medium py-2.5 pr-3">MATCH</th>
                  <th className="font-medium py-2.5 pr-3 w-20">FORMAT</th>
                  <th className="font-medium py-2.5 pr-3 w-32 text-right">DAYS</th>
                  <th className="font-medium py-2.5 pr-3 w-20 text-right">AMOUNT</th>
                  <th className="font-medium py-2.5 pr-3 w-20 text-right">STATUS</th>
                  <th className="font-medium py-2.5 pr-5 w-28 text-right"></th>
                </tr>
              </thead>
              <tbody>
                {data.match_days.map(row => (
                  <MatchDayRow key={row.id} row={row} rate={f.match_day_rate} onSaved={load} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
