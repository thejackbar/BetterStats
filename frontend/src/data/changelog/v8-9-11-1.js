export default {
  version: 'v8.9.11.1',
  date: '2026-06-22',
  sortKey: '2026-06-22T00:00:00Z',
  title: 'Notifications bell stops failing as a whole',
  items: [
    'The notifications panel could show "Internal Server Error" if any one section had trouble loading. Each section now loads on its own, so a single slow or failing query stops breaking the whole bell.',
    'When a section does fail, the rest of the panel still shows and the cause is written to the server log so we can fix the query behind it.',
  ],
}
