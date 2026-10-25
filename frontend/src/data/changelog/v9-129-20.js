export default {
  version: 'v9.129.20',
  date: '2026-10-25',
  // Above v9.129.19's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-08T07:00:00Z',
  title: 'Fantasy: scores keep syncing between rounds',
  items: [
    'Fixed: Sync scores said no round was being played once a round\'s last day had passed, so the games from that last day were never picked up. A round now stays open to syncing from its first day until the next round starts, which covers the days a finished round waits to be confirmed. After its last day it is checked four times a day, not every 10 minutes.',
    'A round that has finished but has not been confirmed now reads \'ended, not confirmed\' on the Fantasy overview, with Sync scores beside it.',
  ],
}
