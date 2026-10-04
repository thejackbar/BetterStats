export default {
  version: 'v9.102.8',
  date: '2026-10-02',
  sortKey: '2026-10-02T14:00:00Z',
  title: 'BetterSelect: pick a player for two games on the same day',
  items: [
    'You can now pick a player for two games on the same day when the games do not clash. A Colts game in the morning and a T20 at night, or a junior game and a senior game, no longer stop the pick. The card shows an amber "Also in" line with the other game and its start time, and the player stays in both teams when you save.',
    'The clash is worked out from the start times on the fixtures, using an estimated length for each format (T20 about 3.5 hours, one day about 8 hours). If the gap between the games is under an hour the line says so. Games that overlap, two-day games, and games with no start time (unless one is junior and one is senior) still stop the pick, as before.',
    'Auto-fill and the BetterIQ suggestion still never put anyone in two games on their own. A player who is already in another team that day is picked by hand.',
    'Fixed: picking a player and getting a pop-up message (a call-up, "marked unavailable", or the new "Also in" note) could wipe the side you were building. The pop-up reloaded the fixture and the unsaved picks went with it.',
  ],
}
