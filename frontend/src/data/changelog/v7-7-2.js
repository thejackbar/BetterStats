export default {
  "version": "v7.7.2",
  "date": "2026-05-22",
  "sortKey": "2026-05-22T00:00:02Z",
  "title": "Sync & Data Quality Fixes",
  "items": [
    "Hard Rebuild now correctly marks sync runs as completed (was stuck at \"running\" forever)",
    "Absent and Did Not Bat dismissals no longer counted as batting innings. Fixes inflated per-game innings counts",
    "Merge history now resolves multi-step redirects correctly. Stats no longer silently drop for merged players",
    "Aggregate sync merge map filtered to active (non-undone) merges only. Fixes poisoned redirects from reversed merges"
  ]
}
