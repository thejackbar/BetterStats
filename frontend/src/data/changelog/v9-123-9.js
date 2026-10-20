export default {
  version: 'v9.123.9',
  date: '2026-10-19',
  // Above v9.123.8's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-29T16:00:00Z',
  title: 'Games Cricket Australia called off no longer count for a player who was only named',
  items: [
    'Cricket Australia sometimes marks a rained-out round as complete, with a result of "Match drawn", while its own scorecard records both teams as abandoned. It does not count a player who was only named in those games. We did, so about twenty Leederville players read one game above PlayCricket for 2020/21, all from 14 November 2020.',
    'Those games are now read from the scorecard and treated like an abandoned fixture. A player who batted, bowled or took a catch in one keeps it, and a genuine draw is untouched.',
    'The sync reads this for every game from now on. Games already stored are read by a one-off dry-run script, club by club, which can be undone from its audit entry. Until a club\'s games have been read, its figures stay as they were.',
    'Match-day fees follow the same rule, so a player who was only named in a called-off game is not enrolled for it.',
  ],
}
