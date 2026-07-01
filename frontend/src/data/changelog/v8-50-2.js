export default {
  version: 'v8.50.2',
  date: '2026-07-01',
  sortKey: '2026-07-01T18:00:00Z',
  title: 'StatLab and season/grade fixes',
  items: [
    'Fixed an Internal Server Error when running a StatLab Player Career report with a Grade filter set. The Grade dropdown was sending the grade\'s name instead of its ID, and the server rejected it.',
    'A malformed ID on any StatLab filter now drops that filter instead of crashing the report.',
    'A club whose season is split across more than one competition (e.g. a masters or Over 60s comp alongside the mainline grades) now sees every grade for that season on the Leaderboard and StatLab, not just the grades under whichever season row happened to be selected.',
  ],
}
