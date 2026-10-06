export default {
  version: 'v9.106.31',
  date: '2026-10-06',
  sortKey: '2026-10-06T14:00:00Z',
  title: 'Club home pages load faster for clubs with a long history',
  items: [
    'The top batters and top bowlers on a club home page were taking about 28 seconds each at a club with 31 seasons, which held up the whole page. The query behind them rebuilt every player\'s season history once for every season they played. It now builds that history once and checks each season against it.',
    'The same check sits behind career totals on player profiles and the milestone scan, so those read from the corrected query too. The figures are unchanged.',
  ],
}
