export default {
  version: 'v9.143.5.4',
  date: '2026-11-12',
  // Above v9.143.5.3's sortKey (2026-11-20T02:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-20T03:00:00Z',
  title: 'Ask BetterIQ no longer stalls looking up a player',
  items: [
    "Ask BetterIQ was taking close to two minutes to find a player by name, which is why questions about a player sat on the loading bar and then failed. It now looks up only the players that match the name.",
    "The games figure it shows for a player is unchanged, and still agrees with the player's own page.",
    "The Players list in BetterIQ is untouched and still loads the whole club.",
  ],
}
