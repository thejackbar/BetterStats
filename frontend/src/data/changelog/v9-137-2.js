export default {
  version: 'v9.137.2',
  date: '2026-10-31',
  // Above v9.137.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-14T17:00:00Z',
  title: 'Best bowling shows wickets and runs, and Manual Games warns about a date that already has a game',
  items: [
    'Fixed: best bowling on a player\'s profile, the leaderboard and the player list read just "5 wickets" for bowling that was typed in or imported, instead of "5/18". Figures now come with the wickets for hand-entered games and for seasons rebuilt from scorecards.',
    'Fixed: a career best of 6 wickets typed as a season adjustment with no figures could print the figures of a 5 wicket season beside it. The figures now only show when they belong to the best spell, and the page says "6 wickets" when they are not known.',
    'New: when you pick a date on Manual Games, the form tells you if your club already has a game that day, whether it came from PlayHQ or was typed in, and links to it. A game you type in counts on top of what is already there, so a match entered twice is counted twice in every total. The Save box repeats it. You can still save, because two real games in one day is normal.',
  ],
}
