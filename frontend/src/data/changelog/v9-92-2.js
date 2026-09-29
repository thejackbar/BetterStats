export default {
  version: 'v9.92.2',
  date: '2026-09-30',
  // Above v9.92.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-09-30T10:30:00Z',
  title: 'Photo scorecard: the opposition total no longer double-counts its extras',
  items: [
    'On a scorecard uploaded from a photo, an opposition innings you did not enter batter by batter records the full total and its extras. The scorecard page adds the extras onto the runs when it draws an innings, so a side that made 118 with 9 extras was reading 127. The recorded total is now stored as the batters’ runs alone, so 109 plus 9 extras comes back to 118.',
    'An innings recorded with a total and no extras, and a game with neither recorded, read exactly as before. Hand-entered games were already correct and are untouched.',
  ],
}
