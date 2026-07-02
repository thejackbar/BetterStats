export default {
  version: 'v8.51.1.1',
  date: '2026-07-02',
  sortKey: '2026-07-02T16:00:00Z',
  title: 'Fix: Club Directory CSV download error',
  items: [
    'Downloading the Club Directory as CSV could fail with a server error when a matching club had a malformed association entry. The export now skips the bad entry instead of failing the whole download.',
  ],
}
