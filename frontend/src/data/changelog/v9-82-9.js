export default {
  version: 'v9.82.9',
  date: '2026-09-19',
  // Above v9.82.8's sortKey (the highest on origin/main at merge time). Check
  // origin/main at merge time.
  sortKey: '2026-09-28T23:00:00Z',
  title: 'Meta Ads HQ loads again',
  items: [
    'The Meta Ads HQ page (Better HQ → Meta Ads) could sit on "Loading…" and never finish. The dashboard summary was running one query that scanned the whole usage-tracking table on every load, and as that table grew it eventually took longer than the page would wait for.',
    'That query now works from the small set of wizard club-selections and looks up each visitor directly, so it stays fast no matter how much traffic history builds up. The numbers it produces are unchanged.',
  ],
}
