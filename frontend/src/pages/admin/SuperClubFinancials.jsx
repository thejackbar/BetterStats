import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import { CORE, PRICED_MODULES, FANTASY } from '../../data/pricing'

// Super Admin per-club financial management (the request in
// claude/super-admin-financial-mgmt). One place a super admin runs a single
// club's money side: a trial/subscription summary with dates & day-counts, the
// primary admin's contact + the club's payment methods, subscribe/trial
// actions (BetterStats stays mandatory under any add-on), bundle-discount +
// coupon-aware quoting, raising a shareable invoice or entering a checkout on
// the club's behalf, and the full invoice history with a drilldown + email.
// Backed by routers/billing.py's /super/clubs/{orgId}/* routes.

const INPUT = 'bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
const LABEL = 'font-mono text-[10px] tracking-wide2 uppercase text-pb-faint block mb-1'
const BTN = 'font-mono text-[10px] tracking-wide2 px-2.5 py-1.5 rounded border pb-hairline text-pb-text hover:bg-pb-surface2 disabled:opacity-50'
const BTN_ACCENT = 'font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded font-semibold text-pb-bg disabled:opacity-50'
const BTN_RED = 'font-mono text-[10px] tracking-wide2 px-2.5 py-1.5 rounded border border-pb-red/40 text-pb-red hover:bg-pb-red/10 disabled:opacity-50'

// The billable modules, in display order, keyed to the backend billing keys.
const MODULES = [CORE, ...PRICED_MODULES, FANTASY]
const NAME_BY_KEY = Object.fromEntries(MODULES.map((m) => [m.key, m.name]))
// Add-ons the super admin can pick for a subscribe/invoice (Core is always
// force-included by the backend's price_for, so it isn't a checkbox).
const ADDON_MODULES = [...PRICED_MODULES, FANTASY]

const fmtMoney = (dollars) =>
  dollars == null ? '—' : `$${Number(dollars).toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const fmtCents = (cents) => fmtMoney((cents || 0) / 100)
const fmtDate = (iso) => {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

const STATUS_STYLE = {
  subscribed: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
  trial: 'bg-sky-500/15 text-sky-300 border-sky-500/40',
  trial_expired: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
  never_trialed: 'bg-pb-surface2 text-pb-faint border-pb-hairline',
  paused: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
  cancelled: 'bg-pb-red/15 text-pb-red border-pb-red/40',
}
const STATUS_LABEL = {
  subscribed: 'Subscribed', trial: 'In trial', trial_expired: 'Trial expired',
  never_trialed: 'Not started', paused: 'Paused', cancelled: 'Cancelled',
}

function StatusPill({ status }) {
  return (
    <span className={`shrink-0 px-2 py-0.5 rounded-full font-mono text-[9px] uppercase border ${STATUS_STYLE[status] || STATUS_STYLE.never_trialed}`}>
      {STATUS_LABEL[status] || status}
    </span>
  )
}

// ─── Club picker (shown when no ?club= is set) ─────────────────────────────
function ClubPicker({ onPick }) {
  const [clubs, setClubs] = useState(null)
  const [q, setQ] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    api.superListClubs().then(setClubs).catch((e) => setError(e.message || 'Could not load clubs'))
  }, [])
  const filtered = useMemo(() => {
    if (!clubs) return []
    const needle = q.trim().toLowerCase()
    return needle ? clubs.filter((c) => (c.name || '').toLowerCase().includes(needle)) : clubs
  }, [clubs, q])
  return (
    <div className="pb-card p-4 max-w-lg">
      <label className={LABEL}>Pick a club</label>
      <input className={`${INPUT} w-full mb-3`} placeholder="Search clubs…" value={q} onChange={(e) => setQ(e.target.value)} />
      {error && <p className="font-mono text-[11px] text-pb-red mb-2">{error}</p>}
      {clubs === null ? (
        <p className="font-mono text-[11px] text-pb-faint">Loading…</p>
      ) : (
        <div className="max-h-96 overflow-y-auto divide-y divide-pb-hairline">
          {filtered.map((c) => (
            <button key={c.id} onClick={() => onPick(c.id)}
              className="w-full text-left px-2 py-2 hover:bg-pb-surface2/50 text-sm text-pb-text">
              {c.name}
            </button>
          ))}
          {filtered.length === 0 && <p className="font-mono text-[11px] text-pb-faint py-2">No clubs match.</p>}
        </div>
      )}
    </div>
  )
}

// ─── Module summary row + per-module actions ───────────────────────────────
function ModuleRow({ orgId, row, coreRow, defaultTrialDays, onChanged, setMsg, setErr }) {
  const [busy, setBusy] = useState('')
  const run = async (label, fn) => {
    setBusy(label); setErr(''); setMsg('')
    try { await fn(); await onChanged() } catch (e) { setErr(e.message || 'Action failed') } finally { setBusy('') }
  }

  const isCore = row.module === 'core'
  const coreLive = coreRow && ['subscribed', 'trial'].includes(coreRow.status)

  const startTrial = () => run('trial', async () => {
    // BetterStats stays mandatory: an add-on trial needs Core live first.
    if (!isCore && !coreLive) await api.superStartModuleTrial(orgId, 'core', {})
    await api.superStartModuleTrial(orgId, row.module, {})
    setMsg(`${row.name} trial started`)
  })
  const pauseTrial = () => run('pause', async () => {
    await api.superPatchModule(orgId, row.module, { status: 'paused' }); setMsg(`${row.name} trial paused`)
  })
  const cancelTrial = () => run('cancel', async () => {
    await api.superPatchModule(orgId, row.module, { status: 'cancelled' }); setMsg(`${row.name} trial cancelled`)
  })
  const resume = () => run('resume', async () => {
    // A paused row keeps its renewal_date only if it was a real paid
    // subscription; a paused trial has none — so restore to the right state.
    await api.superPatchModule(orgId, row.module, { status: row.renewal_date ? 'active' : 'trial' })
    setMsg(`${row.name} resumed`)
  })
  const pauseSub = () => run('pausesub', async () => {
    await api.superPatchModule(orgId, row.module, { status: 'paused' }); setMsg(`${row.name} subscription paused`)
  })
  const cancelSub = () => run('cancelsub', async () => {
    if (!window.confirm(`Cancel ${row.name} subscription for this club?`)) return
    await api.superPatchModule(orgId, row.module, { status: 'cancelled' }); setMsg(`${row.name} subscription cancelled`)
  })
  const resetElig = () => run('reset', async () => {
    if (!window.confirm(`Reset ${row.name} trial eligibility? This clears its trial history so the club can trial it again.`)) return
    await api.superResetTrialEligibility(orgId, row.module); setMsg(`${row.name} trial eligibility reset`)
  })

  return (
    <div className="border-b pb-hairline py-3 last:border-0">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm text-pb-text font-medium">{row.name}</span>
          {isCore && <span className="font-mono text-[9px] text-pb-faintest uppercase">core</span>}
          <StatusPill status={row.status} />
          {row.prorated_days != null && (
            <span className="font-mono text-[9px] text-amber-300/80" title="Prorated days in the first period (added after BetterStats)">
              {row.prorated_days}d prorated
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 flex-wrap justify-end">
          {row.trial_eligible && (
            <button onClick={startTrial} disabled={!!busy} className={BTN}>{busy === 'trial' ? '…' : 'START TRIAL'}</button>
          )}
          {row.status === 'trial' && (
            <>
              <button onClick={pauseTrial} disabled={!!busy} className={BTN}>{busy === 'pause' ? '…' : 'PAUSE'}</button>
              <button onClick={cancelTrial} disabled={!!busy} className={BTN_RED}>{busy === 'cancel' ? '…' : 'CANCEL TRIAL'}</button>
            </>
          )}
          {row.status === 'subscribed' && (
            <>
              <button onClick={pauseSub} disabled={!!busy} className={BTN}>{busy === 'pausesub' ? '…' : 'PAUSE'}</button>
              <button onClick={cancelSub} disabled={!!busy} className={BTN_RED}>{busy === 'cancelsub' ? '…' : 'CANCEL SUB'}</button>
            </>
          )}
          {row.status === 'paused' && (
            <button onClick={resume} disabled={!!busy} className={BTN}>{busy === 'resume' ? '…' : 'RESUME'}</button>
          )}
          {['trial_expired', 'cancelled', 'paused'].includes(row.status) && !row.trial_eligible && (
            <button onClick={resetElig} disabled={!!busy} className={BTN}>{busy === 'reset' ? '…' : 'RESET ELIGIBILITY'}</button>
          )}
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-2 font-mono text-[10px] text-pb-faint">
        <div><span className="text-pb-faintest">Trial</span><br />{fmtDate(row.trial_started_at)} → {fmtDate(row.trial_ends_at)}</div>
        <div><span className="text-pb-faintest">First sub</span><br />{fmtDate(row.first_subscription_date)}</div>
        <div><span className="text-pb-faintest">Renewal</span><br />{fmtDate(row.renewal_date)}</div>
        <div>
          <span className="text-pb-faintest">Days left</span><br />
          {row.days_remaining == null ? '—' : `${row.days_remaining} day${Math.abs(row.days_remaining) === 1 ? '' : 's'}`}
        </div>
      </div>
    </div>
  )
}

// ─── Payment methods card ──────────────────────────────────────────────────
function PaymentMethods({ orgId, hasCustomer, setErr, setMsg }) {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState('')
  const load = useCallback(() => {
    if (!hasCustomer) { setData({ payment_methods: [] }); return }
    api.superListPaymentMethods(orgId).then(setData).catch((e) => setErr(e.message || 'Could not load payment methods'))
  }, [orgId, hasCustomer, setErr])
  useEffect(() => { load() }, [load])

  const add = async () => {
    setBusy('add'); setErr('')
    try {
      const res = await api.superCreatePaymentMethodSetupSession(orgId)
      window.open(res.url, '_blank', 'noopener')
      setMsg('Opened a secure page to add a payment method — refresh once done.')
    } catch (e) { setErr(e.message || 'Could not start adding a payment method') } finally { setBusy('') }
  }
  const setDefault = async (pmId) => {
    setBusy(pmId); setErr('')
    try { setData(await api.superSetDefaultPaymentMethod(orgId, pmId)) }
    catch (e) { setErr(e.message || 'Could not set default') } finally { setBusy('') }
  }
  const remove = async (pmId) => {
    if (!window.confirm('Remove this payment method?')) return
    setBusy(pmId); setErr('')
    try { setData(await api.superRemovePaymentMethod(orgId, pmId)) }
    catch (e) { setErr(e.message || 'Could not remove') } finally { setBusy('') }
  }

  return (
    <div className="pb-card p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-display font-bold text-pb-text">Payment methods</h2>
        <button onClick={load} className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">Refresh</button>
      </div>
      {!hasCustomer ? (
        <p className="font-mono text-[11px] text-pb-faint">No billing account yet — the club gets one on its first checkout or invoice.</p>
      ) : data === null ? (
        <p className="font-mono text-[11px] text-pb-faint">Loading…</p>
      ) : !data.payment_methods.length ? (
        <p className="font-mono text-[11px] text-pb-faint">No payment methods on file.</p>
      ) : (
        <div className="space-y-2">
          {data.payment_methods.map((pm) => (
            <div key={pm.id} className="flex items-center justify-between gap-2 font-mono text-[11px] border-b pb-hairline pb-2 last:border-0">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-pb-text truncate">{pm.summary}</span>
                {pm.is_default && (
                  <span className="shrink-0 px-1.5 py-0.5 rounded-full text-[9px] uppercase bg-emerald-500/15 text-emerald-300 border border-emerald-500/40">Default</span>
                )}
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                {!pm.is_default && <button onClick={() => setDefault(pm.id)} disabled={busy === pm.id} className={BTN}>{busy === pm.id ? '…' : 'SET DEFAULT'}</button>}
                {data.payment_methods.length > 1 && <button onClick={() => remove(pm.id)} disabled={busy === pm.id} className={BTN_RED}>{busy === pm.id ? '…' : 'REMOVE'}</button>}
              </div>
            </div>
          ))}
        </div>
      )}
      <button onClick={add} disabled={busy === 'add'} className={`${BTN} mt-3`}>{busy === 'add' ? 'OPENING…' : '+ RECORD A PAYMENT METHOD (new tab)'}</button>
    </div>
  )
}

// ─── Subscribe / raise-invoice panel ───────────────────────────────────────
function SubscribePanel({ orgId, summary, onChanged, setErr, setMsg }) {
  const [selected, setSelected] = useState([])
  const [coupon, setCoupon] = useState('')
  const [appliedCoupon, setAppliedCoupon] = useState('')
  const [quote, setQuote] = useState(null)
  const [quoting, setQuoting] = useState(false)
  const [busy, setBusy] = useState('')
  const [daysDue, setDaysDue] = useState(14)
  const [altName, setAltName] = useState('')
  const [altEmail, setAltEmail] = useState('')
  const [lastInvoice, setLastInvoice] = useState(null)

  const canSubscribeByKey = Object.fromEntries((summary?.modules || []).map((m) => [m.module, m.can_subscribe]))

  const toggle = (key) => setSelected((cur) => cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key])

  const loadQuote = useCallback(async () => {
    if (!selected.length) { setQuote(null); return }
    setQuoting(true); setErr('')
    try { setQuote(await api.superFinancialQuote(orgId, selected, appliedCoupon || undefined)) }
    catch (e) { setErr(e.message || 'Could not price this'); setQuote(null) } finally { setQuoting(false) }
  }, [orgId, selected, appliedCoupon, setErr])
  useEffect(() => { loadQuote() }, [loadQuote])

  const createInvoice = async () => {
    if (!selected.length) return
    setBusy('invoice'); setErr(''); setMsg(''); setLastInvoice(null)
    try {
      const res = await api.superFinancialCreateInvoice(orgId, {
        module_keys: selected, coupon_code: appliedCoupon || undefined,
        days_until_due: Number(daysDue) || 14, send_email: true,
        recipient_name: altName || undefined, recipient_email: altEmail || undefined,
      })
      setLastInvoice(res.invoice || null)
      setMsg(res.email?.error
        ? `Invoice raised. Email problem: ${res.email.error}`
        : `Invoice raised${res.email?.sent_to ? ` and emailed to ${res.email.sent_to}` : ''}.`)
      setSelected([]); setAppliedCoupon(''); setCoupon('')
      await onChanged()
    } catch (e) { setErr(e.message || 'Could not raise the invoice') } finally { setBusy('') }
  }

  const enterCheckout = async () => {
    if (!selected.length) return
    setBusy('checkout'); setErr(''); setMsg('')
    try {
      const res = await api.superFinancialCheckoutSession(orgId, selected, appliedCoupon || undefined)
      if (res.url) { window.open(res.url, '_blank', 'noopener'); setMsg('Opened Stripe Checkout in a new tab — complete payment there.') }
      else if (res.added) { setMsg(`Added: ${res.modules.map((k) => NAME_BY_KEY[k] || k).join(', ')}`); setSelected([]); await onChanged() }
      else if (res.needs_payment_method && res.url) { window.open(res.url, '_blank', 'noopener'); setMsg('No card on file — opened a page to add one, then retry.') }
    } catch (e) { setErr(e.message || 'Could not start checkout') } finally { setBusy('') }
  }

  return (
    <div className="pb-card p-4">
      <h2 className="font-display font-bold text-pb-text mb-1">Subscribe / raise an invoice</h2>
      <p className="font-mono text-[10px] text-pb-faint mb-3">
        BetterStats (Core) is included automatically under any add-on. Bundle discounts apply to the priced modules.
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-3">
        {ADDON_MODULES.map((m) => {
          const disabled = canSubscribeByKey[m.key] === false
          return (
            <label key={m.key} className={`flex items-center gap-2 px-2 py-1.5 rounded border pb-hairline text-sm ${disabled ? 'opacity-40' : 'cursor-pointer hover:bg-pb-surface2/40'}`}>
              <input type="checkbox" disabled={disabled} checked={selected.includes(m.key)} onChange={() => toggle(m.key)} />
              <span className="text-pb-text">{m.name}</span>
              <span className="font-mono text-[10px] text-pb-faint ml-auto">${m.price}</span>
            </label>
          )
        })}
      </div>

      <div className="flex items-end gap-2 mb-3 flex-wrap">
        <div>
          <label className={LABEL}>Coupon code</label>
          <input className={INPUT} value={coupon} onChange={(e) => setCoupon(e.target.value.toUpperCase())} placeholder="OPTIONAL" />
        </div>
        {appliedCoupon ? (
          <button onClick={() => { setAppliedCoupon(''); setCoupon('') }} className={BTN}>REMOVE</button>
        ) : (
          <button onClick={() => setAppliedCoupon(coupon.trim())} disabled={!coupon.trim()} className={BTN}>APPLY</button>
        )}
      </div>

      {quoting ? (
        <p className="font-mono text-[11px] text-pb-faint mb-3">Pricing…</p>
      ) : quote && quote.mode === 'new_subscription' ? (
        <div className="bg-pb-surface2/40 rounded p-3 mb-3 font-mono text-[11px] text-pb-dim space-y-1">
          {quote.line_items.map((li) => (
            <div key={li.key} className="flex justify-between"><span>{li.name}</span><span>{fmtMoney(li.price)}</span></div>
          ))}
          {quote.discount > 0 && <div className="flex justify-between text-emerald-300"><span>Bundle discount</span><span>−{fmtMoney(quote.discount)}</span></div>}
          {quote.coupon && <div className="flex justify-between text-sky-300"><span>Coupon {quote.coupon.code}</span><span>−{fmtMoney(quote.coupon.amount_off)}</span></div>}
          <div className="flex justify-between text-pb-text font-semibold border-t pb-hairline pt-1"><span>Total / yr</span><span>{fmtMoney(quote.total)}</span></div>
          <p className="text-pb-faintest text-[10px] pt-1">Plus GST, calculated on Stripe's secure checkout/invoice.</p>
        </div>
      ) : quote && quote.mode === 'add_to_existing' ? (
        <div className="bg-pb-surface2/40 rounded p-3 mb-3 font-mono text-[11px] text-pb-dim space-y-1">
          {quote.line_items.map((li) => (
            <div key={li.key} className="flex justify-between"><span>{li.name} (prorated)</span><span>{fmtMoney(li.amount)}</span></div>
          ))}
          <div className="flex justify-between text-pb-text font-semibold border-t pb-hairline pt-1"><span>Charged today</span><span>{fmtMoney(quote.total)}</span></div>
          <p className="text-pb-faintest text-[10px] pt-1">Adds to the live subscription — no bundle discount on add-ons.</p>
        </div>
      ) : null}

      {!summary?.stripe?.has_subscription && (
        <div className="flex items-end gap-2 mb-3 flex-wrap">
          <div>
            <label className={LABEL}>Invoice due (days)</label>
            <input type="number" min="1" className={`${INPUT} w-24`} value={daysDue} onChange={(e) => setDaysDue(e.target.value)} />
          </div>
          <div>
            <label className={LABEL}>Send to (name)</label>
            <input className={INPUT} value={altName} onChange={(e) => setAltName(e.target.value)} placeholder="Primary admin" />
          </div>
          <div>
            <label className={LABEL}>Send to (email)</label>
            <input className={INPUT} value={altEmail} onChange={(e) => setAltEmail(e.target.value)} placeholder="Primary admin's email" />
          </div>
        </div>
      )}

      <div className="flex gap-2 flex-wrap">
        {!summary?.stripe?.has_subscription && (
          <button onClick={createInvoice} disabled={!selected.length || !!busy}
            className={BTN_ACCENT} style={{ background: 'var(--pb-accent)' }}>
            {busy === 'invoice' ? 'RAISING…' : 'CREATE & EMAIL INVOICE'}
          </button>
        )}
        <button onClick={enterCheckout} disabled={!selected.length || !!busy} className={BTN}>
          {busy === 'checkout' ? 'OPENING…' : summary?.stripe?.has_subscription ? 'ADD & CHARGE ON FILE' : 'ENTER PAYMENT ON THEIR BEHALF'}
        </button>
      </div>

      {lastInvoice?.hosted_invoice_url && (
        <div className="mt-3 font-mono text-[11px] text-pb-dim">
          Invoice {lastInvoice.number || ''} · {fmtMoney(lastInvoice.total)} ·{' '}
          <a href={lastInvoice.hosted_invoice_url} target="_blank" rel="noreferrer" className="text-pb-accent underline">shareable pay link</a>
        </div>
      )}
    </div>
  )
}

// ─── Invoice detail modal ──────────────────────────────────────────────────
function InvoiceModal({ orgId, invoice, onClose, setErr, setMsg }) {
  const [detail, setDetail] = useState(null)
  const [busy, setBusy] = useState('')
  const [altName, setAltName] = useState('')
  const [altEmail, setAltEmail] = useState('')
  useEffect(() => {
    api.superFinancialInvoiceDetail(orgId, invoice.id).then(setDetail).catch((e) => setErr(e.message || 'Could not load invoice'))
  }, [orgId, invoice.id, setErr])

  const send = async () => {
    setBusy('send'); setErr('')
    try {
      const res = await api.superFinancialSendInvoice(orgId, invoice.id, {
        recipient_name: altName || undefined, recipient_email: altEmail || undefined,
      })
      setMsg(`Invoice emailed to ${res.sent_to}`); onClose()
    } catch (e) { setErr(e.message || 'Could not send the invoice') } finally { setBusy('') }
  }

  const s = detail?.stripe
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 p-4 overflow-y-auto" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="pb-card w-full max-w-lg bg-pb-surface mt-12">
        <div className="p-5 pb-3 flex items-center justify-between">
          <h2 className="font-display font-bold text-lg text-pb-text">
            Invoice {invoice.invoice_number || (s && s.number) || ''}
          </h2>
          <StatusPill status={invoice.settled ? 'subscribed' : invoice.status === 'open' ? 'trial' : 'cancelled'} />
        </div>
        <div className="px-5 pb-4 font-mono text-[11px] text-pb-dim space-y-1.5">
          <div className="flex justify-between"><span className="text-pb-faint">Raised</span><span>{fmtDate(invoice.created_at)}</span></div>
          <div className="flex justify-between"><span className="text-pb-faint">Source</span><span>{invoice.source || 'subscription'}</span></div>
          <div className="border-t pb-hairline pt-2 mt-2 space-y-1">
            {(invoice.line_items || []).map((li, i) => (
              <div key={i} className="flex justify-between"><span>{li.name}</span><span>{fmtMoney(li.price ?? li.amount)}</span></div>
            ))}
          </div>
          {invoice.bundle_discount_cents > 0 && (
            <div className="flex justify-between text-emerald-300"><span>Bundle discount</span><span>−{fmtCents(invoice.bundle_discount_cents)}</span></div>
          )}
          {invoice.coupon_code && (
            <div className="flex justify-between text-sky-300">
              <span>Coupon {invoice.coupon_code}{invoice.coupon_pct_of_invoice != null ? ` (${invoice.coupon_pct_of_invoice}%)` : ''}</span>
              <span>−{fmtCents(invoice.coupon_discount_cents)}</span>
            </div>
          )}
          <div className="flex justify-between"><span className="text-pb-faint">GST</span><span>{fmtCents(invoice.tax_cents)}</span></div>
          <div className="flex justify-between text-pb-text font-semibold border-t pb-hairline pt-2 mt-1"><span>Amount due</span><span>{fmtCents(invoice.amount_due)}</span></div>
          <div className="flex justify-between"><span className="text-pb-faint">Amount paid</span><span>{fmtCents(invoice.amount_paid)}</span></div>
          {s && s.amount_remaining > 0 && <div className="flex justify-between text-amber-300"><span>Remaining</span><span>{fmtMoney(s.amount_remaining)}</span></div>}
          <div className="flex justify-between"><span className="text-pb-faint">Settled</span><span>{invoice.settled ? 'Yes' : 'No'}</span></div>
          <div className="flex justify-between"><span className="text-pb-faint">Payment method</span><span>{invoice.payment_method_summary || '—'}</span></div>
          {invoice.hosted_invoice_url && (
            <div className="pt-1"><a href={invoice.hosted_invoice_url} target="_blank" rel="noreferrer" className="text-pb-accent underline">Open hosted invoice / pay page</a></div>
          )}
          {invoice.invoice_pdf && (
            <div><a href={invoice.invoice_pdf} target="_blank" rel="noreferrer" className="text-pb-accent underline">Download PDF</a></div>
          )}
        </div>
        <div className="p-5 pt-3 border-t pb-hairline">
          <p className={LABEL}>Email this invoice</p>
          <div className="flex items-end gap-2 flex-wrap">
            <input className={INPUT} value={altName} onChange={(e) => setAltName(e.target.value)} placeholder="Name (primary admin)" />
            <input className={INPUT} value={altEmail} onChange={(e) => setAltEmail(e.target.value)} placeholder="Email (primary admin)" />
            <button onClick={send} disabled={busy === 'send' || !invoice.hosted_invoice_url} className={BTN_ACCENT} style={{ background: 'var(--pb-accent)' }}>
              {busy === 'send' ? 'SENDING…' : 'SEND'}
            </button>
            <button onClick={onClose} className={BTN}>CLOSE</button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Main page ─────────────────────────────────────────────────────────────
export default function SuperClubFinancials() {
  const [params, setParams] = useSearchParams()
  const orgId = params.get('club') || ''
  const [summary, setSummary] = useState(null)
  const [invoices, setInvoices] = useState([])
  const [openInvoice, setOpenInvoice] = useState(null)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    if (!orgId) return
    setLoading(true); setError('')
    try {
      const [s, inv] = await Promise.all([
        api.superFinancialSummary(orgId),
        api.superFinancialInvoices(orgId).catch(() => []),
      ])
      setSummary(s); setInvoices(inv)
    } catch (e) { setError(e.message || 'Could not load the club financials') } finally { setLoading(false) }
  }, [orgId])
  useEffect(() => { load() }, [load])

  if (!orgId) {
    return (
      <AdminLayout>
        <div className="max-w-[1200px] mx-auto p-4 sm:p-6">
          <h1 className="text-xl font-semibold text-pb-text mb-1">Club financials</h1>
          <p className="text-sm text-pb-dim mb-5">Manage a single club's trials, subscriptions, invoices and payments.</p>
          <ClubPicker onPick={(id) => setParams({ club: id })} />
        </div>
      </AdminLayout>
    )
  }

  const coreRow = summary?.modules?.find((m) => m.module === 'core')
  const contact = summary?.primary_admin

  return (
    <AdminLayout>
      <div className="max-w-[1200px] mx-auto p-4 sm:p-6">
        <div className="flex items-center justify-between mb-5 flex-wrap gap-2">
          <div>
            <button onClick={() => setParams({})} className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text mb-1">← All clubs</button>
            <h1 className="text-xl font-semibold text-pb-text">{summary?.club?.name || 'Club'} — financials</h1>
            {summary && !summary.billing_checkout_enabled && (
              <p className="font-mono text-[10px] text-amber-300/80 mt-1">Online checkout is OFF for this club — invoices/checkout will report "not configured" until enabled.</p>
            )}
          </div>
          <button onClick={load} className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">Refresh</button>
        </div>

        {error && <p className="text-sm text-pb-red bg-pb-red/10 border border-pb-red/20 rounded-lg px-4 py-3 mb-4">{error}</p>}
        {msg && <p className="text-sm text-emerald-300 bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-4 py-3 mb-4">{msg}</p>}

        {loading && !summary ? (
          <p className="text-sm text-pb-dim">Loading…</p>
        ) : !summary ? null : (
          <div className="space-y-6">
            {/* Summary + module actions */}
            <div className="pb-card p-4">
              <h2 className="font-display font-bold text-pb-text mb-2">Trials & subscriptions</h2>
              {summary.modules.map((row) => (
                <ModuleRow key={row.module} orgId={orgId} row={row} coreRow={coreRow}
                  defaultTrialDays={summary.default_trial_days} onChanged={load} setMsg={setMsg} setErr={setError} />
              ))}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <SubscribePanel orgId={orgId} summary={summary} onChanged={load} setErr={setError} setMsg={setMsg} />

              <div className="space-y-6">
                {/* Contact */}
                <div className="pb-card p-4">
                  <h2 className="font-display font-bold text-pb-text mb-3">Primary admin</h2>
                  <div className="font-mono text-[11px] text-pb-dim space-y-1.5">
                    <div className="flex justify-between"><span className="text-pb-faint">Name</span><span className="text-pb-text">{contact?.name || '—'}</span></div>
                    <div className="flex justify-between"><span className="text-pb-faint">Email</span><span className="text-pb-text">{contact?.email || '—'}</span></div>
                    <div className="flex justify-between"><span className="text-pb-faint">Mobile</span><span className="text-pb-text">{contact?.mobile || '—'}</span></div>
                    {contact && !contact.is_primary && <p className="text-amber-300/80 text-[10px]">No primary admin flagged — showing the earliest club admin.</p>}
                  </div>
                </div>
                <PaymentMethods orgId={orgId} hasCustomer={summary.stripe.has_customer} setErr={setError} setMsg={setMsg} />
              </div>
            </div>

            {/* Invoices */}
            <div>
              <h2 className="font-display font-bold text-pb-text mb-2">Invoices</h2>
              <div className="pb-card overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint border-b pb-hairline">
                      <th className="px-3 py-2.5">Number</th>
                      <th className="px-3 py-2.5">Raised</th>
                      <th className="px-3 py-2.5">Amount</th>
                      <th className="px-3 py-2.5">GST</th>
                      <th className="px-3 py-2.5">Status</th>
                      <th className="px-3 py-2.5">Settled</th>
                      <th className="px-3 py-2.5"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {invoices.length === 0 ? (
                      <tr><td colSpan={7} className="px-3 py-4 text-pb-faint font-mono text-[11px]">No invoices yet.</td></tr>
                    ) : invoices.map((r) => (
                      <tr key={r.id} className="border-b pb-hairline hover:bg-pb-surface2/40 cursor-pointer" onClick={() => setOpenInvoice(r)}>
                        <td className="px-3 py-2 font-mono text-pb-text">{r.invoice_number || '—'}</td>
                        <td className="px-3 py-2 text-pb-dim">{fmtDate(r.created_at)}</td>
                        <td className="px-3 py-2 font-mono text-pb-text">{fmtCents(r.amount_due)}</td>
                        <td className="px-3 py-2 font-mono text-pb-dim">{fmtCents(r.tax_cents)}</td>
                        <td className="px-3 py-2"><StatusPill status={r.settled ? 'subscribed' : r.status === 'open' ? 'trial' : 'cancelled'} /></td>
                        <td className="px-3 py-2 font-mono text-pb-dim">{r.settled ? 'Yes' : 'No'}</td>
                        <td className="px-3 py-2 text-right font-mono text-[10px] text-pb-accent">DETAIL →</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>

      {openInvoice && (
        <InvoiceModal orgId={orgId} invoice={openInvoice} onClose={() => setOpenInvoice(null)} setErr={setError} setMsg={setMsg} />
      )}
    </AdminLayout>
  )
}
