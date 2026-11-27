import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../../../lib/api'
import BetterClubhouseLayout from '../../../components/admin/BetterClubhouseLayout'
import {
  Badge, Button, Cell, Checkbox, Empty, Field, Modal, Note, SearchInput, SegButtons, Select, StatCard, TableHead,
  TableRow, TableWrap, TextArea, TextInput,
} from '../../../components/admin/ui'
import { fmtDate, fmtDateTime, money, NumberBadge, OrderForm, PHASE_LABEL, stageLabel, stageTone, Stepper } from './shared'

// One order round, from setup to receive and pack. Each tab is one stage of the Concept of
// Operations; the server decides what each stage allows and says why when it refuses.

const TABS = [
  { key: 'setup', label: 'Setup' },
  { key: 'orders', label: 'Orders' },
  { key: 'triage', label: 'Triage' },
  { key: 'payments', label: 'Payments' },
  { key: 'export', label: 'Export' },
  { key: 'pack', label: 'Receive & pack' },
  { key: 'emails', label: 'Emails' },
]

function defaultTab(c) {
  if (!c) return 'setup'
  if (c.stage === 'draft') return 'setup'
  if (c.stage === 'open') return 'orders'
  if (c.stage === 'triage') return 'triage'
  if (c.stage === 'payment') return 'payments'
  if (c.stage === 'exported') return 'export'
  return 'pack'
}

const toLocalInput = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}

function ErrorLine({ error }) {
  if (!error) return null
  return <div className="text-[13px] text-pb-red mt-2" role="alert" data-error>{error}</div>
}

/* ── Setup ─────────────────────────────────────────────────────────────── */

function LaunchModal({ campaign, onClose, onLaunched }) {
  const [preview, setPreview] = useState(null)
  const [sendEmail, setSendEmail] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [testMsg, setTestMsg] = useState(null)
  useEffect(() => { api.twLaunchPreview(campaign.id).then(setPreview).catch(e => setError(e.message)) }, [campaign.id])
  const launch = async () => {
    setBusy(true); setError(null)
    try { onLaunched(await api.twLaunch(campaign.id, sendEmail)) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const test = async () => {
    try { const r = await api.twLaunchEmail(campaign.id, ''); setTestMsg(r.emails.sent ? 'Test sent to you.' : 'The test did not send. Check the email settings.') } catch (e) { setTestMsg(e.message) }
  }
  return (
    <Modal title="Launch this campaign" onClose={onClose} width={620}
      subtitle="Ordering opens on the Player Dashboard straight away and closes at the time you set."
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={busy} onClick={launch}>{busy ? 'Launching…' : 'Launch'}</Button></>}>
      <div className="space-y-3 pb-3">
        {preview && (
          <>
            <Checkbox checked={sendEmail} onChange={setSendEmail}
              hint={preview.email_live ? `To ${preview.recipients} players with an email address, once each.` : 'Email is not live on this server, so nothing would send.'}>
              Email the launch to the club's players
            </Checkbox>
            <div className="border border-pb-hairline rounded-lg overflow-hidden bg-white" style={{ maxHeight: 320, overflowY: 'auto' }}>
              <div className="text-[12px] text-gray-600 px-3 py-2 border-b">Subject: {preview.subject}</div>
              <div dangerouslySetInnerHTML={{ __html: preview.html }} />
            </div>
            <Button size="sm" onClick={test}>Send me a test</Button> {testMsg && <span className="text-[12.5px] text-pb-faint">{testMsg}</span>}
          </>
        )}
        <ErrorLine error={error} />
      </div>
    </Modal>
  )
}

function SetupTab({ data, range, onChange }) {
  const c = data.campaign
  const [f, setF] = useState(() => ({
    name: c.name, intro: c.intro || '', opens_on: c.opens_on || '', closes_at: toLocalInput(c.closes_at),
    pay_due_on: c.pay_due_on || '', moq: c.moq ?? '', reminder_offsets: c.reminder_offsets_own ? c.reminder_offsets.join(', ') : '',
  }))
  const base = useRef(f)
  const [items, setItems] = useState(() => data.items.map(i => i.product_id))
  const [error, setError] = useState(null)
  const [launching, setLaunching] = useState(false)
  const [reopenAt, setReopenAt] = useState('')
  const editable = ['draft', 'open'].includes(c.stage)
  const set = (k, v) => setF(x => ({ ...x, [k]: v }))
  const dirty = Object.keys(f).filter(k => f[k] !== base.current[k])
  const itemsDirty = items.join() !== data.items.map(i => i.product_id).join()
  const save = async () => {
    setError(null)
    const patch = {}
    dirty.forEach(k => { patch[k] = f[k] === '' ? null : f[k] })
    if ('closes_at' in patch && patch.closes_at) patch.closes_at = new Date(patch.closes_at).toISOString()
    if (itemsDirty) patch.product_ids = items
    try { const d = await api.twUpdateCampaign(c.id, patch); base.current = f; onChange(d) } catch (e) { setError(e.message) }
  }
  const act = async (fn) => { setError(null); try { onChange(await fn()) } catch (e) { setError(e.message) } }
  const mto = (range || []).filter(p => p.made_to_order)
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
      <section className="pb-card p-4 space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name"><TextInput value={f.name} onChange={e => set('name', e.target.value)} disabled={!editable && c.stage !== 'triage'} /></Field>
          <Field label="Ordering closes"><TextInput type="datetime-local" value={f.closes_at} onChange={e => set('closes_at', e.target.value)} disabled={!editable} /></Field>
          <Field label="Opens on" hint="Empty opens at launch."><TextInput type="date" value={f.opens_on} onChange={e => set('opens_on', e.target.value)} disabled={!editable} /></Field>
          <Field label="Payment due" hint="Empty: the club's days to pay from the payment request."><TextInput type="date" value={f.pay_due_on} onChange={e => set('pay_due_on', e.target.value)} disabled={c.stage === 'payment' || !!c.exported_at} /></Field>
          <Field label="Supplier minimum per product" hint="Empty uses the club default."><TextInput type="number" min="0" value={f.moq} onChange={e => set('moq', e.target.value)} /></Field>
          <Field label="Reminders (days from due)" hint={`Empty uses the club's (${c.reminder_offsets.join(', ') || 'none'}).`}><TextInput value={f.reminder_offsets} onChange={e => set('reminder_offsets', e.target.value)} /></Field>
        </div>
        <Field label="Message for members" hint="Goes at the top of the launch email and the order page."><TextArea value={f.intro} onChange={e => set('intro', e.target.value)} /></Field>
        <Field label="Items in this round" composite>
          {mto.length === 0 ? <div className="text-[13px] text-pb-faint">No made-to-order items in the shop range.</div> : (
            <div className="space-y-1.5">
              {mto.map(p => {
                const item = data.items.find(i => i.product_id === p.product_id)
                return (
                  <Checkbox key={p.product_id} checked={items.includes(p.product_id)} disabled={!editable || p.price == null}
                    onChange={v => setItems(xs => (v ? [...xs, p.product_id] : xs.filter(x => x !== p.product_id)))}>
                    {p.name} · {money(item ? item.price : p.price)}{item && item.price !== p.price ? ` (shop now ${money(p.price)})` : ''}
                  </Checkbox>
                )
              })}
            </div>
          )}
        </Field>
        <div className="flex items-center gap-2">
          <Button variant="primary" disabled={!dirty.length && !itemsDirty} onClick={save}>Save</Button>
        </div>
        <ErrorLine error={error} />
      </section>
      <aside className="space-y-3">
        <div className="pb-card p-4 space-y-2" data-setup-actions>
          <div className="font-semibold text-pb-text">Stage: {stageLabel(c)}</div>
          {c.stage === 'draft' && <><p className="text-[13px] text-pb-faint">Save the items and close date, then launch to open ordering.</p>
            <Button variant="primary" onClick={() => setLaunching(true)} disabled={dirty.length > 0 || itemsDirty}>Launch campaign</Button></>}
          {c.stage === 'open' && <>
            <p className="text-[13px] text-pb-faint">{c.ordering_open ? `Ordering is open until ${fmtDateTime(c.closes_at)}.` : 'The close date has passed. Close ordering to start triage.'}</p>
            <Button variant="primary" onClick={() => window.confirm('Close ordering now and move to triage?') && act(() => api.twClose(c.id))}>Close ordering</Button>
            <Button onClick={() => act(async () => { const r = await api.twLaunchEmail(c.id, null); window.alert(`Sent ${r.emails.sent}, already sent ${r.emails.skipped}, failed ${r.emails.failed}.`); return api.twCampaign(c.id) })}>Email players again</Button>
          </>}
          {c.stage === 'triage' && !c.payment_requested_at && <>
            <p className="text-[13px] text-pb-faint">Reopen ordering if the round needs more time.</p>
            <div className="flex gap-2 items-center flex-wrap">
              <TextInput type="datetime-local" value={reopenAt} onChange={e => setReopenAt(e.target.value)} style={{ width: 210 }} aria-label="New close date" />
              <Button disabled={!reopenAt} onClick={() => act(() => api.twReopen(c.id, new Date(reopenAt).toISOString()))}>Reopen</Button>
            </div>
          </>}
          {!['exported', 'received', 'closed', 'cancelled'].includes(c.stage) && (
            <Button variant="quiet-danger" onClick={() => window.confirm('Cancel this campaign? Every order in it is cancelled.') && act(async () => { await api.twCancel(c.id); return api.twCampaign(c.id) })}>Cancel campaign</Button>
          )}
        </div>
        <div className="pb-card p-4 text-[12.5px] text-pb-faint space-y-1">
          <div>Created {fmtDate(c.created_at)}</div>
          {c.launched_at && <div>Launched {fmtDateTime(c.launched_at)}</div>}
          {c.approved_on && <div>Committee approved {fmtDate(c.approved_on)}{c.approval_note ? ` (${c.approval_note})` : ''}</div>}
          {c.payment_requested_at && <div>Payment requests sent {fmtDateTime(c.payment_requested_at)}</div>}
          {c.exported_at && <div>Order locked {fmtDateTime(c.exported_at)}</div>}
          {c.received_at && <div>Received {fmtDateTime(c.received_at)}</div>}
        </div>
      </aside>
      {launching && <LaunchModal campaign={c} onClose={() => setLaunching(false)} onLaunched={(d) => { setLaunching(false); onChange(d) }} />}
    </div>
  )
}

/* ── Orders ────────────────────────────────────────────────────────────── */

function LineEditor({ line, sizes, locked, onDone, setError }) {
  const [num, setNum] = useState(line.number || '')
  const [txt, setTxt] = useState(line.text || '')
  const patch = async (p) => { setError(null); try { await api.twUpdateLine(line.id, p); onDone() } catch (e) { setError(e.message) } }
  const cut = line.state === 'cut'
  const removed = line.state === 'removed'
  return (
    <div className={`border-t border-pb-hairline py-2 ${cut || removed ? 'opacity-60' : ''}`} data-order-line>
      <div className="flex flex-wrap items-center gap-2 text-[13px]">
        <span className="font-semibold text-pb-text">{line.qty} × {line.product_name}</span>
        {locked || cut || removed ? <span>({line.size})</span> : (
          <Select value={line.variant_id || ''} onChange={e => patch({ variant_id: e.target.value })} style={{ width: 90 }} aria-label="Size">
            {sizes.map(s => <option key={s.variant_id} value={s.variant_id}>{s.label}</option>)}
          </Select>
        )}
        <span className="text-pb-faint">for {line.wearer_name}</span>
        <NumberBadge line={line} />
        {line.text && <Badge>{line.text}</Badge>}
        {cut && <Badge toneKey="warn">Not available this round</Badge>}
        {removed && <Badge>Removed</Badge>}
        {line.club_covered && <Badge toneKey="accent">Club covers: {line.covered_reason}</Badge>}
        <span className="ml-auto font-mono text-[12px]">{money(line.charge)}</span>
      </div>
      {line.number_note && <div className="text-[12px] mt-1" style={{ color: line.number_status === 'clash' ? '#f5b542' : 'var(--pb-faint)' }}>{line.number_note}</div>}
      {!locked && !cut && (
        <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
          {(line.number || line.text) && <>
            <TextInput value={num} onChange={e => setNum(e.target.value)} style={{ width: 70 }} aria-label="Number" />
            <TextInput value={txt} onChange={e => setTxt(e.target.value.toUpperCase())} style={{ width: 150 }} aria-label="Name text" />
            <Button size="sm" disabled={num === (line.number || '') && txt === (line.text || '')} onClick={() => patch({ number: num, text: txt })}>Save</Button>
            {line.number && line.number_status !== 'approved' && line.number_status !== 'ok' && (
              <Button size="sm" onClick={() => patch({ number: num, approve_number: true })} title="Writes the number to the player's record if they are a player">Approve #{num}</Button>
            )}
          </>}
          {line.club_covered
            ? <Button size="sm" variant="quiet" onClick={() => patch({ club_covered: false })}>Charge again</Button>
            : <Button size="sm" variant="quiet" onClick={() => { const r = window.prompt('Why is the club covering this item? (for example: contracted player)'); if (r) patch({ club_covered: true, covered_reason: r }) }}>Club covers</Button>}
          <Button size="sm" variant="quiet-danger" onClick={() => patch({ removed: !removed })}>{removed ? 'Put back' : 'Remove'}</Button>
        </div>
      )}
    </div>
  )
}

function OrderCard({ order, items, campaign, changes, onChanged }) {
  const [open, setOpen] = useState(false)
  const [error, setError] = useState(null)
  const [paying, setPaying] = useState(false)
  const locked = ['exported', 'received', 'closed', 'cancelled'].includes(campaign.stage) || order.status === 'cancelled'
  const sizesFor = (pid) => items.find(i => i.product_id === pid)?.sizes || []
  const act = async (fn) => { setError(null); try { await fn(); onChanged() } catch (e) { setError(e.message) } }
  const open_changes = changes.filter(r => r.order_id === order.id && r.status === 'open')
  const clashes = order.lines.filter(l => l.state === 'active' && l.number_status === 'clash').length
  return (
    <div className="pb-card px-4 py-3" data-order={order.reference}>
      <button type="button" className="w-full text-left flex items-start justify-between gap-3" onClick={() => setOpen(o => !o)} aria-expanded={open}>
        <div className="min-w-0">
          <div className="font-semibold text-pb-text">{order.contact_name} <span className="font-mono text-[11px] text-pb-faint">{order.reference}</span></div>
          <div className="text-[12px] text-pb-faint mt-0.5 flex flex-wrap gap-1.5 items-center">
            <span>{order.units} units · {PHASE_LABEL[order.phase] || order.phase}</span>
            {order.source === 'coordinator' && <Badge>Entered by club</Badge>}
            {clashes > 0 && <Badge toneKey="warn">{clashes} number{clashes > 1 ? 's' : ''} to check</Badge>}
            {open_changes.length > 0 && <Badge toneKey="warn">Change requested</Badge>}
            {order.unpaid_decision === 'proceed' && <Badge toneKey="accent">Proceeding unpaid</Badge>}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="font-display font-bold text-pb-text">{money(order.total)}</div>
          {order.status === 'cancelled' ? <Badge>Cancelled</Badge>
            : !order.payment_requested_at ? <span className="text-[11px] text-pb-faint">not asked yet</span>
              : order.balance > 0 ? <Badge toneKey={order.overdue ? 'block' : 'warn'}>{money(order.balance)} owing</Badge> : <Badge toneKey="ok">Paid</Badge>}
        </div>
      </button>
      {open && (
        <div className="mt-2">
          <div className="text-[12.5px] text-pb-faint">{order.contact_email}{order.contact_phone ? ` · ${order.contact_phone}` : ''}{order.notes ? ` · “${order.notes}”` : ''}</div>
          {order.cancelled_reason && <div className="text-[12.5px] text-pb-faint">Cancelled: {order.cancelled_reason}</div>}
          <div className="mt-2">
            {order.lines.map(l => <LineEditor key={l.id} line={l} sizes={sizesFor(l.product_id)} locked={locked} onDone={onChanged} setError={setError} />)}
          </div>
          {open_changes.map(r => (
            <div key={r.id} className="mt-2 rounded-lg border border-pb-hairline2 p-3 text-[13px]" data-change-request>
              <div className="text-pb-dim">Change asked {fmtDateTime(r.created_at)}: <i>{r.message}</i></div>
              <div className="flex gap-1.5 mt-2 flex-wrap">
                <Button size="sm" onClick={() => act(() => api.twAnswerChange(r.id, 'done', window.prompt('Note for the member (optional)') || null))}>Mark done and tell them</Button>
                <Button size="sm" variant="quiet" onClick={() => { const why = window.prompt('Why can it not be made?'); if (why !== null) act(() => api.twAnswerChange(r.id, 'declined', why)) }}>Decline</Button>
              </div>
            </div>
          ))}
          {!locked && (
            <div className="flex flex-wrap gap-1.5 mt-3">
              {order.payment_requested_at && order.balance > 0 && <>
                <Button size="sm" onClick={() => setPaying(true)}>Record payment</Button>
                <Button size="sm" onClick={() => act(() => api.twRemind(order.id))}>Send reminder</Button>
                {order.unpaid_decision !== 'proceed'
                  ? <Button size="sm" variant="quiet" onClick={() => { const n = window.prompt('Order this unpaid? Note the arrangement (for example: pays at training).'); if (n !== null) act(() => api.twUpdateOrder(order.id, { unpaid_decision: 'proceed', unpaid_note: n })) }}>Order it unpaid</Button>
                  : <Button size="sm" variant="quiet" onClick={() => act(() => api.twUpdateOrder(order.id, { unpaid_decision: null }))}>Undo unpaid decision</Button>}
              </>}
              {order.payment_requested_at && <Button size="sm" variant="quiet" onClick={() => act(() => api.twResendPaymentRequest(order.id))}>Resend payment request</Button>}
              <Button size="sm" variant="quiet-danger" onClick={() => { const why = window.prompt('Cancel this order? Give a reason.'); if (why) act(() => api.twUpdateOrder(order.id, { cancel: true, cancelled_reason: why })) }}>Cancel order</Button>
            </div>
          )}
          {order.status === 'cancelled' && !['exported', 'received', 'closed', 'cancelled'].includes(campaign.stage) && (
            <Button size="sm" className="mt-2" onClick={() => act(() => api.twUpdateOrder(order.id, { restore: true }))}>Restore order</Button>
          )}
          <ErrorLine error={error} />
        </div>
      )}
      {paying && <PaymentModal order={order} onClose={() => setPaying(false)} onSaved={() => { setPaying(false); onChanged() }} />}
    </div>
  )
}

function PaymentModal({ order, onClose, onSaved }) {
  const [f, setF] = useState({ amount: order.balance, method: 'bank', paid_on: new Date().toISOString().slice(0, 10), reference: order.reference, note: '' })
  const [error, setError] = useState(null)
  const save = async () => { try { await api.twAddPayment(order.id, f); onSaved() } catch (e) { setError(e.message) } }
  return (
    <Modal title={`Payment from ${order.contact_name}`} subtitle={`${money(order.balance)} owing on ${order.reference}`} onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" onClick={save}>Record payment</Button></>}>
      <div className="grid gap-3 sm:grid-cols-2 pb-3">
        <Field label="Amount"><TextInput type="number" step="0.01" value={f.amount} onChange={e => setF({ ...f, amount: e.target.value })} /></Field>
        <Field label="Method"><Select value={f.method} onChange={e => setF({ ...f, method: e.target.value })}>
          <option value="bank">Bank transfer</option><option value="card">Card</option><option value="cash">Cash</option><option value="other">Other</option>
        </Select></Field>
        <Field label="Paid on"><TextInput type="date" value={f.paid_on} onChange={e => setF({ ...f, paid_on: e.target.value })} /></Field>
        <Field label="Reference"><TextInput value={f.reference} onChange={e => setF({ ...f, reference: e.target.value })} /></Field>
        <Field label="Note" className="sm:col-span-2"><TextInput value={f.note} onChange={e => setF({ ...f, note: e.target.value })} /></Field>
      </div>
      <ErrorLine error={error} />
    </Modal>
  )
}

function OrdersTab({ data, reload }) {
  const c = data.campaign
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState('all')
  const [adding, setAdding] = useState(false)
  const orders = data.orders
  const shown = orders.filter(o => {
    if (filter === 'active' && o.status === 'cancelled') return false
    if (filter === 'numbers' && !o.lines.some(l => l.state === 'active' && l.number_status === 'clash')) return false
    if (filter === 'changes' && !data.changes.some(r => r.order_id === o.id && r.status === 'open')) return false
    if (filter === 'owing' && !(o.payment_requested_at && o.balance > 0 && o.status !== 'cancelled')) return false
    if (!q.trim()) return true
    const t = q.trim().toLowerCase()
    return [o.contact_name, o.reference, o.contact_email, ...o.lines.map(l => l.wearer_name)].some(x => (x || '').toLowerCase().includes(t))
  }).slice().reverse()
  const products = data.items.map(i => ({ product_id: i.product_id, name: i.name, price: i.price, personalisation: i.personalisation, sizes: i.sizes }))
  const canAdd = ['draft', 'open', 'triage'].includes(c.stage) && !c.approved
  const count = (fn) => orders.filter(fn).length
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <SegButtons value={filter} onChange={setFilter} tabs={[
          { key: 'all', label: `All ${orders.length}` },
          { key: 'active', label: 'Active' },
          { key: 'numbers', label: 'Numbers to check', badge: count(o => o.status !== 'cancelled' && o.lines.some(l => l.state === 'active' && l.number_status === 'clash')) },
          { key: 'changes', label: 'Changes', badge: data.changes.filter(r => r.status === 'open').length },
          { key: 'owing', label: 'Owing', badge: count(o => o.payment_requested_at && o.balance > 0 && o.status !== 'cancelled') },
        ]} />
      </div>
      <div className="flex flex-wrap items-center gap-2 justify-between">
        <SearchInput value={q} onChange={setQ} placeholder="Search name, reference or wearer" />
        {canAdd && <Button variant="primary" onClick={() => setAdding(true)}>Add order</Button>}
      </div>
      {shown.length === 0 ? <Empty>{orders.length ? 'Nothing matches.' : 'No orders yet. Members order from the Player Dashboard while the campaign is open.'}</Empty>
        : shown.map(o => <OrderCard key={o.id} order={o} items={data.items} campaign={c} changes={data.changes} onChanged={reload} />)}
      {adding && <OrderForm title="Add an order" products={products} onClose={() => setAdding(false)}
        onSubmit={async (body) => { await api.twAddOrder(c.id, body); reload() }} />}
    </div>
  )
}

/* ── Triage ────────────────────────────────────────────────────────────── */

function TriageRow({ row, campaign, locked, onUpdate, setError }) {
  const [open, setOpen] = useState(false)
  const [tops, setTops] = useState(() => Object.fromEntries(row.sizes.map(s => [s.variant_id, s.topup])))
  useEffect(() => { setTops(Object.fromEntries(row.sizes.map(s => [s.variant_id, s.topup]))) }, [row])
  const changed = row.sizes.some(s => Number(tops[s.variant_id] || 0) !== s.topup)
  const run = async (fn) => { setError(null); try { onUpdate(await fn()) } catch (e) { setError(e.message) } }
  return (
    <div className="pb-card px-4 py-3" data-triage-row={row.supplier_code || row.name}>
      <div className="flex flex-wrap items-start gap-3 justify-between">
        <div className="min-w-0">
          <div className="font-semibold text-pb-text">{row.name} {row.supplier_code && <span className="font-mono text-[11px] text-pb-faint">{row.supplier_code}</span>}</div>
          <div className="text-[12.5px] text-pb-faint mt-0.5">
            {row.orders} orders · <b className="text-pb-text">{row.member_units}</b> member units + {row.topup_units} top-ups = {row.total_units} of {row.moq}
            {row.shortfall > 0 && <> · <span style={{ color: '#f5b542' }}>{row.shortfall} short</span></>}
            {row.ratio && <> · {row.ratio}</>}
          </div>
          <div className="flex gap-1.5 mt-1">
            {row.suggested_cut && <Badge toneKey="block">Suggested cut</Badge>}
          </div>
        </div>
        <SegButtons value={row.decision} onChange={(d) => !locked && run(() => api.twDecision(campaign.id, row.product_id, d, row.decision_note))}
          tabs={[{ key: 'include', label: 'Include' }, { key: 'cut', label: 'Cut' }, { key: 'hold', label: 'Hold' }]} />
      </div>
      <button type="button" className="text-[12px] text-pb-faint underline mt-2" onClick={() => setOpen(o => !o)}>{open ? 'Hide sizes' : 'Sizes and top-ups'}</button>
      {open && (
        <div className="mt-2">
          <div className="grid gap-1.5" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(110px, 1fr))' }}>
            {row.sizes.map(s => (
              <div key={s.variant_id} className="border border-pb-hairline rounded-lg p-2 text-[12.5px]">
                <div className="font-semibold text-pb-text">{s.label}</div>
                <div className="text-pb-faint">{s.member} ordered</div>
                <label className="flex items-center gap-1 mt-1">
                  <span className="text-pb-faint">+</span>
                  <TextInput type="number" min="0" value={tops[s.variant_id] ?? 0} disabled={locked} aria-label={`Top-up ${s.label}`}
                    onChange={e => setTops(t => ({ ...t, [s.variant_id]: e.target.value }))} style={{ width: 64 }} />
                </label>
              </div>
            ))}
          </div>
          {!locked && (
            <div className="flex gap-1.5 mt-2">
              <Button size="sm" disabled={!changed} onClick={() => run(() => api.twTopups(campaign.id, row.product_id, Object.fromEntries(Object.entries(tops).map(([k, v]) => [k, Number(v) || 0]))))}>Save top-ups</Button>
              {row.shortfall > 0 && <Button size="sm" onClick={() => run(() => api.twSuggestTopups(campaign.id, row.product_id))}>Suggest top-ups to reach {row.moq}</Button>}
            </div>
          )}
          <div className="text-[11.5px] text-pb-faintest mt-1.5">Top-ups are made for the club and go into club stock when the kit arrives.</div>
        </div>
      )}
    </div>
  )
}

function TriageTab({ campaign, onCampaign }) {
  const [t, setT] = useState(null)
  const [error, setError] = useState(null)
  const [note, setNote] = useState('')
  const [on, setOn] = useState(new Date().toISOString().slice(0, 10))
  const [flash, setFlash] = useState(null)
  useEffect(() => { api.twTriage(campaign.id).then(setT).catch(e => setError(e.message)) }, [campaign.id])
  const update = (d) => {
    setT(d)
    if (d.approval_cleared) setFlash('The plan changed, so the committee approval was cleared. Record it again once they have seen the new plan.')
  }
  if (!t) return <Empty>{error || 'Loading triage…'}</Empty>
  if (campaign.stage === 'open' || campaign.stage === 'draft') return <Note>Triage starts once ordering closes. Members are ordering until {fmtDateTime(campaign.closes_at)}. The table below is live.</Note>
  const locked = campaign.stage !== 'triage'
  const run = async (fn) => { setError(null); try { const d = await fn(); if (d) update(d); onCampaign() } catch (e) { setError(e.message) } }
  return (
    <div className="space-y-3">
      <div className="grid gap-2 grid-cols-2 lg:grid-cols-4">
        <StatCard value={t.totals.member_units} label="Member units" />
        <StatCard value={t.totals.topup_units} label="Top-ups" />
        <StatCard value={t.totals.included_units} label="Units to order" />
        <StatCard value={money(t.totals.value)} label="Member value included" />
      </div>
      <Note>Minimum {t.default_moq} per product code, sizes combined. A product needing {t.cut_ratio} or more top-ups per member unit is flagged Suggested cut. A cut cancels that item in every order holding it, and members see Not available this round.</Note>
      {flash && <Note toneKey="warn">{flash}</Note>}
      {t.items.map(r => <TriageRow key={r.product_id} row={r} campaign={campaign} locked={locked} onUpdate={update} setError={setError} />)}
      <ErrorLine error={error} />
      <section className="pb-card p-4 space-y-2" data-approval>
        <h3 className="font-display font-bold text-pb-text">Committee approval</h3>
        {t.approval_current ? (
          <>
            <div className="text-[13px] text-pb-dim">Approved {fmtDate(t.campaign.approved_on)}{t.campaign.approval_note ? `: ${t.campaign.approval_note}` : ''}.</div>
            {!locked && <div className="flex flex-wrap gap-1.5">
              <Button variant="primary" onClick={() => window.confirm('Send payment requests to every order with items left? Orders left with nothing are told it is not available this round.') && run(async () => { const r = await api.twPaymentRequests(campaign.id); window.alert(`Payment requests: ${r.asked.length}. Not available: ${r.emptied.length}. Emails sent ${r.emails.sent}, failed ${r.emails.failed}.`); return api.twTriage(campaign.id) })}>Send payment requests</Button>
              <Button variant="quiet" onClick={() => run(() => api.twUnapprove(campaign.id))}>Clear approval</Button>
            </div>}
          </>
        ) : locked ? <div className="text-[13px] text-pb-faint">The plan is confirmed.</div> : (
          <>
            {t.holds.length > 0 && <div className="text-[13px]" style={{ color: '#f5b542' }}>Decide include or cut for: {t.holds.join(', ')}.</div>}
            {t.below_minimum.length > 0 && <div className="text-[13px]" style={{ color: '#f5b542' }}>Included but below the minimum: {t.below_minimum.join(', ')}. Add top-ups or check the supplier will take them.</div>}
            <p className="text-[13px] text-pb-faint">Record the committee's sign-off of the whole plan above. Payment requests can go once it is recorded.</p>
            <div className="grid gap-2 sm:grid-cols-[170px_1fr]">
              <Field label="Approved on"><TextInput type="date" value={on} onChange={e => setOn(e.target.value)} /></Field>
              <Field label="Where it was approved"><TextInput value={note} onChange={e => setNote(e.target.value)} placeholder="Committee meeting 2 Dec, minutes item 5" /></Field>
            </div>
            <Button variant="primary" disabled={t.holds.length > 0} onClick={() => run(() => api.twApprove(campaign.id, on, note))}>Record committee approval</Button>
          </>
        )}
      </section>
    </div>
  )
}

/* ── Payments ──────────────────────────────────────────────────────────── */

function BankImport({ campaign, onDone }) {
  const input = useRef(null)
  const [rows, setRows] = useState(null)
  const [pick, setPick] = useState({})
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const load = async (file) => {
    if (!file) return
    setError(null); setResult(null)
    try {
      const d = await api.twBankPreview(file, campaign.id)
      setRows(d.rows)
      setPick(Object.fromEntries(d.rows.filter(r => r.status === 'matched').map(r => [r.key, r.suggestions[0].order_id])))
    } catch (e) { setError(e.message) }
  }
  const commit = async () => {
    const chosen = rows.filter(r => pick[r.key]).map(r => ({ key: r.key, order_id: pick[r.key], amount: r.amount, date: r.date, description: r.description }))
    try { const d = await api.twBankCommit(chosen); setResult(`Recorded ${d.recorded} payment${d.recorded === 1 ? '' : 's'}.`); setRows(null); onDone() } catch (e) { setError(e.message) }
  }
  return (
    <section className="pb-card p-4 space-y-2" data-bank-import>
      <h3 className="font-display font-bold text-pb-text">Match a bank statement</h3>
      <p className="text-[13px] text-pb-faint">Upload the CSV from internet banking. A credit carrying an order's reference is matched for you; the rest suggest an order by name and amount. Nothing is recorded until you confirm, and the same line is never recorded twice.</p>
      <Button onClick={() => input.current?.click()}>Upload CSV</Button>
      <input ref={input} type="file" accept=".csv,text/csv" className="hidden" onChange={e => { load(e.target.files?.[0]); e.target.value = '' }} />
      {result && <div className="text-[13px]" style={{ color: 'var(--pb-positive)' }}>{result}</div>}
      <ErrorLine error={error} />
      {rows && (
        <div className="space-y-1.5">
          {rows.length === 0 && <Empty>No credits in that file.</Empty>}
          {rows.map(r => (
            <div key={r.key} className="grid gap-2 sm:grid-cols-[100px_90px_1fr_260px] items-center text-[13px] border-t border-pb-hairline pt-1.5" data-bank-row={r.status}>
              <span className="text-pb-faint">{fmtDate(r.date)}</span>
              <span className="font-mono">{money(r.amount)}</span>
              <span className="min-w-0 truncate" title={r.description}>{r.description}</span>
              {r.status === 'already_imported' ? <span className="text-pb-faint">Already recorded</span> : (
                <Select value={pick[r.key] || ''} onChange={e => setPick(p => ({ ...p, [r.key]: e.target.value }))} aria-label="Order">
                  <option value="">Skip this line</option>
                  {r.suggestions.map(s => <option key={s.order_id} value={s.order_id}>{s.reference} · {s.contact_name} ({money(s.balance)} owing){s.why === 'reference' ? ' · reference' : ''}</option>)}
                </Select>
              )}
            </div>
          ))}
          {rows.some(r => pick[r.key]) && <Button variant="primary" onClick={commit}>Record {Object.values(pick).filter(Boolean).length} payments</Button>}
        </div>
      )}
    </section>
  )
}

function PaymentsTab({ data, reload }) {
  const c = data.campaign
  const [ledger, setLedger] = useState(null)
  const [error, setError] = useState(null)
  const loadLedger = useCallback(() => { api.twPayments(c.id).then(d => setLedger(d.payments)).catch(e => setError(e.message)) }, [c.id])
  useEffect(() => { loadLedger() }, [loadLedger])
  const asked = data.orders.filter(o => o.payment_requested_at && o.status !== 'cancelled')
  const due = asked.reduce((a, o) => a + o.total, 0)
  const paid = asked.reduce((a, o) => a + o.paid, 0)
  const owing = asked.filter(o => o.balance > 0)
  const refresh = () => { reload(); loadLedger() }
  if (!c.payment_requested_at) return <Note>Payment requests go from the Triage tab once the committee approval is recorded.</Note>
  return (
    <div className="space-y-3">
      <div className="grid gap-2 grid-cols-2 lg:grid-cols-4">
        <StatCard value={money(due)} label="Asked for" />
        <StatCard value={money(paid)} label="Paid" />
        <StatCard value={money(Math.max(0, due - paid))} label="Owing" />
        <StatCard value={`${asked.length - owing.length} of ${asked.length}`} label="Orders paid" />
      </div>
      <BankImport campaign={c} onDone={refresh} />
      <section className="space-y-2">
        <h3 className="font-display font-bold text-pb-text">Still owing</h3>
        {owing.length === 0 ? <Empty>Every order is paid.</Empty> : owing.map(o => <OrderCard key={o.id} order={o} items={data.items} campaign={c} changes={data.changes} onChanged={refresh} />)}
      </section>
      <section className="space-y-2">
        <h3 className="font-display font-bold text-pb-text">Payments</h3>
        <ErrorLine error={error} />
        {!ledger ? <Empty>Loading…</Empty> : ledger.length === 0 ? <Empty>No payments yet.</Empty> : (
          <TableWrap>
            <TableHead cols="100px 1fr 90px 90px 90px" minWidth={560}>
              <Cell head first>Date</Cell><Cell head>From</Cell><Cell head>How</Cell><Cell head num>Amount</Cell><Cell head last />
            </TableHead>
            {ledger.map(p => (
              <TableRow key={p.id} cols="100px 1fr 90px 90px 90px" minWidth={560}>
                <Cell first>{fmtDate(p.paid_on)}</Cell>
                <Cell><span className={p.voided ? 'line-through text-pb-faint' : ''}>{p.contact_name} · {p.order_reference}</span>{p.voided && <span className="text-[11px] text-pb-faint"> voided{p.void_reason ? `: ${p.void_reason}` : ''}</span>}</Cell>
                <Cell>{p.method}{p.source !== 'manual' ? ` (${p.source.replace('_', ' ')})` : ''}</Cell>
                <Cell num>{money(p.amount)}</Cell>
                <Cell last>{!p.voided && <Button size="sm" variant="quiet-danger" onClick={() => { const r = window.prompt('Void this payment? Give a reason.'); if (r) api.twVoidPayment(p.id, r).then(refresh).catch(e => setError(e.message)) }}>Void</Button>}</Cell>
              </TableRow>
            ))}
          </TableWrap>
        )}
      </section>
    </div>
  )
}

/* ── Export ────────────────────────────────────────────────────────────── */

function ExportTab({ data, onChange, reload }) {
  const c = data.campaign
  const [st, setSt] = useState(null)
  const [error, setError] = useState(null)
  const load = useCallback(() => { api.twExportStatus(c.id).then(setSt).catch(e => setError(e.message)) }, [c.id])
  useEffect(() => { load() }, [load])
  if (!st) return <Empty>{error || 'Loading…'}</Empty>
  const form = st.form
  const locked = ['exported', 'received', 'closed'].includes(c.stage)
  const lock = async () => { setError(null); try { onChange(await api.twExportLock(c.id)); load() } catch (e) { setError(e.message) } }
  const download = async () => { setError(null); try { await api.twExportDownload(c.id) } catch (e) { setError(e.message) } }
  const setDate = async (k, v) => { try { onChange(await api.twUpdateCampaign(c.id, { [k]: v || null })) } catch (e) { setError(e.message) } }
  return (
    <div className="space-y-3">
      {!locked && c.stage !== 'payment' && <Note>The order is exported once payment requests have gone and every order is paid or decided.</Note>}
      {!locked && st.unpaid.length > 0 && (
        <Note toneKey="warn" title="Not ready">
          {st.unpaid.length} order{st.unpaid.length > 1 ? 's are' : ' is'} unpaid: {st.unpaid.map(u => `${u.contact_name} (${money(u.balance)})`).join(', ')}.
          Record the payment, cancel the order, or choose Order it unpaid on the order. Nothing is cancelled automatically.
        </Note>
      )}
      {!locked && st.open_changes > 0 && <Note toneKey="warn">{st.open_changes} change request{st.open_changes > 1 ? 's are' : ' is'} still open. Exporting locks every order.</Note>}
      <div className="flex flex-wrap gap-2">
        {!locked && <Button variant="primary" disabled={!st.ready} onClick={() => window.confirm('Lock every order and build the supplier form? Members can no longer ask for changes.') && lock()}>Lock order and build form</Button>}
        {locked && <Button variant="primary" onClick={download}>Download supplier form (.xlsx)</Button>}
      </div>
      <ErrorLine error={error} />
      <section className="pb-card p-4">
        <h3 className="font-display font-bold text-pb-text mb-2">Quantities {locked ? '' : '(preview)'}</h3>
        {form.products.length === 0 ? <Empty>Nothing included yet.</Empty> : (
          <div className="overflow-x-auto pb-scroll">
            <table className="text-[12.5px] w-full" data-qty-grid>
              <thead><tr className="text-pb-faint text-left"><th className="pr-3 py-1">Code</th><th className="pr-3">Product</th>{form.sizes.map(s => <th key={s} className="px-2 text-right">{s}</th>)}<th className="pl-2 text-right">Total</th></tr></thead>
              <tbody>
                {form.products.map(p => (
                  <tr key={p.product_id} className="border-t border-pb-hairline">
                    <td className="pr-3 py-1 font-mono">{p.code}</td><td className="pr-3">{p.name}</td>
                    {form.sizes.map(s => <td key={s} className="px-2 text-right font-mono">{p.sizes[s] || ''}</td>)}
                    <td className="pl-2 text-right font-mono font-semibold">{p.total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {form.names.map(b => (
          <details key={b.code + b.name} className="mt-3">
            <summary className="cursor-pointer text-[13px] text-pb-dim">Names block: {b.code} {b.name} ({b.rows.length})</summary>
            <div className="text-[12.5px] font-mono mt-1 space-y-0.5">{b.rows.map((r, i) => <div key={i}>{r.text || '—'} · {r.size} · {r.number}</div>)}</div>
          </details>
        ))}
      </section>
      {locked && (
        <section className="pb-card p-4 grid gap-3 sm:grid-cols-2">
          <Field label="Deposit paid to supplier" hint="Usually 50% when the order is placed."><TextInput type="date" value={c.deposit_paid_on || ''} onChange={e => setDate('deposit_paid_on', e.target.value)} /></Field>
          <Field label="Balance paid to supplier" hint="Before delivery."><TextInput type="date" value={c.balance_paid_on || ''} onChange={e => setDate('balance_paid_on', e.target.value)} /></Field>
        </section>
      )}
    </div>
  )
}

/* ── Receive and pack ──────────────────────────────────────────────────── */

function PackTab({ data, onChange, reload }) {
  const c = data.campaign
  const [error, setError] = useState(null)
  const [msg, setMsg] = useState(null)
  const act = async (fn, after) => { setError(null); try { const r = await fn(); if (after) after(r); reload() } catch (e) { setError(e.message) } }
  if (!['exported', 'received', 'closed'].includes(c.stage)) return <Note>Receive and pack opens once the order has gone to the supplier.</Note>
  const orders = data.orders.filter(o => o.status !== 'cancelled')
  const packed = orders.filter(o => o.packed_at).length
  return (
    <div className="space-y-3">
      {c.stage === 'exported' && (
        <section className="pb-card p-4 space-y-2">
          <p className="text-[13px] text-pb-faint">When the kit arrives, mark it received. Top-ups go into club stock in Inventory.</p>
          <Button variant="primary" onClick={() => act(() => api.twReceived(c.id), r => setMsg(`${r.to_stock} top-up units added to club stock.`))}>Kit has arrived</Button>
        </section>
      )}
      {msg && <Note toneKey="ok">{msg}</Note>}
      {c.stage !== 'exported' && (
        <div className="flex flex-wrap gap-2 items-center">
          <span className="text-[13px] text-pb-dim">{packed} of {orders.length} bags packed</span>
          <Button disabled={!packed} onClick={() => act(() => api.twArrivalEmail(c.id), r => setMsg(`Arrival email: sent ${r.emails.sent}, already sent ${r.emails.skipped}, failed ${r.emails.failed}.`))}>Email packed orders to collect</Button>
          {c.stage === 'received' && <Button variant="quiet" onClick={() => window.confirm('Finish this campaign?') && act(() => api.twComplete(c.id).then(onChange))}>Finish campaign</Button>}
        </div>
      )}
      <ErrorLine error={error} />
      {orders.map(o => (
        <div key={o.id} className="pb-card px-4 py-3" data-pack={o.reference}>
          <div className="flex flex-wrap items-center gap-2 justify-between">
            <div className="font-semibold text-pb-text">{o.contact_name} <span className="font-mono text-[11px] text-pb-faint">{o.reference}</span></div>
            <div className="flex gap-1.5">
              <Checkbox checked={!!o.packed_at} disabled={c.stage === 'exported'} onChange={v => act(() => api.twUpdateOrder(o.id, { packed: v }))}>Packed</Checkbox>
              <Checkbox checked={!!o.collected_at} disabled={c.stage === 'exported'} onChange={v => act(() => api.twUpdateOrder(o.id, { collected: v }))}>Collected</Checkbox>
            </div>
          </div>
          <ul className="text-[12.5px] text-pb-dim mt-1">
            {o.lines.filter(l => l.state === 'active').map(l => <li key={l.id}>{l.qty} × {l.product_name} ({l.size}) · {l.wearer_name}{l.number ? ` · #${l.number}` : ''}{l.text ? ` ${l.text}` : ''}</li>)}
          </ul>
        </div>
      ))}
    </div>
  )
}

function EmailsTab({ campaign }) {
  const [rows, setRows] = useState(null)
  useEffect(() => { api.twEmails(campaign.id).then(d => setRows(d.emails)).catch(() => setRows([])) }, [campaign.id])
  if (!rows) return <Empty>Loading…</Empty>
  if (!rows.length) return <Empty>No emails yet.</Empty>
  const KIND = { launch: 'Launch', launch_test: 'Launch test', order_received: 'Order received', payment_request: 'Payment request', reminder: 'Reminder', not_available: 'Not available', change_answer: 'Change answered', arrival: 'Arrival' }
  return (
    <TableWrap>
      <TableHead cols="150px 140px 1fr 90px" minWidth={600}><Cell head first>When</Cell><Cell head>Email</Cell><Cell head>To</Cell><Cell head last>Result</Cell></TableHead>
      {rows.map((r, i) => (
        <TableRow key={i} cols="150px 140px 1fr 90px" minWidth={600}>
          <Cell first>{fmtDateTime(r.created_at)}</Cell><Cell>{KIND[r.kind] || r.kind}</Cell>
          <Cell className="truncate">{r.to_email || '—'}{r.reference ? ` · ${r.reference}` : ''}</Cell>
          <Cell last><Badge toneKey={r.status === 'sent' ? 'ok' : 'block'}>{r.status}</Badge>{r.detail && <div className="text-[11px] text-pb-faint">{r.detail}</div>}</Cell>
        </TableRow>
      ))}
    </TableWrap>
  )
}

export default function TeamwearCampaign() {
  const { id } = useParams()
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState(null)
  const [range, setRange] = useState(null)
  const [error, setError] = useState(null)
  const load = useCallback(() => { api.twCampaign(id).then(setData).catch(e => setError(e.message)) }, [id])
  useEffect(() => { load() }, [load])
  useEffect(() => { api.twRange().then(d => setRange(d.products)).catch(() => setRange([])) }, [])
  const tab = TABS.some(t => t.key === params.get('tab')) ? params.get('tab') : defaultTab(data?.campaign)
  const badges = useMemo(() => {
    if (!data) return {}
    return {
      orders: data.changes.filter(r => r.status === 'open').length,
      payments: data.orders.filter(o => o.payment_requested_at && o.balance > 0 && o.status !== 'cancelled').length,
    }
  }, [data])
  if (error) return <BetterClubhouseLayout title="Teamwear"><Note toneKey="block">{error}</Note></BetterClubhouseLayout>
  if (!data) return <BetterClubhouseLayout title="Teamwear"><Empty>Loading the campaign…</Empty></BetterClubhouseLayout>
  const c = data.campaign
  return (
    <BetterClubhouseLayout title={c.name} caption={<span><Link to="/admin/teamwear" className="underline">Teamwear</Link> · {stageLabel(c)}</span>}
      tabs={<SegButtons tabs={TABS.map(t => ({ ...t, badge: badges[t.key] }))} value={tab} onChange={k => setParams({ tab: k }, { replace: true })} />}>
      <div className="max-w-[74rem]" data-campaign-tab={tab}>
        <Stepper campaign={c} />
        <div className="mb-3"><Badge toneKey={stageTone(c)}>{stageLabel(c)}</Badge></div>
        {tab === 'setup' && <SetupTab key={c.stage + c.closes_at} data={data} range={range} onChange={setData} />}
        {tab === 'orders' && <OrdersTab data={data} reload={load} />}
        {tab === 'triage' && <TriageTab campaign={c} onCampaign={load} />}
        {tab === 'payments' && <PaymentsTab data={data} reload={load} />}
        {tab === 'export' && <ExportTab data={data} onChange={setData} reload={load} />}
        {tab === 'pack' && <PackTab data={data} onChange={setData} reload={load} />}
        {tab === 'emails' && <EmailsTab campaign={c} />}
      </div>
    </BetterClubhouseLayout>
  )
}
