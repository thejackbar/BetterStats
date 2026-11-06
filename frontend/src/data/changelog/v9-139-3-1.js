export default {
  version: 'v9.139.3.1',
  date: '2026-11-03',
  // Above v9.139.3's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-15T20:10:00Z',
  title: 'A stats import and your typed games are now settled one season at a time',
  items: [
    'Fixed: when a stats import and your typed games cover the same seasons, what the import holds beyond your games is now worked out for each season on its own. Before, it was pooled across the player\'s whole career. A season where you had typed more games than the import could hide another season where you had typed fewer, and a player with a long PlayHQ record could swallow the difference. The leftover now stays on its own season instead of turning up under Prior seasons.',
    'Changed: for each season, each figure now shows the larger of the import and your typed games. A season total can therefore be higher than the scorecards typed for that season add up to, when the import held more. If the import is the one that is wrong, remove its row on the import page.',
  ],
}
