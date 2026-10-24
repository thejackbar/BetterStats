export default {
  version: 'v9.129.16',
  date: '2026-10-24',
  // Above v9.129.15's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-08T03:00:00Z',
  title: 'Matches: a linked match is counted once',
  items: [
    'Fixed: a player\'s Matches figure could be roughly double the true number when the club\'s own card for a match was linked to the Cricket Australia game and the two sat under different grade names (for example "U14 Knights" and "NEJCA - U/14 Division 3"). The match was counted once under each name. A linked card is now filed under the grade of the game it is linked to, so the profile header, the by-grade table, the season table and the leaderboard M column count it once.',
    'A card with no linked game still counts under the grade it was entered in.',
  ],
}
