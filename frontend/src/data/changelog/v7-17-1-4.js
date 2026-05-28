export default {
  "version": "v7.17.1.4",
  "date": "2026-05-26",
  "sortKey": "2026-05-26T00:00:35Z",
  "title": "Fix: duplicate bowler/fielder rows for merged players",
  "items": [
    "bowler_fielder_combo now routes bowler_id and fielder_id through merge_logs before grouping — a player who was merged appears as one row with their combined catch count instead of two separate rows",
    "Handles two-hop merges (A→B→C); the C&B self-exclusion check also uses canonical IDs"
  ]
}
