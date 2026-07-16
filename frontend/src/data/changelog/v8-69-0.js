export default {
  version: 'v8.69.0',
  date: '2026-07-16',
  sortKey: '2026-07-16T13:00:00Z',
  title: 'Bulk approve for merge duplicates',
  items: [
    'Merge Duplicates gets a "Bulk Approve" button — every candidate pair is already an exact normalised-name match, so one click merges the lot in a single go, picking the same keep/remove side the manual review already uses.',
    'Pairs where either player\'s name is a Cricket Australia-redacted placeholder ("********") are always skipped and left for manual review — two redacted juniors sharing that placeholder text are not provably the same person, so they never auto-merge. Those pairs are flagged "Manual review only" in the list.',
  ],
}
