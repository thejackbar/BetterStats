export default {
  version: 'v9.135.3',
  date: '2026-10-29',
  // Above v9.135.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-12T16:00:00Z',
  title: 'Player page: an error no longer sticks to the next player',
  items: [
    'Fixed: after one player\'s page failed to load, the next player opened from the search box or a teammate link showed the same "Error: Player not found" until the page was reloaded. Each player now loads clean, and a late reply from the player you have left is ignored.',
  ],
}
