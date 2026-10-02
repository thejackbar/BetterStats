export default {
  version: 'v9.102.14',
  date: '2026-10-03',
  sortKey: '2026-10-03T00:30:00Z',
  title: 'Records opens quickly with a grade type or match type filter on',
  items: [
    'The Records page was taking 8 to 12 seconds to open for most clubs, because most clubs open it with a grade type or match type filter on (a club that hides its juniors always does). Each of the twenty boards was searching every innings on the whole platform before it picked out your club\'s players.',
    'Records now pulls your club\'s own innings, bowling, fielding and appearances out once and every board reads that. In testing on a database the size of the live one, Records with a filter on went from 12 seconds to about 1.3, and a picked grade, a season, Finals only and Captain only all opened in under two seconds.',
    'Every figure on every board is unchanged. We compared the old and new pages board by board, including shared fixtures, imported matches that replace a synced game, and called-off games.',
  ],
}
