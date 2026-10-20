export default {
  version: 'v9.125.4',
  date: '2026-10-20',
  // Above v9.125.3's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-04T12:00:00Z',
  title: 'Card review finds club scorecards linked to the wrong game',
  items: [
    'Possible doubles now finds a club scorecard that is linked to the wrong Cricket Australia game. It happens when a club plays two grades against the same opposition on one day: the B grade card is linked to the A grade game, the real B grade game is left unlinked, and the match counts twice, once under One Day and once under Two Day. These were the doubles on some players\' profiles that the list could not see before.',
    'Each one shows the card, the game it is linked to now (and how few of its batters are there), and the game that really matches it. "Move the link to the right match" fixes it. Nothing is deleted, the game the link leaves counts on its own again, and the move can be undone from the match.',
    'A new "Fix the strong ones" button on Possible doubles moves every strong wrong link and links every strong unlinked pair in one batch. It shows a preview with a sample first, checks again afterwards because a freed game may now match its own card, and the whole batch can be undone from the Card review overview. Only strong matches are included, and a link someone chose by hand is left alone.',
    'The kind filter on Possible doubles now reads Wrong link, Not linked and Two club scorecards, with a count for each.',
  ],
}
