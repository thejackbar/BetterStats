export default {
  version: 'v9.70.2',
  date: '2026-09-15',
  // Above v9.70.1, or SITE_VERSION never reaches this release.
  sortKey: '2026-09-15T16:00:00Z',
  title: 'The duplicate check now actually finds the duplicates',
  items: [
    'The check that works out which imported match is one your sync already holds was comparing your own club name, which is on both sides of every match — so nearly everything looked identical and almost nothing was matched up. Careers were reading far too high as a result.',
    'It now compares the opposition, with your own club taken off first, and uses which of your sides played to tell apart the two fixtures you play against one club on the same day.',
    'Measured on four of one club’s real seasons: 706 games held between the two sources, down to 404 once the duplicates are matched up.',
  ],
}
