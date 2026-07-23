// Module registry — keep in sync with backend/app/auth/modules.py.
//
// The Better ecosystem is modular: every club gets Core (BetterStats: data
// ingestion, reconciled stats and the public site), always on and never a
// gateable module, then turns on the bolt-on modules it pays for. The entries
// below are those bolt-on modules, each rendered as a tile on the admin
// dashboard.

import { CAP } from './capabilities'

export const MODULE = {
  SELECT: 'select',
  SOCIALS: 'socials',
  FEES: 'fees',
  IQ: 'iq',
  COMMS: 'comms',
  MERCH: 'merch',
  FANTASY: 'fantasy',
  CRM: 'crm',
}

// Module registry — the admin dashboard renders one tile per entry, in order.
// - built:        false → tile shows "Coming soon" instead of opening
// - caps:         capabilities that let a club_member actually use the module
export const MODULE_INFO = [
  {
    key: MODULE.SELECT,
    name: 'BetterSelect',
    blurb: 'Availability and smart team selection — plan your weekends.',
    to: '/admin/betterselect',
    built: true,
    caps: [CAP.MANAGE_FIXTURES, CAP.MANAGE_SELECTIONS],
  },
  {
    key: MODULE.SOCIALS,
    name: 'BetterSocials',
    blurb: 'Auto-post lineups, scorecards, milestones and match summaries.',
    to: '/admin/social-post',
    built: true,
    caps: [CAP.MANAGE_SOCIAL],
    group: 'socials',  // shown under the BetterSocials umbrella (with the Website)
  },
  {
    key: MODULE.FEES,
    name: 'BetterFees',
    blurb: 'Fee schedules and match-day payment tracking for the treasurer.',
    to: '/admin/fees',
    built: true,
    caps: [CAP.MANAGE_FEES],
    group: 'admin',  // shown under the BetterAdmin umbrella tile
  },
  {
    key: MODULE.COMMS,
    name: 'BetterComms',
    blurb: 'Bulk email to your member database — newsletters and announcements.',
    to: '/admin/comms',
    built: true,
    caps: [CAP.MANAGE_COMMS],
    group: 'admin',
  },
  {
    key: MODULE.MERCH,
    name: 'BetterMerch',
    blurb: 'Track club stock — apparel, equipment and canteen, with low-stock alerts.',
    to: '/admin/merch',
    built: true,
    caps: [CAP.MANAGE_MERCH],
    group: 'admin',
  },
  {
    key: MODULE.CRM,
    name: 'BetterCRM',
    blurb: 'Contacts, sponsorship, grants and a deal pipeline for the club.',
    to: '/admin/crm',
    built: true,
    caps: [CAP.MANAGE_CRM],
    group: 'admin',
  },
  {
    key: MODULE.IQ,
    name: 'BetterIQ',
    blurb: 'AI + stats deep-dive: opposition scouting, selection analysis, trends.',
    to: '/admin/betteriq',
    built: true,
    caps: [CAP.MANAGE_IQ],
  },
  {
    key: MODULE.FANTASY,
    name: 'BetterFantasyCricket',
    blurb: 'Run an internal club fantasy league off your own games — salary cap and draft.',
    to: '/admin/fantasy',
    built: true,
    caps: [CAP.MANAGE_FANTASY],
  },
]

// BetterFees + BetterComms + BetterMerch are sold separately but presented
// together as one **BetterAdmin** umbrella tile on the dashboard / sidebar —
// the club's back office in one place.
export const MODULE_GROUPS = {
  // BetterSocials is an umbrella too: the Post Designer (the socials module)
  // plus the club Website (Core, every club). alwaysOpen keeps the hub reachable for
  // every club so the Core website is never gated behind the socials module.
  socials: {
    key: 'bettersocials',
    billingKey: 'socials',
    name: 'BetterSocials',
    blurb: 'Your public website plus auto-posts for lineups, scorecards and milestones.',
    to: '/admin/bettersocials',
    alwaysOpen: true,
  },
  admin: {
    key: 'admin',
    billingKey: 'admin',
    name: 'BetterAdmin',
    blurb: 'Run the back office — fees, comms, merch and CRM in one place.',
    to: '/admin/betteradmin',
  },
}

// What the dashboard + sidebar render: grouped modules collapse into a single
// umbrella tile (with its `members`), ungrouped modules pass through unchanged.
// Order follows MODULE_INFO; a group lands where its first member appears.
export function dashboardTiles() {
  const tiles = []
  const at = {}
  for (const mod of MODULE_INFO) {
    const g = mod.group && MODULE_GROUPS[mod.group]
    if (g) {
      if (at[g.key] == null) {
        at[g.key] = tiles.length
        tiles.push({ ...g, isGroup: true, built: true, members: [mod] })
      } else {
        tiles[at[g.key]].members.push(mod)
      }
    } else {
      tiles.push({ ...mod, isGroup: false })
    }
  }
  return tiles
}

// The modular toggles a super admin grants per club. BetterAdmin is the
// back-office umbrella, so its toggle covers all three backend module keys (fees
// + comms + merch). `modules` are the backend entitlement keys (app/auth/modules.py
// ALL_MODULES); Core (BetterStats) is always on and isn't a toggle.
export const MODULE_TOGGLES = [
  // BetterStats (Core) is the base every club gets — managed first, controls the
  // public site (its trial/cancel gates the club, per the backend org_core_live).
  { key: 'core',    label: 'BetterStats',   modules: ['core'] },
  { key: 'select',  label: 'BetterSelect',  modules: ['select'] },
  { key: 'socials', label: 'BetterSocials', modules: ['socials'] },
  { key: 'admin',   label: 'BetterAdmin',   modules: ['fees', 'comms', 'merch', 'crm'] },
  { key: 'iq',      label: 'BetterIQ',       modules: ['iq'] },
  { key: 'fantasy', label: 'BetterFantasyCricket', modules: ['fantasy'] },
]

// Display name for a billable module key (BetterAdmin = the fees/comms/merch
// umbrella). Mirrors the backend BILLABLE_MODULE_NAMES; covers the member keys too.
export const BILLABLE_MODULE_NAME = {
  core: 'BetterStats',
  select: 'BetterSelect',
  socials: 'BetterSocials',
  admin: 'BetterAdmin',
  iq: 'BetterIQ',
  fantasy: 'BetterFantasyCricket',
  fees: 'BetterFees',
  comms: 'BetterComms',
  merch: 'BetterMerch',
  crm: 'BetterCRM',
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
