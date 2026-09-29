export default {
  version: 'v9.89.2',
  date: '2026-09-23',
  // Above the highest sortKey on origin/main at the time. Check at merge.
  sortKey: '2026-09-29T03:15:00Z',
  title: 'Grade Type filter: an imported season is no longer counted as junior',
  items: [
    'A senior season that lives only as a BetterImport total (a season played before the online per-grade data begins) no longer shows up under the Juniors, Women\'s or Masters filters. It carries no grade id, so the filter had nothing to exclude it by and kept it under every grade type at once.',
    'The imported season is now classified by its own grade label ("Division 3", etc.), so it counts under the grade type it actually belongs to and stays out of the ones it does not.',
    'Career totals, the season-by-season table, the leaderboards and StatLab all move together. No re-import is needed — every affected club corrects on the next page load.',
  ],
}
