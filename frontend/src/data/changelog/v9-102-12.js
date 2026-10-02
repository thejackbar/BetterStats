export default {
  version: 'v9.102.12',
  date: '2026-10-02',
  sortKey: '2026-10-02T23:00:00Z',
  title: 'Faster club pages, leaderboards, player pages and milestones',
  items: [
    'Club home pages, the Leaderboard, player profiles and the upcoming milestones panel were taking several seconds to load, and the milestones panel sometimes took ten. The database was spending most of that time getting ready to run each stats query rather than running it. That step is now switched off for the whole site, so these pages should open in a fraction of the time.',
    'The Records page read each club\'s season totals fourteen separate times. It now reads them once and every board uses that copy, so an unfiltered Records page no longer waits on the same work fourteen times over. The figures on every board are unchanged.',
    'Records with a grade type or match type filter on (which is how most clubs open it) is still slower than we would like. That one needs separate work and is not part of this release.',
  ],
}
