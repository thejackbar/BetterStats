export default {
  version: 'v1.4.3 Beta',
  date: '2026-06-07',
  sortKey: '2026-06-07T12:00:00Z',
  title: 'Player merge — fix “Internal Server Error” when combining duplicate records',
  items: [
    'Fixed the manual player merge failing with “Internal Server Error” when the two records were the same player held under two IDs (the cross-club shared-ID case). The merge now de-duplicates overlapping game innings instead of crashing.',
    'Merging now also carries across the removed player’s bowling-wicket records, match appearances (incl. captain/keeper flags) and per-grade season stats — previously these were dropped, leaving the kept player short.',
    'If a merge ever is blocked by a genuine data clash, you now get a clear message instead of a blank server error — and the merge is fully reversible from the history tab as before.',
  ],
}
