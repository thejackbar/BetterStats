import { useAuth } from '../../contexts/AuthContext'

const DAY_MS = 24 * 60 * 60 * 1000

// Phase 18 (docs/self-serve-trial-onboarding-plan.md) — a slim, persistent
// strip above every admin page while any module is on trial. Reads
// user.entitlements.billing_modules, already returned by /auth/me and
// /auth/login (auth/modules.py::entitlement_summary) — no new endpoint.
// Super admins act cross-club and are never shown a club's own trial state
// (mirrors the onboarding wizard's own super_admin exclusion).
export default function TrialBanner() {
  const { user } = useAuth()
  if (!user || user.role === 'super_admin') return null

  const mods = user.entitlements?.billing_modules || []
  const trials = mods.filter(m => m.status === 'trial' && m.trial_ends_at)
  if (!trials.length) return null

  const soonest = trials.reduce((a, b) => (new Date(a.trial_ends_at) < new Date(b.trial_ends_at) ? a : b))
  const daysLeft = Math.ceil((new Date(soonest.trial_ends_at).getTime() - Date.now()) / DAY_MS)
  const expired = daysLeft < 0 || !soonest.live
  const others = trials.length - 1
  const urgent = expired || daysLeft <= 7

  return (
    <div
      className={`px-4 py-2 text-center font-mono text-[11px] tracking-wide2 ${
        urgent
          ? 'bg-amber-500/15 text-amber-200 border-b border-amber-500/30'
          : 'bg-pb-surface2 text-pb-faint border-b pb-hairline-b'
      }`}
    >
      {expired ? (
        <>Your {soonest.name} trial has ended{others ? ` (and ${others} more)` : ''}.</>
      ) : (
        <>{daysLeft} day{daysLeft === 1 ? '' : 's'} left in your {soonest.name} trial{others ? ` (+${others} more)` : ''}.</>
      )}
      {' '}
      <a
        href="/pricing"
        target="_blank"
        rel="noopener noreferrer"
        className="underline hover:no-underline font-semibold"
      >
        {expired ? 'Subscribe now' : 'See pricing'}
      </a>
    </div>
  )
}
