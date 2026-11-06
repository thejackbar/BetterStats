export default {
  version: 'v9.132.4',
  date: '2026-10-27',
  // Above v9.132.3's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-09T20:00:00Z',
  title: 'Fix: a win shown as a loss when the other club stored the result first',
  items: [
    'Fixed: a game your side won could show as a loss. It happened when the other club in the fixture synced it first and the result was stored without a winner, so your page read their loss as yours. Shoalwater Bay\'s Ladies B Grade Grand Final was one.',
    'Fixed: the sync now reads those games again, however old they are, and fills in the winner from Cricket Australia. The result then comes out right on the Games list, the scorecard and the win and loss record.',
  ],
}
