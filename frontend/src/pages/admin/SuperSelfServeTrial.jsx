import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import SelfServeTrialModal from '../../components/admin/SelfServeTrialModal'

// Internal entry point for the self-serve club trial registration flow (see
// docs/self-serve-trial-onboarding-plan.md). Reachable only via the Super Admin
// menu (require_super_admin) — this flow always works for a super admin,
// regardless of the All Clubs -> General Settings "Self-serve trials enabled"
// checkbox. That checkbox only gates the public surface (/trial and the
// website's "Request access" / "Get your club on BetterCricket" CTAs) —
// see routers/public_self_serve.py.
export default function SuperSelfServeTrial() {
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)

  useEffect(() => {
    api.selfServeTrialStatus()
      .then((s) => setStatus(s))
      .catch((e) => setError(e?.message || 'Could not load self-serve trial status.'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <AdminLayout>
      <div className="max-w-3xl mx-auto p-4 sm:p-6 space-y-4">
        <div>
          <h1 className="text-xl font-semibold text-pb-text">Self-Serve Trial (Internal)</h1>
          <p className="font-mono text-[11px] text-pb-faintest mt-1">
            Registers a real club and admin account through the same flow /trial and
            the "Get your club on BetterCricket" CTAs use. Always available here,
            regardless of whether the public flow is switched on — see
            docs/self-serve-trial-onboarding-plan.md.
          </p>
        </div>

        {loading && (
          <p className="font-mono text-[11px] text-pb-faint">Loading…</p>
        )}

        {!loading && error && (
          <div className="pb-card p-4 bg-pb-surface2">
            <p className="font-mono text-[11px] text-pb-faint">{error}</p>
          </div>
        )}

        {!loading && !error && status?.enabled && (
          <button
            onClick={() => setModalOpen(true)}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition text-pb-bg"
            style={{ background: 'var(--pb-accent)' }}
          >
            + START A CLUB TRIAL
          </button>
        )}
      </div>

      {modalOpen && (
        <SelfServeTrialModal
          defaultTrialDays={status?.default_trial_days ?? 14}
          onClose={() => setModalOpen(false)}
        />
      )}
    </AdminLayout>
  )
}
