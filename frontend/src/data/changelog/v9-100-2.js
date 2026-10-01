export default {
  version: 'v9.100.2',
  date: '2026-09-30',
  sortKey: '2026-10-08T12:00:00Z',
  title: 'The club teaser crawl has a control panel on the Club Directory',
  items: [
    'The Club Directory page has a new Club teaser crawl panel. Set the calls per second and the hours (Perth time) the crawl runs between, save, and it picks the change up within a couple of minutes. Turn off clears the rate and leaves the hours alone. Switching it on from off asks first, because it starts calling Cricket Australia.',
    'The panel shows whether the crawl is running, off, stopped, waiting for its hours or caught up, and why. It also shows how many clubs have been pulled and are still due, the calls made in the last hour, the average calls a club, and how long the clubs still due will take at the rate you set.',
    'If a large share of pulled clubs read as empty, the panel says so. An upstream problem can look like empty clubs rather than errors, so that is the moment to press Stop crawling and check.',
    'The teaser crawl itself now runs as a steady, paced worker in place of a batch every few minutes. It stays off until a rate is set.',
    'New script for reading pulled snapshots back: python -m app.scripts.inspect_club_teasers lists each club with what its snapshot holds and whether it has enough for a campaign piece, and --show prints the facts for one club so they can be checked against its own page.',
  ],
}
