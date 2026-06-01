// Module + tier registry — keep in sync with backend/app/auth/modules.py.
//
// The Better ecosystem is sold as Good / Better / Best tier bundles. Core
// (BetterStats — data ingestion, reconciled stats and the public site) is
// always on for every club and is NOT a gateable module. The entries below are
// the bolt-on modules, each rendered as a tile on the admin dashboard.

import { CAP } from './capabilities'

export const MODULE = {
  SELECT: 'select',
  SOCIALS: 'socials',
  FEES: 'fees',
  IQ: 'iq',
}

export const TIER = { GOOD: 'good', BETTER: 'better', BEST: 'best' }
export const TIER_ORDER = [TIER.GOOD, TIER.BETTER, TIER.BEST]

// Working price ladder — locked 2026-06-01 (Ecosystem Master Plan).
// NOTE: the master plan's "Risks & Open Decisions" note quotes $350/$650/$990,
// but the detailed "Price ladder (working ladder)" table — used here — quotes
// $449/$649/$999 + monthly $49/$69/$99. This object is the single source of
// truth; edit here if the ladder changes.
export const TIER_INFO = {
  [TIER.GOOD]:   { key: TIER.GOOD,   label: 'Good',   annual: 449, monthly: 49, tagline: 'Your history and a public site to be proud of' },
  [TIER.BETTER]: { key: TIER.BETTER, label: 'Better', annual: 649, monthly: 69, tagline: 'Run the season: availability, selection and socials' },
  [TIER.BEST]:   { key: TIER.BEST,   label: 'Best',   annual: 999, monthly: 99, tagline: 'Run the whole club: money plus an analytics brain' },
}

// Module registry — the admin dashboard renders one tile per entry, in order.
// - requiredTier: the lowest tier that bundles the module (drives the upsell)
// - built:        false → tile shows "Coming soon" instead of opening (BetterIQ)
// - caps:         capabilities that let a club_member actually use the module
export const MODULE_INFO = [
  {
    key: MODULE.SELECT,
    name: 'BetterSelect',
    blurb: 'Availability and smart team selection — plan your weekends.',
    to: '/admin/betterselect',
    requiredTier: TIER.BETTER,
    built: true,
    caps: [CAP.MANAGE_FIXTURES, CAP.MANAGE_SELECTIONS],
  },
  {
    key: MODULE.SOCIALS,
    name: 'BetterSocials',
    blurb: 'Auto-post lineups, scorecards, milestones and match summaries.',
    to: '/admin/social-post',
    requiredTier: TIER.BETTER,
    built: true,
    caps: [CAP.MANAGE_SOCIAL],
  },
  {
    key: MODULE.FEES,
    name: 'BetterFees',
    blurb: 'Fee schedules and match-day payment tracking for the treasurer.',
    to: '/admin/fees',
    requiredTier: TIER.BEST,
    built: true,
    caps: [CAP.MANAGE_FEES],
  },
  {
    key: MODULE.IQ,
    name: 'BetterIQ',
    blurb: 'AI + stats deep-dive: opposition scouting, selection analysis, trends.',
    to: null,
    requiredTier: TIER.BEST,
    built: false,
    caps: [],
  },
]

export function tierLabel(tier) {
  return TIER_INFO[tier]?.label || TIER_INFO[TIER.GOOD].label
}

export function tierInfo(tier) {
  return TIER_INFO[tier] || TIER_INFO[TIER.GOOD]
}

// Subscription statuses — keep in sync with backend ALL_STATUSES /
// ACTIVE_STATUSES. `live` = entitlements stay active for that status.
export const SUBSCRIPTION_STATUSES = [
  { key: 'active', label: 'Active', live: true },
  { key: 'trial', label: 'Trial', live: true },
  { key: 'past_due', label: 'Past due', live: true },
  { key: 'paused', label: 'Paused', live: false },
  { key: 'cancelled', label: 'Cancelled', live: false },
]

export const BILLING_CYCLES = [
  { key: '', label: '—' },
  { key: 'monthly', label: 'Monthly' },
  { key: 'annual', label: 'Annual' },
]

export function statusLabel(status) {
  return SUBSCRIPTION_STATUSES.find(s => s.key === status)?.label || 'Active'
}

export function statusIsLive(status) {
  const s = SUBSCRIPTION_STATUSES.find(x => x.key === status)
  return s ? s.live : true
}
