export default {
  version: 'v9.70.4',
  date: '2026-09-16',
  // Above v9.70.3, or SITE_VERSION never reaches this release.
  sortKey: '2026-09-16T09:00:00Z',
  title: 'The duplicate check now runs when it should',
  items: [
    'The check that matches up an imported match with the one your sync already holds was correct but was not running, so clubs holding both sources were still seeing every match counted twice.',
    'It is now retried nightly as well as after an import and after a full sync, it no longer holds up anything else while it works, and it says in the log what it did each time.',
    'A club can be sorted out immediately from the CricketStatz screen with “Check again for duplicates”.',
  ],
}
