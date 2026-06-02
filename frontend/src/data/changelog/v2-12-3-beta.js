export default {
  version: 'v2.12.3 Beta',
  date: '2026-06-03',
  sortKey: '2026-06-04T05:00:00Z',
  title: 'BetterIQ — fix empty player-trends search',
  items: [
    'Fixed the Player trends search returning “no current-season players”: the picker was filtering on player-club membership on top of the season scope, which hid players whose shared cricket ID is owned by a different (first-synced) club. Now scoped purely by the season’s club, like the form movers.',
  ],
}
