export default {
  version: 'v8.78.3',
  date: '2026-07-23',
  sortKey: '2026-07-23T12:00:00Z',
  title: 'Match scorecard: fixed the query error that was still breaking the rebuild',
  items: [
    'The scorecard rebuild from the last few entries had one more bug: it tried to query a player\'s display name directly, but that field is computed in Python rather than stored as its own database column, so the query itself failed every time and the page silently fell back to the old, broken rendering again. Fixed by querying the two real columns that name is built from instead.',
  ],
}
