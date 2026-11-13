export default {
  version: 'v9.143.8.2',
  date: '2026-11-13',
  // Above v9.143.8.1's sortKey (2026-11-20T07:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-20T08:00:00Z',
  title: 'Fielding: work out the bowler and keeper a scorecard left off',
  items: [
    "Cricket Australia sometimes sends a dismissal with the names missing, like a stumping that reads \"st: b:\" with no keeper or no bowler. Those catches and stumpings showed in a player's fielding total but not against the bowler they came off, so a keeper's count with one bowler read too low.",
    "When the rest of the scorecard leaves only one possible answer (one bowler with a wicket not yet accounted for, or one fielder with a catch or stumping not yet accounted for) the bowler and fielder are now filled in. Where two answers fit, nothing is guessed and it stays under Not recorded.",
    "This applies as a club's scorecards are read again. The ones already stored are corrected when that club's bowler records are rebuilt.",
  ],
}
