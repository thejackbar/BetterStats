import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import AdminLayout from '../../components/admin/AdminLayout'
import { api } from '../../lib/api'
import { moduleBrand } from '../../lib/moduleBrand'

// Phase 19 (docs/self-serve-trial-onboarding-plan.md) — the club's own
// self-serve plan status page. A trial (any club admin) and a cancellation
// (primary admin only) both take effect instantly here — see
// POST /club-admin/modules/{key}/start-trial and .../cancel — no queue, no
// super-admin approval. Subscribe is a deliberate stub, NOT the
// module_action_requests queue (migration 119) — per direct instruction,
// online subscribing is landing in its own phase (Stripe checkout), so this
// button shouldn't quietly go through the human-actioned request queue in
// the meantime.
//
// The invoicing / Stripe checkout flow is being built behind
// plan.billing_checkout_enabled (super admin General Settings, off by
// default — see platform_settings.get_billing_checkout_enabled). While it's
// off, submitSubscribe always shows the stub notice below, regardless of how
// much of the real flow has landed here. Any real checkout call this grows
// into must also depend on require_billing_checkout_enabled server-side —
// this frontend check is UX only, not the actual gate.
const STATUS_LABEL = {
  subscribed: 'Subscribed',
  trial: 'In Trial',
  trial_expired: 'Trial Expired',
  never_trialed: 'Never Trialed',
}

const fmtDate = (d) =>
  d ? new Date(d).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' }) : null

// Survives the full-page redirect out to Stripe's setup-mode Checkout and
// back — see submitSubscribe's needs_payment_method branch.
const ADDON_RETRY_KEY = 'bs_addon_retry_modules'

export default function AdminAccount() {
  const [plan, setPlan] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [trialBusy, setTrialBusy] = useState('')
  const [msg, setMsg] = useState('')
  const [selected, setSelected] = useState(new Set())
  const [blockedMsg, setBlockedMsg] = useState('')
  const [primaryAdminName, setPrimaryAdminName] = useState('')
  const [cancelConfirm, setCancelConfirm] = useState(null) // { module, text } | null
  const [stripeNotice, setStripeNotice] = useState(false)
  // Real Stripe Checkout — only ever exercised once plan.billing_checkout_enabled
  // is true (see submitSubscribe below).
  const [quote, setQuote] = useState(null)
  const [checkoutBusy, setCheckoutBusy] = useState(false)
  const [invoices, setInvoices] = useState([])
  const [searchParams, setSearchParams] = useSearchParams()
  // Discount coupons (migration 154) — couponCode is what's typed in;
  // appliedCouponCode is the committed value the quote effect actually
  // sends, only updated on APPLY so re-selecting modules doesn't re-fire a
  // request on every keystroke. redeem* is the SEPARATE "apply a code to my
  // already-live subscription ahead of renewal" box, independent of module
  // selection entirely.
  const [couponCode, setCouponCode] = useState('')
  const [appliedCouponCode, setAppliedCouponCode] = useState('')
  const [couponError, setCouponError] = useState('')
  const [redeemCode, setRedeemCode] = useState('')
  const [redeemBusy, setRedeemBusy] = useState(false)
  const [redeemMsg, setRedeemMsg] = useState('')
  const [redeemError, setRedeemError] = useState('')

  const load = () =>
    api.accountGetPlan().then(setPlan).catch((e) => setError(e.message || 'Could not load your plan'))

  useEffect(() => { load() }, [])

  // Returning from a real Stripe Checkout Session — the redirect is UX only
  // (the webhook is what actually grants entitlement, see
  // routers/public_stripe.py), so this just shows a status and re-fetches the
  // plan; a moment's delay covers the small race where the webhook hasn't
  // landed yet by the time the browser bounces back.
  useEffect(() => {
    const checkout = searchParams.get('checkout')
    if (!checkout) return
    if (checkout === 'success') {
      const retryModules = sessionStorage.getItem(ADDON_RETRY_KEY)
      if (retryModules) {
        // That "success" was the setup-mode session adding a card, not a
        // real charge — finish the add-on purchase it was standing in for.
        sessionStorage.removeItem(ADDON_RETRY_KEY)
        setMsg('Payment method saved — finishing your purchase…')
        retryAddonPurchase(JSON.parse(retryModules))
      } else {
        setMsg(
          "Payment received — you're subscribed. It can take a few seconds to show below. "
          + "You'll receive an email confirming the subscription and payment."
        )
        setTimeout(load, 3000)
      }
    } else if (checkout === 'cancelled') {
      sessionStorage.removeItem(ADDON_RETRY_KEY)
      setMsg('Checkout was cancelled — nothing was charged.')
    }
    const next = new URLSearchParams(searchParams)
    next.delete('checkout')
    next.delete('session_id')
    setSearchParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    api.billingListInvoices().then(setInvoices).catch(() => {})
  }, [])

  // Live invoice preview for the current selection — only once billing
  // checkout is actually switched on (the endpoint 403s otherwise).
  useEffect(() => {
    if (!plan?.billing_checkout_enabled || selected.size === 0) {
      setQuote(null)
      return
    }
    let cancelled = false
    setCouponError('')
    api.billingQuote([...selected], appliedCouponCode)
      .then((q) => { if (!cancelled) setQuote(q) })
      .catch((e) => {
        if (cancelled) return
        if (appliedCouponCode) setCouponError(e.message || "That code couldn't be applied")
        setQuote(null)
      })
    return () => { cancelled = true }
  }, [plan?.billing_checkout_enabled, selected, appliedCouponCode])

  const applyCoupon = () => {
    setCouponError('')
    setAppliedCouponCode(couponCode.trim())
  }
  const clearCoupon = () => {
    setCouponCode('')
    setAppliedCouponCode('')
    setCouponError('')
  }

  const submitRedeem = async () => {
    if (!redeemCode.trim()) return
    setRedeemBusy(true)
    setRedeemError('')
    setRedeemMsg('')
    try {
      await api.couponRedeem(redeemCode.trim())
      setRedeemMsg("Code applied — it'll reduce your next renewal.")
      setRedeemCode('')
    } catch (e) {
      setRedeemError(e.message || "That code couldn't be applied")
    } finally {
      setRedeemBusy(false)
    }
  }

  useEffect(() => {
    api.getPrimaryAdmin()
      .then((d) => {
        const primary = (d?.admins || []).find((a) => a.is_primary_admin)
        if (primary) setPrimaryAdminName(primary.display_name || primary.username)
      })
      .catch(() => {})
  }, [])

  const rows = plan?.modules || []
  const selectedRows = rows.filter((r) => selected.has(r.module))
  // "Redeem a discount code" only ever discounts a module the club is
  // ALREADY paying for (redeem_for_existing_subscription only looks at
  // status === 'subscribed' rows) — plan.stripe_subscription_active just
  // means a Stripe subscription id exists on the club, which can be true
  // with every module still Trial/Never Trialed (e.g. everything on the
  // original subscription has since been cancelled). Without this check the
  // card renders anyway and any code typed in there fails with "doesn't
  // apply to any of your selected modules", since there's nothing held to
  // apply it to.
  const hasSubscribedModule = rows.some((r) => r.status === 'subscribed')

  // A Trial-status row, or a Never Trialed row, can be selected for the bulk
  // Subscribe request below — Never Trialed is included so a club can go
  // straight to subscribing without running a trial first. Starting a trial
  // and cancelling are both instant per-row buttons now, no bulk selection
  // needed for those. A non-primary admin can't select a row at all (only the
  // primary may request a paid subscription, same rule the backend enforces
  // regardless) — they get pointed at who can.
  const toggle = (row) => {
    if (row.status !== 'trial' && row.status !== 'never_trialed') return
    if (!plan?.is_primary_admin) {
      setBlockedMsg(
        `Only your club's Primary Admin User can subscribe to modules. Please contact ${primaryAdminName || "your club's primary admin"}.`
      )
      return
    }
    setBlockedMsg('')
    setStripeNotice(false)
    setSelected((s) => {
      const next = new Set(s)
      if (next.has(row.module)) next.delete(row.module)
      else next.add(row.module)
      return next
    })
  }

  const startRowTrial = async (moduleKey) => {
    setTrialBusy(moduleKey)
    setError('')
    setMsg('')
    try {
      await api.startModuleTrial(moduleKey)
      const name = rows.find((r) => r.module === moduleKey)?.name || moduleKey
      setMsg(`Trial started for ${name}.`)
      await load()
    } catch (e) {
      setError(e.message || 'Could not start the trial')
    } finally {
      setTrialBusy('')
    }
  }

  const openCancel = (moduleKey) => {
    setCancelConfirm({ module: moduleKey, text: '' })
    setError('')
    setMsg('')
  }
  const closeCancel = () => setCancelConfirm(null)

  const confirmCancel = async () => {
    if (!cancelConfirm || cancelConfirm.text.trim().toLowerCase() !== 'confirm') return
    setBusy(true)
    setError('')
    setMsg('')
    try {
      const row = rows.find((r) => r.module === cancelConfirm.module)
      await api.cancelModule(cancelConfirm.module, cancelConfirm.text)
      setMsg(
        cancelConfirm.module === 'core'
          ? "Cancelled your club's subscription to every BetterCricket module."
          : `Cancelled ${row?.name || cancelConfirm.module}.`
      )
      setCancelConfirm(null)
      await load()
    } catch (e) {
      setError(e.message || 'Could not cancel')
    } finally {
      setBusy(false)
    }
  }

  // While plan.billing_checkout_enabled is off, this is still the deliberate
  // stub — not a queued request (per direct instruction: online subscribing
  // shouldn't quietly go through the human-actioned module_action_requests
  // queue in the meantime). Once a super admin switches the flag on, this
  // either creates a real Stripe Checkout Session and redirects there (a
  // club with no subscription yet), or — a club that already has one —
  // charges the prorated add-on amount immediately against the card already
  // on file and returns { added: true } with no redirect at all, since
  // there's nothing new to collect. Either way the actual entitlement grant
  // is confirmed server-side (webhook for the redirect path, synchronously
  // for the add-on path), never here.
  const submitSubscribe = async () => {
    if (!plan?.billing_checkout_enabled) {
      setStripeNotice(true)
      return
    }
    setCheckoutBusy(true)
    setError('')
    try {
      const res = await api.billingCreateCheckoutSession([...selected], appliedCouponCode)
      if (res.needs_payment_method) {
        // The add-on charge failed because this club has no payment method
        // on file — res.url is a Stripe setup-mode session (add a card, no
        // charge). Remember which modules we were adding so the checkout=
        // success handler below can retry the exact same purchase once the
        // club is back with a card on file.
        sessionStorage.setItem(ADDON_RETRY_KEY, JSON.stringify([...selected]))
      }
      if (res.url) {
        window.location.href = res.url
        return
      }
      setMsg(
        `Added ${res.modules.length} module${res.modules.length === 1 ? '' : 's'} to your subscription. ` +
        "You'll receive an email confirming the subscription and payment."
      )
      setSelected(new Set())
      setQuote(null)
      clearCoupon()
      await load()
    } catch (e) {
      setError(e.message || 'Could not start checkout')
    } finally {
      setCheckoutBusy(false)
    }
  }

  // Re-attempts the same add-on purchase after a round trip to add a
  // payment method (see submitSubscribe's needs_payment_method branch) — a
  // second failure here is a real error (not just "still no card"), since
  // the club just came back from successfully adding one.
  const retryAddonPurchase = async (modules) => {
    setCheckoutBusy(true)
    try {
      const res = await api.billingCreateCheckoutSession(modules, '')
      if (res.url) {
        // Still needs a payment method somehow, or a brand new subscribe —
        // either way, follow the same redirect rule as a fresh attempt.
        window.location.href = res.url
        return
      }
      setMsg(
        `Added ${res.modules.length} module${res.modules.length === 1 ? '' : 's'} to your subscription. ` +
        "You'll receive an email confirming the subscription and payment."
      )
      setSelected(new Set())
      setQuote(null)
      await load()
    } catch (e) {
      setError(e.message || 'Could not finish adding the module(s) — your card was saved, try again below.')
    } finally {
      setCheckoutBusy(false)
    }
  }

  const hasSummary = selected.size > 0

  return (
    <AdminLayout>
      <div className={hasSummary ? 'max-w-5xl' : 'max-w-3xl'}>
        <h1 className="font-display font-bold text-2xl text-pb-text mb-1">Account</h1>
        <p className="font-mono text-[11px] text-pb-faint mb-6">
          Your club's plan, module by module.
        </p>

        {error && <p className="font-mono text-[11px] text-pb-red mb-4">{error}</p>}
        {msg && <p className="font-mono text-[11px] text-emerald-400 mb-4">{msg}</p>}
        {blockedMsg && (
          <p className="font-mono text-[11px] text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded px-3 py-2 mb-4">
            {blockedMsg}
          </p>
        )}

        {!plan ? (
          <p className="font-mono text-[11px] text-pb-faint">Loading…</p>
        ) : (
          // The price summary sits in its own sticky column once a module is
          // selected, instead of stacking below the module list — with 6
          // possible rows the list alone can push a summary that comes after
          // it below the fold, right when it's most useful (mid-selection).
          // lg:sticky keeps it in view as the list/billing history scroll;
          // below lg it just stacks under the list like before (a 2-column
          // layout doesn't fit smaller screens).
          <div className={hasSummary ? 'grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6 items-start' : ''}>
            <div>
              <div className="space-y-3 mb-4">
              {rows.map((row) => {
                const brand = moduleBrand(row.module)
                const pending = row.pending_requests.length > 0
                const showCheckbox = row.status === 'trial' || row.status === 'never_trialed'
                const showCancel = row.status === 'subscribed' && plan.is_primary_admin
                const showStartTrial = row.status === 'never_trialed' && row.trial_eligible
                const cancelling = cancelConfirm?.module === row.module

                return (
                  <div key={row.module} className="pb-card p-4">
                    <div className="flex items-center gap-4">
                      {showCheckbox ? (
                        <input
                          type="checkbox"
                          checked={selected.has(row.module)}
                          onChange={() => toggle(row)}
                          disabled={busy}
                          className="shrink-0 w-4 h-4"
                        />
                      ) : (
                        <span className="shrink-0 w-4" />
                      )}
                      <img src={brand.logo} alt="" className="w-6 h-6 rounded shrink-0" />
                      <div className="min-w-0 flex-1">
                        <p className="font-display font-bold text-sm text-pb-text truncate">{row.name}</p>
                        <p className="font-mono text-[10px] text-pb-faint">
                          {STATUS_LABEL[row.status]}
                          {row.status === 'subscribed' && row.renewal_date && ` · renews ${fmtDate(row.renewal_date)}`}
                          {row.status === 'trial' && row.trial_ends_at && ` · ends ${fmtDate(row.trial_ends_at)}`}
                          {row.status === 'trial_expired' && row.trial_ends_at && ` · ended ${fmtDate(row.trial_ends_at)}`}
                          {pending && (
                            <span className="text-pb-faintest">
                              {' · '}{row.pending_requests.includes('cancel') ? 'cancellation' : row.pending_requests[0]} requested
                            </span>
                          )}
                        </p>
                      </div>
                      {showCancel && !cancelling && (
                        <button
                          type="button"
                          onClick={() => openCancel(row.module)}
                          disabled={busy}
                          className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded border border-pb-red/40 text-pb-red hover:bg-pb-red/10 disabled:opacity-50 shrink-0"
                        >
                          CANCEL
                        </button>
                      )}
                      {showStartTrial && (
                        <button
                          type="button"
                          onClick={() => startRowTrial(row.module)}
                          disabled={trialBusy === row.module}
                          className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded border pb-hairline text-pb-text hover:bg-pb-surface2 disabled:opacity-50 shrink-0"
                        >
                          {trialBusy === row.module ? 'STARTING…' : 'START TRIAL'}
                        </button>
                      )}
                    </div>

                    {cancelling && (
                      <div className="mt-3 pt-3 border-t pb-hairline space-y-2">
                        <p className="font-mono text-[11px] text-pb-red">
                          {row.module === 'core'
                            ? "You are about to cancel your club's subscription to all BetterCricket modules."
                            : `You are about to cancel your club's subscription to ${row.name}.`}
                          {' '}Please type "confirm" to cancel.
                        </p>
                        <div className="flex gap-2">
                          <input
                            type="text"
                            value={cancelConfirm.text}
                            onChange={(e) => setCancelConfirm((c) => ({ ...c, text: e.target.value }))}
                            placeholder="confirm"
                            className="bg-pb-surface2 border pb-hairline rounded px-3 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
                          />
                          <button
                            onClick={confirmCancel}
                            disabled={busy || cancelConfirm.text.trim().toLowerCase() !== 'confirm'}
                            className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded font-semibold disabled:opacity-50 text-pb-bg bg-pb-red"
                          >
                            {busy ? 'CANCELLING…' : 'CONFIRM CANCEL'}
                          </button>
                          <button
                            onClick={closeCancel}
                            disabled={busy}
                            className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded border pb-hairline text-pb-faint hover:text-pb-text disabled:opacity-50"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            {plan.billing_checkout_enabled && plan.stripe_subscription_active && plan.is_primary_admin && hasSubscribedModule && (
              <div className="pb-card p-4 mt-6">
                <p className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mb-3">
                  Redeem a discount code
                </p>
                <p className="font-mono text-[11px] text-pb-faint mb-3">
                  Applies to your account's next renewal, not the current billing period — nothing is
                  charged today.
                </p>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={redeemCode}
                    onChange={(e) => setRedeemCode(e.target.value)}
                    placeholder="Discount code"
                    className="flex-1 bg-pb-surface2 border pb-hairline rounded px-3 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
                  />
                  <button
                    type="button"
                    onClick={submitRedeem}
                    disabled={redeemBusy || !redeemCode.trim()}
                    className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded border pb-hairline text-pb-text hover:bg-pb-surface2 disabled:opacity-50 shrink-0"
                  >
                    {redeemBusy ? 'APPLYING…' : 'REDEEM'}
                  </button>
                </div>
                {redeemMsg && <p className="font-mono text-[11px] text-emerald-400 mt-2">{redeemMsg}</p>}
                {redeemError && <p className="font-mono text-[11px] text-pb-red mt-2">{redeemError}</p>}
              </div>
            )}

            {invoices.length > 0 && (
              <div className="pb-card p-4 mt-6">
                <p className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mb-3">Billing history</p>
                <div className="space-y-2">
                  {invoices.map((inv) => (
                    <div key={inv.id} className="flex items-center gap-3 font-mono text-[11px]">
                      <span className="text-pb-faint w-24 shrink-0">{fmtDate(inv.period_end || inv.created_at)}</span>
                      <span className="text-pb-text w-20 shrink-0">${(inv.amount_paid / 100).toFixed(2)}</span>
                      <span className={`w-16 shrink-0 uppercase ${inv.status === 'paid' ? 'text-emerald-400' : 'text-amber-300'}`}>
                        {inv.status}
                      </span>
                      {inv.hosted_invoice_url && (
                        <a
                          href={inv.hosted_invoice_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-pb-faint hover:text-pb-text underline"
                        >
                          View invoice
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {selected.size > 0 && (
            <div className="pb-card p-4 lg:sticky lg:top-6">
              <p className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mb-3">
                {selected.size} module{selected.size === 1 ? '' : 's'} selected
              </p>
                {plan.billing_checkout_enabled && !plan.stripe_subscription_active && (
                  <div className="mb-3">
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={couponCode}
                        onChange={(e) => setCouponCode(e.target.value)}
                        placeholder="Have a discount code?"
                        className="flex-1 min-w-0 bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-[11px] font-mono focus:outline-none focus:border-pb-accent"
                      />
                      {appliedCouponCode ? (
                        <button
                          type="button"
                          onClick={clearCoupon}
                          className="font-mono text-[10px] tracking-wide2 px-2 py-1.5 rounded border pb-hairline text-pb-faint hover:text-pb-text shrink-0"
                        >
                          REMOVE
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={applyCoupon}
                          disabled={!couponCode.trim()}
                          className="font-mono text-[10px] tracking-wide2 px-2 py-1.5 rounded border pb-hairline text-pb-text hover:bg-pb-surface2 disabled:opacity-50 shrink-0"
                        >
                          APPLY
                        </button>
                      )}
                    </div>
                    {couponError && <p className="font-mono text-[10px] text-pb-red mt-1">{couponError}</p>}
                    {quote?.coupon && (
                      <p className="font-mono text-[10px] text-emerald-400 mt-1">
                        ✓ {quote.coupon.display_name} applied
                      </p>
                    )}
                  </div>
                )}
                {plan.billing_checkout_enabled && quote && quote.mode === 'new_subscription' && (
                  <div className="mb-3 space-y-1">
                    {quote.line_items.map((li) => (
                      <div key={li.key} className="flex items-center justify-between font-mono text-[11px] text-pb-faint">
                        <span>{li.name}</span>
                        <span>${li.price}/yr</span>
                      </div>
                    ))}
                    {quote.discount > 0 && (
                      <div className="flex items-center justify-between font-mono text-[11px] text-emerald-400">
                        <span>Bundle discount</span>
                        <span>-${quote.discount}</span>
                      </div>
                    )}
                    {quote.coupon && (
                      <div className="flex items-center justify-between font-mono text-[11px] text-emerald-400">
                        <span>{quote.coupon.display_name} ({quote.coupon.code})</span>
                        <span>-${quote.coupon.amount_off}</span>
                      </div>
                    )}
                    <div className="flex items-center justify-between font-mono text-[12px] text-pb-text font-semibold pt-2 mt-1 border-t pb-hairline">
                      <span>Total, billed annually</span>
                      <span>${quote.total}/yr</span>
                    </div>
                    <p className="font-mono text-[10px] text-pb-faintest pt-1">
                      Plus GST, calculated on Stripe's secure checkout page (this preview can't show
                      the exact figure until then).
                    </p>
                  </div>
                )}
                {plan.billing_checkout_enabled && quote && quote.mode === 'add_to_existing' && (
                  <div className="mb-3 space-y-2">
                    {quote.line_items.map((li, i) => (
                      <div key={i} className="space-y-0.5 pb-2 border-b pb-hairline last:border-0 last:pb-0">
                        <p className="font-mono text-[11px] text-pb-text font-semibold">{li.name}</p>
                        <div className="flex items-center justify-between font-mono text-[11px] text-pb-faint pl-2">
                          <span>Full annual price</span>
                          <span>${li.full_price.toFixed(2)}</span>
                        </div>
                        <div className="flex items-center justify-between font-mono text-[11px] text-pb-faint pl-2">
                          <span>Prorata deduction</span>
                          <span>-${li.deduction.toFixed(2)}</span>
                        </div>
                        <div className="flex items-center justify-between font-mono text-[11px] text-pb-text pl-2">
                          <span>Charged today (prorated)</span>
                          <span>${li.amount.toFixed(2)}</span>
                        </div>
                      </div>
                    ))}
                    <div className="flex items-center justify-between font-mono text-[12px] text-pb-text font-semibold pt-2 mt-1 border-t pb-hairline">
                      <span>Total charged today (prorated)</span>
                      <span>${quote.total.toFixed(2)}</span>
                    </div>
                    <p className="font-mono text-[10px] text-pb-faintest pt-1">
                      The price due is prorated to your account's current renewal date. Each added
                      module then renews at its full annual price from there, in step with your
                      account renewal date.
                    </p>
                  </div>
                )}
                {stripeNotice ? (
                  <p className="font-mono text-[11px] text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded px-3 py-2">
                    Online subscribing isn't connected yet — this is coming in a follow-up build.
                    In the meantime, contact the BetterCricket team directly to subscribe.
                  </p>
                ) : (
                  <button
                    onClick={submitSubscribe}
                    disabled={checkoutBusy}
                    className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded font-semibold text-pb-bg disabled:opacity-50"
                    style={{ background: 'var(--pb-accent)' }}
                  >
                    {checkoutBusy
                      ? (quote?.mode === 'add_to_existing' ? 'CHARGING…' : 'REDIRECTING…')
                      : !plan.billing_checkout_enabled ? 'SUBSCRIBE'
                      : quote?.mode === 'add_to_existing' ? 'CONFIRM & PAY PRORATED AMOUNT'
                      : 'PROCEED TO SECURE CHECKOUT'}
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
