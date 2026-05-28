export default {
  "version": "v7.17.1.3",
  "date": "2026-05-26",
  "sortKey": "2026-05-26T00:00:34Z",
  "title": "Fix: apostrophe mismatch in bowler/fielder name resolution",
  "items": [
    "Curly/smart apostrophes in CA scorecard names and dismissal text are now normalised to straight apostrophes before matching — fixes cases like O'Hara where fielder_id was silently left NULL because the two fields used different Unicode quote variants",
    "A Full Rebuild is needed to backfill historical bowler_wickets rows with the corrected fielder_id"
  ]
}
