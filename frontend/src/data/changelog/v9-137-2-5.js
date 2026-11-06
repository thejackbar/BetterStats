export default {
  version: 'v9.137.2.5',
  date: '2026-11-02',
  // Above v9.137.2.4's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-14T23:40:00Z',
  title: 'Results posts: two-day games land in the right round',
  items: [
    'Fixed: the latest round on a Results post left out games that run over two Saturdays, like 3rd grade. A two-day game was filed under whichever of its two days Cricket Australia listed first, so 1st grade could land in one week and 3rd grade in the week before. A game now sits in the weekend it finished, next to the one-day grades that finished the same weekend.',
    'Fixed: pasting a match link from a two-day game pulled in last week\'s one-day games and dropped the other two-day grades. The round is now worked out from the weekend that game finished, so the link and the latest round give the same set of games.',
    'The Team of the Week, Team of the Round and period pulls use the same rule, so a two-day game is counted in the round it finished.',
  ],
}
