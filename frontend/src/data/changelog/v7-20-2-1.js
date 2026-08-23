export default {
  "version": "v7.20.2.1",
  "date": "2026-05-27",
  "sortKey": "2026-05-27T00:00:57Z",
  "title": "Fix: career best bowling now sorts by runs conceded, not text",
  "items": [
    "Career best bowling was using SQL MAX() on a text column, so \"2-5\" sorted higher than \"2-2\" lexically, even though 2-2 is the better cricketing figure.",
    "Replaced with a proper sort (wickets DESC, runs conceded ASC) across career bowling, player activity, bowling leaderboard, season-by-season, and yearbook bowling queries.",
    "No data backfill needed. The fix is in the read queries, so all clubs and merged players benefit immediately."
  ]
}
