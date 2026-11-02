export default {
  version: 'v9.137.2.3',
  date: '2026-11-01',
  // Above v9.137.2.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-14T23:00:00Z',
  title: 'Records keeps your history and typed scores',
  items: [
    'Fixed: the Records page left out players whose career came in through a history upload or a hand-typed season. A club that hides its juniors, or that has picked a match type or competition, lost them from Most Runs, Most Wickets, the averages, Most Fifties and Hundreds, Five-Wicket Hauls and the All-Rounders board. They are back, and the totals now match the Leaderboard.',
    'Fixed: a high score typed in under Manual Entries (Adjustments), or carried in by an import, never reached Highest Individual Scores. It is listed now, once, alongside the scorecard innings.',
    'A single competition still leaves out totals that belong to no competition, the same as the Leaderboard.',
  ],
}
