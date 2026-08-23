export default {
  "version": "v7.14.0",
  "date": "2026-05-26",
  "sortKey": "2026-05-26T00:00:21Z",
  "title": "StatLab: plain-English filters + player attribute filters",
  "items": [
    "Filter operators now show full words (\"at least\", \"more than\") instead of ≥ / > symbols",
    "Metric names are now full English: \"Batting Strike Rate\" instead of \"SR\", \"Batting Average\" instead of \"Avg\", etc. (column headers still use short forms to keep tables compact)",
    "Metric picker is single-column for readability with hover tooltips for truncated labels",
    "New \"Player Attributes\" section in the Context panel: filter by Gender, Player Role, Award category/name, Office Bearer",
    "Award / role / office bearer fields use searchable autocomplete (debounced 180ms) so long lists don't clutter dropdowns",
    "Backend now reads all context filters from the URL via a whitelist: fixes silent ignoring of `first_n_matches`, `milestone_runs`, `on_this_day` that we introduced earlier",
    "New /statlab/picker-values endpoint returns distinct values from players + player_achievements for autocomplete"
  ]
}
