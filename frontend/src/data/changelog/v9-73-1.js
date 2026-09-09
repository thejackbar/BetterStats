export default {
  version: 'v9.73.1',
  date: '2026-09-09',
  // Above v9.73.0's sortKey, or SITE_VERSION never reaches this one.
  // Check origin/main at merge time.
  sortKey: '2026-09-20T07:00:00Z',
  title: 'BetterComms Lists, Contacts and Segments open again',
  items: [
    'All three screens were showing "Something went wrong" on load. The Role filter added with the committee rediscover work was listed as a filter but was missing from the code that works out which options to offer, so the screen fell over before it drew anything.',
    'The list of filters now has one definition, so a filter added later reaches every screen that offers one rather than needing to be written out a second time.',
    'Nothing was wrong with the contacts themselves, and nothing needs re-exporting — the screens were down whether or not a single contact had a role against them.',
  ],
}
