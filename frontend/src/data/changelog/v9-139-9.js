export default {
  version: 'v9.139.9',
  date: '2026-11-06',
  // Above v9.139.8's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-16T05:00:00Z',
  title: 'Archived clubs and clubs whose trial has ended now get a season page too',
  items: [
    'The club teaser crawl, the picture drawing and the ad pack used to skip any club linked to a BetterCricket club, even an archived one. They now skip only a club that is a live customer: paying, or on a trial that is still running. A club whose BetterCricket club is archived, or whose trial has ended without a subscription, is pulled like any other, so someone coming back later finds a season page for their club.',
    'On /trial, such a club now opens its season page when it is picked. Claiming from that page asks for more trial time, instead of starting a second trial or opening the paused club site. A club that is paying or still on a trial goes to its own site as before.',
    'A linked club with no subscription records at all is left alone, because we cannot tell whether it is a customer.',
  ],
}
