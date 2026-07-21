export default {
  version: 'v8.76.0',
  date: '2026-07-21',
  sortKey: '2026-07-21T12:00:00Z',
  title: 'Fixed missing games and mislabeled opponents on shared fixtures, per-player import undo, and a club merger tool',
  items: [
    'When a match was between two clubs that both sync with BetterCricket, whichever club synced it first owned the row: the other club could lose the game from their own Games list entirely, and a player could see their own club listed as the opponent in their stats-by-opposition table. Each side of a shared game now records its own club independently, so both clubs see the game and the correct opponent. A background pass fixes existing games without waiting for a resync.',
    'A historical import that attached the wrong player\'s stats can now be undone for just that one player, instead of undoing the whole import and every other player in it. The Past Imports list can be expanded to show each player in a batch with its own undo button.',
    'Added a club merger tool for Super Admins: sync a since-merged club as its own temporary club, then fold its players, seasons, grades, and games into the real, ongoing club in one step. Anything that already exists on both sides (a shared competition, a player who turned out for both clubs) is merged rather than duplicated.',
  ],
}
