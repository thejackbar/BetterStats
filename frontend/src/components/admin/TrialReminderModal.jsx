import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { trialStatus } from '../../lib/trialStatus'

/* An on-screen reminder that pops up as a club's trial winds down, so a
   trialling club doesn't have to know to go looking for the subscribe page.
   Mounted in ProtectedRoute beside TrialBanner (the always-on strip) so it
   covers every admin surface; this is the louder, once-in-a-while push.

   Reminders fire at 10, 7, 5, 3, 2 and 1 day before the trial ends, plus once
   after it has ended. The "tier" is the tightest of those thresholds the club
   is currently inside; dismissing records that tier, so the pop-up stays away
   until the countdown crosses into the next one (chosen behaviour: once per
   threshold, not once per visit). Kept per user (two people can share a club
   login) in localStorage, read in the state initialiser so it never flashes
   open on load and then close. No server round trip — a missed reminder is
   cheap, and the strip is always there underneath. */

// Ascending so .find returns the SMALLEST threshold still >= the days left,
// i.e. the tightest bucket. 6 days left -> tier 7; 4 -> 5; 1 -> 1.
const THRESHOLDS = [1, 2, 3, 5, 7, 10]
const SUPPORT_EMAIL = 'support@bettersports.com.au'

function tierFor(daysLeft, expired) {
  if (expired) return 'expired'
  if (daysLeft > THRESHOLDS[THRESHOLDS.length - 1]) return null // >10 days: too early
  const eff = Math.max(daysLeft, 1)
  return String(THRESHOLDS.find((t) => t >= eff)) // always found for eff in 1..10
}

function useDismissedTier(userId) {
  const key = `bs_trial_reminder_tier_${userId || 'anon'}`
  const [tier, setTier] = useState(() => {
    try {
      return localStorage.getItem(key)
    } catch {
      return null // private mode / storage blocked — reminder just re-shows
    }
  })
  const dismiss = (t) => {
    setTier(String(t))
    try {
      localStorage.setItem(key, String(t))
    } catch {
      /* ignore */
    }
  }
  return [tier, dismiss]
}

function fmtDate(iso) {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    })
  } catch {
    return ''
  }
}

export default function TrialReminderModal() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [dismissedTier, dismiss] = useDismissedTier(user?.id)

  const status = trialStatus(user)
  const tier = status ? tierFor(status.daysLeft, status.expired) : null

  // Nothing to nudge, too early, already seen this tier, or they're already on
  // the Account page actively subscribing — don't get in the way.
  if (!status || !tier) return null
  if (String(tier) === String(dismissedTier)) return null
  if (location.pathname.startsWith('/admin/account')) return null

  const { soonest, daysLeft, expired, others } = status
  const endDate = fmtDate(soonest.trial_ends_at)
  const goSubscribe = () => {
    dismiss(tier)
    navigate(status.subscribePath)
  }
  const remindLater = () => dismiss(tier)

  let heading
  if (expired) heading = 'Your trial has ended'
  else if (daysLeft <= 3) heading = `Only ${daysLeft} day${daysLeft === 1 ? '' : 's'} left on your trial`
  else heading = 'Your trial is ending soon'

  let whenPhrase
  if (expired) whenPhrase = endDate ? `ended on ${endDate}` : 'has ended'
  else if (daysLeft <= 0) whenPhrase = 'ends today'
  else if (daysLeft === 1) whenPhrase = 'ends tomorrow'
  else whenPhrase = `ends in ${daysLeft} days`

  const othersLine =
    others > 0
      ? ` You have ${others} other trial${others === 1 ? '' : 's'} winding down too.`
      : ''

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) remindLater()
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="trial-reminder-title"
    >
      <div className="pb-card bg-pb-surface w-full max-w-md p-6 space-y-4 relative">
        <button
          onClick={remindLater}
          aria-label="Close"
          title="Remind me later"
          className="absolute top-3 right-3 font-mono text-[13px] text-pb-faint hover:text-pb-text w-7 h-7 rounded-full hover:bg-pb-surface2"
        >
          ✕
        </button>

        <div
          className="inline-flex items-center gap-2 font-mono text-[10px] tracking-wide2 px-2.5 py-1 rounded-full"
          style={{ background: 'var(--pb-accent)', color: '#fff' }}
        >
          {expired ? 'TRIAL ENDED' : `${daysLeft} DAY${daysLeft === 1 ? '' : 'S'} LEFT`}
        </div>

        <h3 id="trial-reminder-title" className="font-display font-bold text-xl text-pb-text">
          {heading}
        </h3>

        <p className="text-sm text-pb-dim leading-relaxed">
          Your {soonest.name} trial {whenPhrase}.{othersLine}{' '}
          {expired
            ? "Subscribe to restore full access to your club's stats and tools."
            : 'Subscribe now to keep your access running without a break.'}
        </p>

        <button
          onClick={goSubscribe}
          className="w-full rounded-lg py-3 text-white font-semibold text-sm shadow-sm"
          style={{ background: 'var(--pb-accent)' }}
        >
          {expired ? 'Subscribe now' : 'Convert your trial'} &rarr;
        </button>

        <p className="text-xs text-pb-faint leading-relaxed">
          Questions before you subscribe? Email{' '}
          <a
            href={`mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent('BetterCricket subscription query')}`}
            className="text-pb-text underline hover:no-underline font-medium"
          >
            {SUPPORT_EMAIL}
          </a>{' '}
          and we'll help you out.
        </p>

        <div className="flex justify-end">
          <button
            onClick={remindLater}
            className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text px-2 py-1"
          >
            REMIND ME LATER
          </button>
        </div>
      </div>
    </div>
  )
}
