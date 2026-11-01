export default {
  version: 'v9.137.2.1',
  date: '2026-11-01',
  // Above v9.137.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-14T21:00:00Z',
  title: 'Player Cards: Winner Winner and Match Day catch up',
  items: [
    'Fixed: a win now counts for Winner Winner when the scorecard names the winner but not the player\'s team the same way. The result is read from the club\'s own side, then the player\'s team, then the result the club\'s own sync stored.',
    'Fixed: a problem working out one player\'s Winner Winner pack can no longer stop the rest of their packs, including Match Day. It is logged and the page carries on.',
    'New: a catch-up that pays the Winner Winner and Match Day packs players have earned and not been granted, for the whole club at once, by the same rules as opening the page. It can bring the club\'s Winner Winner start day back to the day before, for wins that fell before it.',
    'New: a check that shows, for one player and one day, why a Winner Winner or Match Day pack did or did not arrive: the fixtures that day, whether they are on the team sheet, and every recent win with the reason.',
  ],
}
