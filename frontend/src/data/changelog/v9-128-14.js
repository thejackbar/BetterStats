export default {
  version: 'v9.128.14',
  date: '2026-10-23',
  // Above v9.128.13's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-07T11:00:00Z',
  title: 'Squads: a new team now shows in "Add a team to this squad"',
  items: [
    'A newly synced team could be missing from the "Add a team to this squad" list even though its squad and fixtures were already in. The list only looked at the two most recent seasons, so a team whose season sorted behind two others, for example a season Cricket Australia sent with no start date, was left out.',
    'The list now also includes any season that holds a team with upcoming fixtures. Older seasons with nothing coming up are still left out.',
  ],
}
