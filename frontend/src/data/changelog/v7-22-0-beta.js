export default {
  "version": "v7.22.0 Beta",
  "date": "2026-05-27",
  "sortKey": "2026-05-27T00:01:01Z",
  "title": "Manual stat entry: bulk CSV import + inline spreadsheet",
  "items": [
    "CSV bulk import for season aggregates: download a template, fill it in Excel / Sheets, upload. Existing player/season/grade combos are upserted (re-runnable without duplicating).",
    "CSV bulk import for full scorecards. Long format where rows sharing the same `game_key` roll up into one manual game with all its batting / bowling / fielding child rows.",
    "Per-row error reporting: rows that fail validation are skipped and listed in the response; the rest still go in, so you can iterate on a CSV without losing the valid rows.",
    "New \"Spreadsheet mode\" on the Season Adjustments tab. Pick a season once, then a paste-friendly grid of player + stat rows. Paste a tab-separated range from Excel into any cell to fill multiple rows at once.",
    "Every bulk import (CSV or spreadsheet) leaves a single \"import\" entry on the Audit tab. Undo wipes every row that import created in one click."
  ]
}
