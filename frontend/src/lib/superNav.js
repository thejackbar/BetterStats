// Better HQ (super-admin) navigation, grouped into sections.
//
// Each section has a hub landing page at /admin/super/hub/:key that lists its
// items as tiles; the sidebar shows one button per section (a single-item
// section links straight to its one item instead of a hub, so it stays one
// click away). Platform Overview stays a standalone top link.
//
// Sections are kept in ALPHABETICAL order by label, and items within a section
// are kept in ALPHABETICAL order by label — keep it that way when adding links.
// `flag` on an item hides it until the matching platform flag is on (same
// convention as the old flat SUPER_LINKS). `badge` drives the count pill.

export const SUPER_OVERVIEW = { to: '/admin/super', label: 'Platform Overview', exact: true }

export const SUPER_SECTIONS = [
  {
    key: 'access',
    label: 'Access',
    blurb: 'Staff and club-admin accounts.',
    items: [
      { to: '/admin/super/users', label: 'Users', blurb: 'Staff and club-admin accounts, roles and password resets.' },
    ],
  },
  {
    key: 'billing',
    label: 'Billing',
    blurb: 'Coupons, discounts and subscription requests.',
    items: [
      { to: '/admin/super/coupons', label: 'Discount Coupons', blurb: 'Create and manage discount codes.' },
      { to: '/admin/super/discount-report', label: 'Discount Report', blurb: 'Redemptions and discount totals.' },
      { to: '/admin/super/module-requests', label: 'Module Requests', blurb: 'Approve subscribe, trial and cancel requests.', badge: 'moduleRequests' },
      { to: '/admin/super/self-serve', label: 'Self-Serve Trial (Internal)', blurb: 'Register a club on a trial from the inside.', flag: 'selfServeRegistration' },
    ],
  },
  {
    key: 'clubs-data',
    label: 'Clubs & Data',
    blurb: 'Backups, merges, migration and onboarding enquiries.',
    items: [
      { to: '/admin/super/backups', label: 'Backups', blurb: 'Database backups and restore points.' },
      { to: '/admin/super/migration', label: 'KlubPro Migration', blurb: 'Import player profiles and sponsors from a legacy KlubPro club.' },
      { to: '/admin/super/merge-clubs', label: 'Merge Clubs', blurb: 'Combine two club records into one.' },
      { to: '/admin/super/onboarding', label: 'Onboarding Requests', blurb: 'Enquiries from the public contact form.' },
      { to: '/admin/super/unpause-requests', label: 'Unpause Requests', blurb: "Leads from a lapsed-trial club's password-protected page.", badge: 'unpauseRequests' },
    ],
  },
  {
    key: 'comms',
    label: 'Comms',
    blurb: 'Email send limits and club-wide announcements.',
    items: [
      { to: '/admin/super/comms-limits', label: 'BetterComms Limits', blurb: 'Email send tiers and suspended clubs.', badge: 'commsRequests' },
      { to: '/admin/super/announce', label: 'Club Announcements', blurb: 'Post a notice to every club.' },
    ],
  },
  {
    key: 'crm',
    label: 'CRM',
    blurb: 'Clubs, directory and the sales pipeline.',
    items: [
      { to: '/admin/super/clubs', label: 'All Clubs', blurb: 'Onboard clubs, edit plans and subscriptions, sync or remove them.' },
      { to: '/admin/super/marketing', label: 'Club Directory', blurb: 'Prospect clubs, outreach lists and Twenty CRM sync.' },
      { to: '/admin/comms/segments', label: 'Directory Segments', blurb: 'Outreach segments built from prospect activity. Opens in BetterClubhouse; switch to BetterCricket internal to see the directory fields.' },
      { to: '/admin/super/crm/automation', label: 'Sales Automation', blurb: 'Automated outreach and follow-up rules.' },
      { to: '/admin/super/crm', label: 'Sales Pipeline', blurb: 'Trials, demos and deal stages.', exact: true },
      { to: '/admin/super/crm/targets', label: 'Sales Targets', blurb: 'Revenue and signup goals.' },
    ],
  },
  {
    key: 'reporting',
    label: 'Reporting',
    blurb: 'Changelog, sign-ins, ad performance and usage.',
    items: [
      { to: '/admin/changelog', label: 'Changelog', blurb: 'Release history across the platform.' },
      { to: '/admin/super/login-attempts', label: 'Login Attempts', blurb: 'Recent sign-in activity and failures.' },
      { to: '/admin/super/meta-ads', label: 'Meta Ads', blurb: 'Campaign performance and ad signups.' },
      { to: '/admin/super/wizard-analytics', label: 'Setup Wizard Analytics', blurb: 'How clubs move through setup.' },
      { to: '/admin/usage', label: 'Usage', blurb: 'Traffic, features and per-club engagement.' },
    ],
  },
]

// Runtime flags decide which items are visible (e.g. the self-serve trial page
// is hidden until its platform flag is on). Returns the section's items with
// hidden ones removed.
export function visibleSectionItems(section, { selfServeEnabled } = {}) {
  return section.items.filter(i =>
    i.flag !== 'selfServeRegistration' || selfServeEnabled)
}

// Aggregate badge count for a section's sidebar button — sums the counts of
// whichever badge-bearing items it contains.
export function sectionBadgeCount(section, { moduleReqCount = 0, commsReqCount = 0, unpauseReqCount = 0 } = {}) {
  return section.items.reduce((n, i) => {
    if (i.badge === 'moduleRequests') return n + moduleReqCount
    if (i.badge === 'commsRequests') return n + commsReqCount
    if (i.badge === 'unpauseRequests') return n + unpauseReqCount
    return n
  }, 0)
}

export function findSection(key) {
  return SUPER_SECTIONS.find(s => s.key === key) || null
}
