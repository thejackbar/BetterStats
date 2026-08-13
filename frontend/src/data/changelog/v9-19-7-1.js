export default {
  version: 'v9.19.7.1',
  date: '2026-08-11',
  // Must sort above v9.19.7's 2026-08-15T23:00:00Z key.
  sortKey: '2026-08-15T23:30:00Z',
  title: 'Imported seasons reach batting analysis and StatLab again',
  items: [
    'A club whose imported history shared a year with a junior grade (so the default club filter left the junior grade out) saw an imported season on the club dashboard but nothing on the player\'s own Batting Analysis tab or in StatLab. The season table and the club-wide reports were built straight from per-game scorecards, and an imported season has none behind it. Both now add back the imported and manually-entered totals, so the numbers line up everywhere again.',
    'StatLab dropped an imported or manually-entered season the moment any filter was set, even a season or year range, because that switched it to the same per-game-only view. A season/year/grade filter (and player filters like gender or role) now still finds it; a filter that genuinely needs per-game detail (a date range, an opponent, a dismissal type) still can\'t, since there\'s no scorecard behind an imported season to check it against.',
  ],
}
