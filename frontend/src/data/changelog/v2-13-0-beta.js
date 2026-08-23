export default {
  version: 'v2.13.0 Beta',
  date: '2026-06-03',
  sortKey: '2026-06-04T06:00:00Z',
  title: 'BetterIQ. Opposition player page, MVP fix, deeper bowling',
  items: [
    'New “Opposition player” in the BetterIQ sidebar (the old “Opposition” is now “Opposition club”): pick an opponent club, then search any of their players for a full profile: season batting & bowling, recent form, dismissal patterns and their complete record against us.',
    'Fixed the Club MVP board disappearing: it was filtering on player-club membership on top of the season scope (the cross-club anti-pattern). Now scoped by the season’s club, so it always populates.',
    'Player deep-dive bowling is much deeper now: a full bowling profile (wickets, average, economy, strike rate, best, five-fors, maidens), where their wickets come from (top order / middle / lower), and how they take them.',
  ],
}
