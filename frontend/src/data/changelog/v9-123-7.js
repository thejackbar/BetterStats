export default {
  version: 'v9.123.7',
  date: '2026-10-19',
  // Above v9.123.6.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-28T12:00:00Z',
  title: 'A 12th man who did not play no longer counts a game',
  items: [
    'A player who was only 12th man or a substitute fielder was getting a match credited. If they were named on the team sheet but never on the batting card (not even as did not bat), took no wicket or catch, and sat 12th or later on the sheet, that game no longer counts in their matches. It applies on the player profile, the season table, the leaderboards, Records, StatLab and the match-day fee list, so a 12th man who did not play is not charged a match fee.',
    'It also applies where Cricket Australia\'s own season total still counts the game, so BetterCricket can now read a game lower than PlayCricket for these players. Where Cricket Australia already left the game out, nothing is taken off twice.',
    'Anyone with a batting, bowling or fielding line still counts, as does a did not bat on the card and a game where the side never got to bat. A game is only treated this way once the scorecard shows it.',
    'New games are checked as they sync. Games already stored are read by a one-off script that is run club by club, with a dry run first and an undo. Until a club\'s games have been read, nothing changes for that club.',
  ],
}
