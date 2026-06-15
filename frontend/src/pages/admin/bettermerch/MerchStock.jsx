import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
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

// Build a quick id -> "Parent › Child" path string map for display.
export function categoryPathMap(categories) {
  const byId = Object.fromEntries((categories || []).map((c) => [c.id, c]))
  const map = {}
  for (const c of categories || []) {
    const parts = []
    let n = c, guard = 0
    while (n && guard < 8) { parts.unshift(n.name); n = n.parent_id ? byId[n.parent_id] : null; guard++ }
    map[c.id] = parts.join(' › ')
  }
  return map
}

// Category picker — one dropdown of the type's categories (shown as a path like
// "Balls › Match"), plus an inline "+ New category" with an optional parent.
function CategoryPicker({ topCategory, value, categories, onChange, onCreated }) {
  const toast = useToast()
  const [adding, setAdding] = useState(false)
  const [newName, setNewName] = useState('')
  const [parentId, setParentId] = useState('')
  const [busy, setBusy] = useState(false)

  const scoped = (categories || []).filter((c) => c.top_category === topCategory)
  const byId = Object.fromEntries(scoped.map((c) => [c.id, c]))
  const pathOf = (c) => {
    const parts = []; let n = c, g = 0
    while (n && g < 8) { parts.unshift(n.name); n = n.parent_id ? byId[n.parent_id] : null; g++ }
    return parts.join(' › ')
  }
  const sorted = [...scoped].sort((a, b) => pathOf(a).localeCompare(pathOf(b)))
  const parentOpts = sorted.filter((c) => c.depth < 3)

  const add = async () => {
    const name = newName.trim()
    if (!name) return
    setBusy(true)
    try {
      const created = await api.merchCreateCategory({ top_category: topCategory, parent_id: parentId || undefined, name })
      setNewName(''); setParentId(''); setAdding(false)
      await onCreated()
      onChange(created.id)
    } catch (e) { toast.error(e.message || 'Could not add category') } finally { setBusy(false) }
  }

  return (
    <div className="space-y-2">
      <Select value={adding ? '__new' : (value || '')} onChange={(e) => {
        if (e.target.value === '__new') setAdding(true)
        else { setAdding(false); onChange(e.target.value || null) }
      }}>
        <option value="">Uncategorised</option>
        {sorted.map((c) => <option key={c.id} value={c.id}>{pathOf(c)}</option>)}
        <option value="__new">+ New category…</option>
      </Select>
      {adding && (
        <div className="flex flex-wrap items-center gap-2">
          <TextInput value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="New category name" className="flex-1 min-w-[150px]" />
          {parentOpts.length > 0 && (
            <Select value={parentId} onChange={(e) => setParentId(e.target.value)} className="w-44">
              <option value="">Top level</option>
              {parentOpts.map((c) => <option key={c.id} value={c.id}>under {pathOf(c)}</option>)}
            </Select>
          )}
          <Btn sm variant="primary" onClick={add} disabled={busy}>Add</Btn>
          <Btn sm variant="subtle" onClick={() => { setAdding(false); setNewName('') }}>Cancel</Btn>
        </div>
      )}
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

function ProductModal({ category, categories, onCategoriesChanged, onClose, onSaved }) {
  const toast = useToast()
  const initCat = category && category !== 'all' ? category : 'apparel'
  const [cat, setCat] = useState(initCat)
  const [forResale, setForResale] = useState(initCat !== 'equipment')
  const [categoryId, setCategoryId] = useState(null)
  const [name, setName] = useState('')
  const [cost, setCost] = useState('')
  const [price, setPrice] = useState('')
  const [threshold, setThreshold] = useState('')
  const [supplier, setSupplier] = useState('')
  const [variants, setVariants] = useState([blankVariant()])
  const [busy, setBusy] = useState(false)
  const isApparel = cat === 'apparel'
  const isFood = cat === 'food_drink'

  // Picking a type sets a sensible default mode: equipment is club-use (a
  // straight cost), everything else is bought to sell. Reset the category too,
  // since categories are scoped to the type.
  const onCat = (next) => { setCat(next); setForResale(next !== 'equipment'); setCategoryId(null) }

  const setV = (i, k, v) => setVariants((vs) => vs.map((row, j) => (j === i ? { ...row, [k]: v } : row)))

  const submit = async () => {
    if (!name.trim()) { toast.error('Name is required'); return }
    setBusy(true)
    try {
      const payload = {
        category: cat,
        category_id: categoryId || undefined,
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

        <Field label="Category (optional)" hint="Group items for reporting. Type a new one and pick + New to create it.">
          <CategoryPicker topCategory={cat} value={categoryId} categories={categories} onChange={setCategoryId} onCreated={onCategoriesChanged} />
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
function VariantRow({ variant, product, onMove, onEditVariant }) {
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
      <div className="flex items-center gap-2 shrink-0">
        <span className={`font-display font-bold text-sm ${low ? 'text-pb-amber' : 'text-pb-text'}`}>{variant.quantity}</span>
        {low && <Pill tone="amber">low</Pill>}
        <button onClick={() => onEditVariant(variant, product)} title="Edit line" className="text-pb-faint hover:text-pb-accent p-1"><Icon name="settings" size={14} /></button>
        <Btn sm icon="plus" onClick={() => onMove(variant, 'in')}>In</Btn>
        <Btn sm icon="minus" onClick={() => onMove(variant, 'out')}>Out</Btn>
      </div>
    </div>
  )
}

function ProductCard({ product, catPathById, onMove, onAddVariant, onEdit, onEditVariant }) {
  const path = product.category_id ? catPathById[product.category_id] : null
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
          {path && <div className="text-[10.5px] text-pb-faintest mt-0.5">{path}</div>}
          <div className="text-[11.5px] text-pb-faint mt-0.5">
            {product.on_hand} on hand
            {product.unit_cost != null && <> · cost {money(product.unit_cost)}</>}
            {product.for_resale && product.unit_price != null && <> · sell {money(product.unit_price)}</>}
            {product.supplier && <> · {product.supplier}</>}
          </div>
        </div>
        <button onClick={() => onEdit(product)} title="Edit product" className="text-pb-faint hover:text-pb-accent p-1 shrink-0"><Icon name="settings" size={15} /></button>
      </div>
      <div className="divide-y divide-pb-hairline/50">
        {(product.variants || []).map((v) => (
          <VariantRow key={v.id} variant={v} product={product} onMove={onMove} onEditVariant={onEditVariant} />
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

function ProductEditModal({ product, categories, onCategoriesChanged, onClose, onSaved }) {
  const toast = useToast()
  const [cat, setCat] = useState(product.category)
  const [forResale, setForResale] = useState(product.for_resale)
  const [categoryId, setCategoryId] = useState(product.category_id || null)
  const [name, setName] = useState(product.name)
  const [cost, setCost] = useState(product.unit_cost != null ? String(product.unit_cost) : '')
  const [price, setPrice] = useState(product.unit_price != null ? String(product.unit_price) : '')
  const [threshold, setThreshold] = useState(product.low_stock_threshold != null ? String(product.low_stock_threshold) : '')
  const [supplier, setSupplier] = useState(product.supplier || '')
  const [busy, setBusy] = useState(false)
  const onCat = (next) => { setCat(next); setCategoryId(null) }

  const save = async () => {
    if (!name.trim()) { toast.error('Name is required'); return }
    setBusy(true)
    try {
      await api.merchUpdateProduct(product.id, {
        name: name.trim(), category: cat, for_resale: forResale, category_id: categoryId,
        unit_cost: cost === '' ? null : Number(cost),
        unit_price: (forResale && price !== '') ? Number(price) : null,
        low_stock_threshold: threshold === '' ? null : Number(threshold),
        supplier: supplier || null,
      })
      toast.success('Saved'); onSaved()
    } catch (e) { toast.error(e.message || 'Could not save') } finally { setBusy(false) }
  }
  const remove = async () => {
    if (!window.confirm('Delete this product? Its stock history is kept but it leaves the list.')) return
    setBusy(true)
    try { await api.merchDeleteProduct(product.id); toast.success('Deleted'); onSaved() }
    catch (e) { toast.error(e.message || 'Could not delete') } finally { setBusy(false) }
  }

  return (
    <Modal open wide title={`Edit ${product.name}`} onClose={onClose}
      footer={<>
        <Btn variant="danger" onClick={remove} disabled={busy}>Delete</Btn>
        <Btn variant="subtle" onClick={onClose}>Cancel</Btn>
        <Btn variant="primary" onClick={save} disabled={busy}>Save</Btn>
      </>}>
      <div className="space-y-3">
        <div className="flex gap-2">
          <Field half label="Type">
            <Select value={cat} onChange={(e) => onCat(e.target.value)}>
              {CATEGORIES.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
            </Select>
          </Field>
          <Field half label="Name"><TextInput value={name} onChange={(e) => setName(e.target.value)} /></Field>
        </div>
        <Field label="How is it tracked?">
          <div className="inline-flex rounded-lg border border-pb-hairline2 overflow-hidden text-[12.5px]">
            <button type="button" onClick={() => setForResale(true)} className={`px-3 py-1.5 ${forResale ? 'bg-pb-accent text-black' : 'text-pb-faint hover:text-pb-text'}`}>For sale</button>
            <button type="button" onClick={() => setForResale(false)} className={`px-3 py-1.5 ${!forResale ? 'bg-pb-accent text-black' : 'text-pb-faint hover:text-pb-text'}`}>Club use</button>
          </div>
        </Field>
        <Field label="Category">
          <CategoryPicker topCategory={cat} value={categoryId} categories={categories} onChange={setCategoryId} onCreated={onCategoriesChanged} />
        </Field>
        <div className="flex gap-2">
          <Field half label={forResale ? 'Default cost (buy)' : 'Default cost'}><NumberInput value={cost} onChange={(e) => setCost(e.target.value)} placeholder="0.00" /></Field>
          {forResale && <Field half label="Default price (sell)"><NumberInput value={price} onChange={(e) => setPrice(e.target.value)} placeholder="0.00" /></Field>}
        </div>
        <div className="flex gap-2">
          <Field half label="Low-stock alert at"><NumberInput value={threshold} onChange={(e) => setThreshold(e.target.value)} placeholder="e.g. 5" /></Field>
          <Field half label="Supplier"><TextInput value={supplier} onChange={(e) => setSupplier(e.target.value)} /></Field>
        </div>
        <p className="text-[10.5px] text-pb-faintest">Sizes and stock lines are managed on the card. This edits the product details.</p>
      </div>
    </Modal>
  )
}

function VariantEditModal({ variant, product, onClose, onSaved }) {
  const toast = useToast()
  const isApparel = product.category === 'apparel'
  const isFood = product.category === 'food_drink'
  const forResale = product.for_resale
  const [label, setLabel] = useState(variant.label || '')
  const [size, setSize] = useState(variant.size || '')
  const [colour, setColour] = useState(variant.colour || '')
  const [cost, setCost] = useState(variant.unit_cost != null ? String(variant.unit_cost) : '')
  const [price, setPrice] = useState(variant.unit_price != null ? String(variant.unit_price) : '')
  const [threshold, setThreshold] = useState(variant.low_stock_threshold != null ? String(variant.low_stock_threshold) : '')
  const [expiry, setExpiry] = useState(variant.expiry_date || '')
  const [busy, setBusy] = useState(false)

  const save = async () => {
    setBusy(true)
    try {
      const patch = {
        unit_cost: cost === '' ? null : Number(cost),
        low_stock_threshold: threshold === '' ? null : Number(threshold),
      }
      if (forResale) patch.unit_price = price === '' ? null : Number(price)
      if (isApparel) {
        patch.size = size || null
        patch.colour = colour || null
        patch.label = [size, colour].filter(Boolean).join(' / ') || 'Standard'
      } else {
        patch.label = label.trim() || 'Standard'
      }
      if (isFood) patch.expiry_date = expiry || null
      await api.merchUpdateVariant(variant.id, patch)
      toast.success('Saved'); onSaved()
    } catch (e) { toast.error(e.message || 'Could not save') } finally { setBusy(false) }
  }
  const remove = async () => {
    if (!window.confirm('Remove this line? Its stock history is kept.')) return
    setBusy(true)
    try { await api.merchDeleteVariant(variant.id); toast.success('Removed'); onSaved() }
    catch (e) { toast.error(e.message || 'Could not remove') } finally { setBusy(false) }
  }

  return (
    <Modal open title={`Edit ${variant.label}`} onClose={onClose}
      footer={<>
        <Btn variant="danger" onClick={remove} disabled={busy}>Remove</Btn>
        <Btn variant="subtle" onClick={onClose}>Cancel</Btn>
        <Btn variant="primary" onClick={save} disabled={busy}>Save</Btn>
      </>}>
      <div className="space-y-3">
        {isApparel ? (
          <div className="flex gap-2">
            <Field half label="Size"><TextInput value={size} onChange={(e) => setSize(e.target.value)} /></Field>
            <Field half label="Colour"><TextInput value={colour} onChange={(e) => setColour(e.target.value)} /></Field>
          </div>
        ) : (
          <Field label="Kind / name"><TextInput value={label} onChange={(e) => setLabel(e.target.value)} /></Field>
        )}
        <div className="flex gap-2">
          <Field half label={forResale ? 'Buy $' : 'Cost $'}><NumberInput value={cost} onChange={(e) => setCost(e.target.value)} placeholder="0.00" /></Field>
          {forResale && <Field half label="Sell $"><NumberInput value={price} onChange={(e) => setPrice(e.target.value)} placeholder="0.00" /></Field>}
        </div>
        <div className="flex gap-2">
          <Field half label="Low-stock alert at" hint="Blank uses the product default"><NumberInput value={threshold} onChange={(e) => setThreshold(e.target.value)} placeholder="e.g. 10" /></Field>
          {isFood && <Field half label="Expiry"><input type="date" value={expiry} onChange={(e) => setExpiry(e.target.value)} className="w-full bg-pb-surface2 text-pb-text border border-pb-hairline2 rounded-lg px-2.5 py-2 text-[13.5px]" /></Field>}
        </div>
        <p className="text-[10.5px] text-pb-faintest">Quantity is changed with In / Out, not here.</p>
      </div>
    </Modal>
  )
}

function CategoryManagerModal({ categories, onChanged, onClose }) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [renaming, setRenaming] = useState(null)
  const [name, setName] = useState('')
  const pathMap = categoryPathMap(categories)
  const sorted = [...categories].sort((a, b) =>
    a.top_category.localeCompare(b.top_category) || (pathMap[a.id] || '').localeCompare(pathMap[b.id] || ''))

  const doRename = async (c) => {
    if (!name.trim()) { setRenaming(null); return }
    setBusy(true)
    try { await api.merchRenameCategory(c.id, { name: name.trim() }); setRenaming(null); await onChanged() }
    catch (e) { toast.error(e.message || 'Could not rename') } finally { setBusy(false) }
  }
  const del = async (c) => {
    if (!window.confirm(`Delete "${c.name}"? Items under it become uncategorised, and any sub-categories move up a level.`)) return
    setBusy(true)
    try { await api.merchDeleteCategory(c.id); await onChanged() }
    catch (e) { toast.error(e.message || 'Could not delete') } finally { setBusy(false) }
  }
  const seed = async () => {
    setBusy(true)
    try { const r = await api.merchSeedCategories(); await onChanged(); toast.success(r.created > 0 ? `Added ${r.created} categories` : 'Starter categories already there') }
    catch (e) { toast.error(e.message || 'Could not add starter set') } finally { setBusy(false) }
  }

  return (
    <Modal open wide title="Manage categories" onClose={onClose}
      footer={<>
        <Btn variant="subtle" onClick={seed} disabled={busy}>Add starter set</Btn>
        <Btn variant="primary" onClick={onClose}>Done</Btn>
      </>}>
      {sorted.length === 0 ? (
        <div className="text-center py-6">
          <p className="text-[13px] text-pb-faint mb-3">No categories yet.</p>
          <Btn variant="primary" onClick={seed} disabled={busy}>Add starter categories</Btn>
          <p className="text-[11px] text-pb-faintest mt-2">A generic set (Match attire, Balls, Canteen, and so on) you can rename or remove.</p>
        </div>
      ) : (
        <div className="divide-y divide-pb-hairline/50">
          {sorted.map((c) => (
            <div key={c.id} className="flex items-center gap-2 py-2">
              <span className="text-[10px] font-mono text-pb-faintest w-20 shrink-0">{categoryLabel(c.top_category)}</span>
              {renaming === c.id ? (
                <>
                  <TextInput value={name} onChange={(e) => setName(e.target.value)} className="flex-1" />
                  <Btn sm variant="primary" onClick={() => doRename(c)} disabled={busy}>Save</Btn>
                  <Btn sm variant="subtle" onClick={() => setRenaming(null)}>Cancel</Btn>
                </>
              ) : (
                <>
                  <span className="flex-1 text-[13px]" style={{ paddingLeft: `${(c.depth - 1) * 14}px` }}>
                    {c.name}{c.depth > 1 && <span className="text-pb-faintest text-[11px]"> · {pathMap[c.id]}</span>}
                  </span>
                  <button onClick={() => { setRenaming(c.id); setName(c.name) }} className="text-pb-faint hover:text-pb-accent p-1" title="Rename"><Icon name="settings" size={14} /></button>
                  <button onClick={() => del(c)} className="text-pb-faint hover:text-pb-red p-1" title="Delete"><Icon name="trash" size={14} /></button>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </Modal>
  )
}

export default function MerchStock() {
  const toast = useToast()
  const [cat, setCat] = useState('all')
  const [catFilter, setCatFilter] = useState('')
  const [q, setQ] = useState('')
  const [products, setProducts] = useState([])
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [showNew, setShowNew] = useState(false)
  const [move, setMove] = useState(null)        // { variant, product, dir }
  const [addVariantFor, setAddVariantFor] = useState(null)
  const [editProduct, setEditProduct] = useState(null)
  const [editVariant, setEditVariant] = useState(null)  // { variant, product }
  const [showCatManager, setShowCatManager] = useState(false)

  const catPathById = useMemo(() => categoryPathMap(categories), [categories])

  const loadCategories = useCallback(async () => {
    try { const d = await api.merchListCategories(); setCategories(d.categories || []) } catch { /* non-fatal */ }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const d = await api.merchListProducts({ category: cat === 'all' ? undefined : cat, categoryId: catFilter || undefined, q: q || undefined })
      setProducts(d.products || [])
    } catch (e) {
      toast.error(e.message || 'Could not load stock')
    } finally {
      setLoading(false)
    }
  }, [cat, catFilter, q])

  useEffect(() => { loadCategories() }, [loadCategories])
  useEffect(() => { load() }, [load])

  const pickTab = (next) => { setCat(next); setCatFilter('') }
  const onMove = (variant, dir) => {
    const product = products.find((p) => (p.variants || []).some((v) => v.id === variant.id))
    setMove({ variant, product, dir })
  }
  const scopedCats = categories
    .filter((c) => cat === 'all' || c.top_category === cat)
    .slice()
    .sort((a, b) => (catPathById[a.id] || '').localeCompare(catPathById[b.id] || ''))

  return (
    <BetterMerchLayout title="Stock"
      actions={<div className="flex items-center gap-2">
        <Btn sm icon="list" onClick={() => setShowCatManager(true)}>Categories</Btn>
        <Btn variant="primary" sm icon="plus" onClick={() => setShowNew(true)}>New product</Btn>
      </div>}>
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <button onClick={() => pickTab('all')} className={`px-3 py-1.5 rounded-lg text-[12.5px] ${cat === 'all' ? 'bg-pb-accent/12 text-pb-accent' : 'text-pb-faint hover:text-pb-text'}`}>All</button>
        {CATEGORIES.map((c) => (
          <button key={c.key} onClick={() => pickTab(c.key)} className={`px-3 py-1.5 rounded-lg text-[12.5px] ${cat === c.key ? 'bg-pb-accent/12 text-pb-accent' : 'text-pb-faint hover:text-pb-text'}`}>{c.label}</button>
        ))}
        <div className="ml-auto flex items-center gap-2">
          {scopedCats.length > 0 && (
            <Select value={catFilter} onChange={(e) => setCatFilter(e.target.value)} className="w-48">
              <option value="">All categories</option>
              {scopedCats.map((c) => <option key={c.id} value={c.id}>{catPathById[c.id]}</option>)}
            </Select>
          )}
          <TextInput placeholder="Search products…" value={q} onChange={(e) => setQ(e.target.value)} className="w-44" />
        </div>
      </div>

      {loading ? <PbSpinner message="Loading stock…" /> : products.length === 0 ? (
        <div className="pb-card p-8 text-center text-pb-faint text-sm">
          {catFilter || q ? 'No products match.' : <>No products yet. <button className="text-pb-accent" onClick={() => setShowNew(true)}>Add your first one</button>.</>}
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {products.map((p) => (
            <ProductCard key={p.id} product={p} catPathById={catPathById} onMove={onMove} onAddVariant={setAddVariantFor}
              onEdit={setEditProduct} onEditVariant={(v, prod) => setEditVariant({ variant: v, product: prod })} />
          ))}
        </div>
      )}

      {showNew && <ProductModal category={cat} categories={categories} onCategoriesChanged={loadCategories} onClose={() => setShowNew(false)} onSaved={() => { setShowNew(false); load() }} />}
      {editProduct && <ProductEditModal product={editProduct} categories={categories} onCategoriesChanged={loadCategories} onClose={() => setEditProduct(null)} onSaved={() => { setEditProduct(null); load() }} />}
      {move && <MovementModal variant={move.variant} product={move.product} dir={move.dir} onClose={() => setMove(null)} onSaved={() => { setMove(null); load() }} />}
      {addVariantFor && <AddVariantModal product={addVariantFor} onClose={() => setAddVariantFor(null)} onSaved={() => { setAddVariantFor(null); load() }} />}
      {editVariant && <VariantEditModal variant={editVariant.variant} product={editVariant.product} onClose={() => setEditVariant(null)} onSaved={() => { setEditVariant(null); load() }} />}
      {showCatManager && <CategoryManagerModal categories={categories} onChanged={async () => { await loadCategories(); load() }} onClose={() => setShowCatManager(false)} />}
    </BetterMerchLayout>
  )
}
