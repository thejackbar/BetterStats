export default {
  version: 'v9.139.9.2',
  date: '2026-11-06',
  // Above v9.139.9.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-16T05:45:00Z',
  title: 'The returning-clubs script can run while the Stop switch is on',
  items: [
    'pull_returning_club_teasers has a new --ignore-stop option. It pulls just the archived and expired-trial clubs even when the Stop switch is on, so the main crawl can stay held while those few are done. It says so when it ignores the switch, and it leaves the switch on.',
  ],
}
