export default {
  version: 'v9.143.7.1',
  date: '2026-11-12',
  // Above v9.143.7's sortKey (2026-11-20T05:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-20T06:00:00Z',
  title: 'Fielding list: catches and stumpings with no names on the scorecard are listed now',
  items: [
    "The list of catches and stumpings on a player's Fielding tab missed any wicket where the scorecard did not name the bowler or the fielder in its dismissal text, even though the scorecard still credited the catch or stumping to the player. For Ryan Carmody that was 17 stumpings and 26 catches. The totals above counted them and the list did not.",
    "Those wickets now appear in the list, dated and placed in order, with \"Not recorded\" where the bowler would be. The summary by bowler holds them as one line at the bottom, and a note under the list says how many rows have no bowler.",
    "A bowler's own caught and bowled is not shown as a catch with no bowler.",
  ],
}
