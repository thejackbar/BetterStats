export default {
  version: 'v9.137.1.1',
  date: '2026-10-31',
  // Above v9.137.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-14T17:00:00Z',
  title: 'Voting: a team that moves grade is offered its real game, and its chosen voters come with it',
  items: [
    'Fixed: when Cricket Australia moved a team to another grade, a player on that team could be offered the old game, still showing the old grade and opponent, and told it was the wrong team. A cancelled game is no longer open for voting, is not listed on the voting page, is not nudged, and a bulk Open skips it. An admin can still reopen one from its own page, and ballots already cast on it still count.',
    'Fixed: the people chosen to vote for a team, and a team\'s own "who votes" setting, now follow the team into its new grade. Before, they were stored under the old grade and the team\'s new games fell back to the club default, so a chosen person could not vote for their own team\'s real game.',
    'Admin: a cancelled game shows a CANCELLED badge in the Games list and a short note on its page.',
  ],
}
