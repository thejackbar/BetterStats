export default {
  version: 'v8.67.0',
  date: '2026-07-16',
  sortKey: '2026-07-16T09:00:00Z',
  title: 'Grade-scoped historical imports now reconcile correctly',
  items: [
    'A BetterImport historical stats upload scoped to one grade (common in Premier cricket, where a club keeps a detailed 1st Grade honour board but nothing for the lower grades) was being reconciled against the player\'s Cricket Australia coverage across every grade, not just the grade the upload actually covers. That understated the top-up for players who also had synced history in other grades, and grade-filtered ladders never showed the import figure at all, since it carried no grade of its own. Both are fixed: the reconciler now matches a grade-labelled upload against that grade\'s own Grassroots coverage, and grade-filtered leaderboards read the resulting figure.',
  ],
}
