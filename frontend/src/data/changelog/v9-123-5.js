export default {
  version: 'v9.123.5',
  date: '2026-10-19',
  // Above v9.123.4's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-27T09:00:00Z',
  title: 'Mark a dormant player as no longer dormant',
  items: [
    'A player who has not played for longer than your dormancy window is hidden from Availability, the Squads board and selection until they play again. That left no way to list someone who is coming back before their first game.',
    'On Availability (set the list to All) a dormant player now has a "Not dormant" button. The Squads board has the same button on a card in Potential fill-ins. One tap and they are listed again everywhere, and they can answer on the self-service link and be checked in at nets.',
    'Their real last-played date does not change. The mark counts from the day you press it, so a player who never turns up goes dormant again after the same window. Once they play, the game takes over. A "returning" tag with an undo link shows while it applies, and each change is in Audit History.',
  ],
}
