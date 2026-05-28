export default {
  "version": "v7.18.5",
  "date": "2026-05-27",
  "sortKey": "2026-05-27T00:00:44Z",
  "title": "Fix: opposition appearances were inflating player match counts",
  "items": [
    "Per-game stat inserts (batting / bowling / fielding / FOW / partnerships / bowler wickets) now gate on \"was this player on OUR team for this game\" rather than \"is this player anywhere in our org\". A current club member who played AGAINST us in a match (on another club's roster that season) was previously having their opposition innings stored as ours, inflating their match count and totals.",
    "New admin endpoint /club-admin/cleanup-opposition-stats removes existing bad rows and recomputes player_season_stats. Cheaper than a full hard refresh."
  ]
}
