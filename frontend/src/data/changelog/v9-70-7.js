export default {
  version: 'v9.70.7',
  date: '2026-09-16',
  // Above v9.70.6, or SITE_VERSION never reaches this release.
  sortKey: '2026-09-16T22:00:00Z',
  title: 'Career totals for clubs holding two sources, finally right',
  items: [
    'For a club with both a CricketStatz import and a Cricket Australia sync, two of the eight places we work out totals had been left on an older definition and were counting each shared match twice.',
    'Careers, matches, hundreds and averages now count each match once — one reported career went from 547 matches and 28 hundreds to 372 and 17, matching the club’s own records.',
    'The startup check that watches for this now reports every time it runs rather than only when something is wrong, so it can’t go unnoticed again.',
  ],
}
