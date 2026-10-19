export default {
  version: 'v9.120.4.1',
  date: '2026-10-24',
  // Above v9.120.4's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-24T10:00:00Z',
  title: 'A game no longer goes missing over one player',
  items: [
    'Fixed a sync problem where a whole game could fail to save, run after run, when it named a player whose new Cricket Australia id was recorded as merged into a player who no longer exists. The game now saves. The player is matched to your existing record by full name, or added as a new player if there is no match.',
    'The Sync page now says when a game could not be saved. Before, those games were dropped with no message and the run still showed OK.',
    'If your club is missing games from an earlier sync, run Sync Now once after this update to bring them in.',
  ],
}
