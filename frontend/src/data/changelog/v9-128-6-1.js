export default {
  version: 'v9.128.6.1',
  date: '2026-10-21',
  // Above v9.128.6's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-05T21:00:00Z',
  title: 'Leaderboard: the strike rate minimum no longer hides players on a runs board',
  items: [
    'If your club has set a minimum number of innings for a strike rate (Club Settings), the Leaderboard was also using it when the board was ranked by runs, average or anything else, and dropping anyone under it. A player whose career comes from a historical import has no ball-by-ball innings behind it, so the minimum counted them as having none. It could leave a player with a long imported history off a board ranked by runs. The batting minimum now only applies when the board is ranked by strike rate, and the bowling one only when it is ranked by economy. A minimum picked from the pills above the board still applies as before.',
  ],
}
