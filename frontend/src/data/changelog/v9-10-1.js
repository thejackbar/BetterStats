export default {
  version: 'v9.10.1',
  date: '2026-08-08',
  sortKey: '2026-08-08T18:00:00Z',
  title: 'BetterFootball: a record per team on the games page',
  items: [
    'The games page shows each team\'s own played, won, lost, drawn and win percentage under the club totals, seniors first and juniors below. The rows always add up to the totals above them.',
    'Those totals now follow the season, grade and finals filters. Filtering to one grade used to leave the cards on the club-wide numbers, reading as though the filter had done nothing.',
    'The players list splits its under-100 band into 1–49 and 50–99, since at a club with a long register most players sit in that range.',
    'A grade written as "Under 18s" or "Over 35s" was being classed as senior. The plural was enough to defeat the check, so any age group written the way clubs actually write it landed in the wrong group.',
  ],
}
