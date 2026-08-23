export default {
  version: 'v2.13.1 Beta',
  date: '2026-06-03',
  sortKey: '2026-06-04T07:00:00Z',
  title: 'BetterIQ. Fix empty player search & Club MVP (ambiguous SQL)',
  items: [
    'Fixed the Player-trends search and the Club MVP board coming back empty: recent queries that joined the seasons table left a bare “name” in their GROUP BY, which Postgres rejected as ambiguous (players, seasons and teams all have a name column), 500-ing the request. Qualified the grouping so both populate again. Also hardened the team-fielding and rich-opponent queries that had the same latent issue.',
  ],
}
