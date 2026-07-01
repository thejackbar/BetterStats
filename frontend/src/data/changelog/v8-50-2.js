export default {
  version: 'v8.50.2',
  date: '2026-07-01',
  sortKey: '2026-07-01T18:00:00Z',
  title: 'StatLab grade filter fix',
  items: [
    'Fixed an Internal Server Error when running a StatLab Player Career report with a Grade filter set. The Grade dropdown was sending the grade\'s name instead of its ID, and the server rejected it.',
    'A malformed ID on any StatLab filter now drops that filter instead of crashing the report.',
  ],
}
