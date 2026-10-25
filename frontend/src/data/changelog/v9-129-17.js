export default {
  version: 'v9.129.17',
  date: '2026-10-25',
  // Above v9.129.16's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-08T04:00:00Z',
  title: 'Fixtures: both teams show when two of your own sides play each other',
  items: [
    'Fixed: when two of the club\'s own teams play each other (the Applecross 8th XI and 10th XI in One Day Grade 6 Black, for example), only one of them showed on the BetterSelect fixtures. Sync made one fixture for the match, seen from the home side, so the other team had nothing to pick an XI for, take availability against or collect votes on. Sync now makes one fixture for each side, and each goes to its own team.',
    'A game already on your list is fixed the next time you press Sync on the Fixtures screen. The fixture you already have, and any XI picked on it, stays as it is. The missing side is added beside it.',
    'The public Lineups page now marks both sides of such a game as yours and links every player to their profile. Before, only the first team listed did. Votes that use the Play.Cricket team list read the XI for the side of the fixture they are on.',
    'A game against another club, and any game where Cricket Australia does not say who owns both teams, still gives one fixture.',
  ],
}
