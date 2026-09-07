export default {
  version: 'v9.69.4',
  date: '2026-09-14',
  // Above v9.69.3, or SITE_VERSION never reaches this release.
  sortKey: '2026-09-14T16:00:00Z',
  title: 'One source per season — never both',
  items: [
    'A season is now read from either your Cricket Australia sync or your CricketStatz import, never counted from both. The choice is recorded the moment a CricketStatz match lands in that season, so nothing can drift out of step part way through an import.',
    'Handing a season back to your sync now stops counting the imported copy, instead of counting both until you undo the import.',
    'Any club already holding a season twice is repaired automatically on the next deploy, with no re-import.',
  ],
}
