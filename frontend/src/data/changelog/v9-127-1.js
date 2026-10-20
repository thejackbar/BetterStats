export default {
  version: 'v9.127.1',
  date: '2026-10-20',
  // Above v9.127.0's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-04T18:00:00Z',
  title: 'The CSV import stops linking a card to the wrong grade',
  items: [
    'On a day your club played A, B and C grade against the same opposition, the import matched a card to a game it already held by the date and one word of the opposition name. The B grade card could land on the A grade game while the real B grade game stayed unlinked and counted. The match then showed twice, once under One Day and once under Two Day. That no longer happens.',
    'Before it links a card to a game, the import now checks the scorecard (the same batters on the same scores) and then the grade name. A card whose batters do not match a game is never linked to that game.',
    'When neither the scorecard nor the grade can tell which game a card belongs to, the card is left unlinked and the review says how many. It comes in as a new match. Open Card review, then Possible doubles, to link it once you have checked the pair.',
    'Where a day has only one game that could fit, nothing changes. It still links, even if your sheet says "A grade" and Cricket Australia says "1st Grade".',
  ],
}
