export default {
  version: 'v9.108.5',
  date: '2026-10-08',
  sortKey: '2026-10-08T11:00:00Z',
  title: 'Undoing a merge no longer brings back a person who asked to be hidden',
  items: [
    'If a club merged two records of a person who had asked to be hidden and later undid the merge, the restored record came back visible. It now comes back hidden, the same as the record it was merged into.',
    'Checked that a sync, a Full Rebuild, a hard refresh and a club\'s rows being deleted and pulled again all leave a hidden person hidden, including at a second club that picks up a fixture they played in.',
  ],
}
