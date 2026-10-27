export default {
  version: 'v9.131.4',
  date: '2026-10-27',
  // Above v9.131.3's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-09T13:00:00Z',
  title: 'Premierships: no doubled flags, and edit a squad on the page',
  items: [
    'Fixed: a premiership the club had typed in against a team ("1st XI", "2nd Grade One Day Premiership") showed up a second time under the grade name once the scorecards filled it in. The two are now matched by player and season, so the typed flag keeps its wording, takes the scorecard link and the extra card goes. Where a player has fewer typed flags than grand finals won and none of them names the grade, nothing is guessed and both are left as they are.',
    'New: an admin can edit a premiership card that links to a scorecard. Edit squad on the Premierships page marks Player of the Match, 12th Man or 13th Man on a player, adds a player the scorecard missed, or takes a player off. A 12th or 13th man added this way is on the card without a premiership of their own. A player taken off is not added back by the next sync.',
    'Changed: every honour linked to one scorecard now shows as one card, however each was worded, and a note that repeats the player\'s role ("Captain" under a Captain award) is shown once.',
  ],
}
