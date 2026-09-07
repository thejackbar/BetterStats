export default {
  version: 'v9.69.5',
  date: '2026-09-14',
  // Above v9.69.4, or SITE_VERSION never reaches this release.
  sortKey: '2026-09-14T17:00:00Z',
  title: 'The app checks its own database schema on start-up',
  items: [
    'A club was found counting its matches from two sources because a database view had not picked up a change, with nothing anywhere reporting a problem.',
    'On start-up the app now reads the schema back and logs a clear error if it does not match, instead of running on quietly and producing wrong figures.',
  ],
}
