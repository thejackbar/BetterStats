export default {
  version: 'v9.138.1',
  date: '2026-11-02',
  // Above v9.138.0's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-15T10:10:00Z',
  title: 'A season-totals import and the same games typed in are now counted once',
  items: [
    'Fixed: if you uploaded a season-by-season stats sheet and then typed in the same games, every figure for those seasons was counted twice: games, innings, runs, overs and wickets. The import now takes your typed games off before it adds anything, the same way it already took off PlayHQ\'s figures. Seasons you never typed games for keep the sheet\'s figures.',
    'Fixed: a sheet that said a player had 3 games in a season while you typed only 1 showed 4 games. It now shows 3: your typed game plus the 2 the sheet holds that you have not typed.',
    'Changed: typing, editing or deleting a game now updates the import straight away. Before, the totals were only right after the next sync.',
  ],
}
