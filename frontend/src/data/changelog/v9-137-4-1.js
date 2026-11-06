export default {
  version: 'v9.137.4.1',
  date: '2026-11-02',
  // Above v9.137.4's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-15T09:10:00Z',
  title: 'Faster player page, and a way back to the club site',
  items: [
    'Faster: a player\'s own page used to ask for the club list, then who is signed in, then their profile, one after the other. It now asks for all three at once, which takes roughly two waits out of the load.',
    'New: a "Back to BetterCricket" link at the top of the player page, and above the name list when you are not signed in. It goes to your club\'s home page.',
    'The server now writes one line to its log each time a player page loads, with how long each part took. If the page is still slow after this, that line says which part.',
  ],
}
