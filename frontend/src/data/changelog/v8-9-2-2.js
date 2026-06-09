export default {
  version: 'v8.9.2.2',
  date: '2026-06-09',
  sortKey: '2026-06-09T23:30:00Z',
  title: 'Records: collapse hand-entered partnerships that duplicate synced ones',
  items: [
    'Records → Partnerships no longer shows a stand twice when it exists both as a hand-entered record and as a synced scorecard partnership (e.g. the 233 opening stand at #4 and #5). The two sources label the same stand differently — "Summer 2016/17" vs "2016", and "Last, First" vs "First Last" — so the de-duplication now matches on the season start year and on name regardless of order/format, keeping the synced copy.',
  ],
}
