export default {
  version: 'v8.72.0',
  date: '2026-07-17',
  sortKey: '2026-07-17T11:00:00Z',
  title: 'All Clubs: Pause, Cancel and Continue a running Full Sync',
  items: [
    'A club with a live Full Sync (Sync Now or Full Rebuild) now shows Pause Sync and Cancel Sync next to its row on All Clubs.',
    'Pause Sync stops the sync cleanly at its next safe checkpoint. Continue Sync then picks up with a fresh incremental sync rather than starting over.',
    'Cancel Sync stops a running or paused sync for good.',
  ],
}
