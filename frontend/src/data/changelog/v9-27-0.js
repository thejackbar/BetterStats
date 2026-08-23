export default {
  version: 'v9.27.0',
  date: '2026-08-17',
  sortKey: '2026-08-21T03:00:00Z',
  title: 'Match Type reads each game, and a new format split on every player profile',
  items: [
    'The dashboard\'s Match Type filter now reads each match\'s own format instead of the grade\'s. A 1st Grade season is usually a mix of one-day and two-day games, so the grade could never answer it: asking for the two-day figures now gives you exactly the two-day matches out of that same grade, and the one-day ones stay in the one-day column.',
    'Leaderboards, the win rate, runs, wickets, player counts and the recent games list all follow the same per-match reading, so every figure on a filtered page agrees with every other one.',
    'New FORMATS tab on a player profile, under Analysis: batting, bowling and fielding side by side for Two Day, One Day and T20, with a line calling out which format they average best in with the bat and with the ball.',
    'The page is honest about coverage. Matches with no recorded format are counted separately rather than quietly added to one of the three columns, and it tells you how many of a player\'s matches it could actually place.',
    'The Match Type ticks on Admin → Grades are now a fallback, not the filter. They fill in for older matches that were synced before we started recording the format, and only for a grade that plays a single format. A mixed grade tells us nothing useful about one unlabelled game.',
    'A club\'s imported season totals sit out a Match Type filter, because an imported total has no match behind it and so no format. They still count under a Grade Type filter, as before.',
  ],
}
