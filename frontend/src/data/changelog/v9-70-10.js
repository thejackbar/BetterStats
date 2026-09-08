export default {
  version: 'v9.70.10',
  date: '2026-09-17',
  // Above v9.70.9, or SITE_VERSION never reaches this release.
  sortKey: '2026-09-17T09:00:00Z',
  title: 'Duplicate career totals can no longer be reintroduced',
  items: [
    'The setting that counts each shared match once was being silently overwritten on the server, which is why doubled career totals kept coming back for clubs holding both a CricketStatz import and a Cricket Australia sync.',
    'That overwrite is now rejected outright rather than accepted, so the figures stay correct instead of being repaired after the fact.',
  ],
}
