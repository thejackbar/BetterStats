export default {
  "version": "v7.32.1 Beta",
  "date": "2026-06-02",
  "sortKey": "2026-06-02T12:00:00Z",
  "title": "Fix: players at two clubs no longer have the other club's stats counted",
  "items": [
    "A player who has turned out for more than one club (for example a senior club and its junior club) was sometimes having the other club's matches, runs, wickets and catches added to their profile here, so 7 matches for the club could show as 63.",
    "The same person can share one ID across every club they play for, and a second club's sync was attaching its seasons to the player's card. Each club's profile now only ever counts the seasons that belong to that club.",
    "Applies everywhere the number showed up: the player card and season-by-season table, club records, the yearbook, StatLab, milestone projections and BetterIQ. No re-sync needed. The corrected totals show immediately.",
    "Any career milestone badges that had been awarded off the inflated totals (e.g. a '50 matches' badge for someone who's played 7 here) are cleared out, so the milestones shown match each club's real numbers."
  ]
}
