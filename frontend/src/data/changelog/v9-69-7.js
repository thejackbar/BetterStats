export default {
  version: 'v9.69.7',
  date: '2026-09-14',
  // Above v9.69.6, or SITE_VERSION never reaches this release.
  sortKey: '2026-09-14T19:00:00Z',
  title: 'The by-grade grid stops counting a season twice',
  items: [
    "A player's season-by-grade grid still counted both sources for a season read from CricketStatz, because it reads Cricket Australia's own per-grade totals — a separate table the change only covered elsewhere.",
    'The two sources file the same cricket under different grade names, so instead of one winning they landed in separate rows and added.',
    'The grid and the grade record boards now follow the same choice as the rest of your figures.',
  ],
}
