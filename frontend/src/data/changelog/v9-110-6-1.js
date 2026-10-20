export default {
  version: 'v9.110.6.1',
  date: '2026-10-12',
  // Above v9.110.6's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-12T19:30:00Z',
  title: 'Scorecard import names the bad cell instead of failing',
  items: [
    'Importing a scorecard spreadsheet with a cell that is not a number in a number column (a stray backtick where a wicket count belongs, "n/a" in a runs column) showed only "Internal Server Error". The review screen now lists each bad cell with its row, player, match and column, and the Import button stays off until the file is fixed.',
    'Nothing is written while a bad cell remains, so correct it in the spreadsheet and choose the file again.',
  ],
}
