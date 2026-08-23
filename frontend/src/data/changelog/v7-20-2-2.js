export default {
  "version": "v7.20.2.2",
  "date": "2026-05-27",
  "sortKey": "2026-05-27T00:00:58Z",
  "title": "Fix: bowling leaderboard \"Best Figures\" tab now tiebreaks on runs",
  "items": [
    "When the leaderboard was sorted by Best Figures, it ranked players by wickets only, so 9/60 sat above 9/21.",
    "Added a secondary sort on runs conceded (ASC) so 9/21 ranks above 9/28 above 9/60, as expected.",
    "Applies to every leaderboard filter combination: grade, grade-name, finals-only, captain-only, and all-games."
  ]
}
