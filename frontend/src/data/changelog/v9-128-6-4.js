export default {
  version: 'v9.128.6.4',
  date: '2026-10-21',
  // Above v9.128.6.3's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-06T00:00:00Z',
  title: 'Imported history stays on the Leaderboard when Competition is set to All',
  items: [
    'On a club that shows the Competition filter, a player whose career came from a historical stats upload could be on the Leaderboard for a moment and then drop off once the page finished loading. The "All" setting was leaving out any history that has no grade, because a history book cannot say which competition a season belonged to. "All" now keeps that history, and the same goes for season totals we hold without scorecards. Picking a single competition still leaves it out, as it should, and a grade that is in no competition still stays out of "All".',
  ],
}
