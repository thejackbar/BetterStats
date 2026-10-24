export default {
  version: 'v9.129.17',
  date: '2026-10-24',
  // Above v9.129.16's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-08T04:00:00Z',
  title: 'Club teaser crawl: when it last pulled a club',
  items: [
    'The Club teaser crawl panel now shows the date and time of the last club it pulled from Cricket Australia, in Perth time, with how long ago that was. A pull that failed does not count, so the time only moves when a club was actually retrieved.',
    'When every club is up to date the panel also says when the next club comes due, so a crawl that is "Caught up" no longer looks stuck.',
    'The panel now says when the crawler last looked for work and what it found (pulled clubs, nothing due, stopped, outside its hours). After a server restart it says it has not reported yet until its first pass finishes.',
  ],
}
