export default {
  version: 'v9.139.9.1',
  date: '2026-11-06',
  // Above v9.139.9's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-16T05:30:00Z',
  title: 'A script to re-crawl just the archived and lapsed clubs',
  items: [
    'New server script, pull_returning_club_teasers, re-pulls the season data for clubs whose BetterCricket club is archived, or whose trial has expired without a subscription, and for no one else. A dry run counts the group and lists it. Adding --apply pulls every club in the group, paced and stoppable with the Stop switch.',
  ],
}
