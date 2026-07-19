export default {
  version: 'v8.74',
  date: '2026-07-19',
  sortKey: '2026-07-19T12:00:00Z',
  title: 'BetterIQ: filters that mean what they say, clickable players, and a fixture-aware Ask',
  items: [
    'Opposition analysis no longer shows an all-time record under a "2025/26" header. The page opens on All seasons (so the big head-to-head numbers are honestly labelled), and the moment you pick a season or grade every card follows it — record, bat/bowl well vs them, venues, last meeting, match-ups.',
    'Fixed "Bat well vs them" and "Bowl well vs them" sometimes listing the OPPONENT\'S own players (and redacted ******** rows). When both clubs are on BetterCricket a shared game carries both sides\' scorecard rows, and the lists weren\'t filtering to your club. Same fix applied to the bowler match-ups grid, the last-meeting scoreline and top performers, and Match review.',
    'The Team filter across BetterIQ is now multi-select: tick any set of grades, or hit "Seniors only" to exclude junior, women\'s, masters and social grades in one go (uses the same automatic grade classification as the merge-grades screen). Works on Opposition, Team analysis, Trends, Review, Preview and Selection.',
    'Threat-profile spider graphs now explain themselves: hover any point for the 0-100 score, the player\'s actual number and the squad average behind it, plus a key under each chart naming the solid shape and the dashed average ring.',
    'Player names across BetterIQ are now clickable. Your players open their Player trends deep-dive; opposition players open their opposition profile — from the squad tables, danger cards, threat radars, match-ups, "bat/bowl well vs them", Team analysis boards, Match review and Match preview.',
    '"Bat/bowl well vs them" now shows each player\'s current squad (1st XI, 2nd XI…) next to their name, so you can see at a glance whether a good record belongs to someone in that side\'s range.',
    'Ask BetterIQ now knows your fixtures and the opposition. Ask "who should we pick for the upcoming 1st XI match" and it finds the fixture, works out the opponent, weighs who bats and bowls well against them (keeping suggestions relevant to that team), and pulls their current-season danger players — kicking off the live scout in the background if it hasn\'t been built yet.',
  ],
}
