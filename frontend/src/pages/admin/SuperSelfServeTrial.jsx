import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import SelfServeTrialModal from '../../components/admin/SelfServeTrialModal'

// Internal entry point for the self-serve club trial registration flow (see
// docs/self-serve-trial-onboarding-plan.md). Reachable only via the Super Admin
// menu, and only while the self_serve_registration_enabled platform flag is on —
// the backend 404s /self-serve-trial/status when it's off, so a direct link after
// the flag is disabled fails closed rather than showing a broken modal.
export default function SuperSelfServeTrial() {
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)

  useEffect(() => {
    api.selfServeTrialStatus()
      .then((s) => setStatus(s))
      .catch((e) => setError(e?.status === 404
        ? 'Self-serve registration is currently switched off. Turn it on from General Settings on All Clubs.'
        : (e?.message || 'Could not load self-serve trial status.')))
      .finally(() => setLoading(false))
  }, [])

  return (
    <AdminLayout>
      <div className="max-w-3xl mx-auto p-4 sm:p-6 space-y-4">
        <div>
          <h1 className="text-xl font-semibold text-pb-text">Self-Serve Trial (Internal)</h1>
          <p className="font-mono text-[11px] text-pb-faintest mt-1">
            Registers a real club and admin account through the same flow the public
            site will eventually use. Internal-only for now — see
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
