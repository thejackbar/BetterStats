export default {
  version: 'v9.19.4.2',
  date: '2026-08-11',
  // Must sort above v9.19.4.1's (future-dated) 2026-08-15T19:00:00Z key,
  // or SITE_VERSION keeps reading v9.19.4.1.
  sortKey: '2026-08-15T20:00:00Z',
  title: 'Season list tidy-up',
  items: [
    'A club whose history came in through an import could end up with two rows per season, a bare "1968/69" sitting next to the synced "Summer 1968/69", plus older seasons with no year set. There is now a cleanup that merges those duplicates through the normal Merge Seasons machinery (so it can be undone) and renames the rest to the one format. Run by our team on request.',
  ],
}
