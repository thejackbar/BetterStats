export default {
  version: 'v9.149.1',
  date: '2026-11-23',
  // Above v9.149.0's sortKey (2026-11-23T12:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-23T15:00:00Z',
  title: 'Games played keep counting after a career import',
  items: [
    'A career sheet you uploaded through BetterImport is now read as each player\'s career on the day you uploaded it. Games played since then add to the total each week, the same as runs and wickets.',
    'Before this, a player whose sheet held more games than the online record could sit on the same games total round after round, while their runs and wickets kept going up.',
    'If you have been adding games by hand in Manual Entries to keep up, check those players after the next sync, because the games you added will now count twice.',
  ],
}
