export default {
  version: 'v8.69.1',
  date: '2026-07-16',
  sortKey: '2026-07-16T14:00:00Z',
  title: 'Real progress bar on bulk approve',
  items: [
    'Bulk Approve on Merge Duplicates now merges one pair at a time and shows a real "Merging X of Y…" progress bar instead of a single opaque wait, so a big batch of duplicates gives visible feedback as it works through them.',
    'The individual pair cards are locked while a bulk merge is running, so a stray click can\'t race a pair that\'s already been merged.',
  ],
}
