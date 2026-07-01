export default {
  version: 'v8.50.2',
  date: '2026-07-01',
  sortKey: '2026-07-01T18:00:00Z',
  title: 'StatLab and season/grade fixes',
  items: [
    'Fixed an Internal Server Error when running a StatLab Player Career report with a Grade filter set. The Grade dropdown was sending the grade\'s name instead of its ID, and the server rejected it.',
    'A malformed ID on any StatLab filter now drops that filter instead of crashing the report.',
    'Fixed the Leaderboard and StatLab Grade dropdown dropping a grade entirely for the current season when Cricket Australia renamed it (e.g. "1st Grade" reporting as "Men\'s First Grade") and the club had merged the two names for continuity of records. The dropdown now shows the grade under its merged name instead of hiding it.',
  ],
}
