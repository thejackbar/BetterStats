export default {
  version: 'v9.146.0',
  date: '2026-11-18',
  // Above v9.145.5's sortKey (2026-11-21T13:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-21T14:00:00Z',
  title: 'Take a game off a player who was named but did not play',
  items: [
    'If a player was named in the side but did not play, for example as 12th man, 13th man or a late withdrawal, you can now mark that exact game. The game comes off their games played on the profile, the season table, leaderboards and milestones.',
    'On a match page, club admins see the team list under the scorecard with a Didn\'t play button beside anyone who did not bat, bowl or take a catch. Pick a reason and add a note if you like. Anyone with a line on the scorecard played the game, so they cannot be marked.',
    'You can also do it from Manual Entries, Adjustments: pick the player, then the game. If you already typed a -1 adjustment for that season, you are offered to move it onto the game so the game is not taken off twice.',
    'The public scorecard says who was named but did not play, and why. A sync or a full rebuild keeps your marks, and every change can be undone from the Audit tab.',
    'New Games to Check tab in Manual Entries: it lists players named in a game where they recorded nothing, in a season where we count more games than Cricket Australia does. Mark each one as not played, or keep it as played and it will not be listed again. Nothing changes on its own.',
    'Fixed: a player\'s season table could add up to less than the games played at the top of the profile. Each season now shows the same figure as the profile\'s Analysis grid, so the two always agree.',
  ],
}
