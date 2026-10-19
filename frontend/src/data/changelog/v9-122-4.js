export default {
  version: 'v9.122.4',
  date: '2026-10-25',
  // Above v9.122.3's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-25T05:00:00Z',
  title: 'Weight votes by grade, so a 12 game grade and an 18 game grade are fair against each other',
  items: [
    'In Vote settings there is a new "Weight by grade" setting. It lists each grade the medal counts, with the number of games it has this season, counted from your Fixtures (byes and cancelled rounds are left out).',
    'Same for every grade keeps 3-2-1 everywhere, as it works today. Nothing changes until you pick something else.',
    'Auto-weight measures every grade against your top grade, which is the first one in your own team order (or the grade with the most games if you have not set an order). A vote in a grade with fewer games counts for more, so 3-2-1 is worth the same per game played. If the top grade plays 18 and another plays 12, its votes count x1.5, so a top vote there is worth 4.5.',
    'Manual lets you type the weight for each grade yourself. It starts from the auto weights so nothing resets to 1.',
    'The leaderboard, awards night and each game\'s count use the weighted points. The real vote counts (the 3s, 2s and 1s) never change, and the leaderboard says when points are weighted. Each medal has its own setting.',
  ],
}
