import { useEffect, useState } from 'react'
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
  const [trialBusy, setTrialBusy] = useState('')
  const [msg, setMsg] = useState('')
  const [selected, setSelected] = useState(new Set())
  const [blockedMsg, setBlockedMsg] = useState('')
  const [primaryAdminName, setPrimaryAdminName] = useState('')
  const [cancelConfirm, setCancelConfirm] = useState(null) // { module, text } | null
  const [stripeNotice, setStripeNotice] = useState(false)

  const load = () =>
    api.accountGetPlan().then(setPlan).catch((e) => setError(e.message || 'Could not load your plan'))

  useEffect(() => { load() }, [])

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

  // Only a Trial-status row can be selected (for the bulk Subscribe request
  // below) — starting a trial and cancelling are both instant per-row buttons
  // now, no bulk selection needed for those. A non-primary admin can't select
  // a trial row at all (only the primary may request a paid subscription,
  // same rule the backend enforces regardless) — they get pointed at who can.
  const toggle = (row) => {
    if (row.status !== 'trial') return
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

  // Stripe checkout isn't wired up yet — this is a deliberate stub, not a
  // queued request (per direct instruction: online subscribing is landing in
  // its own phase, so this button shouldn't quietly go through the human-
  // actioned module_action_requests queue in the meantime).
  const submitSubscribe = () => {
    setStripeNotice(true)
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
        {blockedMsg && (
          <p className="font-mono text-[11px] text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded px-3 py-2 mb-4">
            {blockedMsg}
          </p>
        )}

        {!plan ? (
          <p className="font-mono text-[11px] text-pb-faint">Loading…</p>
        ) : (
          <>
            <div className="space-y-3 mb-4">
              {rows.map((row) => {
                const brand = moduleBrand(row.module)
                const pending = row.pending_requests.length > 0
                const isTrialRow = row.status === 'trial'
                const showCancel = row.status === 'subscribed' && plan.is_primary_admin
                const showStartTrial = row.status === 'never_trialed' && row.trial_eligible
                const cancelling = cancelConfirm?.module === row.module

                return (
                  <div key={row.module} className="pb-card p-4">
                    <div className="flex items-center gap-4">
                      {isTrialRow ? (
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

            {selected.size > 0 && (
              <div className="pb-card p-4 sticky bottom-4">
                <p className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mb-3">
                  {selected.size} module{selected.size === 1 ? '' : 's'} selected
                </p>
                {stripeNotice ? (
                  <p className="font-mono text-[11px] text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded px-3 py-2">
                    Online subscribing isn't connected yet — this is coming in a follow-up build.
                    In the meantime, contact the BetterCricket team directly to subscribe.
                  </p>
                ) : (
                  <button
                    onClick={submitSubscribe}
                    className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded font-semibold text-pb-bg"
                    style={{ background: 'var(--pb-accent)' }}
                  >
                    SUBSCRIBE
                  </button>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </AdminLayout>
  )
}
