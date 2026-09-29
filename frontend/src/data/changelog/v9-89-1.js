export default {
  version: 'v9.89.1',
  date: '2026-09-23',
  // Above the highest sortKey on origin/main at the time. Check at merge.
  sortKey: '2026-09-29T02:45:00Z',
  title: 'Import Stats: a sheet split by team no longer doubles careers',
  items: [
    'A season-by-season sheet labelled by the club\'s own teams (1XI, 2XI, 3XI) is now compared against the player\'s whole online record, season by season. Cricket Australia names those teams differently most years, so each season used to be checked against only one grade and was often added on top of what was already online.',
    'A season is treated as already online when the online data holds that year under any season row, not only the exact one the sheet was matched to.',
    'Imported rows already committed are corrected on the club\'s next sync, or straight away by re-running the reconciler.',
  ],
}
