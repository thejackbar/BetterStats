import { useState, useEffect, useCallback, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import BetterMerchLayout from '../../../components/admin/BetterMerchLayout'
import { PbSpinner } from '../../../lib/presskit'
import {
  money, CATEGORIES, categoryLabel, MOVEMENT_KINDS, kindLabel,
  Btn, Field, TextInput, NumberInput, Select, TextArea, Modal, Pill, Icon,
} from './ui'

// A labelled cell in the variant editor — the label only renders on the first
// row but always reserves height so the rows line up.
function VField({ label, w = '', children }) {
  return (
    <div className={w}>
      <span className="block text-[10.5px] text-pb-faint mb-1">{label || ' '}</span>
      {children}
    </div>
  )
}

// ── Player typeahead (for the 'issued to' field) ─────────────────────────────
function PlayerPicker({ value, valueName, onPick }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [results, setResults] = useState([])
  const timer = useRef(null)
  useEffect(() => {
    if (!q) { setResults([]); return }
    clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      api.merchSearchPlayers(q).then((d) => setResults(d.players || [])).catch(() => setResults([]))
    }, 200)
    return () => clearTimeout(timer.current)
  }, [q])
  if (value) {
    return (
      <div className="flex items-center gap-2">
        <Pill tone="accent">{valueName}</Pill>
        <button className="text-pb-faint hover:text-pb-red text-xs" onClick={() => onPick(null, null)}>clear</button>
      </div>
    )
  }
  return (
    <div className="relative">
      <TextInput placeholder="Search players…" value={q}
        onChange={(e) => { setQ(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)} />
      {open && results.length > 0 && (
        <div className="absolute z-10 mt-1 w-full bg-pb-surface border border-pb-hairline2 rounded-lg max-h-48 overflow-y-auto shadow-lg">
          {results.map((p) => (
            <button key={p.id} className="block w-full text-left px-3 py-1.5 text-[13px] hover:bg-pb-surface2"
              onClick={() => { onPick(p.id, p.name); setOpen(false); setQ('') }}>{p.name}</button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Record a stock movement (in / out / stocktake / adjustment) ──────────────
function MovementModal({ variant, product, dir, onClose, onSaved }) {
  const toast = useToast()
  // Club-use items (no sell price) can't be sold or issued for money.
  const meta = product.for_resale ? MOVEMENT_KINDS : MOVEMENT_KINDS.filter((m) => !m.money)
  const [kind, setKind] = useState(dir === 'out' ? (product.for_resale ? 'sold' : 'used') : 'received')
  const [qty, setQty] = useState('')
  const [price, setPrice] = useState(variant.eff_price != null ? String(variant.eff_price) : '')
  const [cost, setCost] = useState(variant.eff_cost != null ? String(variant.eff_cost) : '')
  const [playerId, setPlayerId] = useState(null)
  const [playerName, setPlayerName] = useState(null)
  const [paid, setPaid] = useState(true)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  const k = meta.find((m) => m.key === kind)
  const isMoney = !!k?.money
  const isSet = k?.dir === 'set'
  const isDelta = k?.dir === 'delta'

  useEffect(() => { setPaid(kind === 'sold') }, [kind])

  const submit = async () => {
    setBusy(true)
    try {
      const body = { variant_id: variant.id, kind, note: note || undefined }
      if (isSet) body.new_quantity = Number(qty || 0)
      else if (isDelta) body.delta = Number(qty || 0)
      else body.quantity = Number(qty || 0)
      if (kind === 'received') body.unit_cost = cost === '' ? undefined : Number(cost)
      if (isMoney) {
        body.unit_price = price === '' ? undefined : Number(price)
        body.paid = paid
        if (playerId) body.player_id = playerId
      }
      await api.merchRecordMovement(body)
      toast.success('Stock updated')
      onSaved()
    } catch (e) {
      toast.error(e.message || 'Could not record movement')
    } finally {
      setBusy(false)
    }
  }

  const qtyLabel = isSet ? 'New count (from hand count)' : isDelta ? 'Change (+/-)' : 'Quantity'
  return (
    <Modal open title={`${product.name} · ${variant.label}`} onClose={onClose}
      footer={<><Btn variant="subtle" onClick={onClose}>Cancel</Btn><Btn variant="primary" onClick={submit} disabled={busy || qty === ''}>Record</Btn></>}>
      <div className="space-y-3">
        <div className="text-[12.5px] text-pb-faint">On hand now: <b className="text-pb-text">{variant.quantity}</b></div>
        <Field label="What happened?">
          <Select value={kind} onChange={(e) => setKind(e.target.value)}>
            {meta.map((m) => <option key={m.key} value={m.key}>{m.label} · {m.blurb}</option>)}
          </Select>
        </Field>
        <Field label={qtyLabel}>
          <NumberInput value={qty} onChange={(e) => setQty(e.target.value)} placeholder="0" />
        </Field>
        {kind === 'received' && (
          <Field label="Unit cost (optional)"><NumberInput value={cost} onChange={(e) => setCost(e.target.value)} placeholder="0.00" /></Field>
        )}
        {isMoney && (
          <>
            <div className="flex gap-2">
              <Field half label="Unit price"><NumberInput value={price} onChange={(e) => setPrice(e.target.value)} placeholder="0.00" /></Field>
              <Field half label="Total">
                <div className="px-2.5 py-2 text-[13.5px] text-pb-text">{money((Number(price) || 0) * (Number(qty) || 0))}</div>
              </Field>
            </div>
            <Field label={kind === 'issued' ? 'Issued to (player)' : 'Sold to (player, optional)'}>
              <PlayerPicker value={playerId} valueName={playerName} onPick={(id, name) => { setPlayerId(id); setPlayerName(name) }} />
            </Field>
            <label className="flex items-center gap-2 text-[13px] cursor-pointer">
              <input type="checkbox" checked={paid} onChange={(e) => setPaid(e.target.checked)} />
              Paid now {!paid && <span className="text-pb-amber">— recorded as owing</span>}
            </label>
          </>
        )}
        <Field label="Note (optional)"><TextInput value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      </div>
    </Modal>
  )
}

// ── New product (with an initial variants editor) ────────────────────────────
function blankVariant() { return { label: '', size: '', colour: '', quantity: '', unit_cost: '', unit_price: '', expiry_date: '' } }

function ProductModal({ category, onClose, onSaved }) {
  const toast = useToast()
  const initCat = category && category !== 'all' ? category : 'apparel'
  const [cat, setCat] = useState(initCat)
  const [forResale, setForResale] = useState(initCat !== 'equipment')
  const [name, setName] = useState('')
  const [cost, setCost] = useState('')
  const [price, setPrice] = useState('')
  const [threshold, setThreshold] = useState('')
  const [supplier, setSupplier] = useState('')
  const [variants, setVariants] = useState([blankVariant()])
  const [busy, setBusy] = useState(false)
  const isApparel = cat === 'apparel'
  const isFood = cat === 'food_drink'

  // Picking a category sets a sensible default mode: equipment is club-use
  // (a straight cost), everything else is bought to sell.
  const onCat = (next) => { setCat(next); setForResale(next !== 'equipment') }

  const setV = (i, k, v) => setVariants((vs) => vs.map((row, j) => (j === i ? { ...row, [k]: v } : row)))

  const submit = async () => {
    if (!name.trim()) { toast.error('Name is required'); return }
    setBusy(true)
    try {
      const payload = {
        category: cat,
        name: name.trim(),
        for_resale: forResale,
        unit_cost: cost === '' ? undefined : Number(cost),
        unit_price: (forResale && price !== '') ? Number(price) : undefined,
        low_stock_threshold: threshold === '' ? undefined : Number(threshold),
        supplier: supplier || undefined,
        variants: variants
          .filter((v) => v.size || v.colour || v.label || v.unit_cost !== '' || v.unit_price !== '' || v.quantity !== '')
          .map((v) => ({
            label: v.label || undefined,
            size: v.size || undefined,
            colour: v.colour || undefined,
            unit_cost: v.unit_cost === '' ? undefined : Number(v.unit_cost),
            unit_price: (forResale && v.unit_price !== '') ? Number(v.unit_price) : undefined,
            quantity: v.quantity === '' ? 0 : Number(v.quantity),
            expiry_date: v.expiry_date || undefined,
          })),
      }
      await api.merchCreateProduct(payload)
      toast.success('Product added')
      onSaved()
    } catch (e) {
      toast.error(e.message || 'Could not add product')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open wide title="New product" onClose={onClose}
      footer={<><Btn variant="subtle" onClick={onClose}>Cancel</Btn><Btn variant="primary" onClick={submit} disabled={busy}>Add product</Btn></>}>
      <div className="space-y-3">
        <div className="flex gap-2">
          <Field half label="Category">
            <Select value={cat} onChange={(e) => onCat(e.target.value)}>
              {CATEGORIES.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
            </Select>
          </Field>
          <Field half label="Name"><TextInput value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Playing shirt" /></Field>
        </div>

        <Field label="How is it tracked?">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="inline-flex rounded-lg border border-pb-hairline2 overflow-hidden text-[12.5px]">
              <button type="button" onClick={() => setForResale(true)} className={`px-3 py-1.5 ${forResale ? 'bg-pb-accent text-black' : 'text-pb-faint hover:text-pb-text'}`}>For sale</button>
              <button type="button" onClick={() => setForResale(false)} className={`px-3 py-1.5 ${!forResale ? 'bg-pb-accent text-black' : 'text-pb-faint hover:text-pb-text'}`}>Club use</button>
            </div>
            <span className="text-[11px] text-pb-faint">
              {forResale ? 'Bought at one price, sold at another. Can be sold or issued to members.' : 'A straight cost the club uses up (e.g. balls). No sell price.'}
            </span>
          </div>
        </Field>

        <div className="flex gap-2">
          <Field half label={forResale ? 'Default cost (buy)' : 'Default cost'}><NumberInput value={cost} onChange={(e) => setCost(e.target.value)} placeholder="0.00" /></Field>
          {forResale && <Field half label="Default price (sell)"><NumberInput value={price} onChange={(e) => setPrice(e.target.value)} placeholder="0.00" /></Field>}
        </div>
        <div className="flex gap-2">
          <Field half label="Low-stock alert at" hint="Leave blank for no alert"><NumberInput value={threshold} onChange={(e) => setThreshold(e.target.value)} placeholder="e.g. 5" /></Field>
          <Field half label="Supplier (optional)"><TextInput value={supplier} onChange={(e) => setSupplier(e.target.value)} /></Field>
        </div>

        <div className="border-t border-pb-hairline pt-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[12px] font-mono tracking-wide2 text-pb-faint uppercase">
              {isApparel ? 'Sizes / colours' : 'Options / kinds'}
            </span>
            <Btn sm icon="plus" onClick={() => setVariants((vs) => [...vs, blankVariant()])}>{isApparel ? 'Add size' : 'Add option'}</Btn>
          </div>
          <div className="space-y-2">
            {variants.map((v, i) => (
              <div key={i} className="flex flex-wrap items-end gap-2">
                {isApparel ? (
                  <>
                    <VField label={i === 0 ? 'Size' : ''} w="w-16"><TextInput value={v.size} onChange={(e) => setV(i, 'size', e.target.value)} placeholder="M" /></VField>
                    <VField label={i === 0 ? 'Colour' : ''} w="w-24"><TextInput value={v.colour} onChange={(e) => setV(i, 'colour', e.target.value)} placeholder="Navy" /></VField>
                  </>
                ) : (
                  <VField label={i === 0 ? 'Kind / name' : ''} w="flex-1 min-w-[150px]"><TextInput value={v.label} onChange={(e) => setV(i, 'label', e.target.value)} placeholder="e.g. Kookaburra 4-piece" /></VField>
                )}
                <VField label={i === 0 ? 'Buy $' : ''} w="w-20"><NumberInput value={v.unit_cost} onChange={(e) => setV(i, 'unit_cost', e.target.value)} placeholder="0.00" /></VField>
                {forResale && <VField label={i === 0 ? 'Sell $' : ''} w="w-20"><NumberInput value={v.unit_price} onChange={(e) => setV(i, 'unit_price', e.target.value)} placeholder="0.00" /></VField>}
                <VField label={i === 0 ? 'Qty' : ''} w="w-16"><NumberInput value={v.quantity} onChange={(e) => setV(i, 'quantity', e.target.value)} placeholder="0" /></VField>
                {isFood && <VField label={i === 0 ? 'Expiry' : ''} w="w-36"><input type="date" value={v.expiry_date} onChange={(e) => setV(i, 'expiry_date', e.target.value)} className="w-full bg-pb-surface2 text-pb-text border border-pb-hairline2 rounded-lg px-2 py-2 text-[13px]" /></VField>}
                {variants.length > 1 && <button className="text-pb-faint hover:text-pb-red p-2 self-end" onClick={() => setVariants((vs) => vs.filter((_, j) => j !== i))}><Icon name="trash" size={15} /></button>}
              </div>
            ))}
          </div>
          <p className="text-[10.5px] text-pb-faintest mt-2">
            {isApparel
              ? 'A line per size or colour. A price on a line overrides the default above.'
              : 'Add a line per kind (a match ball and a training ball, say), each with its own price.'}
          </p>
        </div>
      </div>
    </Modal>
  )
}

// ── Variant row ──────────────────────────────────────────────────────────────
function VariantRow({ variant, product, onMove }) {
  const low = variant.low_stock
  return (
    <div className="flex items-center justify-between gap-3 py-1.5 px-2 rounded hover:bg-pb-surface2/50">
      <div className="min-w-0 flex items-center gap-2">
        <span className="text-[13px] truncate">{variant.label}</span>
        {product.for_resale
          ? (variant.eff_price != null && <span className="text-[11px] text-pb-faint shrink-0">{money(variant.eff_price)}</span>)
          : (variant.eff_cost != null && <span className="text-[11px] text-pb-faint shrink-0">{money(variant.eff_cost)}</span>)}
        {variant.sku && <span className="font-mono text-[10px] text-pb-faintest">{variant.sku}</span>}
        {variant.expiry_date && <Pill tone="amber">exp {variant.expiry_date}</Pill>}
      </div>
      <div className="flex items-center gap-3 shrink-0">
        <span className={`font-display font-bold text-sm ${low ? 'text-pb-amber' : 'text-pb-text'}`}>{variant.quantity}</span>
        {low && <Pill tone="amber">low</Pill>}
        <Btn sm icon="plus" onClick={() => onMove(variant, 'in')}>In</Btn>
        <Btn sm icon="minus" onClick={() => onMove(variant, 'out')}>Out</Btn>
      </div>
    </div>
  )
}

function ProductCard({ product, onMove, onAddVariant }) {
  return (
    <div className="pb-card p-4">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-display font-bold text-sm truncate">{product.name}</h3>
            <Pill>{categoryLabel(product.category)}</Pill>
            {!product.for_resale && <Pill>club use</Pill>}
            {product.low_stock && <Pill tone="amber">low stock</Pill>}
          </div>
          <div className="text-[11.5px] text-pb-faint mt-0.5">
            {product.on_hand} on hand
            {product.unit_cost != null && <> · cost {money(product.unit_cost)}</>}
            {product.for_resale && product.unit_price != null && <> · sell {money(product.unit_price)}</>}
            {product.supplier && <> · {product.supplier}</>}
          </div>
        </div>
      </div>
      <div className="divide-y divide-pb-hairline/50">
        {(product.variants || []).map((v) => (
          <VariantRow key={v.id} variant={v} product={product} onMove={onMove} />
        ))}
      </div>
      <button className="mt-2 text-[11.5px] text-pb-faint hover:text-pb-accent flex items-center gap-1" onClick={() => onAddVariant(product)}>
        <Icon name="plus" size={12} /> Add size / line
      </button>
    </div>
  )
}

function AddVariantModal({ product, onClose, onSaved }) {
  const toast = useToast()
  const isApparel = product.category === 'apparel'
  const forResale = product.for_resale
  const [size, setSize] = useState('')
  const [colour, setColour] = useState('')
  const [label, setLabel] = useState('')
  const [qty, setQty] = useState('')
  const [cost, setCost] = useState('')
  const [price, setPrice] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async () => {
    setBusy(true)
    try {
      await api.merchAddVariant(product.id, {
        label: label || undefined, size: size || undefined, colour: colour || undefined,
        unit_cost: cost === '' ? undefined : Number(cost),
        unit_price: (forResale && price !== '') ? Number(price) : undefined,
        quantity: qty === '' ? 0 : Number(qty),
      })
      toast.success('Line added'); onSaved()
    } catch (e) { toast.error(e.message || 'Could not add line') } finally { setBusy(false) }
  }
  return (
    <Modal open title={`Add to ${product.name}`} onClose={onClose}
      footer={<><Btn variant="subtle" onClick={onClose}>Cancel</Btn><Btn variant="primary" onClick={submit} disabled={busy}>Add</Btn></>}>
      <div className="space-y-3">
        {isApparel ? (
          <div className="flex gap-2">
            <Field half label="Size"><TextInput value={size} onChange={(e) => setSize(e.target.value)} placeholder="L" /></Field>
            <Field half label="Colour"><TextInput value={colour} onChange={(e) => setColour(e.target.value)} placeholder="White" /></Field>
          </div>
        ) : (
          <Field label="Kind / name"><TextInput value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Training ball" /></Field>
        )}
        <div className="flex gap-2">
          <Field half label={forResale ? 'Buy $' : 'Cost $'}><NumberInput value={cost} onChange={(e) => setCost(e.target.value)} placeholder="0.00" /></Field>
          {forResale && <Field half label="Sell $"><NumberInput value={price} onChange={(e) => setPrice(e.target.value)} placeholder="0.00" /></Field>}
        </div>
        <Field label="Starting quantity"><NumberInput value={qty} onChange={(e) => setQty(e.target.value)} placeholder="0" /></Field>
      </div>
    </Modal>
  )
}

export default function MerchStock() {
  const toast = useToast()
  const [params] = useSearchParams()
  const [cat, setCat] = useState('all')
  const [q, setQ] = useState('')
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [showNew, setShowNew] = useState(false)
  const [move, setMove] = useState(null)        // { variant, product }
  const [addVariantFor, setAddVariantFor] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const d = await api.merchListProducts({ category: cat === 'all' ? undefined : cat, q: q || undefined })
      setProducts(d.products || [])
    } catch (e) {
      toast.error(e.message || 'Could not load stock')
    } finally {
      setLoading(false)
    }
  }, [cat, q])

  useEffect(() => { load() }, [load])

  const onMove = (variant, dir) => {
    const product = products.find((p) => (p.variants || []).some((v) => v.id === variant.id))
    setMove({ variant, product, dir })
  }

  return (
    <BetterMerchLayout title="Stock"
      actions={<Btn variant="primary" sm icon="plus" onClick={() => setShowNew(true)}>New product</Btn>}>
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <button onClick={() => setCat('all')} className={`px-3 py-1.5 rounded-lg text-[12.5px] ${cat === 'all' ? 'bg-pb-accent/12 text-pb-accent' : 'text-pb-faint hover:text-pb-text'}`}>All</button>
        {CATEGORIES.map((c) => (
          <button key={c.key} onClick={() => setCat(c.key)} className={`px-3 py-1.5 rounded-lg text-[12.5px] ${cat === c.key ? 'bg-pb-accent/12 text-pb-accent' : 'text-pb-faint hover:text-pb-text'}`}>{c.label}</button>
        ))}
        <div className="ml-auto relative">
          <TextInput placeholder="Search products…" value={q} onChange={(e) => setQ(e.target.value)} className="w-56" />
        </div>
      </div>

      {loading ? <PbSpinner message="Loading stock…" /> : products.length === 0 ? (
        <div className="pb-card p-8 text-center text-pb-faint text-sm">
          No products yet. <button className="text-pb-accent" onClick={() => setShowNew(true)}>Add your first one</button>.
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {products.map((p) => (
            <ProductCard key={p.id} product={p} onMove={onMove} onAddVariant={setAddVariantFor} />
          ))}
        </div>
      )}

      {showNew && <ProductModal category={cat} onClose={() => setShowNew(false)} onSaved={() => { setShowNew(false); load() }} />}
      {move && <MovementModal variant={move.variant} product={move.product} dir={move.dir} onClose={() => setMove(null)} onSaved={() => { setMove(null); load() }} />}
      {addVariantFor && <AddVariantModal product={addVariantFor} onClose={() => setAddVariantFor(null)} onSaved={() => { setAddVariantFor(null); load() }} />}
    </BetterMerchLayout>
  )
}
