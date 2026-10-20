export default {
  version: 'v9.106.18',
  date: '2026-10-06',
  sortKey: '2026-10-06T01:30:00Z',
  title: 'Fantasy: the relink script leaves unfinished games to sync',
  items: [
    'The script that adds missing game rows now skips a game where none of your players has been stored yet. Sync adds the whole side itself on its next run, and rows added first would clash with it. Those games are listed as left to sync.',
  ],
}
