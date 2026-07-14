import { useEffect, useState } from 'react'
import AdminLayout from '../../components/admin/AdminLayout'
import { api } from '../../lib/api'
import { moduleBrand } from '../../lib/moduleBrand'

// Phase 19 (docs/self-serve-trial-onboarding-plan.md) — the club's own
// self-serve plan status page. Trial and cancel actions still queue into the
// existing module_action_requests table (migration 119) — the same queue the
// Super Admin's Module requests page already actions, unchanged. Subscribe
// is NOT that queue (per direct instruction — a subscription is a real
// payment, not a request for a human to action) and is a placeholder until
// the Stripe checkout integration lands in its own phase.
const STATUS_LABEL = {
  subscribed: 'Subscribed',
  trial: 'In Trial',
  trial_expired: 'Trial Expired',
  never_trialed: 'Never Trialed',
}

const fmtDate = (d) =>
  d ? new Date(d).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' }) : null

export default function AdminAccount() {
  const [plan, setPlan] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [selected, setSelected] = useState(new Set())
  const [confirmUnsubscribe, setConfirmUnsubscribe] = useState(false)
  const [confirmText, setConfirmText] = useState('')
  const [stripeNotice, setStripeNotice] = useState(false)

  const load = () =>
    api.accountGetPlan().then(setPlan).catch((e) => setError(e.message || 'Could not load your plan'))

  useEffect(() => { load() }, [])

  const rows = plan?.modules || []
  const selectedRows = rows.filter((r) => selected.has(r.module))
  const toggle = (moduleKey) => {
    setSelected((s) => {
      const next = new Set(s)
      if (next.has(moduleKey)) next.delete(moduleKey)
      else next.add(moduleKey)
      return next
    })
    setConfirmUnsubscribe(false)
    setConfirmText('')
    setStripeNotice(false)
  }

  const anyTrialEligible = selectedRows.some((r) => r.trial_eligible && r.pending_requests.length === 0)
  const anySubscribable = selectedRows.some((r) => r.can_subscribe)
  const anySubscribed = selectedRows.some((r) => r.status === 'subscribed' && r.pending_requests.length === 0)

  const finishAction = async (msgText) => {
    setMsg(msgText)
    setSelected(new Set())
    setConfirmUnsubscribe(false)
    setConfirmText('')
    setStripeNotice(false)
    await load()
    setBusy(false)
  }

  const startTrial = async () => {
    setBusy(true)
    setError('')
    setMsg('')
    try {
      const targets = selectedRows.filter((r) => r.trial_eligible && r.pending_requests.length === 0)
      await Promise.all(targets.map((r) => api.requestModule(r.module, 'trial')))
      await finishAction(
        targets.length === 1
          ? `Trial requested for ${targets[0].name}.`
          : `Trial requested for ${targets.length} modules.`
      )
    } catch (e) {
      setError(e.message || 'Could not request a trial')
      setBusy(false)
    }
  }

  const unsubscribe = async () => {
    if (confirmText.trim().toLowerCase() !== 'confirm') return
    setBusy(true)
    setError('')
    setMsg('')
    try {
      const targets = selectedRows.filter((r) => r.status === 'subscribed' && r.pending_requests.length === 0)
      await Promise.all(targets.map((r) => api.requestModule(r.module, 'cancel')))
      await finishAction(
        targets.length === 1
          ? `Cancellation requested for ${targets[0].name}.`
          : `Cancellation requested for ${targets.length} modules.`
      )
    } catch (e) {
      setError(e.message || 'Could not request cancellation')
      setBusy(false)
    }
  }

  return (
    <AdminLayout>
      <div className="max-w-3xl">
        <h1 className="font-display font-bold text-2xl text-pb-text mb-1">Account</h1>
        <p className="font-mono text-[11px] text-pb-faint mb-6">
          Your club's plan, module by module.
        </p>

        {error && <p className="font-mono text-[11px] text-pb-red mb-4">{error}</p>}
        {msg && <p className="font-mono text-[11px] text-emerald-400 mb-4">{msg}</p>}

        {!plan ? (
          <p className="font-mono text-[11px] text-pb-faint">Loading…</p>
        ) : (
          <>
            <div className="space-y-3 mb-4">
              {rows.map((row) => {
                const brand = moduleBrand(row.module)
                const pending = row.pending_requests.length > 0
                return (
                  <div key={row.module} className="pb-card p-4 flex items-center gap-4">
                    <input
                      type="checkbox"
                      checked={selected.has(row.module)}
                      onChange={() => toggle(row.module)}
                      disabled={busy}
                      className="shrink-0 w-4 h-4"
                    />
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
                  </div>
                )
              })}
            </div>

            {selected.size > 0 && (
              <div className="pb-card p-4 sticky bottom-4">
                <p className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mb-3">
                  {selected.size} module{selected.size === 1 ? '' : 's'} selected
                </p>

                {stripeNotice && (
                  <p className="font-mono text-[11px] text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded px-3 py-2 mb-3">
                    Online subscribing isn't connected yet — this is coming in a follow-up build.
                    In the meantime, contact the BetterCricket team directly to subscribe.
                  </p>
                )}

                {confirmUnsubscribe ? (
                  <div className="space-y-2">
                    <p className="font-mono text-[11px] text-pb-red">
                      This requests cancellation of {selectedRows.filter((r) => r.status === 'subscribed').length === 1
                        ? 'this module' : 'these modules'}. Type "confirm" to proceed.
                    </p>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={confirmText}
                        onChange={(e) => setConfirmText(e.target.value)}
                        placeholder="confirm"
                        className="bg-pb-surface2 border pb-hairline rounded px-3 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
                      />
                      <button
                        onClick={unsubscribe}
                        disabled={busy || confirmText.trim().toLowerCase() !== 'confirm'}
                        className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded font-semibold disabled:opacity-50 text-pb-bg bg-pb-red"
                      >
                        {busy ? 'SENDING…' : 'CONFIRM UNSUBSCRIBE'}
                      </button>
                      <button
                        onClick={() => { setConfirmUnsubscribe(false); setConfirmText('') }}
                        className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded border pb-hairline text-pb-faint hover:text-pb-text"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {anyTrialEligible && (
                      <button
                        onClick={startTrial}
                        disabled={busy}
                        className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded border pb-hairline text-pb-text hover:bg-pb-surface2 disabled:opacity-50"
                      >
                        {busy ? 'SENDING…' : 'START TRIAL'}
                      </button>
                    )}
                    {anySubscribable && (
                      <button
                        onClick={() => setStripeNotice(true)}
                        disabled={busy}
                        className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded font-semibold disabled:opacity-50 text-pb-bg"
                        style={{ background: 'var(--pb-accent)' }}
                      >
                        SUBSCRIBE
                      </button>
                    )}
                    {anySubscribed && (
                      <button
                        onClick={() => setConfirmUnsubscribe(true)}
                        disabled={busy}
                        className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded border border-pb-red/40 text-pb-red hover:bg-pb-red/10 disabled:opacity-50"
                      >
                        UNSUBSCRIBE
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </AdminLayout>
  )
}
