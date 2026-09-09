export default {
  version: 'v9.70.6',
  date: '2026-09-16',
  // Above v9.70.5, or SITE_VERSION never reaches this release.
  sortKey: '2026-09-16T18:00:00Z',
  title: 'Career totals for a club holding both sources',
  items: [
    'Reported off a player profile: the innings history read 16 hundreds and the career header above it read 28, with every season both sources cover coming out at exactly double.',
    'The scorecards were right and only the season totals were wrong — where we keep the imported card because your sync never pulled one, the season total was counting that match from both sources.',
    'Career totals, matches, hundreds and averages now count each of those matches once, and no re-import or re-sync is needed for it to take effect.',
  ],
}
