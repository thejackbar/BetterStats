export default {
  "version": "v1.0.1 Beta",
  "date": "2026-05-27",
  "sortKey": "2026-05-27T00:01:06Z",
  "title": "Manual entries: usability round 1: career fix, section tabs, dropdowns, WK catches",
  "items": [
    "Fixed: career adjustments now actually apply to player profile lifetime totals. The view from PR 1 had never UNIONed them in. Migration 039 extends v_effective_player_season_stats to include manual_career_adjustments (with NULL season_id so they correctly stay out of season leaderboards).",
    "Career Adjustments tab removed. The \"Adjustments\" tab now handles both. Leave the Season picker blank to save as a career-only adjustment. Existing career rows are listed alongside season rows (\"Career (no season)\" in the Season column). Edit / Delete / Undo all dispatch to the right endpoint based on which kind it is.",
    "WK Catches column added to Spreadsheet mode (was missing).",
    "Section tabs added to both Spreadsheet mode (All / Matches / Batting / Bowling / Fielding) AND the Manual Game form (Match Info / Batting / Bowling / Fielding), so you don't have to scroll across 17 columns or down a long stacked form. Spreadsheet paste still works in section-relative cells.",
    "Up/down spinner arrows hidden on every number input on the Manual Entries page: just type, no more clicking the tiny arrows.",
    "Manual games now show in the player profile per-opposition and per-venue analytics. Previously these only read from game_appearances (which manual games don't populate). Rewritten to union batting/bowling/fielding presence so manual games show up against the opposition and venue you entered."
  ]
}
