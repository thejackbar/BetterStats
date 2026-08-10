export default {
  version: 'v9.19.4.1',
  date: '2026-08-10',
  // Must sort above v9.19.4's (future-dated) 2026-08-15T18:00:00Z key,
  // or SITE_VERSION keeps reading v9.19.4.
  sortKey: '2026-08-15T19:00:00Z',
  title: 'Undoing a stats import now cleans up after itself',
  items: [
    'Undoing a historical stats import now also removes the player records that import created, so a mis-mapped upload no longer leaves empty names cluttering your Players page. A created player who has since gained anything real — synced stats, a membership, votes, an edited profile — is kept, and the undo tells you either way.',
    'The same applies when you undo a single player\'s rows from an import.',
  ],
}
