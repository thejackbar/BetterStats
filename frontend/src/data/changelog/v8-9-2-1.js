export default {
  version: 'v8.9.2.1',
  date: '2026-06-09',
  sortKey: '2026-06-09T23:00:00Z',
  title: 'Fix duplicate partnership in Records',
  items: [
    'Records → Partnerships no longer lists the same stand twice (e.g. a 233-run opening partnership appearing as both #4 and #5). Duplicate partnership rows are cleaned up and a guard prevents them recurring, and the page now collapses any identical stand on read.',
  ],
}
