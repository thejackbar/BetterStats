export default {
  version: 'v9.139.0',
  date: '2026-11-02',
  // Above v9.138.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-15T10:20:00Z',
  title: 'Choosing your own scorecard in Card review now changes every total, and best bowling is one entry',
  items: [
    'Fixed: when PlayHQ has a match wrong (the bowling credited to the wrong player, a missing batter, a wrong score) you can type the correct card, link it to the PlayHQ game in Card review and choose your card. The match page followed that choice, but season and career totals kept PlayHQ\'s figures, so the profile disagreed with the match. Now the season counts each match from the scorecard you chose, so profiles, the leaderboard, records and milestones all agree with the match pages.',
    'Changed: once your card is chosen for any match in a season, that season\'s totals are counted match by match (your card for the matches you chose, PlayHQ\'s for the rest). Switching every match in the season back to PlayHQ puts the season back on PlayHQ\'s own totals. Card review tells you this when you choose.',
    'Changed: on Adjustments, best bowling is one box, entered as wickets/runs (for example 4/13). It used to be two boxes, and filling only the wickets made the profile say "4 wickets". An adjustment saved that way earlier says so on its edit form and can be re-entered. A sheet that gives only the figures now fills the wickets as well.',
    'New: when you pick a date on Manual Games and PlayHQ already has a game that day, the form points you to Card review to link the two.',
  ],
}
