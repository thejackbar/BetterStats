import { useEffect, useState } from 'react'
import AdminLayout from '../../components/admin/AdminLayout'
import { api } from '../../lib/api'
import { moduleBrand } from '../../lib/moduleBrand'

// Phase 19 (docs/self-serve-trial-onboarding-plan.md) — the club's own
// self-serve plan status page. No Stripe yet (per the plan's own Cut from
// this effort), so "Start trial" / "Subscribe" don't change anything
// instantly — they queue a module_action_requests row (the same table/queue
// the Super Admin module editor already actions), matching manual billing
// as it stands today.
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
  const [busyKey, setBusyKey] = useState('')
  const [msg, setMsg] = useState('')

  const load = () =>
    api.accountGetPlan().then(setPlan).catch((e) => setError(e.message || 'Could not load your plan'))

  useEffect(() => { load() }, [])

  const act = async (moduleKey, kind) => {
    setBusyKey(`${moduleKey}:${kind}`)
    setMsg('')
    setError('')
    try {
      await api.requestModule(moduleKey, kind)
      setMsg(
        kind === 'trial'
          ? "Trial requested — we'll set it up shortly."
          : "Subscription requested — we'll be in touch shortly."
      )
      await load()
    } catch (e) {
      setError(e.message || 'Could not send the request')
    } finally {
      setBusyKey('')
    }
  }

  return (
    <AdminLayout>
      <div className="max-w-3xl">
        <h1 className="font-display font-bold text-2xl text-pb-text mb-1">Account</h1>
        <p className="font-mono text-[11px] text-pb-faint mb-6">
          Your club's plan, module by module. Requesting a trial or subscription goes to the
          BetterCricket team — nothing changes instantly.
        </p>

        {error && <p className="font-mono text-[11px] text-pb-red mb-4">{error}</p>}
        {msg && <p className="font-mono text-[11px] text-emerald-400 mb-4">{msg}</p>}

        {!plan ? (
          <p className="font-mono text-[11px] text-pb-faint">Loading…</p>
        ) : (
          <div className="space-y-3">
            {plan.modules.map((row) => {
              const brand = moduleBrand(row.module)
              const pending = row.pending_requests.length > 0
              return (
                <div key={row.module} className="pb-card p-4 flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ background: brand.accent }} />
                    <div className="min-w-0">
                      <p className="font-display font-bold text-sm text-pb-text truncate">{row.name}</p>
                      <p className="font-mono text-[10px] text-pb-faint">
                        {STATUS_LABEL[row.status]}
                        {row.status === 'subscribed' && row.renewal_date && ` · renews ${fmtDate(row.renewal_date)}`}
                        {row.status === 'trial' && row.trial_ends_at && ` · ends ${fmtDate(row.trial_ends_at)}`}
                        {row.status === 'trial_expired' && row.trial_ends_at && ` · ended ${fmtDate(row.trial_ends_at)}`}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {pending ? (
                      <span className="font-mono text-[10px] tracking-wide2 text-pb-faint">
                        {row.pending_requests.includes('subscribe') ? 'SUBSCRIBE REQUESTED' : 'TRIAL REQUESTED'}
                      </span>
                    ) : (
                      <>
                        {row.trial_eligible && (
                          <button
                            onClick={() => act(row.module, 'trial')}
                            disabled={!!busyKey}
                            className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded border pb-hairline text-pb-text hover:bg-pb-surface2 disabled:opacity-50"
                          >
                            {busyKey === `${row.module}:trial` ? 'SENDING…' : 'START TRIAL'}
                          </button>
                        )}
                        {row.can_subscribe && (
                          <button
                            onClick={() => act(row.module, 'subscribe')}
                            disabled={!!busyKey || !plan.is_primary_admin}
                            title={!plan.is_primary_admin
                              ? "Only the club's primary admin can request a subscription" : undefined}
                            className="font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded font-semibold disabled:opacity-50 text-pb-bg"
                            style={{ background: 'var(--pb-accent)' }}
                          >
                            {busyKey === `${row.module}:subscribe` ? 'SENDING…' : 'SUBSCRIBE'}
                          </button>
                        )}
                      </>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {plan && !plan.is_primary_admin && (
          <p className="font-mono text-[10px] text-pb-faintest mt-4">
            Only the club's primary admin can request a paid subscription — ask them, or see{' '}
            <a href="/pricing" target="_blank" rel="noopener noreferrer"
              className="text-pb-faint hover:text-pb-text underline">
              pricing
            </a>.
          </p>
        )}
      </div>
    </AdminLayout>
  )
}
