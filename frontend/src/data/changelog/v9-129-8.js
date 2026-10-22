export default {
  version: 'v9.129.8',
  date: '2026-10-22',
  // Above v9.129.7's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-07T23:00:00Z',
  title: 'Card review: two cards sitting on each other\'s games can be swapped back',
  items: [
    'Possible doubles now finds cards that each sit on the other\'s game. A C grade card was linked to the D grade game and the D grade card (often empty) to the C grade game, so the C grade match counted twice. The earlier repair held these back because moving one link needs the other game to be free.',
    'A new "Swapped links" kind shows the card, the game it belongs on, the other card and where that one goes. "Swap the two links" puts both right in one step. It only offers a swap when the other card is the same grade as the game it would move to, on the same day, against the same opposition, and does not contradict that game\'s scores.',
    'The strong ones are included in "Fix the strong ones" and in the command-line repair, as one batch that can be undone from Recent changes. Nothing is deleted. "Different matches" on a swap is remembered like any other.',
  ],
}
