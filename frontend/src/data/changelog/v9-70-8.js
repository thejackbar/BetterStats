export default {
  version: 'v9.70.8',
  date: '2026-09-16',
  // Above v9.70.7, or SITE_VERSION never reaches this release.
  sortKey: '2026-09-17T02:00:00Z',
  title: 'Doubled career totals can no longer come back',
  items: [
    'For clubs holding both a CricketStatz import and a Cricket Australia sync, the setting that counts each shared match once was being overwritten on the server and their careers were flipping between correct and doubled.',
    'BetterCricket now checks for that every hour and puts it straight, instead of relying on it being right at startup.',
  ],
}
