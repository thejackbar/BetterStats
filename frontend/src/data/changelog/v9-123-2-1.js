export default {
  version: 'v9.123.2.1',
  date: '2026-10-19',
  // Above v9.123.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-25T10:00:00Z',
  title: 'Games played no longer jumps when next round\'s team is named',
  items: [
    'Fixed a games played count that rose by one for every player named in a fixture that had not been played yet. When a club published next week\'s side on PlayCricket, the next sync added that game to everyone in it, so most of a club read a game or two above PlayCricket with nothing changed on the admin side.',
    'A fixture still marked Upcoming with no scorecard is now left out of Matches on the player profile, the by-grade table, Formats, Competitions, StatLab, Milestones and Records. It counts the moment its scorecard is saved.',
    'A game that has started still counts, and so does a washed-out game that has scorecard data.',
  ],
}
