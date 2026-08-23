export default {
  "version": "v7.21.0 Beta",
  "date": "2026-05-27",
  "sortKey": "2026-05-27T00:00:59Z",
  "title": "New: Manual stat entry: backfill historical games and totals",
  "items": [
    "New admin page at /admin/manual-entries with three entry modes:",
    ". Season Adjustments: add or correct a player's totals for a specific season (e.g. \"+1 game, 8 runs, 1 catch\").",
    ". Manual Games: add full or partial historical scorecards with batting / bowling / fielding rows.",
    ". Career Adjustments: career-only totals for when no season info is available.",
    "Manual data flows into leaderboards and career views like any other data, but lives in separate tables, so sync never overwrites it. Hard rebuild is safe too.",
    "Every change records a before/after snapshot in a new audit log. Anything can be undone from the Audit tab: even deletes, which restore the row from the snapshot.",
    "Gated by a new \"Manual stat entry\" capability you can grant per user.",
    "Confirmation modal on every save, edit and delete so accidental clicks don't go through.",
    "\"Beta\" added to the version while we work towards the v1.0.0.0 launch milestone."
  ]
}
