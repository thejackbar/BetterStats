export default {
  version: 'v9.123.7.1',
  date: '2026-10-19',
  // Above v9.123.7's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-28T14:00:00Z',
  title: 'A washed-out round no longer comes back on the profile header',
  items: [
    'Where a round was washed out, the season table already took that game off a player\'s total, but the profile header and the by-grade table could put it back. Leederville\'s players read one game above the figure the club expected for the 2025/26 season, in every grade, because Cricket Australia\'s own per-grade count still included the abandoned round. The header now agrees with the season table.',
    'It applies to abandoned and cancelled fixtures where the player was named and recorded nothing. A player Cricket Australia never counted the game for is not reduced, and a game that was played and scored is untouched.',
    'Nothing changes for a club with no called-off games. A season Cricket Australia has not yet counted a recent game for is still raised to the games we hold, as before.',
  ],
}
