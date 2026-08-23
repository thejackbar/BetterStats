export default {
  version: 'v1.4.1 Beta',
  date: '2026-06-06',
  sortKey: '2026-06-06T20:00:00Z',
  title: 'Better HQ: staff dashboard, per-club usage & switcher fixes',
  items: [
    'Fixed the Platform Overview “Internal Server Error” (the fleet stats query has been rewritten to scale across every club).',
    'Rebuilt it as Better HQ: platform tools laid out as tiles, headline KPIs incl. estimated ARR, a “needs attention” worklist (lapsed subs, stale syncs, dormant clubs), and subscription + module-adoption rollups.',
    'Usage is now genuinely platform-wide: a new “By club” breakdown attributes page views to each club, so it’s no longer dominated by one club’s traffic.',
    'New “Visitors” panel on Usage: new vs returning vs multi-day visitors, derived from the privacy-preserving IP hash (we never store raw IPs).',
    'When a super admin switches clubs, the public site nav bar now reflects the club being managed instead of staying on the previous club.',
  ],
}
