export default {
  "version": "v7.23.1.1 Beta",
  "date": "2026-05-29",
  "sortKey": "2026-05-29T10:30:00Z",
  "title": "Fix: opposition + venue totals now reconcile with career match count",
  "items": [
    "Per-opposition and per-venue match counts were including abandoned / washed-out games (team-sheet exists but no winner was determined). The career total uses the aggregate count which excludes those, so summing across opposition or venue rows came out higher than the career total, e.g. Tristram Fletcher showed 312 across oppositions vs 309 in his career stats.",
    "Both queries now filter out games with no recorded result. Abandoned-game appearances stay in game_appearances (so the underlying record isn't lost), they just don't roll up into opposition / venue breakdowns. Wins + losses also reconcile inside each row, e.g. Western Suburbs 15 / 4 / 10 had a NULL-result row; it now shows as 14 / 4 / 10."
  ]
}
