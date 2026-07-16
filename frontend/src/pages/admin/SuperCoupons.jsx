import { useEffect, useMemo, useState } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import { CORE, PRICED_MODULES, FANTASY } from '../../data/pricing'

// BetterCricket-managed discount coupons (migration 154) — Super Admin owns
// the whole lifecycle here; the corresponding Stripe Coupon is a pure sync
// target (services/stripe_client.sync_coupon_to_stripe), never hand-edited
// in the Stripe Dashboard. See services/discount_coupons.py for every rule
// enforced server-side — this page is a thin CRUD + force-apply front end.

const ALL_MODULES = [CORE, ...PRICED_MODULES, FANTASY]
const MODULE_NAME = Object.fromEntries(ALL_MODULES.map((m) => [m.key, m.name]))

const INPUT_CLS = 'w-full bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
const LABEL_CLS = 'font-mono text-[10px] text-pb-faint block mb-1'

function fmtDate(d) {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

function discountLabel(c) {
  return c.discount_type === 'percent' ? `${c.discount_value}%` : `$${c.discount_value}`
}

function durationLabel(c) {
  if (c.duration_mode === 'once') return 'Once'
  if (c.duration_mode === 'forever') return 'Forever'
  return `${c.duration_renewals || '?'} renewal${c.duration_renewals === 1 ? '' : 's'}`
}

function moduleLabel(keys) {
  if (!keys || keys.length === 0) return 'All modules'
  return keys.map((k) => MODULE_NAME[k] || k).join(', ')
}

const EMPTY_FORM = {
  code: '',
  display_name: '',
  discount_type: 'amount',
  discount_value: '',
  module_keys: [],
  redeem_window_start: '',
  redeem_window_end: '',
  new_signup_window_start: '',
  new_signup_window_end: '',
  loyalty_window_start: '',
  loyalty_window_end: '',
  duration_mode: 'once',
  duration_renewals: '',
  stackable_with_bundle: false,
  max_redemptions: '1',
}

function toFormValue(coupon) {
  if (!coupon) return { ...EMPTY_FORM }
  return {
    code: coupon.code,
    display_name: coupon.display_name,
    discount_type: coupon.discount_type,
    discount_value: String(coupon.discount_value),
    module_keys: coupon.module_keys || [],
    redeem_window_start: coupon.redeem_window_start || '',
    redeem_window_end: coupon.redeem_window_end || '',
    new_signup_window_start: coupon.new_signup_window_start || '',
    new_signup_window_end: coupon.new_signup_window_end || '',
    loyalty_window_start: coupon.loyalty_window_start || '',
    loyalty_window_end: coupon.loyalty_window_end || '',
    duration_mode: coupon.duration_mode,
    duration_renewals: coupon.duration_renewals ? String(coupon.duration_renewals) : '',
    stackable_with_bundle: !!coupon.stackable_with_bundle,
    max_redemptions: coupon.max_redemptions ? String(coupon.max_redemptions) : '',
  }
}

// Financial terms lock once a coupon has any redemption — mirrors the
// backend's FINANCIAL_FIELDS set in services/discount_coupons.py.
const FINANCIAL_FIELDS = new Set(['discount_type', 'discount_value', 'module_keys', 'duration_mode', 'duration_renewals'])

function CouponModal({ coupon, onClose, onSaved }) {
  const [form, setForm] = useState(() => toFormValue(coupon))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const isEdit = !!coupon
  const locked = isEdit && (coupon.redemption_count || 0) > 0

  const set = (field, value) => setForm((f) => ({ ...f, [field]: value }))
  const toggleModule = (key) => setForm((f) => ({
    ...f,
    module_keys: f.module_keys.includes(key) ? f.module_keys.filter((k) => k !== key) : [...f.module_keys, key],
  }))
  const dateOrNull = (v) => (v ? v : null)

  const save = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const payload = {
        display_name: form.display_name,
        module_keys: form.module_keys.length ? form.module_keys : null,
        redeem_window_start: dateOrNull(form.redeem_window_start),
        redeem_window_end: dateOrNull(form.redeem_window_end),
        new_signup_window_start: dateOrNull(form.new_signup_window_start),
        new_signup_window_end: dateOrNull(form.new_signup_window_end),
        loyalty_window_start: dateOrNull(form.loyalty_window_start),
        loyalty_window_end: dateOrNull(form.loyalty_window_end),
        stackable_with_bundle: form.stackable_with_bundle,
        max_redemptions: form.max_redemptions ? Number(form.max_redemptions) : null,
      }
      if (!locked) {
        payload.discount_type = form.discount_type
        payload.discount_value = Number(form.discount_value)
        payload.duration_mode = form.duration_mode
        payload.duration_renewals = form.duration_mode === 'repeating' ? Number(form.duration_renewals) : null
      }
      if (isEdit) {
        await api.superUpdateCoupon(coupon.id, payload)
      } else {
        await api.superCreateCoupon({ ...payload, code: form.code.trim().toUpperCase() })
      }
      onSaved()
    } catch (err) {
      setError(err.message || 'Could not save this coupon')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 p-4 overflow-y-auto" onClick={onClose}>
      <form onSubmit={save} onClick={(e) => e.stopPropagation()}
        className="pb-card w-full max-w-lg bg-pb-surface mt-16 max-h-[85vh] overflow-hidden flex flex-col">
        <div className="p-5 pb-0 shrink-0">
          <h2 className="font-display font-bold text-lg text-pb-text">{isEdit ? `Edit ${coupon.code}` : 'New coupon'}</h2>
          {locked && (
            <p className="font-mono text-[10px] text-amber-300 mt-1">
              This coupon has {coupon.redemption_count} redemption{coupon.redemption_count === 1 ? '' : 's'} —
              discount amount, type, module coverage and duration are locked. Deactivate and create a
              new coupon instead if these need to change.
            </p>
          )}
        </div>
        <div className="p-5 overflow-y-auto space-y-4">
          {!isEdit && (
            <div>
              <label className={LABEL_CLS}>Code</label>
              <input type="text" value={form.code} onChange={(e) => set('code', e.target.value)}
                className={INPUT_CLS} placeholder="WELCOME10" required autoFocus />
            </div>
          )}
          <div>
            <label className={LABEL_CLS}>Display name</label>
            <input type="text" value={form.display_name} onChange={(e) => set('display_name', e.target.value)}
              className={INPUT_CLS} placeholder="Launch promo" required />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={LABEL_CLS}>Discount type</label>
              <select value={form.discount_type} onChange={(e) => set('discount_type', e.target.value)}
                disabled={locked} className={INPUT_CLS}>
                <option value="amount">Dollar amount</option>
                <option value="percent">Percentage</option>
              </select>
            </div>
            <div>
              <label className={LABEL_CLS}>{form.discount_type === 'percent' ? 'Percent off' : 'Dollars off'}</label>
              <input type="number" min="0" step="0.01" value={form.discount_value}
                onChange={(e) => set('discount_value', e.target.value)} disabled={locked}
                className={INPUT_CLS} required />
            </div>
          </div>

          <div>
            <label className={LABEL_CLS}>Modules covered (none selected = all modules)</label>
            <div className="flex flex-wrap gap-2">
              {ALL_MODULES.map((m) => (
                <label key={m.key} className={`flex items-center gap-1.5 font-mono text-[10px] px-2 py-1 rounded border ${
                  form.module_keys.includes(m.key) ? 'border-pb-accent text-pb-text' : 'border-pb-hairline text-pb-faint'
                } ${locked ? 'opacity-50' : 'cursor-pointer'}`}>
                  <input type="checkbox" checked={form.module_keys.includes(m.key)}
                    onChange={() => toggleModule(m.key)} disabled={locked} className="w-3 h-3" />
                  {m.name}
                </label>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={LABEL_CLS}>Duration</label>
              <select value={form.duration_mode} onChange={(e) => set('duration_mode', e.target.value)}
                disabled={locked} className={INPUT_CLS}>
                <option value="once">Once (first payment only)</option>
                <option value="repeating">N renewals</option>
                <option value="forever">Forever (until removed)</option>
              </select>
            </div>
            {form.duration_mode === 'repeating' && (
              <div>
                <label className={LABEL_CLS}>Number of renewals</label>
                <input type="number" min="1" value={form.duration_renewals}
                  onChange={(e) => set('duration_renewals', e.target.value)} disabled={locked}
                  className={INPUT_CLS} required />
              </div>
            )}
          </div>

          <label className="flex items-center gap-2 font-mono text-[10px] text-pb-faint">
            <input type="checkbox" checked={form.stackable_with_bundle}
              onChange={(e) => set('stackable_with_bundle', e.target.checked)} disabled={locked} />
            Stackable with the bundle discount (a new club buying several modules at once keeps
            both discounts; otherwise this coupon replaces the bundle discount)
          </label>

          <div className="pt-3 border-t pb-hairline space-y-3">
            <p className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase">When the code can be entered</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={LABEL_CLS}>From</label>
                <input type="date" value={form.redeem_window_start}
                  onChange={(e) => set('redeem_window_start', e.target.value)} className={INPUT_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>Until</label>
                <input type="date" value={form.redeem_window_end}
                  onChange={(e) => set('redeem_window_end', e.target.value)} className={INPUT_CLS} />
              </div>
            </div>

            <p className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase pt-2">
              New-signup window (only usable at a club's first-ever subscribe, in this range)
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={LABEL_CLS}>From</label>
                <input type="date" value={form.new_signup_window_start}
                  onChange={(e) => set('new_signup_window_start', e.target.value)} className={INPUT_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>Until</label>
                <input type="date" value={form.new_signup_window_end}
                  onChange={(e) => set('new_signup_window_end', e.target.value)} className={INPUT_CLS} />
              </div>
            </div>

            <p className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase pt-2">
              Loyalty window (only usable by a club whose original join date falls in this range)
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={LABEL_CLS}>From</label>
                <input type="date" value={form.loyalty_window_start}
                  onChange={(e) => set('loyalty_window_start', e.target.value)} className={INPUT_CLS} />
              </div>
              <div>
                <label className={LABEL_CLS}>Until</label>
                <input type="date" value={form.loyalty_window_end}
                  onChange={(e) => set('loyalty_window_end', e.target.value)} className={INPUT_CLS} />
              </div>
            </div>
            <p className="font-mono text-[10px] text-pb-faintest">
              Leave a window's dates blank for no restriction from that rule. Both windows are
              independent — a coupon can leave either or both unset.
            </p>
          </div>

          <div>
            <label className={LABEL_CLS}>Max redemptions (blank = unlimited)</label>
            <input type="number" min="1" value={form.max_redemptions}
              onChange={(e) => set('max_redemptions', e.target.value)} className={INPUT_CLS} />
          </div>

          {error && <p className="font-mono text-[11px] text-pb-red">{error}</p>}
        </div>
        <div className="p-5 pt-3 border-t pb-hairline shrink-0 flex gap-2 justify-end">
          <button type="button" onClick={onClose} disabled={busy}
            className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded border pb-hairline text-pb-faint hover:text-pb-text disabled:opacity-50">
            Cancel
          </button>
          <button type="submit" disabled={busy}
            className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded font-semibold text-pb-bg disabled:opacity-50"
            style={{ background: 'var(--pb-accent)' }}>
            {busy ? 'SAVING…' : isEdit ? 'SAVE' : 'CREATE'}
          </button>
        </div>
      </form>
    </div>
  )
}

function RedemptionsModal({ coupon, onClose }) {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState('')

  const load = () => api.superCouponRedemptions(coupon.id).then(setRows).catch((e) => setError(e.message || 'Could not load redemptions'))
  useEffect(() => { load() }, [])

  const revoke = async (id) => {
    if (!window.confirm('Revoke this redemption? The club will be able to use this code again.')) return
    setBusyId(id)
    try {
      await api.superRevokeCouponRedemption(coupon.id, id)
      await load()
    } catch (e) {
      setError(e.message || 'Could not revoke this redemption')
    } finally {
      setBusyId('')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 p-4 overflow-y-auto" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="pb-card w-full max-w-md bg-pb-surface mt-16 max-h-[80vh] overflow-hidden flex flex-col">
        <div className="p-5 pb-3 shrink-0">
          <h2 className="font-display font-bold text-lg text-pb-text">{coupon.code} — redemptions</h2>
        </div>
        <div className="p-5 pt-0 overflow-y-auto space-y-2">
          {error && <p className="font-mono text-[11px] text-pb-red mb-2">{error}</p>}
          {rows === null ? (
            <p className="font-mono text-[11px] text-pb-faint">Loading…</p>
          ) : rows.length === 0 ? (
            <p className="font-mono text-[11px] text-pb-faint">No redemptions yet.</p>
          ) : (
            rows.map((r) => (
              <div key={r.id} className="flex items-center justify-between gap-2 font-mono text-[11px] border-b pb-hairline pb-2">
                <div>
                  <p className="text-pb-text">{r.organisation_name}</p>
                  <p className="text-pb-faint">
                    {fmtDate(r.redeemed_at)} · {r.applied_via === 'super_admin' ? 'super admin' : 'self-serve'} ·{' '}
                    <span className={r.status === 'active' ? 'text-emerald-400' : r.status === 'pending' ? 'text-amber-300' : 'text-pb-faint'}>
                      {r.status}
                    </span>
                  </p>
                </div>
                {r.status !== 'revoked' && (
                  <button onClick={() => revoke(r.id)} disabled={busyId === r.id}
                    className="font-mono text-[10px] tracking-wide2 px-2 py-1 rounded border border-pb-red/40 text-pb-red hover:bg-pb-red/10 disabled:opacity-50 shrink-0">
                    {busyId === r.id ? '…' : 'REVOKE'}
                  </button>
                )}
              </div>
            ))
          )}
        </div>
        <div className="p-5 pt-3 border-t pb-hairline shrink-0 flex justify-end">
          <button onClick={onClose} className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded border pb-hairline text-pb-faint hover:text-pb-text">
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

function ForceApplyModal({ coupon, onClose, onApplied }) {
  const [clubs, setClubs] = useState([])
  const [query, setQuery] = useState('')
  const [selectedClub, setSelectedClub] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { api.superListClubs().then(setClubs).catch(() => {}) }, [])

  const filtered = useMemo(() => {
    if (!query.trim()) return []
    const q = query.trim().toLowerCase()
    return clubs.filter((c) => (c.name || '').toLowerCase().includes(q)).slice(0, 10)
  }, [clubs, query])

  const apply = async () => {
    if (!selectedClub) return
    setBusy(true)
    setError('')
    try {
      await api.superForceApplyCoupon(selectedClub.id, coupon.code)
      onApplied()
    } catch (e) {
      setError(e.message || 'Could not apply this coupon')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 p-4 overflow-y-auto" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="pb-card w-full max-w-sm bg-pb-surface mt-16">
        <div className="p-5">
          <h2 className="font-display font-bold text-lg text-pb-text">Force-apply {coupon.code}</h2>
          <p className="font-mono text-[10px] text-pb-faintest mt-1 mb-3">
            Applies immediately to a club's already-live subscription, ahead of its next renewal —
            bypasses the redemption-window and max-redemptions checks (never the "already redeemed"
            or "inactive" ones). The club must already have an active Stripe subscription.
          </p>
          {!selectedClub ? (
            <>
              <input type="text" value={query} onChange={(e) => setQuery(e.target.value)}
                placeholder="Search clubs…" className={INPUT_CLS} autoFocus />
              {filtered.length > 0 && (
                <div className="mt-2 border pb-hairline rounded divide-y divide-pb-hairline max-h-48 overflow-y-auto">
                  {filtered.map((c) => (
                    <button key={c.id} onClick={() => setSelectedClub(c)}
                      className="w-full text-left px-2 py-1.5 font-mono text-[11px] text-pb-text hover:bg-pb-surface2">
                      {c.name}
                    </button>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="flex items-center justify-between font-mono text-[11px] bg-pb-surface2 rounded px-2 py-1.5">
              <span className="text-pb-text">{selectedClub.name}</span>
              <button onClick={() => setSelectedClub(null)} className="text-pb-faint hover:text-pb-text">Change</button>
            </div>
          )}
          {error && <p className="font-mono text-[11px] text-pb-red mt-2">{error}</p>}
        </div>
        <div className="p-5 pt-0 flex gap-2 justify-end">
          <button onClick={onClose} disabled={busy}
            className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded border pb-hairline text-pb-faint hover:text-pb-text disabled:opacity-50">
            Cancel
          </button>
          <button onClick={apply} disabled={busy || !selectedClub}
            className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded font-semibold text-pb-bg disabled:opacity-50"
            style={{ background: 'var(--pb-accent)' }}>
            {busy ? 'APPLYING…' : 'APPLY'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function SuperCoupons() {
  const [coupons, setCoupons] = useState(null)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(null)   // coupon object | 'new' | null
  const [redemptionsFor, setRedemptionsFor] = useState(null)
  const [forceApplyFor, setForceApplyFor] = useState(null)

  const load = () =>
    api.superListCoupons().then(setCoupons).catch((e) => setError(e.message || 'Could not load coupons'))
  useEffect(() => { load() }, [])

  const deactivate = async (c) => {
    if (!window.confirm(`Deactivate ${c.code}? It'll stop being redeemable, but existing redemptions are untouched.`)) return
    try {
      await api.superDeactivateCoupon(c.id)
      load()
    } catch (e) {
      setError(e.message || 'Could not deactivate this coupon')
    }
  }

  const activate = async (c) => {
    try {
      await api.superUpdateCoupon(c.id, { active: true })
      load()
    } catch (e) {
      setError(e.message || 'Could not reactivate this coupon')
    }
  }

  return (
    <AdminLayout>
      <div className="max-w-[1200px] mx-auto p-4 sm:p-6">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-pb-text">Discount coupons</h1>
            <p className="text-sm text-pb-dim mt-1">
              Managed entirely here — never in the Stripe Dashboard. The corresponding Stripe Coupon
              is synced automatically.
            </p>
          </div>
          <button onClick={() => setEditing('new')}
            className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded font-semibold text-pb-bg shrink-0"
            style={{ background: 'var(--pb-accent)' }}>
            + NEW COUPON
          </button>
        </div>

        {error && <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 mb-4">{error}</p>}

        {coupons === null ? (
          <p className="text-sm text-pb-dim">Loading…</p>
        ) : coupons.length === 0 ? (
          <div className="pb-card p-8 text-center">
            <p className="text-sm text-pb-dim">No coupons yet.</p>
          </div>
        ) : (
          <div className="pb-card overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint border-b pb-hairline">
                  <th className="px-3 py-2.5">Code</th>
                  <th className="px-3 py-2.5">Display name</th>
                  <th className="px-3 py-2.5">Discount</th>
                  <th className="px-3 py-2.5">Modules</th>
                  <th className="px-3 py-2.5">Duration</th>
                  <th className="px-3 py-2.5">Stacks?</th>
                  <th className="px-3 py-2.5">Redemptions</th>
                  <th className="px-3 py-2.5">Active</th>
                  <th className="px-3 py-2.5"></th>
                </tr>
              </thead>
              <tbody>
                {coupons.map((c) => (
                  <tr key={c.id} className="border-b pb-hairline align-top hover:bg-pb-surface2/40">
                    <td className="px-3 py-2.5 font-mono text-pb-text">{c.code}</td>
                    <td className="px-3 py-2.5 text-pb-text">{c.display_name}</td>
                    <td className="px-3 py-2.5 text-pb-dim">{discountLabel(c)}</td>
                    <td className="px-3 py-2.5 text-pb-dim">{moduleLabel(c.module_keys)}</td>
                    <td className="px-3 py-2.5 text-pb-dim">{durationLabel(c)}</td>
                    <td className="px-3 py-2.5 text-pb-dim">{c.stackable_with_bundle ? 'Yes' : 'No'}</td>
                    <td className="px-3 py-2.5 text-pb-dim">
                      {c.redemption_count}{c.max_redemptions ? ` / ${c.max_redemptions}` : ''}
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={`px-2 py-0.5 rounded-full border text-[10px] font-mono uppercase ${
                        c.active ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40' : 'bg-pb-surface2 text-pb-faint border-pb-hairline'
                      }`}>
                        {c.active ? 'active' : 'inactive'}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap space-y-1.5">
                      <button onClick={() => setEditing(c)}
                        className="block w-full font-mono text-[10px] tracking-wide2 uppercase text-pb-faint hover:text-pb-text border pb-hairline rounded px-2 py-1 hover:bg-pb-surface2 transition">
                        Edit
                      </button>
                      <button onClick={() => setRedemptionsFor(c)}
                        className="block w-full font-mono text-[10px] tracking-wide2 uppercase text-pb-faint hover:text-pb-text border pb-hairline rounded px-2 py-1 hover:bg-pb-surface2 transition">
                        Redemptions
                      </button>
                      {c.active && (
                        <button onClick={() => setForceApplyFor(c)}
                          className="block w-full font-mono text-[10px] tracking-wide2 uppercase text-pb-faint hover:text-pb-text border pb-hairline rounded px-2 py-1 hover:bg-pb-surface2 transition">
                          Force-apply…
                        </button>
                      )}
                      {c.active ? (
                        <button onClick={() => deactivate(c)}
                          className="block w-full font-mono text-[10px] tracking-wide2 uppercase text-pb-faint hover:text-red-400 border pb-hairline rounded px-2 py-1 hover:border-red-500/40 transition">
                          Deactivate
                        </button>
                      ) : (
                        <button onClick={() => activate(c)}
                          className="block w-full font-mono text-[10px] tracking-wide2 uppercase text-pb-faint hover:text-emerald-400 border pb-hairline rounded px-2 py-1 hover:border-emerald-500/40 transition">
                          Reactivate
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {editing && (
          <CouponModal
            coupon={editing === 'new' ? null : editing}
            onClose={() => setEditing(null)}
            onSaved={() => { setEditing(null); load() }}
          />
        )}
        {redemptionsFor && (
          <RedemptionsModal coupon={redemptionsFor} onClose={() => { setRedemptionsFor(null); load() }} />
        )}
        {forceApplyFor && (
          <ForceApplyModal
            coupon={forceApplyFor}
            onClose={() => setForceApplyFor(null)}
            onApplied={() => { setForceApplyFor(null); load() }}
          />
        )}
      </div>
    </AdminLayout>
  )
}
