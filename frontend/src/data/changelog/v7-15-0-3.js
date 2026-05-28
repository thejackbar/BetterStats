export default {
  "version": "v7.15.0.3",
  "date": "2026-05-26",
  "sortKey": "2026-05-26T00:00:26Z",
  "title": "Fix: Ducks/Golden Ducks Inflicted — store opposition batter’s score",
  "items": [
    "Most Ducks Inflicted and Most Golden Ducks Inflicted were returning empty because they joined bowler_wickets to batting_innings, but batting_innings only stores OUR club’s batters — our bowlers can only dismiss opposition batters, so the join never matched.",
    "Added batter_runs / batter_balls columns to bowler_wickets (migration 034) and updated the sync to denormalise the dismissed opposition batter’s score onto the wicket row at save time.",
    "Both reports now read these columns directly — Most Ducks Inflicted = rows where batter_runs = 0, Most Golden Ducks Inflicted = rows where batter_runs = 0 AND batter_balls IN (0, 1).",
    "Existing bowler_wickets rows have batter_runs = NULL. A Full Rebuild from Admin → Data Sync is required to backfill them (one-time cost).",
    "Top Bowler/Fielder Combinations: query is structurally correct (joins bowler_wickets where fielder_id is set) but description now notes that data quality depends on the catcher’s name in dismissalText resolving to a known player — substitute fielders or unrecognised names fall through. No SQL change."
  ]
}
