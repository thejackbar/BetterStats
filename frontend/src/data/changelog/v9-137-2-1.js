export default {
  version: 'v9.137.2.1',
  date: '2026-10-31',
  // Above v9.137.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-14T21:00:00Z',
  title: 'Voting: a medal now follows a team that moved grade, even when the sync could not pair the games',
  items: [
    'Fixed: when Cricket Australia moved a team to another grade and the old game was kept as cancelled (because you had picked an XI on it), a medal ticked for the old grade never counted the new grade. The team\'s real game was missing from the voting page, so its players had nothing to vote on. Sync fixtures now spots the pair (a cancelled game in one grade and a live game for the same team on the same day in another) and adds the new grade to every grade-limited medal that counts the old one. Nothing is ever unticked, an all-grades medal is left alone, and a team that still plays its old grade is not treated as moved.',
    'To fix a club already affected, press Sync fixtures once. It works on games that have already been played, and the Hullett Medal picks up Grade 5 straight away. You can also tick the grade yourself under Votes, Settings.',
  ],
}
