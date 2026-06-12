export default {
  version: 'v8.15.1',
  date: '2026-06-13',
  sortKey: '2026-06-13T01:30:00Z',
  title: 'Opposition player fixes: five-year list and empty squads',
  items: [
    'Picking a player from the opposition player search now lands on their profile even when they have not played this season: the club page lists everyone CA has seen at that club in the last five years (under a "Last five years" divider), not just the current-season squad, and the name matching now copes with short names like "S Morgan" against "Morgan, Simon".',
    'A synced opposition club with no usable game data for its latest season (the Murdoch "SQUAD (0)" case) now falls back to live scouting instead of showing an empty squad with full head-to-head.',
    'Players outside the current squad still show their record against us when they are on the historically-hurt-us shelf.',
  ],
}
