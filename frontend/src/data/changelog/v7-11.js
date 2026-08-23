export default {
  "version": "v7.11",
  "date": "2026-05-25",
  "sortKey": "2026-05-25T00:00:14Z",
  "title": "Activity Log + form validation polish",
  "items": [
    "New Admin → Activity Log page records every sensitive admin action, player merges (and undo), grade merges, season merges, settings changes, with who did it, when, and what changed. Append-only; useful for diagnosing \"wait, where did that come from?\" moments",
    "Image uploads (club logo, player photo, sponsor logo) now fail fast on the client with a clear error when the file is too big or the wrong format, no more 30-second upload + cryptic 400 from the server",
    "CSV / XLSX imports (achievements, partnership records) get the same pre-flight checks: format + 5 MB cap with a helpful message",
    "AdminSettings save status now shows in red when something failed instead of the default accent green. Was previously indistinguishable from a success"
  ]
}
