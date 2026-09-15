import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { trialStatus } from '../../lib/trialStatus'

// A prominent trial-conversion bar. Rendered by AdminLayout and ModuleLayout
// directly under the sticky chrome header (not at the very top of the page),
// so it sits in the admin content flow where it reads as part of the app.
// Reads the shared trialStatus() helper (over user.entitlements.billing_modules,
// already on /auth/me and /auth/login) so it can never disagree with the
// TrialReminderModal pop-up about days left.
//
// The bar carries the club's own primary->secondary gradient (a light tint over
// the surface so text stays readable in both themes), an explainer line and an
// animated arrow pointing at a solid "Subscribe now" button that goes to the
// real subscribe flow (/admin/account, which pre-ticks the trialling modules
// for the primary admin) rather than the marketing pricing page.
export default function TrialBanner() {
  const { user } = useAuth()
  const navigate = useNavigate()

  const status = trialStatus(user)
  if (!status) return null

  const { daysLeft, expired, subscribePath } = status

  let whenPhrase
  if (daysLeft <= 0) whenPhrase = 'today'
  else if (daysLeft === 1) whenPhrase = 'tomorrow'
  else whenPhrase = `in ${daysLeft} days`

  // "BetterCricket trial" (the product) rather than the soonest-expiring
  // module's own name — a club is trialling BetterCricket, and naming one
  // module while several are winding down reads as confusing. daysLeft is
  // still the soonest expiry, so the countdown is the earliest one to act on.
  const explainer = expired ? (
    <>Your BetterCricket trial has ended. Subscribe now to restore full access to your club's stats and tools.</>
  ) : (
    <>Ready to keep going? Subscribe before your BetterCricket trial ends {whenPhrase} so you don't lose access.</>
  )

  return (
    <div
      className="w-full px-4 py-2.5 border-b"
      style={{
        background:
          'linear-gradient(90deg, color-mix(in srgb, var(--pb-accent) 22%, var(--pb-surface)) 0%, color-mix(in srgb, var(--pb-accent-2-safe) 22%, var(--pb-surface)) 100%)',
        borderColor: 'color-mix(in srgb, var(--pb-accent) 35%, transparent)',
      }}
    >
      <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-center gap-x-3 gap-y-2 text-center">
        <span
          className="font-mono text-[10px] tracking-wide2 px-2 py-0.5 rounded-full shrink-0 font-semibold"
          style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}
        >
          {expired ? 'TRIAL ENDED' : `${daysLeft} DAY${daysLeft === 1 ? '' : 'S'} LEFT`}
        </span>

        <span className="text-sm text-pb-text font-medium">{explainer}</span>

        <span
          aria-hidden="true"
          className="pb-nudge-x text-lg font-bold shrink-0 leading-none"
          style={{ color: 'var(--pb-accent-ink, var(--pb-accent))' }}
        >
          &rarr;
        </span>

        <button
          onClick={() => navigate(subscribePath)}
          className="rounded-md px-4 py-1.5 font-semibold text-sm shadow-sm hover:opacity-90 shrink-0"
          style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}
        >
          Subscribe now
        </button>

        <a
          href="/pricing"
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-pb-dim underline hover:no-underline opacity-80 shrink-0"
        >
          See pricing
        </a>
      </div>
    </div>
  )
}
