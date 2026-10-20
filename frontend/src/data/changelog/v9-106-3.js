export default {
  version: 'v9.106.3',
  date: '2026-10-04',
  sortKey: '2026-10-04T09:00:00Z',
  title: 'Season totals from Cricket Australia are back on profiles and the Players list',
  items: [
    'A season we only have Cricket Australia\'s summary for (no scorecards) now counts on a player\'s profile, the Players list, the leaderboards and Milestones. With the usual "juniors not counted" setting on, those seasons were being read as zero, so a player with 4 games showed 0 games, 0 runs and dashes on the Players list.',
    'It only fills in a year where the club holds no scorecard for that player, so nothing is counted twice. A season that sat wholly in a junior grade still stays out, and so does a season split between a junior and a senior grade, because Cricket Australia gives one total across both.',
    'Clubs with only summary figures are covered too, including seasons with no grade breakdown at all.',
  ],
}
