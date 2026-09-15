import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { trialStatus } from '../../lib/trialStatus'

// Phase 18 (docs/self-serve-trial-onboarding-plan.md) — a slim, persistent
// strip above every admin page while any module is on trial. Reads the shared
// trialStatus() helper (over user.entitlements.billing_modules, already
// returned by /auth/me and /auth/login) so it can never disagree with the
// TrialReminderModal pop-up about days left. Super admins act cross-club and
// are never shown a club's own trial state (trialStatus returns null for them).
//
// The primary CTA now goes to the real subscribe flow (/admin/account, which
// pre-ticks the trialling modules for the primary admin) rather than the
// marketing pricing page, so a club doesn't have to know where to convert.
export default function TrialBanner() {
  const { user } = useAuth()
  const navigate = useNavigate()

  const status = trialStatus(user)
  if (!status) return null

  const { soonest, daysLeft, expired, others, subscribePath } = status
  const urgent = expired || daysLeft <= 7

  return (
    <div
      className={`px-4 py-2 flex flex-wrap items-center justify-center gap-x-3 gap-y-1.5 text-center font-mono text-[11px] tracking-wide2 ${
        urgent
          ? 'bg-amber-500/15 text-amber-200 border-b border-amber-500/30'
          : 'bg-pb-surface2 text-pb-faint border-b pb-hairline-b'
      }`}
    >
      <span>
        {expired ? (
          <>Your {soonest.name} trial has ended{others ? ` (and ${others} more)` : ''}.</>
        ) : (
          <>{daysLeft} day{daysLeft === 1 ? '' : 's'} left in your {soonest.name} trial{others ? ` (+${others} more)` : ''}.</>
        )}
      </span>
      <button
        onClick={() => navigate(subscribePath)}
        className="rounded-full px-3 py-1 text-white font-semibold text-[11px] shadow-sm"
        style={{ background: 'var(--pb-accent)' }}
      >
        {expired ? 'Subscribe now' : 'Convert your trial'} &rarr;
      </button>
      <a
        href="/pricing"
        target="_blank"
        rel="noopener noreferrer"
        className="underline hover:no-underline opacity-80"
      >
        See pricing
      </a>
    </div>
  )
}
