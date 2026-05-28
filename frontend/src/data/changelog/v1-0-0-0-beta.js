export default {
  "version": "v1.0.0.0 Beta",
  "date": "2026-05-27",
  "sortKey": "2026-05-27T00:01:03Z",
  "title": "v1.0 milestone — manual stat entry is feature-complete",
  "items": [
    "Version reset to v1.0.0.0 Beta — marking the milestone where manual historical-stat entry is end-to-end usable: scorecards, season aggregates, career deltas, CSV bulk import, inline spreadsheet, audit + undo, AND visibility everywhere stats appear.",
    "Manual games now show up in fixture lists alongside synced games — both for clubs on PlayHQ and clubs without it. Clicking through opens the same scorecard view (it transparently falls back to the manual_games table when the ID isn't in the synced games table).",
    "Per-grade leaderboards now see manual data. Records page, player profile per-game tables, yearbooks, StatLab — all now read through four new SQL views (v_effective_games, v_effective_batting_innings, v_effective_bowling_spells, v_effective_fielding_stats) that UNION synced + manual data with a `source` discriminator.",
    "142+ read-path SQL references swapped to the new views in one go; write paths (sync, hard refresh, admin merges) still target the raw tables, so syncing remains untouched by manual data.",
    "The \"Beta\" badge stays on while real clubs put this through its paces. Drops on official launch."
  ]
}
