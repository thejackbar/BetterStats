export default {
  version: 'v8.51.1.1',
  date: '2026-07-02',
  sortKey: '2026-07-02T16:00:00Z',
  title: 'Fix: Club Directory CSV download error',
  items: [
    'Downloading the Club Directory as CSV failed with a server error when certain filters were on (for example "exclude already exported" or "exclude suppressed"). The contact filters now build correctly for the CSV and BetterComms exports, so the download works with any filter combination.',
  ],
}
