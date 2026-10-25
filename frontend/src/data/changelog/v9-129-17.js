export default {
  version: 'v9.129.17',
  date: '2026-10-25',
  // Above v9.129.16's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-08T04:00:00Z',
  title: 'Matches: both sides of a same-club fixture count once',
  items: [
    'Fixed: when two sides of the same club play each other, Cricket Australia holds one game and the club holds a card for each side. Only one card can link to the game, so the other side\'s players had their card counted as an extra match on top of Cricket Australia\'s own count, which could leave a player\'s Matches one or two above the real figure. The card is now counted inside the match Cricket Australia already has.',
  ],
}
