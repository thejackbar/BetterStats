export default {
  version: 'v9.64.2',
  date: '2026-09-07',
  sortKey: '2026-09-08T18:00:00Z',
  title: 'Strike rate and economy by competition, from the innings that can answer',
  items: [
    'A club asked for batting strike rates and bowling economy by competition, and pointed out that balls faced were only recorded from 2013 onwards, competition by competition. The competition breakdown was dividing every run by only the balls somebody typed in, which inflates the rate on any competition with older innings.',
    'It now works the rate out from the innings that carry a ball count, the same rule every other rate in the app has followed since 9.59. Runs, innings and wickets are still the whole competition\'s.',
    'Where fewer than every innings could answer, the figure carries a dagger and a footnote under the table says how many did.',
  ],
}
