export default {
  version: 'v9.106.11',
  date: '2026-10-05',
  sortKey: '2026-10-05T16:00:00Z',
  title: 'Fantasy: clearer reasons when a player has no stats, and the engine can switch grades off',
  items: [
    'The card on Fantasy > Registered players now says "added by hand" only for a player created in Fantasy with no Cricket Australia or PlayHQ id. Before, it also said so for any synced player whose pool role an admin had changed, which was misleading.',
    'The list underneath is now every player picked by teams who has no games counted this season and no same-name profile to merge, with the usual reasons: their game may be on a different profile (a duplicate on the Players page), in a grade that is switched off, or not synced yet.',
    'The scoring engine can now leave out chosen grades for a season, by grade name, so the same grade is left out whichever club\'s record a shared fixture sits under. A grade that turns up later counts by default. The screen for choosing them is coming next.',
  ],
}
