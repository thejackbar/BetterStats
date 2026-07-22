export default {
  version: 'v8.77.0',
  date: '2026-07-22',
  sortKey: '2026-07-22T10:00:00Z',
  title: 'Historical stats import: fixed a stray-space name bug, added spelling-mistake detection',
  items: [
    'A hand-kept "Last, First" name with an extra space before the comma (e.g. "Hampton , Neil") used to fail to match the correctly-typed version of the same name ("Hampton, Neil"), silently splitting one player\'s career across two records. Fixed in BetterImport, the merge-duplicates tool, and the partnerships bulk-entry upload, all three read "Last, First" names the same way.',
    'Merge Duplicates now also surfaces near-miss spelling pairs (e.g. "Taylor, Malcolm" vs "Taylor, Malcom") as a separate "possible spelling mistake" tier, so a typo in an old stats sheet doesn\'t sit undetected as two different players. These always need a manual confirm, since a similar name can just as easily be two different club members.',
  ],
}
