export default {
  version: 'v9.142.3.2',
  date: '2026-11-10',
  // Above v9.142.3.1's sortKey (2026-11-19T08:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-19T09:00:00Z',
  title: 'Fees now count games the other club recorded first',
  items: [
    "A game does not belong to either club. A game against another club that also uses BetterCricket is stored once, under whichever club synced it first, and Fees only looked under your own club's season. So a player could have two games on their profile and one match day on their member page. Fees now finds a season's games by the season itself and by which of your players are in them.",
    "Only your own players are charged. The other team's players are not added to your fee list, and a game none of your players is in is ignored.",
    "A grade's Exclude or women's setting comes from your own grade of the same name. Another club's setting on its grade never changes what your players are charged.",
    "The grade settings screen now counts the same games the member pages charge, including games stored under the other club's grade.",
    "The missing games are added the next time your club syncs, or when you press Rebuild match days. They are charged like any other game, so a few members may owe a little more than before. Paid, waived and edited match days are not touched.",
  ],
}
