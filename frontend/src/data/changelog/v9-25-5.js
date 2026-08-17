export default {
  version: 'v9.25.5',
  date: '2026-08-17',
  sortKey: '2026-08-19T05:00:00Z',
  title: 'Sales Pipeline settings show whether the background score sweeps are actually running',
  items: [
    'A reminder of what already runs in the background: a frequent sweep re-scores any club with new activity (every minute by default), and a full directory sweep recomputes every club regardless (every hour by default) to catch a score that should have decayed from a club simply going quiet — the case a viewed-card correction alone can\'t fix on its own.',
    'Pipeline settings now shows when each of those last ran and what it did, so a cadence set to "hourly" is something a super admin can actually verify rather than take on trust — including a plain failure message if a sweep has started erroring.',
  ],
}
