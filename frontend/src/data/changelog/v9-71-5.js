export default {
  version: 'v9.71.5',
  date: '2026-09-09',
  // Above v9.71.4, whose sortKey is the highest so far, or SITE_VERSION never
  // reaches this one.
  sortKey: '2026-09-18T05:00:00Z',
  title: 'Rediscover committees runs on its own, and the crawl re-reads associations',
  items: [
    'Rediscover committees no longer needs the crawler switched on. Stopping the crawler stops the unattended crawl, and pressing Rediscover yourself is the opposite of that — the per-club Rediscover on a club\'s own row has always worked this way, so the two now agree.',
    'It has its own Stop, so you can still halt every bit of PlayHQ traffic. Stopping it part way is safe: clubs it already re-read keep their refreshed committee, and clubs it never reached are left exactly as they were.',
    'A rediscover that was stopped part way says so, instead of printing the same line a finished one does.',
    'The crawl now re-reads the associations of clubs it already has. It only ever read them once, so a club that moved association kept the old one for good and nothing would correct it. Clubs nobody has enriched yet are still served first.',
    'A club that has left every association it played in now reads as having none, rather than keeping the last one on screen.',
  ],
}
