export default {
  version: 'v9.137.3',
  date: '2026-11-02',
  // Above v9.137.2.4's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-15T09:00:00Z',
  title: 'Player Cards: much faster to load',
  items: [
    'Fixed: cards were slow because every card downloaded the player\'s photo at the size it was uploaded, often several megabytes. A card now asks for a copy about as wide as it is drawn, usually under 150 KB, and the server keeps those copies.',
    'Fixed: the server read all three of a player\'s photos from the database to send one. It now reads only the one asked for.',
    'Fixed: when the club\'s card figures were due for a refresh, the next player to open a page waited several seconds for it, and so did anyone who arrived at the same time. The old figures are now served straight away while one refresh runs in the background, and a page that opens several requests at once shares a single refresh.',
    'Fixed: special cards are brought up to date after the page has loaded rather than before it. A new special card shows on the next visit.',
  ],
}
