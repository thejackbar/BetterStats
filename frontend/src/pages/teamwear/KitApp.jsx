import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../../lib/api'

// The Kit page of the Player Dashboard (/playerdash/:token/kit): order club teamwear while an
// order round is open, buy in-stock kit, and see, change, pay for your orders.
//
// One order covers the whole family: each item names who wears it (you, anyone in your family,
// or a typed name). Nobody pays for a round until the club has confirmed which items reach the
// supplier's minimum; then the order shows the amount, the bank reference and the card buttons.

const money = (n) => `$${Number(n || 0).toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const fmtDate = (iso) => (iso ? new Date(iso.length === 10 ? `${iso}T00:00:00` : iso).toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: 'short' }) : '')
const fmtWhen = (iso) => (iso ? new Date(iso).toLocaleString('en-AU', { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' }) : '')

const PHASE = {
  editable: { label: 'Ordering open', blurb: 'You can change or cancel this order until ordering closes. Nothing is charged yet.' },
  waiting: { label: 'Being checked', blurb: 'Ordering has closed. The club is checking which items reach the supplier’s minimum, then you will get a payment request.' },
  payment: { label: 'Payment requested', blurb: 'Pay by the due date. Ask for a change below if something is wrong.' },
  locked: { label: 'With the supplier', blurb: 'Your order has gone to the supplier. You will get an email when it arrives.' },
  collected: { label: 'Collected', blurb: '' },
  cancelled: { label: 'Cancelled', blurb: '' },
}

const INPUT = 'w-full bg-pb-surface2 border pb-hairline rounded-lg px-3 py-2 text-[14px] text-pb-text outline-none focus:border-pb-accent'
const BTN = 'inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-[14px] font-semibold disabled:opacity-50'
const PRIMARY = { background: 'var(--pb-accent)', color: '#0a0d14' }

function Card({ children, className = '', ...rest }) {
  return <section className={`rounded-xl border pb-hairline p-4 mb-3 min-w-0 ${className}`} {...rest}>{children}</section>
}

function H({ children }) {
  return <h2 className="font-display font-bold text-[18px] mb-2">{children}</h2>
}

function Gallery({ images, name }) {
  const [i, setI] = useState(0)
  if (!images?.length) return <div className="w-full aspect-square rounded-lg bg-pb-surface2 flex items-center justify-center text-pb-faint text-[12px]">No picture</div>
  return (
    <div>
      <img src={images[i]} alt={name} className="w-full aspect-square object-cover rounded-lg" />
      {images.length > 1 && (
        <div className="flex gap-1 mt-1">
          {images.map((src, n) => (
            <button key={src} type="button" onClick={() => setI(n)} aria-label={`Picture ${n + 1}`}
              className={`w-2 h-2 rounded-full ${n === i ? 'bg-pb-accent' : 'bg-pb-surface2'}`} />
          ))}
        </div>
      )}
    </div>
  )
}

function newLine(product, family) {
  const me = family.find(f => f.me)
  return {
    key: Math.random().toString(36).slice(2), product_id: product.product_id, variant_id: product.sizes[0]?.variant_id || '',
    qty: 1, wearer: me ? me.player_id : 'other', wearer_name: '', number: product.personalisation !== 'none' ? (me?.shirt_number || '') : '', text: '',
  }
}

// Live check of a requested number against the club register.
function NumberCheck({ token, number, wearer, campaignId }) {
  const [res, setRes] = useState(null)
  useEffect(() => {
    if (!number) { setRes(null); return undefined }
    const t = setTimeout(() => {
      api.kitNumberCheck(token, number, wearer !== 'other' ? wearer : null, campaignId).then(setRes).catch(() => setRes(null))
    }, 350)
    return () => clearTimeout(t)
  }, [token, number, wearer, campaignId])
  if (!res?.note) return null
  return <div className="text-[12px] mt-1" data-number-note={res.status} style={{ color: res.status === 'clash' ? 'var(--pb-amber)' : 'var(--pb-faint)' }}>{res.note}{res.status === 'clash' ? ' The kit coordinator will check it with you.' : ''}</div>
}

function LineEditor({ token, line, product, family, campaignId, onChange, onRemove, showStock }) {
  const pers = product.personalisation !== 'none'
  const size = product.sizes.find(s => s.variant_id === line.variant_id)
  return (
    <div className="rounded-lg border pb-hairline p-3" data-basket-line>
      <div className="flex items-start justify-between gap-2">
        <div className="font-semibold">{product.name} <span className="text-pb-faint font-normal">{money(product.price)}</span></div>
        <button type="button" onClick={onRemove} className="text-[12px] text-pb-faint underline shrink-0">Remove</button>
      </div>
      <div className="grid gap-2 mt-2 grid-cols-2">
        <label className="block text-[12px] text-pb-faint">Size
          <select className={INPUT} value={line.variant_id} onChange={e => onChange({ variant_id: e.target.value })}>
            {product.sizes.map(s => <option key={s.variant_id} value={s.variant_id}>{s.label}{showStock ? ` (${s.available} left)` : ''}</option>)}
          </select>
        </label>
        {!pers && (
          <label className="block text-[12px] text-pb-faint">How many
            <input className={INPUT} type="number" min={1} max={showStock ? size?.available || 1 : 50} value={line.qty}
              onChange={e => onChange({ qty: e.target.value })} />
          </label>
        )}
        <label className={`block text-[12px] text-pb-faint ${pers ? '' : 'col-span-2'}`}>Who wears it
          <select className={INPUT} value={line.wearer} onChange={e => {
            const f = family.find(x => x.player_id === e.target.value)
            onChange({ wearer: e.target.value, ...(pers && f?.shirt_number && !line.number ? { number: f.shirt_number } : {}) })
          }}>
            {family.map(f => <option key={f.player_id} value={f.player_id}>{f.name}{f.me ? ' (you)' : ''}</option>)}
            <option value="other">Someone else…</option>
          </select>
        </label>
      </div>
      {line.wearer === 'other' && (
        <label className="block text-[12px] text-pb-faint mt-2">Their name
          <input className={INPUT} value={line.wearer_name} onChange={e => onChange({ wearer_name: e.target.value })} placeholder="First and last name" />
        </label>
      )}
      {pers && (
        <div className="grid gap-2 mt-2 grid-cols-[90px_1fr]">
          <label className="block text-[12px] text-pb-faint">Number
            <input className={INPUT} value={line.number} inputMode="numeric" maxLength={4} onChange={e => onChange({ number: e.target.value })} />
          </label>
          <label className="block text-[12px] text-pb-faint">{product.personalisation === 'number_initials' ? 'Initials' : 'Name on the back'}
            <input className={INPUT} value={line.text} onChange={e => onChange({ text: e.target.value.toUpperCase() })}
              placeholder={product.personalisation === 'number_initials' ? 'JS' : 'SMITH'} />
          </label>
          <div className="col-span-2"><NumberCheck token={token} number={line.number} wearer={line.wearer} campaignId={campaignId} /></div>
        </div>
      )}
    </div>
  )
}

// The order form: pick items, then who wears each. Used for a campaign and for in-stock kit.
function Basket({ token, products, family, contact, campaignId, initial, submitLabel, onSubmit, onCancel, showStock }) {
  const [lines, setLines] = useState(() => initial || [])
  const [who, setWho] = useState(() => ({ contact_name: contact?.name || '', contact_email: contact?.email || '', contact_phone: contact?.phone || '' }))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const byId = Object.fromEntries(products.map(p => [p.product_id, p]))
  const total = lines.reduce((a, l) => a + (byId[l.product_id]?.price || 0) * (byId[l.product_id]?.personalisation !== 'none' ? 1 : Number(l.qty) || 1), 0)
  const add = (p) => setLines(ls => [...ls, newLine(p, family)])
  const submit = async () => {
    setBusy(true); setError(null)
    try {
      await onSubmit({
        campaign_id: campaignId || null, ...who,
        lines: lines.map(l => ({
          product_id: l.product_id, variant_id: l.variant_id, qty: Number(l.qty) || 1,
          wearer_player_id: l.wearer !== 'other' ? l.wearer : null, wearer_name: l.wearer === 'other' ? l.wearer_name : null,
          number: l.number || null, text: l.text || null,
        })),
      })
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return (
    <div>
      <div className="grid gap-3 grid-cols-2 sm:grid-cols-3">
        {products.map(p => (
          <div key={p.product_id} className="min-w-0" data-shop-product={p.name}>
            <Gallery images={p.images} name={p.name} />
            <div className="font-semibold text-[14px] mt-1.5 leading-tight">{p.name}</div>
            <div className="text-[13px] text-pb-dim">{money(p.price)}</div>
            <div className="text-[11.5px] text-pb-faint">{p.sizes.map(s => s.label).join(', ')}</div>
            {p.personal_label && <div className="text-[11.5px] text-pb-faint">Number and {p.personal_label.toLowerCase()}</div>}
            <button type="button" className={`${BTN} mt-1.5 w-full border pb-hairline`} onClick={() => add(p)}>Add</button>
          </div>
        ))}
      </div>
      {lines.length > 0 && (
        <div className="mt-4 space-y-2" data-basket>
          <div className="font-semibold">Your order</div>
          {lines.map((l, i) => byId[l.product_id] && (
            <LineEditor key={l.key || i} token={token} line={l} product={byId[l.product_id]} family={family} campaignId={campaignId} showStock={showStock}
              onChange={patch => setLines(ls => ls.map((x, n) => (n === i ? { ...x, ...patch } : x)))}
              onRemove={() => setLines(ls => ls.filter((_, n) => n !== i))} />
          ))}
          <div className="grid gap-2 sm:grid-cols-3">
            <label className="block text-[12px] text-pb-faint">Your name<input className={INPUT} value={who.contact_name} onChange={e => setWho({ ...who, contact_name: e.target.value })} /></label>
            <label className="block text-[12px] text-pb-faint">Email<input className={INPUT} type="email" value={who.contact_email} onChange={e => setWho({ ...who, contact_email: e.target.value })} /></label>
            <label className="block text-[12px] text-pb-faint">Mobile<input className={INPUT} value={who.contact_phone} onChange={e => setWho({ ...who, contact_phone: e.target.value })} /></label>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
            <div className="text-[15px]">Total <b>{money(total)}</b>{campaignId && <span className="text-[12px] text-pb-faint"> · not charged until the club confirms</span>}</div>
            <div className="flex gap-2">
              {onCancel && <button type="button" className={`${BTN} border pb-hairline`} onClick={onCancel}>Back</button>}
              <button type="button" className={BTN} style={PRIMARY} disabled={busy} onClick={submit} data-place-order>{busy ? 'Saving…' : submitLabel}</button>
            </div>
          </div>
          {error && <div className="text-[13px]" style={{ color: 'var(--pb-red)' }} role="alert" data-kit-error>{error}</div>}
        </div>
      )}
    </div>
  )
}

function linesToBasket(order, family) {
  return order.lines.filter(l => l.state === 'active').map(l => ({
    key: l.id, product_id: l.product_id, variant_id: l.variant_id, qty: l.qty,
    wearer: l.wearer_player_id && family.some(f => f.player_id === l.wearer_player_id) ? l.wearer_player_id : 'other',
    wearer_name: l.wearer_name || '', number: l.number || '', text: l.text || '',
  }))
}

function PayBox({ token, order, bank, card, onError }) {
  const [busy, setBusy] = useState(null)
  const go = async (provider) => {
    setBusy(provider)
    try { const { url } = await api.kitPay(token, order.id, provider); window.location.assign(url) } catch (e) { onError(e.message); setBusy(null) }
  }
  return (
    <div className="rounded-lg p-3 mt-2" style={{ background: 'var(--pb-surface2)' }} data-pay-box>
      <div className="flex items-baseline justify-between">
        <span className="text-[14px]">To pay{order.due_on ? ` by ${fmtDate(order.due_on)}` : ''}</span>
        <span className="font-display font-bold text-[20px]" style={{ color: 'var(--pb-amber)' }}>{money(order.balance)}</span>
      </div>
      {bank && (
        <div className="text-[13px] mt-2 leading-relaxed">
          Bank transfer to {bank.account_name}<br />BSB {bank.bsb} · Account {bank.account_number}<br />
          Reference <b className="font-mono" data-pay-reference>{order.reference}</b>
        </div>
      )}
      {(card?.stripe || card?.square) && (
        <div className="flex flex-wrap gap-2 mt-3">
          {card.stripe && <button type="button" className={BTN} style={PRIMARY} disabled={!!busy} onClick={() => go('stripe')}>{busy === 'stripe' ? 'Opening…' : 'Pay by card'}</button>}
          {card.square && <button type="button" className={`${BTN} border pb-hairline`} disabled={!!busy} onClick={() => go('square')}>{busy === 'square' ? 'Opening…' : card.stripe ? 'Pay by card (Square)' : 'Pay by card'}</button>}
        </div>
      )}
      {!bank && !card?.stripe && !card?.square && <div className="text-[13px] text-pb-faint mt-2">Ask the kit coordinator how to pay.</div>}
    </div>
  )
}

function OrderCard({ token, order, kit, onEdit, reload }) {
  const [asking, setAsking] = useState(false)
  const [msg, setMsg] = useState('')
  const [error, setError] = useState(null)
  const [note, setNote] = useState(null)
  const phase = PHASE[order.phase] || { label: order.phase }
  const act = async (fn, after) => { setError(null); try { await fn(); if (after) after(); reload() } catch (e) { setError(e.message) } }
  const cut = order.lines.some(l => l.state === 'cut')
  return (
    <Card data-my-order={order.reference}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-semibold">{order.campaign_name || 'Shop order'}</div>
          <div className="text-[12px] text-pb-faint">{order.reference} · placed {fmtDate(order.created_at)}</div>
        </div>
        <span className="text-[11px] font-mono uppercase tracking-wide2 rounded px-1.5 py-0.5 shrink-0" style={{ background: 'var(--pb-surface2)', color: 'var(--pb-faint)' }} data-phase={order.phase}>{phase.label}</span>
      </div>
      {phase.blurb && <p className="text-[12.5px] text-pb-faint mt-1.5">{phase.blurb}</p>}
      {order.cancelled_reason && <p className="text-[12.5px] text-pb-faint mt-1">{order.cancelled_reason}.</p>}
      <ul className="mt-2 space-y-1 text-[13.5px]">
        {order.lines.filter(l => l.state === 'active' || l.state === 'cut').map(l => (
          <li key={l.id} className={`flex justify-between gap-2 ${l.state === 'cut' ? 'text-pb-faint' : ''}`} data-line-state={l.state}>
            <span className="min-w-0">{l.qty} × {l.product_name} ({l.size}) · {l.wearer_name}{l.number ? ` · #${l.number}` : ''}{l.text ? ` ${l.text}` : ''}
              {l.state === 'cut' && <span className="block text-[12px]" style={{ color: 'var(--pb-amber)' }}>Not available this round</span>}
              {l.club_covered && <span className="block text-[12px] text-pb-faint">Covered by the club</span>}
            </span>
            <span className="font-mono shrink-0">{l.state === 'cut' ? '—' : money(l.charge)}</span>
          </li>
        ))}
      </ul>
      {cut && <p className="text-[12px] text-pb-faint mt-1">Items that did not reach the supplier’s minimum are not made this round and not charged.</p>}
      <div className="flex justify-between text-[14px] mt-2 pt-2 border-t pb-hairline"><span>Total</span><b>{money(order.total)}</b></div>
      {order.paid > 0 && <div className="flex justify-between text-[13px] text-pb-dim"><span>Paid</span><span>{money(order.paid)}</span></div>}
      {order.payment_requested_at && order.balance > 0 && order.status !== 'cancelled' && <PayBox token={token} order={order} bank={kit.bank} card={kit.card} onError={setError} />}
      {order.payment_requested_at && order.balance <= 0 && order.status !== 'cancelled' && <div className="text-[13px] mt-2" style={{ color: 'var(--pb-positive)' }}>Paid in full. Thanks.</div>}
      {(order.changes || []).map(r => (
        <div key={r.id} className="text-[12.5px] text-pb-dim mt-2 rounded-lg p-2" style={{ background: 'var(--pb-surface2)' }}>
          You asked: <i>{r.message}</i> · {r.status === 'open' ? 'waiting for the club' : r.status === 'done' ? 'done' : 'not possible'}{r.response ? `: ${r.response}` : ''}
        </div>
      ))}
      <div className="flex flex-wrap gap-2 mt-3">
        {order.phase === 'editable' && <>
          <button type="button" className={`${BTN} border pb-hairline`} onClick={() => onEdit(order)}>Change order</button>
          <button type="button" className={`${BTN} text-pb-faint`} onClick={() => window.confirm('Cancel this order?') && act(() => api.kitCancel(token, order.id))}>Cancel order</button>
        </>}
        {['waiting', 'payment'].includes(order.phase) && !asking && order.campaign_id && (
          <button type="button" className={`${BTN} border pb-hairline`} onClick={() => setAsking(true)}>Ask for a change</button>
        )}
      </div>
      {asking && (
        <div className="mt-2">
          <textarea className={INPUT} rows={3} value={msg} onChange={e => setMsg(e.target.value)} placeholder="For example: change Kim's shirt from S to M" />
          <div className="flex gap-2 mt-2">
            <button type="button" className={BTN} style={PRIMARY} disabled={!msg.trim()} onClick={() => act(() => api.kitChange(token, order.id, msg), () => { setAsking(false); setMsg(''); setNote('Sent. The kit coordinator will email you.') })}>Send</button>
            <button type="button" className={`${BTN} border pb-hairline`} onClick={() => setAsking(false)}>Back</button>
          </div>
        </div>
      )}
      {note && <div className="text-[13px] mt-2" style={{ color: 'var(--pb-positive)' }}>{note}</div>}
      {error && <div className="text-[13px] mt-2" style={{ color: 'var(--pb-red)' }} role="alert">{error}</div>}
    </Card>
  )
}

export default function KitApp({ token, club }) {
  const location = useLocation()
  const [kit, setKit] = useState(null)
  const [error, setError] = useState(null)
  const [editing, setEditing] = useState(null) // order being changed
  const [flash, setFlash] = useState(null)
  const firstQuery = useRef(location.search)
  const load = useCallback((query = '') => {
    return api.kitGet(token, query).then(setKit).catch(e => setError(e.message))
  }, [token])
  useEffect(() => {
    const q = firstQuery.current
    const p = new URLSearchParams(q)
    if (p.get('paid')) setFlash('Thanks. Your card payment is being confirmed and will show here shortly.')
    load(p.get('paid') === 'square' ? q : '')
  }, [load])
  if (error) return <div className="max-w-2xl mx-auto px-4 py-10 text-center text-pb-faint" data-kit-dead>{error}</div>
  if (!kit) return <div className="py-24 text-center text-pb-faint text-sm">Loading…</div>
  const back = `/playerdash/${token}`
  const placed = (verb) => { setEditing(null); setFlash(verb); load(); window.scrollTo({ top: 0, behavior: 'smooth' }) }
  const editingCampaign = editing && kit.campaigns.find(c => c.id === editing.campaign_id)
  return (
    <div className="max-w-3xl mx-auto px-4 py-6" data-kit-page>
      <a href={back} className="inline-flex items-center gap-1.5 mb-3 text-[13px] font-semibold text-pb-dim hover:text-pb-text"><span aria-hidden="true">←</span> Back to your page</a>
      <h1 className="font-display font-bold text-[24px] mb-1">Teamwear</h1>
      <p className="text-[13px] text-pb-faint mb-4">{club?.name}{kit.coordinator?.name ? ` · questions to ${kit.coordinator.name}${kit.coordinator.email ? ` (${kit.coordinator.email})` : ''}` : ''}</p>
      {flash && <div role="status" className="rounded-lg px-3.5 py-2.5 mb-3 text-sm" style={{ background: 'color-mix(in srgb, var(--pb-positive) 12%, transparent)', color: 'var(--pb-positive)' }}>{flash}</div>}

      {editing && editingCampaign ? (
        <Card>
          <H>Change your order</H>
          <Basket token={token} products={editingCampaign.products} family={kit.family} contact={{ name: editing.contact_name, email: editing.contact_email, phone: editing.contact_phone }}
            campaignId={editing.campaign_id} initial={linesToBasket(editing, kit.family)} submitLabel="Save changes"
            onCancel={() => setEditing(null)}
            onSubmit={async (body) => { await api.kitEdit(token, editing.id, body); placed('Your order is updated.') }} />
        </Card>
      ) : (
        <>
          {kit.campaigns.map(c => (
            <Card key={c.id} data-campaign={c.name}>
              <H>{c.name}</H>
              {c.intro && <p className="text-[13.5px] text-pb-dim whitespace-pre-line mb-2">{c.intro}</p>}
              <p className="text-[13px] mb-3" style={{ color: 'var(--pb-amber)' }}>Order by {fmtWhen(c.closes_at)}. Nothing is charged until the club confirms which items are being made.</p>
              <Basket token={token} products={c.products} family={kit.family} contact={kit.contact} campaignId={c.id}
                submitLabel="Place order" onSubmit={async (body) => { await api.kitPlace(token, body); placed('Your order is in. We have emailed you a copy.') }} />
            </Card>
          ))}
          {kit.stock.length > 0 && (
            <Card data-stock>
              <H>In stock now</H>
              <p className="text-[13px] text-pb-faint mb-3">Club kit on the shelf. Pay when you order and collect from the kit coordinator.</p>
              <Basket token={token} products={kit.stock} family={kit.family} contact={kit.contact} campaignId={null} showStock
                submitLabel="Order and pay" onSubmit={async (body) => { await api.kitPlace(token, body); placed('Your order is in. Pay below to finish.') }} />
            </Card>
          )}
          {kit.campaigns.length === 0 && kit.stock.length === 0 && (
            <Card><p className="text-[14px] text-pb-dim">No order round is open right now. The club will email you when the next one opens.</p></Card>
          )}
        </>
      )}

      {!editing && kit.orders.length > 0 && (
        <div className="mt-5" data-my-orders>
          <H>Your orders</H>
          {kit.orders.map(o => <OrderCard key={o.id} token={token} order={o} kit={kit} onEdit={setEditing} reload={() => load()} />)}
        </div>
      )}
    </div>
  )
}
