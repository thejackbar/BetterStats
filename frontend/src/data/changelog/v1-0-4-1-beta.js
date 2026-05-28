export default {
  "version": "v1.0.4.1 Beta",
  "date": "2026-05-28",
  "sortKey": "2026-05-28T00:01:11Z",
  "title": "Fix: outright losses (and drawn-with-first-innings results) now count toward W/L records",
  "items": [
    "Two-day matches use compound result codes like LOST_OUTRIGHT_LOST_FIRST_INNINGS / WON_OUTRIGHT_WON_FIRST_INNINGS / DRAWN_WON_FIRST_INNINGS. The sync only recognised the bare literals (LOST, WON_ON_FIRST_INNINGS, DREW, TIED) so every outright LOSS (and every drawn-with-FI match) was stored with result=NULL — counted in total games but not in wins or losses.",
    "Result was asymmetric: outright wins were still classified correctly (the winning team has isWinner=true, which the existing code already caught). Only the losing side of outright matches and drawn-with-first-innings rows slipped through.",
    "Parser now matches WON_* → WIN, LOST_* → LOSS, DRAWN_* / DREW / TIED → DRAW. Existing rows with result=NULL get backfilled on the next sync (the scorecard is already fetched per game, so no extra API cost).",
    "Run Sync Now after deploying to populate the result column on historical games — by-opposition and by-venue W/L will retroactively pick up the corrected counts."
  ]
}
