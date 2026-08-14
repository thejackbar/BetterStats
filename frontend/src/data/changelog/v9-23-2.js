export default {
  version: 'v9.23.2',
  date: '2026-08-14',
  sortKey: '2026-08-14T12:00:00Z',
  title: 'A merged grade in StatLab now shows its whole history',
  items: [
    'StatLab → Query, filtered to a GRADE that was built by merging several old grade names together (Admin → Merge Grades): any pre-digitisation seasons that only exist as an imported career or season total were dropped the moment the grade filter was applied, even though the same data showed fine with no grade picked.',
    'Fixed for all three grade-grouped query targets (Career, Season and Grade). Imported history now resolves through the same grade merge a real scorecard uses, so it lands under the merged grade\'s name no matter which of its old names it was originally recorded under.',
  ],
}
