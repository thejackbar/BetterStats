export default {
  version: 'v9.133.0',
  date: '2026-10-28',
  // Above v9.132.8's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-10T12:00:00Z',
  title: 'Mark a hand-entered match as the grand final, and the premierships follow',
  items: [
    'New: a Grand Final tick on Manual Games and on Upload Historical Scorecard. If your side won the match, every player on its card gets the premiership automatically, on their Honours, the Premierships page and the scorecard.',
    'New: an is_grand_final column in the spreadsheet import. Put yes against the match. On a match you are overwriting, a blank cell keeps whatever was set before.',
    'New: a Details button on every manual and imported match. It edits the match\'s own details (date, teams, result, winner, grade, Final and Grand Final) without touching its scorecard, so setting a grand final on an old imported match cannot lose its fall of wickets. It is logged on the Audit tab and can be undone there.',
    'New: when you save a match marked as the grand final, the page says whether a premiership was written, or why not (no winner recorded, the winner and result disagree, or no grade). Your side has to be named as the winner, or the result has to start with Won.',
  ],
}
