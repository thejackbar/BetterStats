export default {
  version: 'v8.60.1',
  date: '2026-07-14',
  sortKey: '2026-07-14T13:00:00Z',
  title: 'Fixed a fill-in scorecard regression: two more redacted players recovered, and the total no longer double-counts extras',
  items: [
    'The fill-in fix shipped earlier today missed a case: a game can carry a stale, blank player record for a Cricket Australia-redacted participant, and that record was hiding their innings from the same code path the new fill-in handling was meant to fix. Two batters worth 22 and 116 runs were still vanishing from one match, and the shown total came out higher than the real scorecard because a fix for the undercount ended up adding the innings extras twice.',
    'Both gaps are closed: a player record with no usable name now falls back to the same FILL-IN display as a genuine borrowed player, and the innings total is built by adding up the batting card once every row is in place, not by mixing in a Cricket Australia figure that already included extras.',
  ],
}
