export default {
  version: 'v9.70.11',
  date: '2026-09-17',
  // Above v9.70.10, or SITE_VERSION never reaches this release.
  sortKey: '2026-09-17T12:00:00Z',
  title: 'Doubled career totals, fixed at the source',
  items: [
    'Clubs holding both a CricketStatz import and a Cricket Australia sync were seeing every shared match counted twice, and it kept coming back after each fix.',
    'The cause was a step late in BetterCricket’s own startup putting an older setting back over the corrected one. It no longer does, so the figures stay right.',
  ],
}
