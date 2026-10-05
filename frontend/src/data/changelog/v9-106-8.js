export default {
  version: 'v9.106.8',
  date: '2026-10-05',
  sortKey: '2026-10-05T09:00:00Z',
  title: 'Fantasy: merging a player no longer removes them from teams, plus team and score overrides',
  items: [
    'Fixed: merging a player who had been added to Fantasy by hand into their real record removed them from every team that had picked them. The merge now moves their Fantasy picks, pool entry, round points, captain and vice-captain marks, and draft and waiver records onto the real record, and the stored round lineups follow too. Undoing a merge hands the picks back.',
    'Teams that were already hit can be put back. Where a team\'s stored round lineup still names the player, a repair restores the pick (with the role and, if the team has no captain, the armband), adds them to the pool if needed, scores the rounds again and writes an audit entry. It is run for a club by the support team and shows what it would change before it changes anything. A team that is short of players with no record of who is missing is listed rather than guessed at.',
    'On Fantasy > Registered players, a team that has fewer players than the rules want now shows "11 of 12 players". Open the team and use Add player to put someone back in, optionally in place of another player, and choose which round they count from. Rounds already scored from that round on are scored again, so the player counts as if they had been picked then. The lock, the budget and the role quota are ignored, and anything out of line is shown as a warning. A Remove link takes a player out the same way.',
    'The same page has a new Typed-in scores card, for a player whose games are not in the data yet. Pick the round and the player, type their fantasy points and save. The team scores and the ladder update straight away, and settling a round or unsettling it never changes a typed-in score. Remove hands the round back to the scorecards.',
    'Settling a round that is already scored (to pick up one of the changes above, or a corrected scorecard) no longer gives every team another free transfer. Only the first settle does.',
  ],
}
