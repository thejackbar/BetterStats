export default {
  version: 'v9.22.3',
  date: '2026-08-13',
  sortKey: '2026-08-16T19:00:00Z',
  title: 'BetterScout: search finds a player by surname, and Tracked means your own tracking',
  items: [
    "\"Scan for other clubs\" could come back empty even for a player genuinely registered elsewhere, if the name on their record didn't match PlayHQ's own spelling closely enough for a full-name search. It now falls back to a surname search and matches loosely, so a nickname or a slightly different spelling no longer blanks the result.",
    "A player marked \"Tracked\" in search results now reflects your own tracking, not anyone else's. Search used to show \"Tracked\" for a player another BetterScout customer had added, or one you had already removed from My Players, since the underlying record stays on file even after you remove it. Fixed everywhere a tracked badge can show.",
  ],
}
