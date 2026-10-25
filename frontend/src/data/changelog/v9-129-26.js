export default {
  version: 'v9.129.26',
  date: '2026-10-25',
  // Above v9.129.25's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-08T13:00:00Z',
  title: 'Club teaser crawl: pull clubs again now',
  items: [
    'The Club teaser crawl panel has a "Pull again now" control. Pick the oldest 100, 500 or 1,000 clubs, or all of them, and press Pull now. It asks first and quotes the calls and hours it will take at your rate.',
    'It does not run a separate crawl. It marks those clubs due, and the normal crawler takes them at the same rate, inside the same hours, with the Stop button still working. The crawler now wakes straight away, so it starts within seconds instead of at its next look in up to five minutes.',
    'Clubs pulled longest ago go first. A club that fails to pull keeps its last good teaser. If the crawler is stopped or outside its hours, the message says when the clubs will start. The control is hidden while the crawl is off.',
  ],
}
