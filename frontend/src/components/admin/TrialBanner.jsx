import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { trialStatus } from '../../lib/trialStatus'

// Phase 18 (docs/self-serve-trial-onboarding-plan.md) — a persistent bar above
// every admin page while any module is on trial, so the Subscribe button is
// present and prominent at all times during a trial. Reads the shared
// trialStatus() helper (over user.entitlements.billing_modules, already
// returned by /auth/me and /auth/login) so it can never disagree with the
// TrialReminderModal pop-up about days left.
//
// The button always carries the club's accent fill (even early in the trial,
// not only when urgent) so it reads as a real button whatever the countdown,
// and goes to the real subscribe flow (/admin/account, which pre-ticks the
// trialling modules for the primary admin) rather than the marketing pricing
// page.
export default function TrialBanner() {
  const { user } = useAuth()
  const navigate = useNavigate()

  const status = trialStatus(user)
  if (!status) return null

  const { soonest, daysLeft, expired, others, subscribePath } = status
  const urgent = expired || daysLeft <= 7

  return (
    <div
      className={`px-4 py-2.5 flex flex-wrap items-center justify-center gap-x-3 gap-y-2 text-center text-sm ${
        urgent
          ? 'bg-amber-500/15 text-amber-100 border-b border-amber-500/40'
          : 'bg-pb-surface2 text-pb-dim border-b pb-hairline-b'
      }`}
    >
      <span className="font-medium">
        {expired ? (
          <>Your {soonest.name} trial has ended{others ? ` (and ${others} more)` : ''}.</>
        ) : (
          <>{daysLeft} day{daysLeft === 1 ? '' : 's'} left in your {soonest.name} trial{others ? ` (+${others} more)` : ''}.</>
        )}
      </span>
      <button
        onClick={() => navigate(subscribePath)}
        className="rounded-md px-4 py-1.5 text-white font-semibold text-sm shadow-sm hover:opacity-90"
        style={{ background: 'var(--pb-accent)' }}
      >
        Subscribe now &rarr;
      </button>
      <a
        href="/pricing"
        target="_blank"
        rel="noopener noreferrer"
        className="text-xs underline hover:no-underline opacity-70"
      >
        See pricing
      </a>
    </div>
  )
}
