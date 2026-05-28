export default {
  "version": "v7.17.2",
  "date": "2026-05-26",
  "sortKey": "2026-05-26T00:00:41Z",
  "title": "StatLab: fix ducks/golden ducks inflicted reports",
  "items": [
    "\"Most ducks inflicted\" and \"Most golden ducks inflicted\" were returning no results — batter run totals were not being stored during scorecard sync. Fixed; run rebuild_bowler_wickets to backfill existing data."
  ]
}
