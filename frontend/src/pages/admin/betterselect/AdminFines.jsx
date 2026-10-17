// BetterSelect → Club Life → Fines.
//
// After a game a side sits around and runs a fines session; the money goes into a
// pot. This is the tracker for it, per squad: who was fined what and when, who has
// paid, and the details a player needs to pay (PayID, bank transfer). Fines is off
// until a squad switches it on; the players then see their own balance on their
// private page (the "My page" tab of the self-service link).
//
// What a player owes is worked out by the server (fined minus paid). Nothing is
// ever deleted here: a wrong fine or payment is voided and can be brought back.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { PbSpinner } from '../../../lib/presskit'
import usePersistedState from '../../../lib/usePersistedState'
import { Btn, Segmented } from './ui'

const money = (n) => `${n < 0 ? '-' : ''}$${Math.abs(Number(n) || 0).toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const shortDate = (iso) => {
  try { return new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) } catch { return iso }
}
const todayISO = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const METHODS = ['PayID', 'Bank transfer', 'Cash', 'Other']
// useToast() hands back a new object each time a toast comes or goes, so a load
// keyed on it would re-run (and blank the screen) after every message. Read the
// latest one through a ref instead.
function useLatest(value) {
  const ref = useRef(value)
  ref.current = value
  return ref
}
const inputCls = 'bg-pb-surface2 border pb-hairline rounded-lg px-2.5 py-1.5 text-[13.5px] focus:outline-none focus:border-pb-accent min-w-0'

function Card({ title, sub, children, right }) {
  return (
    <section className="pb-card rounded-xl p-4 sm:p-5 mb-4">
      <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
        <div className="min-w-0">
          <h2 className="font-display font-bold text-[15px] tracking-tight">{title}</h2>
          {sub && <p className="text-[12.5px] text-pb-dim mt-0.5 max-w-[66ch]">{sub}</p>}
        </div>
        {right}
      </div>
      {children}
    </section>
  )
}

function Modal({ title, onClose, children }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-3" style={{ background: 'rgba(0,0,0,.55)' }} onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div role="dialog" aria-label={title} className="pb-card rounded-xl w-full max-w-md max-h-[88vh] overflow-y-auto p-4 sm:p-5 bg-pb-bg">
        <div className="flex items-center justify-between gap-3 mb-3">
          <h3 className="font-display font-bold text-[16px] min-w-0 truncate">{title}</h3>
          <button type="button" onClick={onClose} aria-label="Close" className="text-pb-faint hover:text-pb-text text-lg leading-none px-1">×</button>
        </div>
        {children}
      </div>
    </div>
  )
}

// ── One line of a fines session ─────────────────────────────────────────────
function FineRow({ row, squadPlayers, otherPlayers, types, onChange, onRemove }) {
  const type = types.find((t) => t.id === row.fine_type_id)
  return (
    <div className="grid grid-cols-2 sm:grid-cols-[minmax(0,1.3fr)_minmax(0,1.3fr)_88px_60px_auto] gap-2 items-center py-2 border-t border-pb-hairline first:border-t-0" data-fine-row>
      <select value={row.player_id} onChange={(e) => onChange({ player_id: e.target.value })} aria-label="Player" className={`${inputCls} col-span-2 sm:col-span-1`}>
        <option value="">Pick a player…</option>
        {squadPlayers.length > 0 && (
          <optgroup label="Squad">
            {squadPlayers.map((p) => <option key={p.player_id} value={p.player_id}>{p.name}</option>)}
          </optgroup>
        )}
        {otherPlayers.length > 0 && (
          <optgroup label="Other players">
            {otherPlayers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </optgroup>
        )}
      </select>
      <div className="flex flex-col gap-1.5 col-span-2 sm:col-span-1 min-w-0">
        <select value={row.fine_type_id} onChange={(e) => onChange({ fine_type_id: e.target.value, amount: '' })} aria-label="Fine" className={inputCls}>
          <option value="">Something else…</option>
          {types.map((t) => <option key={t.id} value={t.id}>{t.name} ({money(t.amount)})</option>)}
        </select>
        {!row.fine_type_id && (
          <input value={row.reason} onChange={(e) => onChange({ reason: e.target.value })} maxLength={120}
            placeholder="What was it for?" aria-label="Reason" className={inputCls} />
        )}
      </div>
      <input value={row.amount} onChange={(e) => onChange({ amount: e.target.value.replace(/[^0-9.]/g, '') })} inputMode="decimal"
        placeholder={type ? String(type.amount) : '$'} aria-label="Amount" className={`${inputCls} w-full`} />
      <input value={row.quantity} onChange={(e) => onChange({ quantity: e.target.value.replace(/\D/g, '').slice(0, 2) })} inputMode="numeric"
        aria-label="How many" title="How many" className={`${inputCls} w-full text-center`} />
      <button type="button" onClick={onRemove} aria-label="Remove this line" className="text-pb-faint hover:text-pb-red text-lg leading-none px-1 justify-self-end">×</button>
    </div>
  )
}

let rowSeq = 0
const blankRow = () => ({ key: ++rowSeq, player_id: '', fine_type_id: '', reason: '', amount: '', quantity: '1' })

function AddFines({ teamId, data, onSaved }) {
  const toast = useToast()
  const [date, setDate] = useState(todayISO())
  const [rows, setRows] = useState(() => [blankRow(), blankRow(), blankRow()])
  const [saving, setSaving] = useState(false)
  const squadPlayers = useMemo(() => data.players.filter((p) => p.in_squad), [data.players])
  // Anyone fined before outside the squad stays pickable; the rest come from candidates.
  const otherPlayers = useMemo(() => [
    ...data.players.filter((p) => !p.in_squad).map((p) => ({ id: p.player_id, name: p.name })),
    ...data.candidates,
  ], [data.players, data.candidates])

  const patch = (key, p) => setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...p } : r)))
  const filled = rows.filter((r) => r.player_id)
  const total = filled.reduce((sum, r) => {
    const t = data.types.find((x) => x.id === r.fine_type_id)
    const amt = r.amount !== '' ? Number(r.amount) : (t ? t.amount : 0)
    return sum + (Number.isFinite(amt) ? amt : 0) * (Number(r.quantity) || 1)
  }, 0)

  const save = async () => {
    if (filled.length === 0) { toast.error('Pick a player for at least one line'); return }
    setSaving(true)
    try {
      const res = await api.bsFinesAddEntries(teamId, {
        fined_on: date,
        items: filled.map((r) => ({
          player_id: r.player_id,
          fine_type_id: r.fine_type_id || null,
          reason: r.fine_type_id ? null : r.reason,
          amount: r.amount === '' ? null : r.amount,
          quantity: Number(r.quantity) || 1,
        })),
      })
      toast.success(`${res.created} fine${res.created === 1 ? '' : 's'} added, ${money(res.total)} into the pot to collect`)
      setRows([blankRow(), blankRow(), blankRow()])
      onSaved()
    } catch (e) { toast.error(e.message || 'Could not save the fines') } finally { setSaving(false) }
  }

  return (
    <Card title="Add fines" sub="One session: pick the date, then a line for each fine. Pick from your fine list or type your own reason and amount.">
      <div className="flex flex-wrap items-center gap-2.5 mb-2">
        <label className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint" htmlFor="fines-date">Date</label>
        <input id="fines-date" type="date" value={date} max={todayISO()} onChange={(e) => setDate(e.target.value)} className={inputCls} />
      </div>
      <div>
        {rows.map((r) => (
          <FineRow key={r.key} row={r} squadPlayers={squadPlayers} otherPlayers={otherPlayers} types={data.types}
            onChange={(p) => patch(r.key, p)} onRemove={() => setRows((rs) => (rs.length > 1 ? rs.filter((x) => x.key !== r.key) : [blankRow()]))} />
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-3 mt-3">
        <Btn sm variant="ghost" icon="plus" onClick={() => setRows((rs) => [...rs, blankRow()])}>Add a line</Btn>
        <span className="text-[13px] text-pb-dim ml-auto">{filled.length} line{filled.length === 1 ? '' : 's'}, <b className="text-pb-text">{money(total)}</b></span>
        <Btn variant="primary" onClick={save} disabled={saving || filled.length === 0}>{saving ? 'Saving…' : 'Save fines'}</Btn>
      </div>
    </Card>
  )
}

// ── Money in ────────────────────────────────────────────────────────────────
function PaymentModal({ teamId, player, onClose, onSaved }) {
  const toast = useToast()
  const [amount, setAmount] = useState(player.owing > 0 ? String(player.owing) : '')
  const [date, setDate] = useState(todayISO())
  const [method, setMethod] = useState('PayID')
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const save = async () => {
    setSaving(true)
    try {
      await api.bsFinesAddPayment(teamId, { player_id: player.player_id, amount, paid_on: date, method, note })
      toast.success(`${money(amount)} recorded for ${player.name}`)
      onSaved()
      onClose()
    } catch (e) { toast.error(e.message || 'Could not record the payment') } finally { setSaving(false) }
  }
  return (
    <Modal title={`${player.name} paid`} onClose={onClose}>
      <p className="text-[13px] text-pb-dim mb-3">Owes {money(player.owing)} right now. Paying more than that shows as credit.</p>
      <div className="grid grid-cols-2 gap-2.5">
        <label className="text-[12px] text-pb-faint">Amount
          <input value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^0-9.]/g, ''))} inputMode="decimal" autoFocus className={`${inputCls} w-full mt-1`} />
        </label>
        <label className="text-[12px] text-pb-faint">Date
          <input type="date" value={date} max={todayISO()} onChange={(e) => setDate(e.target.value)} className={`${inputCls} w-full mt-1`} />
        </label>
        <label className="text-[12px] text-pb-faint col-span-2">How
          <select value={method} onChange={(e) => setMethod(e.target.value)} className={`${inputCls} w-full mt-1`}>
            {METHODS.map((m) => <option key={m}>{m}</option>)}
          </select>
        </label>
        <label className="text-[12px] text-pb-faint col-span-2">Note (optional)
          <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} className={`${inputCls} w-full mt-1`} />
        </label>
      </div>
      <div className="flex justify-end gap-2 mt-4">
        <Btn onClick={onClose}>Cancel</Btn>
        <Btn variant="primary" onClick={save} disabled={saving || !amount}>{saving ? 'Saving…' : 'Record payment'}</Btn>
      </div>
    </Modal>
  )
}

// One fine or payment in the history. A voided row stays, struck through.
function LedgerLine({ voided, children, onVoid, onRestore }) {
  return (
    <div className={`flex items-center gap-2 py-1.5 border-t border-pb-hairline first:border-t-0 text-[13px] ${voided ? 'opacity-50' : ''}`}>
      <div className={`min-w-0 flex-1 ${voided ? 'line-through' : ''}`}>{children}</div>
      <button type="button" onClick={voided ? onRestore : onVoid} className="text-[12px] text-pb-faint underline shrink-0">
        {voided ? 'Restore' : 'Void'}
      </button>
    </div>
  )
}

function LedgerModal({ teamId, player, onClose, onChanged }) {
  const toast = useToast()
  const toastRef = useLatest(toast)
  const [led, setLed] = useState(null)
  const load = useCallback(() => {
    api.bsFinesLedger(teamId, player.player_id).then(setLed).catch((e) => toastRef.current.error(e.message))
  }, [teamId, player.player_id, toastRef])
  useEffect(() => { load() }, [load])
  const act = async (fn, id) => {
    try { await fn(id); load(); onChanged() } catch (e) { toast.error(e.message || 'Could not change that') }
  }
  return (
    <Modal title={`${player.name}: history`} onClose={onClose}>
      {!led ? <PbSpinner message="Loading…" /> : (
        <>
          <p className="text-[13px] text-pb-dim mb-3">Owes <b className="text-pb-text">{money(led.owing)}</b>. Voiding takes a row out of the balance without deleting it.</p>
          <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">Fines</div>
          {led.entries.length === 0 && <div className="text-[13px] text-pb-faint mb-2">None yet.</div>}
          {led.entries.map((e) => (
            <LedgerLine key={e.id} voided={e.voided} onVoid={() => act(api.bsFinesVoidEntry, e.id)} onRestore={() => act(api.bsFinesRestoreEntry, e.id)}>
              {shortDate(e.date)} · {e.reason} · <b>{money(e.amount)}</b>
            </LedgerLine>
          ))}
          <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mt-4 mb-1">Payments</div>
          {led.payments.length === 0 && <div className="text-[13px] text-pb-faint">None yet.</div>}
          {led.payments.map((p) => (
            <LedgerLine key={p.id} voided={p.voided} onVoid={() => act(api.bsFinesVoidPayment, p.id)} onRestore={() => act(api.bsFinesRestorePayment, p.id)}>
              {shortDate(p.date)} · {p.method || 'Payment'} · <b>{money(p.amount)}</b>{p.note ? ` · ${p.note}` : ''}
            </LedgerLine>
          ))}
        </>
      )}
    </Modal>
  )
}

// ── The tracker ─────────────────────────────────────────────────────────────
function Tracker({ teamId, data, onChanged }) {
  const [paying, setPaying] = useState(null)
  const [ledger, setLedger] = useState(null)
  const dates = [...data.dates].reverse() // oldest to newest, left to right
  const t = data.totals
  return (
    <Card title="Who owes what" sub={`Fines by date, then what each player has put in the pot. The last ${dates.length || 'few'} fines date${dates.length === 1 ? '' : 's'} show as columns.`}
      right={<div className="text-[12.5px] text-pb-dim text-right">In the pot <b className="text-pb-text">{money(t.paid)}</b><br />Still to collect <b className="text-pb-text">{money(Math.max(t.owing, 0))}</b></div>}>
      {data.players.length === 0 ? (
        <p className="text-sm text-pb-faint" data-no-players>No players in this squad yet. Add players on the Squads page, or fine a player from the list above.</p>
      ) : (
        <div className="overflow-x-auto -mx-1 px-1">
          <table className="w-full text-[13px] min-w-[400px]">
            <thead>
              <tr className="text-left text-pb-faint font-mono text-[10px] uppercase tracking-wide2">
                <th className="py-1.5 pr-3 font-normal">Player</th>
                {dates.map((d) => <th key={d} className="py-1.5 px-2 font-normal text-right">{shortDate(d)}</th>)}
                <th className="py-1.5 px-2 font-normal text-right">Paid</th>
                <th className="py-1.5 px-2 font-normal text-right">Owes</th>
                <th className="py-1.5 pl-2 font-normal hidden sm:table-cell" />
              </tr>
            </thead>
            <tbody>
              {data.players.map((p) => (
                <tr key={p.player_id} className="border-t border-pb-hairline" data-fines-player={p.player_id}>
                  <td className="py-2 pr-3 font-medium min-w-0">
                    {p.name}{!p.in_squad && <span className="ml-1.5 text-[10.5px] text-pb-faint font-normal">outside squad</span>}
                    {/* On a phone the buttons would sit past the right edge of the scrolling table, so they live here instead. */}
                    <div className="sm:hidden mt-1.5 flex gap-1.5">
                      <Btn sm variant="soft" onClick={() => setPaying(p)}>Paid</Btn>
                      <Btn sm onClick={() => setLedger(p)}>History</Btn>
                    </div>
                  </td>
                  {dates.map((d) => <td key={d} className="py-2 px-2 text-right text-pb-dim">{p.by_date[d] ? money(p.by_date[d]) : <span className="text-pb-faintest">·</span>}</td>)}
                  <td className="py-2 px-2 text-right text-pb-dim">{p.paid ? money(p.paid) : <span className="text-pb-faintest">·</span>}</td>
                  <td className="py-2 px-2 text-right font-bold" style={{ color: p.owing > 0 ? 'var(--pb-amber)' : 'var(--pb-positive)' }}>
                    {p.owing > 0 ? money(p.owing) : p.owing < 0 ? `${money(-p.owing)} credit` : 'Square'}
                  </td>
                  <td className="py-2 pl-2 whitespace-nowrap text-right hidden sm:table-cell">
                    <Btn sm variant="soft" onClick={() => setPaying(p)}>Paid</Btn>{' '}
                    <Btn sm onClick={() => setLedger(p)}>History</Btn>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {paying && <PaymentModal teamId={teamId} player={paying} onClose={() => setPaying(null)} onSaved={onChanged} />}
      {ledger && <LedgerModal teamId={teamId} player={ledger} onClose={() => setLedger(null)} onChanged={onChanged} />}
    </Card>
  )
}

// ── The squad's fine list ───────────────────────────────────────────────────
function TypeRow({ type, onSave, archived }) {
  const [name, setName] = useState(type.name)
  const [amount, setAmount] = useState(String(type.amount))
  const dirty = name !== type.name || Number(amount) !== type.amount
  return (
    <div className="flex flex-wrap items-center gap-2 py-1.5 border-t border-pb-hairline first:border-t-0" data-fine-type={type.id}>
      <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} aria-label="Fine name" disabled={archived} className={`${inputCls} flex-1 min-w-[140px]`} />
      <input value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^0-9.]/g, ''))} inputMode="decimal" aria-label="Fine amount" disabled={archived} className={`${inputCls} w-24`} />
      {archived
        ? <Btn sm onClick={() => onSave(type.id, { archived: false })}>Bring back</Btn>
        : (<>
          {dirty && <Btn sm variant="primary" onClick={() => onSave(type.id, { name, amount })}>Save</Btn>}
          <Btn sm onClick={() => onSave(type.id, { archived: true })} title="Takes it off the list. Fines already given keep their name and amount.">Archive</Btn>
        </>)}
    </div>
  )
}

function FineList({ teamId, data, onChanged }) {
  const toast = useToast()
  const [name, setName] = useState('')
  const [amount, setAmount] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const add = async () => {
    try {
      await api.bsFinesAddType(teamId, { name, amount })
      setName(''); setAmount(''); onChanged()
    } catch (e) { toast.error(e.message || 'Could not add that fine') }
  }
  const save = async (id, patch) => {
    try { await api.bsFinesPatchType(id, patch); onChanged() } catch (e) { toast.error(e.message || 'Could not save') }
  }
  return (
    <Card title="Fine list" sub="The usual fines and their price, for quick picking. Changing a price only affects fines you hand out from now on.">
      {data.types.length === 0 && <p className="text-sm text-pb-faint mb-2">No fines on the list yet. You can still type a reason and amount each time.</p>}
      {data.types.map((t) => <TypeRow key={`${t.id}:${t.name}:${t.amount}`} type={t} onSave={save} />)}
      <div className="flex flex-wrap items-center gap-2 pt-3 mt-1 border-t border-pb-hairline">
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} placeholder="e.g. Dropped catch" aria-label="New fine name" className={`${inputCls} flex-1 min-w-[140px]`} />
        <input value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^0-9.]/g, ''))} inputMode="decimal" placeholder="$" aria-label="New fine amount" className={`${inputCls} w-24`} />
        <Btn variant="primary" sm icon="plus" onClick={add} disabled={!name.trim() || !amount}>Add to list</Btn>
      </div>
      {data.archived_types.length > 0 && (
        <div className="mt-3">
          <button type="button" onClick={() => setShowArchived((v) => !v)} className="text-[12px] text-pb-faint underline">
            {showArchived ? 'Hide' : 'Show'} {data.archived_types.length} archived
          </button>
          {showArchived && data.archived_types.map((t) => <TypeRow key={t.id} type={t} onSave={save} archived />)}
        </div>
      )}
    </Card>
  )
}

// ── How players pay ─────────────────────────────────────────────────────────
const PAY_FIELDS = [
  ['payid', 'PayID', 'An email, mobile or ABN, e.g. fines@yourclub.com.au'],
  ['payid_name', 'Name shown when they pay', 'What the bank shows once the PayID is typed in'],
  ['account_name', 'Account name', 'For a bank transfer'],
  ['bsb', 'BSB', '000-000'],
  ['account_number', 'Account number', ''],
  ['reference_hint', 'Reference to use', 'e.g. Fines and your name'],
]

function HowToPay({ teamId, data, onChanged }) {
  const toast = useToast()
  // Seeded once. Other actions on the screen reload the squad, and a reload must
  // not wipe what is half typed here; the squad tab remounts this on a switch.
  const [form, setForm] = useState(data.settings)
  const [saving, setSaving] = useState(false)
  const save = async () => {
    setSaving(true)
    try {
      const body = {}
      for (const [k] of PAY_FIELDS) body[k] = form[k] || ''
      body.other_instructions = form.other_instructions || ''
      await api.bsFinesSettings(teamId, body)
      toast.success('How to pay saved')
      onChanged()
    } catch (e) { toast.error(e.message || 'Could not save') } finally { setSaving(false) }
  }
  return (
    <Card title="How players pay" sub="Shown on each player's page. Fill in whatever you use; empty boxes are left out.">
      <div className="grid sm:grid-cols-2 gap-x-4 gap-y-3">
        {PAY_FIELDS.map(([k, label, hint]) => (
          <label key={k} className="text-[12px] text-pb-faint min-w-0">{label}
            <input value={form[k] || ''} onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))} maxLength={300} placeholder={hint}
              className={`${inputCls} w-full mt-1`} />
          </label>
        ))}
        <label className="text-[12px] text-pb-faint sm:col-span-2">Anything else players should know
          <textarea value={form.other_instructions || ''} onChange={(e) => setForm((f) => ({ ...f, other_instructions: e.target.value }))} maxLength={300} rows={2}
            placeholder="e.g. Cash to the captain at training also works" className={`${inputCls} w-full mt-1`} />
        </label>
      </div>
      <div className="flex justify-end mt-3"><Btn variant="primary" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save'}</Btn></div>
    </Card>
  )
}

// ── One squad ───────────────────────────────────────────────────────────────
function SquadFines({ teamId, onSwitched }) {
  const toast = useToast()
  const toastRef = useLatest(toast)
  const [data, setData] = useState(null)
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  const load = useCallback(() => {
    return api.bsFinesSquad(teamId).then((d) => { if (alive.current) setData(d) })
      .catch((e) => toastRef.current.error(e.message || 'Could not load this squad'))
  }, [teamId, toastRef])
  useEffect(() => { load() }, [load])

  const setEnabled = async (on) => {
    try {
      await api.bsFinesSettings(teamId, { enabled: on })
      await load()
      onSwitched()
    } catch (e) { toast.error(e.message || 'Could not change that') }
  }
  const changed = () => { load(); onSwitched() }

  if (!data) return <PbSpinner message="Loading this squad…" />
  const on = data.settings.enabled
  return (
    <div data-fines-squad={teamId}>
      <Card title={`Fines for ${data.squad.name}`}
        sub={on
          ? 'Fines is on. Players in this squad see what they owe, and how to pay, on their private page. They also see the squad name there.'
          : 'Fines is off for this squad. Set it up below, then switch it on and players see their balance on their private page.'}
        right={<Segmented sm value={on ? 'on' : 'off'} onChange={(v) => setEnabled(v === 'on')} options={[{ value: 'on', label: 'On' }, { value: 'off', label: 'Off' }]} />}>
        {on && (
          <p className="text-[12px] text-pb-faint">
            The Fines section shows on the page players open from your self-service link. Check it is ticked under
            {' '}<em>Self-service link → Player page</em> in Availability.
          </p>
        )}
      </Card>
      <AddFines teamId={teamId} data={data} onSaved={changed} />
      <Tracker teamId={teamId} data={data} onChanged={changed} />
      <FineList teamId={teamId} data={data} onChanged={load} />
      <HowToPay teamId={teamId} data={data} onChanged={load} />
    </div>
  )
}

export default function AdminFines() {
  const toast = useToast()
  const toastRef = useLatest(toast)
  const [squads, setSquads] = useState(null)
  const [picked, setPicked] = usePersistedState('select.fines.squad', null)

  const load = useCallback(() => {
    return api.bsFinesSquads().then((d) => setSquads(d.squads || []))
      .catch((e) => { toastRef.current.error(e.message || 'Could not load squads'); setSquads([]) })
  }, [toastRef])
  useEffect(() => { load() }, [load])

  const current = useMemo(() => {
    if (!squads || squads.length === 0) return null
    return squads.find((s) => s.id === picked) || squads.find((s) => s.enabled) || squads[0]
  }, [squads, picked])

  if (squads === null) return <BetterSelectLayout title="Fines"><PbSpinner message="Loading squads…" /></BetterSelectLayout>
  return (
    <BetterSelectLayout title="Fines">
      <p className="text-pb-faint text-sm mb-4 max-w-2xl">
        The after-game fines session: who was fined what, who has paid into the pot, and how to pay. It is on
        per squad, so a side that doesn't run fines never sees it.
      </p>
      {squads.length === 0 ? (
        <div className="pb-card rounded-xl p-6 text-sm text-pb-faint" data-no-squads>Fines run per squad. Add a squad on the Squads page first.</div>
      ) : (
        <>
          <div className="flex flex-wrap gap-1.5 mb-4" role="tablist" aria-label="Squad">
            {squads.map((s) => (
              <button key={s.id} type="button" role="tab" aria-selected={current?.id === s.id} onClick={() => setPicked(s.id)}
                className={`px-3 py-1.5 rounded-lg text-[13px] font-display font-semibold border transition ${current?.id === s.id ? 'bg-pb-accent/15 text-pb-accent border-pb-accent/40' : 'text-pb-dim border-pb-hairline hover:text-pb-text'}`}>
                {s.name}{' '}
                <span className="ml-1 font-mono text-[9.5px]" style={{ color: s.enabled ? 'var(--pb-positive)' : 'var(--pb-faintest)' }}>{s.enabled ? 'ON' : 'OFF'}</span>
                {s.enabled && s.owing > 0 && <span className="ml-1.5 text-[11.5px] text-pb-faint font-normal">{money(s.owing)} owing</span>}
              </button>
            ))}
          </div>
          {current && <SquadFines key={current.id} teamId={current.id} onSwitched={load} />}
        </>
      )}
    </BetterSelectLayout>
  )
}
