export default {
  version: 'v9.71.2',
  date: '2026-09-09',
  // Above v9.71.1, or SITE_VERSION never reaches this release.
  sortKey: '2026-09-18T04:00:00Z',
  title: 'The Club Directory says why a button is greyed out',
  items: [
    'Rediscover committees is held back while the crawler is stopped — it re-reads the whole of PlayHQ, so it genuinely cannot run then. It now says so beside the button and points at Start crawling, instead of just sitting there greyed out.',
    'Run crawl batch explains itself the same way.',
    'A rediscover this server has lost track of no longer keeps the button switched off for good. It could already be started again from the server\'s point of view; now the screen agrees.',
    'A rediscover that never got going because the crawler was stopped says that, rather than reporting itself as a finished run that read nothing.',
  ],
}
