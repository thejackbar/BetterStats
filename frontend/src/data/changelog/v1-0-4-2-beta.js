export default {
  version: 'v1.0.4.2 Beta',
  date: '2026-05-29',
  sortKey: '2026-05-29T13:00:00Z',
  title: 'Fix: Clean Opposition Stats no longer wipes legit aggregate-only players',
  items: [
    "The CLEAN OPPOSITION STATS admin button (added in v7.18.5) was wiping pre-PlayHQ-migration players whose stats only exist as CA career summaries (e.g. MyCricket-era aggregate totals, no scorecards, no appearances). Symptom: player count on the club dashboard suddenly dropped and individual profiles for those players reset to zero — reported for Applecross (1573 players in DB, only 1516 with stats showing).",
    "Root cause: the cleanup endpoint's phantom-row check (NOT EXISTS in batting_innings / bowling_spells / fielding_stats / game_appearances) matched both real phantoms AND legitimate aggregate-only rows. Same SQL shape, no way to tell them apart after the fact.",
    "Added player_season_stats.source ('api' | 'backfill', migration 040). The aggregate sync's API path inserts as 'api' (default), the _backfill_missing_season_stats path inserts as 'backfill'. CLEAN OPPOSITION STATS now restricts its DELETE to source='backfill', so API rows are always preserved even when they have no per-game backing.",
    "If you clicked CLEAN OPPOSITION STATS before this deploy, run Sync Now to restore any legit data that CA's aggregate API still surfaces. Players whose data CA has retired from the per-season API are permanently lost on our side and would need to be re-entered via Manual Season Adjustments.",
  ],
}
