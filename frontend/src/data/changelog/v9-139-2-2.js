export default {
  version: 'v9.139.2.2',
  date: '2026-11-03',
  // Above v9.139.2.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-15T15:00:00Z',
  title: 'Closest wins is now two reports: by runs and by wickets',
  items: [
    'Fixed: StatLab\'s Closest wins report compared the two sides\' whole-match runs, so a chase won by one wicket showed as a win by however many runs the chasing side scored. It is replaced by two reports.',
    'Closest wins (Runs) lists only wins where your side batted first and defended its total, closest margin first, with a Won by (runs) column.',
    'Closest wins (Wickets) lists only successful chases, fewest wickets in hand first, so the one-wicket wins come first, with a Won by (wickets) column.',
    'You can filter and sort on both Won by columns in a custom Team innings query.',
  ],
}
