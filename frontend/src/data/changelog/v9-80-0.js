export default {
  version: 'v9.80.0',
  date: '2026-09-14',
  // Above v9.79.0's sortKey, which origin/main still has as the highest, or
  // SITE_VERSION never reaches this one. Check origin/main at merge time.
  sortKey: '2026-09-26T06:00:00Z',
  title: 'Competition filters are yours to switch on, and "All" now sums them',
  items: [
    'A new "Show Competition Filters" setting in club admin Settings (just above Password protection). It is off by default. Turn it on to show the Competition filter row on your public Leaderboard, Records, Players, Games and dashboard pages; turn it off to hide it everywhere. The row still only appears when your club plays in more than one competition.',
    'While the filter is on, the "All" option now means the sum of every competition it lists, rather than your Cricket Australia lifetime totals. So the "All" figures line up with the per-competition numbers behind them instead of quietly including grades that sit in no competition.',
  ],
}
