export default {
  version: 'v9.2.7',
  date: '2026-08-04',
  sortKey: '2026-08-04T09:00:00Z',
  title: 'Fixed the Usage map failing to load under traffic',
  items: [
    'The Usage page\'s visitor map could fail with a server error when the site was busy. Visitor tracking was opening an unlimited number of database connections in the background and starving the rest of the app, so the map (and occasionally the notification bell) timed out before it could run.',
    'Visitor location lookups now run once per address instead of once per page view, and only ever update the rows they need to. The lookup used to scan the whole tracking table each time, which got slower as the table grew.',
    'Background tracking now has a ceiling on how much of the database it can use at once, so a spike in traffic can no longer take admin pages down with it.',
  ],
}
