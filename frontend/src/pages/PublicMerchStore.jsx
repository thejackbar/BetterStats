// Merch storefront (public, no login) — browse a club's BetterMerch catalogue
// and pay online via the club's own Stripe Connect account. See
// routers/public_merch_store.py.
import { useState, useEffect, useCallback, useMemo } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'

const inp = 'w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
const money = (cents) => `$${(Number(cents || 0) / 100).toFixed(2)}`

function Banner({ tone = 'error', children }) {
  if (!children) return null
  const color = tone === 'error' ? 'var(--pb-red)' : tone === 'ok' ? 'var(--pb-positive)' : 'var(--pb-amber)'
  return (
    <div className="rounded-lg px-3.5 py-2.5 mb-4 text-sm" style={{ background: `color-mix(in srgb, ${color} 12%, transparent)`, color, border: `1px solid color-mix(in srgb, ${color} 35%, transparent)` }}>
      {children}
    </div>
  )
}

function ProductCard({ product, cart, setCart }) {
  const [variantId, setVariantId] = useState(product.variants[0]?.id)
  const variant = product.variants.find(v => v.id === variantId) || product.variants[0]
  const inCart = cart.find(c => c.variant_id === variantId)?.quantity || 0
  const soldOut = (variant?.in_stock ?? 0) <= 0

  function add() {
    if (!variant || soldOut) return
    setCart(prev => {
      const existing = prev.find(c => c.variant_id === variant.id)
      if (existing) {
        return prev.map(c => c.variant_id === variant.id ? { ...c, quantity: Math.min(variant.in_stock, c.quantity + 1) } : c)
      }
      return [...prev, { variant_id: variant.id, quantity: 1, product_name: product.name, variant_label: variant.label === 'Standard' ? null : variant.label, price_cents: variant.price_cents, in_stock: variant.in_stock }]
    })
  }

  return (
    <div className="pb-card p-4">
      <div className="text-pb-text font-semibold text-sm mb-0.5">{product.name}</div>
      {product.description && <div className="text-pb-faint text-[12px] mb-2">{product.description}</div>}
      <div className="flex flex-wrap gap-1.5 mb-2">
        {product.variants.map(v => (
          <button key={v.id} onClick={() => setVariantId(v.id)}
            disabled={v.in_stock <= 0}
            className={`font-mono text-[10px] px-2 py-1 rounded border transition disabled:opacity-30 ${v.id === variantId ? 'pb-hairline text-pb-text bg-pb-surface2' : 'border-dashed border-pb-faintest text-pb-faintest hover:text-pb-faint'}`}>
            {v.label}{v.in_stock <= 0 ? ' (sold out)' : ''}
          </button>
        ))}
      </div>
      <div className="flex items-center justify-between">
        <span className="font-display font-bold text-pb-text">{money(variant?.price_cents)}</span>
        <button onClick={add} disabled={soldOut}
          className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40"
          style={{ background: 'var(--pb-accent)' }}>
          {inCart > 0 ? `IN CART (${inCart})` : 'ADD TO CART'}
        </button>
      </div>
    </div>
  )
}

function CartPanel({ cart, setCart, slug, clubName }) {
  const [form, setForm] = useState({ customer_name: '', email: '', phone: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const total = cart.reduce((sum, c) => sum + c.price_cents * c.quantity, 0)

  function updateQty(variantId, quantity) {
    setCart(prev => quantity <= 0 ? prev.filter(c => c.variant_id !== variantId) : prev.map(c => c.variant_id === variantId ? { ...c, quantity } : c))
  }

  async function checkout() {
    if (!form.customer_name.trim()) { setError('Name is required'); return }
    setBusy(true); setError('')
    try {
      const r = await api.shopCheckout(slug, {
        customer_name: form.customer_name, email: form.email || null, phone: form.phone || null,
        items: cart.map(c => ({ variant_id: c.variant_id, quantity: c.quantity })),
      })
      window.location.assign(r.checkout_url)
    } catch (e) { setError(e.message); setBusy(false) }
  }

  if (cart.length === 0) return null
  return (
    <div className="pb-card p-4 sticky top-4">
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">YOUR CART</div>
      <div className="space-y-2 mb-3">
        {cart.map(c => (
          <div key={c.variant_id} className="flex items-center justify-between gap-2 text-sm">
            <div>
              <div className="text-pb-text">{c.product_name}{c.variant_label ? ` (${c.variant_label})` : ''}</div>
              <div className="font-mono text-[10px] text-pb-faint">{money(c.price_cents)} each</div>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <button onClick={() => updateQty(c.variant_id, c.quantity - 1)} className="w-6 h-6 rounded border pb-hairline text-pb-faint hover:text-pb-text">−</button>
              <span className="font-mono text-[11px] w-4 text-center">{c.quantity}</span>
              <button onClick={() => updateQty(c.variant_id, c.quantity + 1)} disabled={c.quantity >= c.in_stock} className="w-6 h-6 rounded border pb-hairline text-pb-faint hover:text-pb-text disabled:opacity-30">+</button>
            </div>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between font-display font-bold text-pb-text mb-3 pt-2 border-t pb-hairline-t">
        <span>Total</span><span>{money(total)}</span>
      </div>
      {error && <Banner>{error}</Banner>}
      <div className="space-y-2">
        <input className={inp} placeholder="Your name" value={form.customer_name} onChange={e => setForm(f => ({ ...f, customer_name: e.target.value }))} />
        <input className={inp} placeholder="Email (optional)" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
        <input className={inp} placeholder="Phone (optional)" value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))} />
        <button onClick={checkout} disabled={busy || !form.customer_name.trim()}
          className="w-full py-2.5 rounded font-mono text-[11px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50"
          style={{ background: 'var(--pb-accent)' }}>
          {busy ? 'REDIRECTING…' : `PAY ${money(total)}`}
        </button>
        <p className="font-mono text-[9px] text-pb-faintest">Pickup at the club — {clubName} will be in touch to arrange collection.</p>
      </div>
    </div>
  )
}

export default function PublicMerchStore() {
  const { slug } = useParams()
  const [searchParams] = useSearchParams()
  const [status, setStatus] = useState(null)
  const [products, setProducts] = useState(null)
  const [error, setError] = useState('')
  const [cart, setCart] = useState([])

  useEffect(() => {
    let cancelled = false
    api.shopStatus(slug).then(s => {
      if (cancelled) return
      setStatus(s)
      if (s.enabled) api.shopCatalogue(slug).then(d => { if (!cancelled) setProducts(d.products || []) }).catch(() => {})
    }).catch(e => { if (!cancelled) setError(e.message || 'Club not found') })
    return () => { cancelled = true }
  }, [slug])

  const grouped = useMemo(() => {
    const out = {}
    for (const p of (products || [])) {
      const key = p.category_name || p.category
      out[key] = out[key] || []
      out[key].push(p)
    }
    return out
  }, [products])

  const orderParam = searchParams.get('order')

  if (error) {
    return <div className="min-h-screen bg-pb-bg flex items-center justify-center px-4"><div className="font-mono text-[11px] text-pb-faint">{error}</div></div>
  }
  if (!status) {
    return <div className="min-h-screen bg-pb-bg flex items-center justify-center"><div className="font-mono text-[11px] text-pb-faint">Loading…</div></div>
  }
  if (!status.enabled) {
    return (
      <div className="min-h-screen bg-pb-bg flex items-center justify-center px-4">
        <div className="max-w-sm text-center">
          <div className="font-display font-bold text-lg text-pb-text mb-1">Not available yet</div>
          <div className="font-mono text-[11px] text-pb-faint">The online store isn't switched on for this club yet.</div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-pb-bg px-4 py-10">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-6">
          <div className="font-mono text-[10px] tracking-wide2 text-pb-faint mb-1">{status.club_name?.toUpperCase()}</div>
          <div className="font-display font-bold text-2xl text-pb-text">Club Store</div>
        </div>

        {orderParam === '1' && <Banner tone="ok">Thanks for your order! The club will be in touch to arrange pickup.</Banner>}
        {orderParam === '0' && <Banner tone="warn">Checkout cancelled — nothing was charged, your cart is still here.</Banner>}
        {!status.checkout_ready && <Banner tone="warn">Online payment isn't set up for this club yet — you can browse, but checkout isn't available.</Banner>}

        {products === null ? (
          <div className="text-center font-mono text-[11px] text-pb-faint">Loading products…</div>
        ) : products.length === 0 ? (
          <div className="pb-card p-6 text-center text-pb-dim text-sm">Nothing in the store yet — check back soon.</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-[1fr_320px] gap-4 items-start">
            <div className="space-y-6">
              {Object.entries(grouped).map(([cat, items]) => (
                <div key={cat}>
                  <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">{cat.toUpperCase()}</div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {items.map(p => <ProductCard key={p.id} product={p} cart={cart} setCart={setCart} />)}
                  </div>
                </div>
              ))}
            </div>
            {status.checkout_ready && <CartPanel cart={cart} setCart={setCart} slug={slug} clubName={status.club_name} />}
          </div>
        )}
      </div>
    </div>
  )
}
