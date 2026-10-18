export default {
  version: 'v9.120.6.1',
  date: '2026-10-24',
  // Above v9.120.6's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-24T13:00:00Z',
  title: 'An old scorecard that lists a player twice no longer drops the whole game',
  items: [
    'Fixed a sync problem where a game could fail to save, on every sync, because Cricket Australia listed the same player twice in one innings. This was mostly old junior games. The game now saves with the first entry for that player, and the repeat is skipped.',
    'The Sync page now shows more of the games that could not be saved, so the cause of any that remain is easier to find.',
  ],
}
