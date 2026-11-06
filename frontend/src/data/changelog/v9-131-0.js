export default {
  version: 'v9.131.0',
  date: '2026-10-27',
  // Above v9.130.3's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-09T08:00:00Z',
  title: 'Premierships fill in from grand final scorecards',
  items: [
    'New: when the club wins a grand final, every player in the side gets the Premiership honour without anyone typing it in. It is added after each sync, from the round name and the winner on the scorecard. A 12th man who did not play, and a player who asked to be removed, are left out.',
    'New: each premiership links to its scorecard. A player\'s Premiership badge has a Scorecard link, each flag on the Premierships page shows the opponent, the date and a Scorecard link, and the grand final scorecard shows a Premiership banner that links back to the page.',
    'New: Admin, Awards has a Premierships from scorecards panel. Check scorecards shows what would be added, and Add them writes it. Older grand finals show up after the club\'s next full sync, when their round names arrive.',
    'Changed: a premiership the club already typed in is not doubled. It is linked to the grand final instead and its wording is left alone. If a result is corrected, only honours the app added are taken off. Delete one the app added and it stays gone.',
    'Changed: a grand final with no winner on the card (a draw, or no result) adds nothing, and the panel names it so a club can add the honour by hand.',
  ],
}
