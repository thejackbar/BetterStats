import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../../../lib/api'
import BetterClubhouseLayout from '../../../components/admin/BetterClubhouseLayout'
import {
  Badge, Button, Cell, Checkbox, Empty, Field, Modal, Note, SegButtons, Select, TableHead, TableRow, TableWrap,
  TextArea, TextInput,
} from '../../../components/admin/ui'
import { fmtDate, fmtDateTime, money, OrderForm, PERSONALISATION, PHASE_LABEL, stageLabel, stageTone } from './shared'

// Teamwear: the club's kit ordering. Campaigns (each order round), the shop range they draw on,
// orders of in-stock kit from the shop, and the settings (price rule, bank details, reminders).

const TABS = [
  { key: 'campaigns', label: 'Campaigns' },
  { key: 'range', label: 'Shop range' },
  { key: 'shop', label: 'Shop orders' },
  { key: 'settings', label: 'Settings' },
]

/* ── Campaigns ─────────────────────────────────────────────────────────── */

function NewCampaign({ range, onClose, onCreated }) {
  const mto = range.filter(p => p.made_to_order && p.active)
  const [name, setName] = useState('')
  const [picked, setPicked] = useState(() => mto.filter(p => p.in_shop && p.price != null).map(p => p.product_id))
  const [closes, setCloses] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const toggle = (id) => setPicked(ps => (ps.includes(id) ? ps.filter(x => x !== id) : [...ps, id]))
  const save = async () => {
    setBusy(true); setError(null)
    try {
      const d = await api.twCreateCampaign({ name, product_ids: picked, closes_at: closes || null })
      onCreated(d.campaign.id)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return (
    <Modal title="New campaign" subtitle="One order round. Pick the made-to-order items members can order and when ordering closes."
      onClose={onClose} width={520}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={busy || !name.trim()} onClick={save}>Create campaign</Button></>}>
      <div className="space-y-3 pb-3">
        <Field label="Name"><TextInput value={name} onChange={e => setName(e.target.value)} placeholder="Summer 2026/27 teamwear" /></Field>
        <Field label="Ordering closes" hint="You can change this before launching."><TextInput type="date" value={closes} onChange={e => setCloses(e.target.value)} style={{ width: 200 }} /></Field>
        <Field label="Items" composite>
          {mto.length === 0 ? (
            <div className="text-[13px] text-pb-faint">No made-to-order items in the shop range yet. Add them under Shop range first.</div>
          ) : (
            <div className="space-y-1.5">
              {mto.map(p => (
                <Checkbox key={p.product_id} checked={picked.includes(p.product_id)} onChange={() => toggle(p.product_id)}
                  disabled={p.price == null} hint={p.price == null ? 'Set an RRP or price first.' : null}>
                  {p.name}{p.supplier_code ? ` (${p.supplier_code})` : ''} · {p.price != null ? money(p.price) : 'no price'}
                </Checkbox>
              ))}
            </div>
          )}
        </Field>
        {error && <div className="text-[13px] text-pb-red" role="alert">{error}</div>}
      </div>
    </Modal>
  )
}

function CampaignsTab({ range, onRangeNeeded }) {
  const navigate = useNavigate()
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)
  const [adding, setAdding] = useState(false)
  useEffect(() => {
    api.twCampaigns().then(d => setRows(d.campaigns || [])).catch(e => setError(e.message))
  }, [])
  if (error) return <Note toneKey="block">{error}</Note>
  if (!rows) return <Empty>Loading campaigns…</Empty>
  const cols = 'minmax(180px,1.6fr) 150px 120px 90px 90px'
  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button variant="primary" onClick={() => { onRangeNeeded(); setAdding(true) }}>New campaign</Button>
      </div>
      {rows.length === 0 ? (
        <Empty>No order rounds yet. Set up the shop range, then start a campaign.</Empty>
      ) : (
        <>
          <TableWrap className="hidden md:block">
            <TableHead cols={cols} minWidth={640}>
              <Cell head first>Campaign</Cell><Cell head>Stage</Cell><Cell head>Closes</Cell><Cell head num>Orders</Cell><Cell head num last>Units</Cell>
            </TableHead>
            {rows.map(c => (
              <TableRow key={c.id} cols={cols} minWidth={640} onClick={() => navigate(`/admin/teamwear/campaigns/${c.id}`)}>
                <Cell first><span className="font-semibold text-pb-text">{c.name}</span></Cell>
                <Cell><Badge toneKey={stageTone(c)}>{stageLabel(c)}</Badge></Cell>
                <Cell>{fmtDate(c.closes_at)}</Cell>
                <Cell num>{c.orders}</Cell>
                <Cell num last>{c.units}</Cell>
              </TableRow>
            ))}
          </TableWrap>
          <div className="md:hidden space-y-2">
            {rows.map(c => (
              <Link key={c.id} to={`/admin/teamwear/campaigns/${c.id}`} className="block pb-card px-4 py-3 no-underline">
                <div className="flex items-start justify-between gap-2">
                  <span className="font-semibold text-pb-text min-w-0">{c.name}</span>
                  <Badge toneKey={stageTone(c)}>{stageLabel(c)}</Badge>
                </div>
                <div className="text-[12px] text-pb-faint mt-1">{c.orders} orders · {c.units} units{c.closes_at ? ` · closes ${fmtDate(c.closes_at)}` : ''}</div>
              </Link>
            ))}
          </div>
        </>
      )}
      {adding && range && <NewCampaign range={range} onClose={() => setAdding(false)}
        onCreated={(id) => navigate(`/admin/teamwear/campaigns/${id}`)} />}
    </div>
  )
}

/* ── Shop range ────────────────────────────────────────────────────────── */

function ProductEditor({ product, settings, onClose, onSaved }) {
  const isNew = !product
  const [f, setF] = useState(() => ({
    name: product?.name || '', description: product?.description || '', supplier_code: product?.supplier_code || '',
    rrp: product?.rrp ?? '', price_override: product?.price_override ?? '', made_to_order: product ? product.made_to_order : true,
    personalisation: product?.personalisation || 'none', moq: product?.moq ?? '', in_shop: product ? product.in_shop : true,
    active: product ? product.active : true, sizes: (product?.sizes || []).map(s => s.label).join(', '),
  }))
  const baseline = useRef(f)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const set = (k, v) => setF(x => ({ ...x, [k]: v }))
  // The price the shop will show, by the club rule (the server is the real calculator).
  const preview = (() => {
    if (f.price_override !== '' && f.price_override != null) return Number(f.price_override)
    if (f.rrp === '' || f.rrp == null) return null
    const raw = Number(f.rrp) * (1 + Number(settings?.markup_pct || 0) / 100)
    const step = Number(settings?.round_to || 0)
    return step > 0 ? Math.ceil(Math.round(raw / step * 1e6) / 1e6) * step : Math.ceil(raw * 100) / 100
  })()
  const save = async () => {
    setBusy(true); setError(null)
    try {
      // Only what changed goes to the server (an absent key leaves a field alone).
      const patch = {}
      for (const k of Object.keys(f)) if (isNew || f[k] !== baseline.current[k]) patch[k] = f[k]
      for (const k of ['rrp', 'price_override', 'moq']) if (k in patch && patch[k] === '') patch[k] = null
      const d = isNew ? await api.twCreateProduct(patch) : await api.twUpdateProduct(product.product_id, patch)
      onSaved(d.product)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return (
    <Modal title={isNew ? 'Add a shop item' : `Edit ${product.name}`} onClose={onClose} width={560}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={busy || !f.name.trim()} onClick={save}>Save</Button></>}>
      <div className="space-y-3 pb-3">
        <Field label="Name"><TextInput value={f.name} onChange={e => set('name', e.target.value)} placeholder="Playing shirt" /></Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Supplier product code"><TextInput value={f.supplier_code} onChange={e => set('supplier_code', e.target.value)} placeholder="e.g. MS101" /></Field>
          <Field label="Sizes" hint="In the order they should list, separated by commas."><TextInput value={f.sizes} onChange={e => set('sizes', e.target.value)} placeholder="S, M, L, XL, 2XL" /></Field>
          <Field label="RRP inc GST"><TextInput type="number" step="0.01" min="0" value={f.rrp} onChange={e => set('rrp', e.target.value)} /></Field>
          <Field label="Price override" hint="Leave empty to use the club rule."><TextInput type="number" step="0.01" min="0" value={f.price_override} onChange={e => set('price_override', e.target.value)} /></Field>
          <Field label="Personalisation">
            <Select value={f.personalisation} onChange={e => set('personalisation', e.target.value)}>
              {PERSONALISATION.map(p => <option key={p.key} value={p.key}>{p.label}</option>)}
            </Select>
          </Field>
          <Field label="Supplier minimum" hint={`Empty uses the club default (${settings?.default_moq ?? 10}).`}><TextInput type="number" min="0" value={f.moq} onChange={e => set('moq', e.target.value)} /></Field>
        </div>
        <Field label="Description"><TextArea value={f.description} onChange={e => set('description', e.target.value)} /></Field>
        <div className="space-y-1.5">
          <Checkbox checked={f.made_to_order} onChange={v => set('made_to_order', v)} hint="Made-to-order items are only offered inside a campaign. In-stock items can be bought from the shop any time.">Made to order</Checkbox>
          <Checkbox checked={f.in_shop} onChange={v => set('in_shop', v)}>Show in the shop</Checkbox>
          {!isNew && <Checkbox checked={f.active} onChange={v => set('active', v)}>Active</Checkbox>}
        </div>
        <Note>Members see {preview != null ? <b>{money(preview)}</b> : 'no price yet'}{f.price_override === '' && f.rrp !== '' ? ` (RRP plus ${settings?.markup_pct ?? 10}%, rounded up)` : ''}.</Note>
        {error && <div className="text-[13px] text-pb-red" role="alert">{error}</div>}
      </div>
    </Modal>
  )
}

function ImageStrip({ product, onChange }) {
  const input = useRef(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const upload = async (file) => {
    if (!file) return
    setBusy(true); setError(null)
    try { onChange((await api.twUploadImage(product.product_id, file)).product) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const remove = async (imageId) => {
    try { await api.twDeleteImage(imageId); onChange({ ...product, images: product.images.filter((_, i) => product.image_ids[i] !== imageId), image_ids: product.image_ids.filter(x => x !== imageId) }) } catch (e) { setError(e.message) }
  }
  return (
    <div className="flex flex-wrap items-center gap-2 mt-2">
      {product.images.map((src, i) => (
        <div key={src} className="relative">
          <img src={src} alt="" className="w-14 h-14 object-cover rounded-md border border-pb-hairline" />
          <button type="button" aria-label="Remove picture" onClick={() => remove(product.image_ids[i])}
            className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-pb-surface border border-pb-hairline2 text-[10px] text-pb-faint hover:text-pb-red">✕</button>
        </div>
      ))}
      {product.images.length < 6 && (
        <Button size="sm" disabled={busy} onClick={() => input.current?.click()}>{busy ? 'Uploading…' : 'Add picture'}</Button>
      )}
      <input ref={input} type="file" accept="image/png,image/jpeg,image/webp,image/gif" className="hidden"
        onChange={e => { upload(e.target.files?.[0]); e.target.value = '' }} />
      {error && <span className="text-[12px] text-pb-red">{error}</span>}
    </div>
  )
}

function RangeTab({ data, reload, setData }) {
  const [editing, setEditing] = useState(null) // product, or 'new'
  const [linking, setLinking] = useState('')
  const [error, setError] = useState(null)
  if (!data) return <Empty>Loading the shop range…</Empty>
  const replace = (p) => setData(d => ({ ...d, products: d.products.some(x => x.product_id === p.product_id) ? d.products.map(x => (x.product_id === p.product_id ? p : x)) : [...d.products, p] }))
  const link = async () => {
    if (!linking) return
    try { replace((await api.twLinkProduct(linking)).product); setLinking(''); reload() } catch (e) { setError(e.message) }
  }
  const unlink = async (p) => {
    if (!window.confirm(`Take ${p.name} out of the shop? The stock record stays.`)) return
    try { await api.twUnlinkProduct(p.product_id); reload() } catch (e) { setError(e.message) }
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <p className="text-[13px] text-pb-faint max-w-xl">
          The range members order from. Made-to-order items go into a campaign; in-stock items sell from the shop any time
          from club stock. Price is the RRP plus {data.settings?.markup_pct}% rounded up to the next ${Number(data.settings?.round_to || 1).toFixed(2)}, unless you set one.
        </p>
        <Button variant="primary" onClick={() => setEditing('new')}>Add item</Button>
      </div>
      {error && <Note toneKey="block">{error}</Note>}
      {data.products.length === 0 ? <Empty>No items in the shop yet.</Empty> : (
        <div className="grid gap-2 lg:grid-cols-2">
          {data.products.map(p => (
            <div key={p.product_id} className="pb-card px-4 py-3" data-range-item>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-semibold text-pb-text">{p.name} {p.supplier_code && <span className="font-mono text-[11px] text-pb-faint">{p.supplier_code}</span>}</div>
                  <div className="text-[12px] text-pb-faint mt-0.5">
                    {p.made_to_order ? 'Made to order' : `In stock: ${p.in_stock}`} · {p.sizes.map(s => s.label).join(', ') || 'no sizes'}
                    {p.personalisation !== 'none' && ` · ${PERSONALISATION.find(x => x.key === p.personalisation)?.label}`}
                    {!p.in_shop && ' · hidden'}{!p.active && ' · inactive'}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className="font-display font-bold text-pb-text">{p.price != null ? money(p.price) : '—'}</div>
                  {p.rrp != null && <div className="text-[11px] text-pb-faint">RRP {money(p.rrp)}</div>}
                </div>
              </div>
              <ImageStrip product={p} onChange={replace} />
              <div className="flex gap-1 mt-2">
                <Button size="sm" icon="edit" onClick={() => setEditing(p)}>Edit</Button>
                <Button size="sm" variant="quiet-danger" onClick={() => unlink(p)}>Remove from shop</Button>
              </div>
            </div>
          ))}
        </div>
      )}
      {data.available_products?.length > 0 && (
        <div className="pb-card px-4 py-3">
          <div className="text-[13px] text-pb-dim mb-2">Sell something already in the stock register through the shop:</div>
          <div className="flex flex-wrap gap-2 items-center">
            <Select value={linking} onChange={e => setLinking(e.target.value)} style={{ width: 280, maxWidth: '100%' }} aria-label="Stock item">
              <option value="">Pick a stock item…</option>
              {data.available_products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
            <Button disabled={!linking} onClick={link}>Add to shop</Button>
          </div>
        </div>
      )}
      {editing && (
        <ProductEditor product={editing === 'new' ? null : editing} settings={data.settings} onClose={() => setEditing(null)}
          onSaved={(p) => { replace(p); setEditing(null) }} />
      )}
    </div>
  )
}

/* ── Shop orders (in-stock kit) ────────────────────────────────────────── */

function ShopOrdersTab({ range }) {
  const [orders, setOrders] = useState(null)
  const [error, setError] = useState(null)
  const [adding, setAdding] = useState(false)
  const load = useCallback(() => { api.twStockOrders().then(d => setOrders(d.orders || [])).catch(e => setError(e.message)) }, [])
  useEffect(() => { load() }, [load])
  const stock = (range || []).filter(p => !p.made_to_order && p.in_shop && p.price != null && p.in_stock > 0)
  const act = async (fn) => { try { await fn(); load() } catch (e) { setError(e.message) } }
  if (!orders) return <Empty>{error || 'Loading shop orders…'}</Empty>
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[13px] text-pb-faint max-w-xl">Orders of in-stock kit. Each is asked to pay when it is placed; handing it over takes it out of club stock as a sale.</p>
        <Button variant="primary" disabled={!stock.length} onClick={() => setAdding(true)}>Add shop order</Button>
      </div>
      {error && <Note toneKey="block">{error}</Note>}
      {orders.length === 0 ? <Empty>No shop orders yet.</Empty> : orders.map(o => (
        <div key={o.id} className="pb-card px-4 py-3" data-shop-order>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="font-semibold text-pb-text">{o.contact_name} <span className="font-mono text-[11px] text-pb-faint">{o.reference}</span></div>
              <div className="text-[12px] text-pb-faint">{fmtDateTime(o.created_at)} · {PHASE_LABEL[o.phase] || o.phase}</div>
            </div>
            <div className="text-right shrink-0">
              <div className="font-display font-bold text-pb-text">{money(o.total)}</div>
              {o.balance > 0 ? <Badge toneKey={o.overdue ? 'block' : 'warn'}>{money(o.balance)} owing</Badge> : <Badge toneKey="ok">Paid</Badge>}
            </div>
          </div>
          <ul className="mt-2 text-[12.5px] text-pb-dim">
            {o.lines.filter(l => l.state === 'active').map(l => <li key={l.id}>{l.qty} × {l.product_name} ({l.size}) · {l.wearer_name}</li>)}
          </ul>
          {o.status !== 'cancelled' && !o.collected_at && (
            <div className="flex flex-wrap gap-1 mt-2">
              {o.balance > 0 && <Button size="sm" onClick={() => act(() => api.twAddPayment(o.id, { amount: o.balance, method: 'cash' }))}>Record {money(o.balance)} paid</Button>}
              <Button size="sm" onClick={() => act(() => api.twUpdateOrder(o.id, { collected: true }))}>Handed over</Button>
              <Button size="sm" variant="quiet-danger" onClick={() => window.confirm('Cancel this order?') && act(() => api.twUpdateOrder(o.id, { cancel: true }))}>Cancel</Button>
            </div>
          )}
        </div>
      ))}
      {adding && <OrderForm title="Shop order" products={stock.map(p => ({ ...p, sizes: p.sizes.filter(s => s.available > 0) }))}
        onClose={() => setAdding(false)} onSubmit={async (body) => { await api.twAddStockOrder(body); load() }} />}
    </div>
  )
}

/* ── Settings ──────────────────────────────────────────────────────────── */

function SettingsTab() {
  const [data, setData] = useState(null)
  const [f, setF] = useState(null)
  const base = useRef(null)
  const [msg, setMsg] = useState(null)
  useEffect(() => {
    api.twSettings().then(d => {
      const s = { ...d.settings, reminder_offsets: (d.settings.reminder_offsets || []).join(', ') }
      setData(d); setF(s); base.current = s
    }).catch(e => setMsg({ tone: 'block', text: e.message }))
  }, [])
  if (!f) return <Empty>{msg?.text || 'Loading settings…'}</Empty>
  const set = (k, v) => setF(x => ({ ...x, [k]: v }))
  const dirty = Object.keys(f).filter(k => f[k] !== base.current[k])
  const save = async () => {
    const patch = {}
    dirty.forEach(k => { patch[k] = f[k] })
    try {
      const d = await api.twSaveSettings(patch)
      const s = { ...d.settings, reminder_offsets: (d.settings.reminder_offsets || []).join(', ') }
      setF(s); base.current = s; setMsg({ tone: 'ok', text: 'Saved.' })
    } catch (e) { setMsg({ tone: 'block', text: e.message }) }
  }
  const card = data.card || {}
  return (
    <div className="max-w-3xl space-y-4">
      <section className="pb-card p-4 space-y-3">
        <h3 className="font-display font-bold text-pb-text">Price and minimums</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Markup on RRP (%)"><TextInput type="number" min="0" step="0.5" value={f.markup_pct} onChange={e => set('markup_pct', e.target.value)} /></Field>
          <Field label="Round prices up to the next ($)" hint="1 rounds to the dollar, 0.5 to the next 50 cents."><TextInput type="number" min="0" step="0.05" value={f.round_to} onChange={e => set('round_to', e.target.value)} /></Field>
          <Field label="Supplier minimum per product" hint="Sizes combined."><TextInput type="number" min="0" value={f.default_moq} onChange={e => set('default_moq', e.target.value)} /></Field>
          <Field label="Suggest a cut at 1 member unit to this many top-ups"><TextInput type="number" min="1" value={f.cut_ratio} onChange={e => set('cut_ratio', e.target.value)} /></Field>
          <Field label="Supplier"><TextInput value={f.supplier_name || ''} onChange={e => set('supplier_name', e.target.value)} /></Field>
        </div>
      </section>
      <section className="pb-card p-4 space-y-3">
        <h3 className="font-display font-bold text-pb-text">Paying</h3>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Account name"><TextInput value={f.bank_account_name || ''} onChange={e => set('bank_account_name', e.target.value)} /></Field>
          <Field label="BSB"><TextInput value={f.bank_bsb || ''} onChange={e => set('bank_bsb', e.target.value)} /></Field>
          <Field label="Account number"><TextInput value={f.bank_account_number || ''} onChange={e => set('bank_account_number', e.target.value)} /></Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Reference ends with" hint="Members pay with SURNAME then this."><TextInput value={f.reference_suffix} onChange={e => set('reference_suffix', e.target.value.toUpperCase())} /></Field>
          <Field label="Days to pay" hint="When a campaign sets no due date."><TextInput type="number" min="1" value={f.pay_days} onChange={e => set('pay_days', e.target.value)} /></Field>
          <Field label="Reminders (days from due)" hint="-3, 0, 3 is three days before, on the day and three days after."><TextInput value={f.reminder_offsets} onChange={e => set('reminder_offsets', e.target.value)} /></Field>
        </div>
        <div className="space-y-1.5">
          <Checkbox checked={f.card_stripe} onChange={v => set('card_stripe', v)}
            hint={card.stripe ? 'Stripe is connected and taking payments.' : 'Connect Stripe on the Integrations screen to take card payments.'}>Take card payments through Stripe</Checkbox>
          <Checkbox checked={f.card_square} onChange={v => set('card_square', v)}
            hint={card.square ? 'Square is connected and can take payments.' : card.square_needs_reconnect ? 'Square was connected before payments were added. Reconnect it under Stock > Square to take card payments.' : 'Connect Square to take card payments through a Square payment link.'}>Take card payments through Square</Checkbox>
        </div>
        <Note>Unpaid orders are never cancelled automatically. Reminders go on the days above; after that the coordinator decides each one.</Note>
      </section>
      <section className="pb-card p-4 space-y-3">
        <h3 className="font-display font-bold text-pb-text">Kit coordinator</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name"><TextInput value={f.coordinator_name || ''} onChange={e => set('coordinator_name', e.target.value)} /></Field>
          <Field label="Email"><TextInput type="email" value={f.coordinator_email || ''} onChange={e => set('coordinator_email', e.target.value)} /></Field>
        </div>
        {data.dashboard_link && <div className="text-[12.5px] text-pb-faint">Members order at <span className="font-mono break-all">{data.dashboard_link}</span>. The Teamwear card shows on the Player Dashboard while the PIN is on.</div>}
      </section>
      <div className="flex items-center gap-3">
        <Button variant="primary" disabled={!dirty.length} onClick={save}>Save settings</Button>
        {msg && <span className="text-[13px]" style={{ color: msg.tone === 'ok' ? 'var(--pb-positive)' : 'var(--pb-red)' }}>{msg.text}</span>}
      </div>
    </div>
  )
}

export default function TeamwearHome() {
  const [params, setParams] = useSearchParams()
  const tab = TABS.some(t => t.key === params.get('tab')) ? params.get('tab') : 'campaigns'
  const [range, setRange] = useState(null)
  const [rangeError, setRangeError] = useState(null)
  const loadRange = useCallback(() => {
    api.twRange().then(setRange).catch(e => setRangeError(e.message))
  }, [])
  useEffect(() => { loadRange() }, [loadRange])
  return (
    <BetterClubhouseLayout title="Teamwear" caption="Order rounds, the shop range and kit sales"
      tabs={<SegButtons tabs={TABS} value={tab} onChange={k => setParams({ tab: k }, { replace: true })} />}>
      <div className="max-w-[74rem]" data-teamwear-tab={tab}>
        {rangeError && <Note toneKey="block" className="mb-3">{rangeError}</Note>}
        {tab === 'campaigns' && <CampaignsTab range={range?.products} onRangeNeeded={() => !range && loadRange()} />}
        {tab === 'range' && <RangeTab data={range} reload={loadRange} setData={setRange} />}
        {tab === 'shop' && <ShopOrdersTab range={range?.products} />}
        {tab === 'settings' && <SettingsTab />}
      </div>
    </BetterClubhouseLayout>
  )
}
