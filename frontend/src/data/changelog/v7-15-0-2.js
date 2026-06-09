export default {
  "version": "v7.15.0.2",
  "date": "2026-05-26",
  "sortKey": "2026-05-26T00:00:25Z",
  "title": "Fix: Highest Bowled / Caught / C&B / Stumped reports returning empty",
  "items": [
    "Highest Bowled, Caught, Stumped count reports were returning no rows because their LIKE patterns expected long forms (\"bowled\", \"caught%\") but the sync stores dismissal_type as bare short forms (\"b\", \"c\", \"st\"). Patterns updated to match both — same approach already used in the per-player dismissal breakdown chart.",
    "Highest C&B count (batter): rewritten to join batting_innings → bowler_wickets on (game, innings, batting_position). The batter's own dismissal_type is just \"c\" so c&b can't be told apart from a normal catch without consulting the bowler-wickets table."
  ]
}
