import { useEffect, useRef, useState } from 'react'
import { api } from '../../../lib/api'
import { Badge, Button, Field, Modal, Select, TextInput } from '../../../components/admin/ui'

// Shared bits for the Teamwear screens (BetterAdmin > Stock > Teamwear).

export const money = (n) =>
  `$${Number(n || 0).toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

export const fmtDate = (iso) => {
  if (!iso) return ''
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso)
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

export const fmtDateTime = (iso) => {
  if (!iso) return ''
  return new Date(iso).toLocaleString('en-AU', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })
}

// The eight stages of a round, in order. `stage` values from the server map onto them.
export const STEPS = [
  { key: 'setup', label: 'Shop setup' },
  { key: 'announce', label: 'Announce' },
  { key: 'order', label: 'Order' },
  { key: 'triage', label: 'Triage' },
  { key: 'confirm', label: 'Confirm' },
  { key: 'pay', label: 'Pay' },
  { key: 'export', label: 'Export' },
  { key: 'receive', label: 'Receive' },
]

// Where a campaign sits on the eight steps.
export function stepOf(c) {
  if (!c) return 0
  switch (c.stage) {
    case 'draft': return 1
    case 'open': return 2
    case 'triage': return c.approved ? 4 : 3
    case 'payment': return 5
    case 'exported': return 6
    case 'received': case 'closed': return 7
    default: return 0
  }
}

export const STAGE_LABEL = {
  draft: 'Draft', open: 'Ordering open', triage: 'Triage', payment: 'Collecting payment',
  exported: 'With supplier', received: 'Received', closed: 'Finished', cancelled: 'Cancelled',
}

export function stageLabel(c) {
  if (c.stage === 'open' && !c.ordering_open) return 'Ordering closed'
  if (c.stage === 'triage' && c.approved) return 'Plan approved'
  return STAGE_LABEL[c.stage] || c.stage
}

export function stageTone(c) {
  if (c.stage === 'cancelled' || c.stage === 'closed') return 'calm'
  if (c.stage === 'triage' || c.stage === 'payment') return 'warn'
  if (c.stage === 'open') return 'ok'
  return 'calm'
}

export const PERSONALISATION = [
  { key: 'none', label: 'None' },
  { key: 'number_name', label: 'Number and name' },
  { key: 'number_initials', label: 'Number and initials' },
]

export const PHASE_LABEL = {
  editable: 'Ordering', waiting: 'Waiting for triage', payment: 'Payment requested', locked: 'With supplier',
  cancelled: 'Cancelled', collected: 'Collected',
}

export function NumberBadge({ line }) {
  if (!line.number) return null
  const tone = line.number_status === 'clash' ? 'block' : line.number_status === 'approved' || line.number_status === 'ok' ? 'ok' : 'calm'
  return <span title={line.number_note || ''}><Badge toneKey={tone}>#{line.number}</Badge></span>
}

export function Stepper({ campaign }) {
  const at = stepOf(campaign)
  const cancelled = campaign?.stage === 'cancelled'
  return (
    <ol className="flex flex-wrap gap-1.5 mb-4" data-stepper aria-label="Order round stages">
      {STEPS.map((s, i) => {
        const done = !cancelled && i < at
        const now = !cancelled && i === at
        return (
          <li key={s.key} data-step={s.key} data-state={done ? 'done' : now ? 'now' : 'todo'}
            className="text-[11.5px] font-semibold px-2.5 py-1 rounded-md border"
            style={now
              ? { background: 'color-mix(in srgb, var(--pb-accent) 18%, transparent)', borderColor: 'var(--pb-accent)', color: 'var(--pb-accent-ink)' }
              : done
                ? { borderColor: 'var(--pb-hairline2)', color: 'var(--pb-dim)' }
                : { borderColor: 'var(--pb-hairline)', color: 'var(--pb-faintest)' }}>
            {i + 1} · {s.label}
          </li>
        )
      })}
    </ol>
  )
}

// One line being built in the coordinator's order form.
function blankLine(products) {
  const p = products[0]
  return { product_id: p?.product_id || '', variant_id: p?.sizes?.[0]?.variant_id || '', qty: 1, wearer_name: '', wearer_player_id: null, number: '', text: '' }
}

// Search the club's players for a wearer (debounced). Composite: lives outside a <label>.
function PlayerPick({ value, onPick }) {
  const [q, setQ] = useState(value || '')
  const [hits, setHits] = useState([])
  const timer = useRef(null)
  useEffect(() => { setQ(value || '') }, [value])
  const search = (term) => {
    setQ(term)
    onPick({ wearer_name: term, wearer_player_id: null })
    clearTimeout(timer.current)
    if (term.trim().length < 2) { setHits([]); return }
    timer.current = setTimeout(() => {
      api.twFindPlayers(term).then(d => setHits(d.players || [])).catch(() => setHits([]))
    }, 250)
  }
  return (
    <div className="relative">
      <TextInput value={q} onChange={e => search(e.target.value)} placeholder="Wearer (player or any name)" aria-label="Wearer" />
      {hits.length > 0 && (
        <div className="absolute z-10 left-0 right-0 mt-1 bg-pb-surface border border-pb-hairline2 rounded-lg max-h-48 overflow-y-auto">
          {hits.map(h => (
            <button key={h.id} type="button" className="block w-full text-left px-3 py-1.5 text-[13px] hover:bg-pb-surface2"
              onMouseDown={e => { e.preventDefault(); onPick({ wearer_name: h.name, wearer_player_id: h.id, number: h.shirt_number || '' }); setQ(h.name); setHits([]) }}>
              {h.name}{h.shirt_number ? ` · #${h.shirt_number}` : ''}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function LineRow({ line, products, onChange, onRemove }) {
  const p = products.find(x => x.product_id === line.product_id)
  const pers = p?.personalisation && p.personalisation !== 'none'
  return (
    <div className="border border-pb-hairline rounded-lg p-3 space-y-2" data-line-row>
      <div className="grid gap-2 sm:grid-cols-[1fr_110px_70px]">
        <Select value={line.product_id} aria-label="Product"
          onChange={e => { const np = products.find(x => x.product_id === e.target.value); onChange({ product_id: e.target.value, variant_id: np?.sizes?.[0]?.variant_id || '' }) }}>
          {products.map(x => <option key={x.product_id} value={x.product_id}>{x.name} · {money(x.price)}</option>)}
        </Select>
        <Select value={line.variant_id} aria-label="Size" onChange={e => onChange({ variant_id: e.target.value })}>
          {(p?.sizes || []).map(z => <option key={z.variant_id} value={z.variant_id}>{z.label}</option>)}
        </Select>
        <TextInput type="number" min={1} max={50} value={line.qty} aria-label="Quantity"
          onChange={e => onChange({ qty: e.target.value })} />
      </div>
      <PlayerPick value={line.wearer_name} onPick={(patch) => onChange(patch)} />
      {pers && (
        <div className="grid gap-2 grid-cols-[90px_1fr]">
          <TextInput value={line.number} onChange={e => onChange({ number: e.target.value })} placeholder="No." aria-label="Number" />
          <TextInput value={line.text} onChange={e => onChange({ text: e.target.value.toUpperCase() })}
            placeholder={p.personalisation === 'number_initials' ? 'Initials' : 'Name on the back'} aria-label="Name or initials" />
        </div>
      )}
      <div className="flex justify-end"><Button size="sm" variant="quiet-danger" onClick={onRemove}>Remove line</Button></div>
    </div>
  )
}

// The coordinator enters an order for someone (a non-player, a phone order, a late add).
export function OrderForm({ title, products, onClose, onSubmit, withContact = true }) {
  const [lines, setLines] = useState(() => [blankLine(products)])
  const [contact, setContact] = useState({ contact_name: '', contact_email: '', contact_phone: '' })
  const [sendEmail, setSendEmail] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const set = (i, patch) => setLines(ls => ls.map((l, n) => (n === i ? { ...l, ...patch } : l)))
  const submit = async () => {
    setBusy(true); setError(null)
    try {
      await onSubmit({ ...(withContact ? contact : {}), lines: lines.map(l => ({ ...l, qty: Number(l.qty) || 1 })), send_email: sendEmail })
      onClose()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return (
    <Modal title={title} onClose={onClose} width={560}
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" disabled={busy || !lines.length} onClick={submit}>{busy ? 'Saving…' : 'Save order'}</Button>
      </>}>
      <div className="space-y-3 pb-3">
        {withContact && (
          <div className="grid gap-2 sm:grid-cols-2">
            <Field label="Contact name"><TextInput value={contact.contact_name} onChange={e => setContact(c => ({ ...c, contact_name: e.target.value }))} /></Field>
            <Field label="Email"><TextInput type="email" value={contact.contact_email} onChange={e => setContact(c => ({ ...c, contact_email: e.target.value }))} /></Field>
            <Field label="Mobile"><TextInput value={contact.contact_phone} onChange={e => setContact(c => ({ ...c, contact_phone: e.target.value }))} /></Field>
          </div>
        )}
        {lines.map((l, i) => (
          <LineRow key={i} line={l} products={products} onChange={patch => set(i, patch)}
            onRemove={() => setLines(ls => ls.filter((_, n) => n !== i))} />
        ))}
        <Button size="sm" onClick={() => setLines(ls => [...ls, blankLine(products)])}>Add a line</Button>
        {withContact && (
          <label className="flex items-center gap-2 text-[13px] text-pb-dim">
            <input type="checkbox" checked={sendEmail} onChange={e => setSendEmail(e.target.checked)} className="accent-pb-accent" />
            Email the contact a copy
          </label>
        )}
        {error && <div className="text-[13px] text-pb-red" role="alert">{error}</div>}
      </div>
    </Modal>
  )
}
