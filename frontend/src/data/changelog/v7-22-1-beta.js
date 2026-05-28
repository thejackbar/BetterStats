export default {
  "version": "v7.22.1 Beta",
  "date": "2026-05-27",
  "sortKey": "2026-05-27T00:01:02Z",
  "title": "Fix: 500 on player profile after CSV import with Excel-dated bowling figures",
  "items": [
    "When best bowling figures like \"1-7\" were typed into Excel, Excel silently auto-converted them to \"1-Jul\". The CSV import then accepted the date-shaped string into best_bowling_figures, and the next time the player profile / leaderboard tried to read the figure it crashed because the aggregation SQL tried to cast \"Jul\" to an integer.",
    "Hardened all bowling-figure SQL filters (8 sites across aggregations, records, yearbooks) to use a strict regex `^[0-9]+-[0-9]+$` instead of the loose `LIKE '%-%'` — so any bad data already in the DB is now silently excluded rather than 500-ing the page.",
    "Added validation at the import boundary: both the CSV upload and the single-entry / spreadsheet paths now reject Excel-dated values with a clear error (\"looks like Excel converted bowling figures into a date — re-enter as text, e.g. prefix with a single quote or use 4/25 format\").",
    "Slash form is now accepted too — \"4/25\" auto-normalizes to \"4-25\" before saving."
  ]
}
