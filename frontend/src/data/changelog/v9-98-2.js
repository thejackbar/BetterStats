export default {
  version: 'v9.98.2',
  date: '2026-10-04',
  // Above v9.98.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-04T13:30:00Z',
  title: 'Match CSV template: a worked example that adds up, and a single sundries figure',
  items: [
    'The match CSV template now has an example you can copy. It shows one match with your side’s total and sundries, the opposition’s total, and your bowlers filed against the opposition’s innings. Its example rows used to sit one column out from batting_caught_behind onwards, so the bowling overs landed under the wrong heading.',
    'If your scorebook only has one sundries figure for an innings, put it in innings_extras for your side or opp_extras for theirs. Where a sheet gives both a breakdown and a single figure, the breakdown is used.',
    'Undoing an edit to a hand-entered game now puts its sundries and innings totals back as well. Undoing a delete or an import already did.',
  ],
}
