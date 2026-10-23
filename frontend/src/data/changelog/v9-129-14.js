export default {
  version: 'v9.129.14',
  date: '2026-10-23',
  // Above v9.129.13's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-08T01:00:00Z',
  title: 'Scorebook import: grade decides which game a match is',
  items: [
    'Fixed: the scorebook CSV import linked a card to the first synced game on the same day that shared a word of the opposition name, and did not look at grade. On a day a club played two grades against one opposition, the B grade card was linked to the A grade game and the real B grade game was counted beside it. Shoalwater Bay and Payneham both had this.',
    'The import now never takes a game of a clearly different grade or age group on a date and an opposition name alone, and prefers the game of the same grade. "Under 12", "U12 Dukes" and "NEJCA - U/12 Division 3" are read as one age group. A card with no game of its grade that day is imported on its own, and shows in Card review, Possible doubles, for a person to link.',
    'Batters in common still pair two records whose grades are named differently, so a grade renamed between sources (for example Under 16 and Under 17 Division 2) is still paired when the scores agree. The CricketStatz import and the doubles scan use the same rule.',
  ],
}
