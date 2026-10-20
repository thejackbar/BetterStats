export default {
  version: 'v9.123.2.2',
  date: '2026-10-19',
  // Above v9.123.2.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-25T11:00:00Z',
  title: 'Fantasy points count fielding from every innings',
  items: [
    'Fixed Fantasy points for fielding in a two-day game. A player who took catches or run outs in both innings was only scored for the second innings, so their catches, run outs and stumpings read short for the round.',
    'Round points update by themselves. A round scored in the last fortnight is checked against the scorecards on the next daily run and settled again if the points have changed. For an older scored round, ask support to re-settle it.',
  ],
}
