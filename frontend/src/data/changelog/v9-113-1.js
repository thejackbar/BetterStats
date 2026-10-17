export default {
  version: 'v9.113.1',
  date: '2026-10-15',
  sortKey: '2026-10-15T18:00:00Z',
  title: 'Sync fills in a recent game that was stored without its scorecard detail',
  items: [
    'A game can reach us with its result but without its batting, bowling and fielding yet (Cricket Australia fills the detail in later). We kept the game, and because a scheduled sync only reads fixtures newer than the last run, nothing ever went back for the detail. A player\'s appearance counted but their innings did not, so the match total and the runs disagreed.',
    'Every sync now also reads again any game from the last 14 days that has no batting or bowling stored for the club\'s own players, even when the game is older than that run\'s window. It adds the missing rows and nothing else, so a game that already has its detail is left alone.',
    'If a club is waiting on one now, Quick Sync on Admin > Data Sync reads the last 7 days and fills it in straight away.',
  ],
}
