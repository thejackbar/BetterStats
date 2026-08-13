export default {
  version: 'v9.19.7',
  date: '2026-08-11',
  // Must sort above v9.19.6's key, which is itself lifted above v9.19.5's
  // future-dated 2026-08-15T21:00:00Z — see the note in v9-19-6.js.
  sortKey: '2026-08-15T23:00:00Z',
  title: 'Families moved to BetterStats, suggestions confirmed by selection',
  items: [
    'Family setup now lives in BetterStats, under Club Data in the sidebar at /admin/families. The old Clubhouse link redirects there, so nothing breaks.',
    'Family suggestions work the other way round now: instead of starting with everyone included and removing the strangers, you select the players who belong to the family and confirm. Anyone you leave unselected stays in the suggestion list for later.',
  ],
}
