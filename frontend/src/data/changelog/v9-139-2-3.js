export default {
  version: 'v9.139.2.3',
  date: '2026-11-03',
  // Above v9.139.2.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-15T16:00:00Z',
  title: 'Biggest wins and biggest defeats are now split by runs and by wickets',
  items: [
    'Fixed: Biggest winning margins and Biggest defeats compared the two sides\' whole-match runs, so a chase showed as a big run margin it never had. Each is replaced by two reports, the same way Closest wins was.',
    'Biggest wins (Runs) and Biggest defeats (Runs) cover matches where the winning side batted first. Biggest wins (Wickets) and Biggest defeats (Wickets) cover chases, most wickets in hand first.',
    'A defeat is the other side\'s win: the row names the team that won, who they played, and the margin.',
  ],
}
