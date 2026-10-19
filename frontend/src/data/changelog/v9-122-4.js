export default {
  version: 'v9.122.4',
  date: '2026-10-19',
  // Above v9.122.3's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-25T05:00:00Z',
  title: 'Fill from last week now follows the grade',
  items: [
    'Fill from last week now picks the last saved XI for the same grade, whichever squad that game sat on. If two grades\' games were filed on one squad, the board used to hand you the other side\'s players.',
    'A grade with no saved XI of its own still falls back to the squad\'s last side, as it did before.',
  ],
}
