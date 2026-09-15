// One reading of a club's trial state, shared by TrialBanner (the persistent
// strip) and TrialReminderModal (the threshold pop-up) so the two can never
// disagree about how many days are left or which modules are expiring.
//
// Reads user.entitlements.billing_modules, already returned by /auth/me and
// /auth/login (auth/modules.py::_billing_module_summary) — no separate fetch.
// Each entry carries { module, name, status, live, trial_ends_at }.

const DAY_MS = 24 * 60 * 60 * 1000

// The subscribe flow lives at /admin/account; the ?subscribe= deep link
// pre-ticks the named module checkboxes for the primary admin (and auto-adds
// core when an add-on needs it), so we hand it the modules actually on trial.
export function subscribePath(trials) {
  const keys = [...new Set((trials || []).map((t) => t.module).filter(Boolean))]
  return `/admin/account?subscribe=${(keys.length ? keys : ['core']).join(',')}`
}

// Returns null for anyone with no trial to nudge (a fully paid club, a club
// with no trial modules held) — every caller treats null as "render nothing".
//
// A super admin acts cross-club, so a plain super-admin view has no single
// club whose trial to convert; but once they've scoped INTO a specific club
// (acting_as_club), the entitlements they carry are that one club's, and a
// super admin counts as its primary admin, so the Subscribe CTA is both
// meaningful and functional. Only that acting-as case is shown.
export function trialStatus(user) {
  if (!user) return null
  if (user.role === 'super_admin' && !user.acting_as_club) return null

  const mods = user.entitlements?.billing_modules || []
  const trials = mods.filter((m) => m.status === 'trial' && m.trial_ends_at)
  if (!trials.length) return null

  const soonest = trials.reduce((a, b) =>
    new Date(a.trial_ends_at) < new Date(b.trial_ends_at) ? a : b
  )
  // Mirror TrialBanner exactly: ceil so "1 day left" covers the final
  // part-day, and lean on the server's own `live` flag for the ends-today /
  // just-expired edge rather than the ceil'd number.
  const daysLeft = Math.ceil(
    (new Date(soonest.trial_ends_at).getTime() - Date.now()) / DAY_MS
  )
  const expired = daysLeft < 0 || !soonest.live

  return {
    trials,
    soonest,
    daysLeft,
    expired,
    others: trials.length - 1,
    subscribePath: subscribePath(trials),
  }
}
