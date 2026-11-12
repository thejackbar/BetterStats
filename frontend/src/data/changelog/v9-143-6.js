export default {
  version: 'v9.143.6',
  date: '2026-11-12',
  // Above v9.143.5.3's sortKey (2026-11-20T02:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-20T03:00:00Z',
  title: 'Fielding: every catch and stumping, and the bowler it came off',
  items: [
    "A player's Fielding tab now lists every catch and stumping they have taken, oldest first, with the bowler it came off, the batter and the match. A keeper's first stumping is the first row and their latest is the last. Flip it to newest first if you prefer.",
    "Above the list, a summary by bowler shows how many stumpings, catches and keeper catches the player has taken off each one, with the first and latest date. It is there on every player's profile, not only keepers.",
    "Filter the list to stumpings, catches or keeper catches. Rows are numbered from the oldest, so \"stumping 12\" stays stumping 12 whichever way you sort.",
    "The list follows the same filters as the fielding totals above it: grade type, match type, competition, grade and season.",
    "It is built from scorecards, so it can hold fewer than the totals, which also count seasons we only have a total for and caught and bowled. Where it does, a note says how many are listed. Run outs are not listed because no bowler is credited with one.",
    "A bowler the club has hidden from its public site is shown as \"Not shown\" and is not linked. The catch or stumping still counts for the fielder.",
  ],
}
