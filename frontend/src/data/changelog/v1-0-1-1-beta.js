export default {
  "version": "v1.0.1.1 Beta",
  "date": "2026-05-27",
  "sortKey": "2026-05-27T00:01:07Z",
  "title": "Manual game: typeahead autocomplete on Opposition + Venue",
  "items": [
    "New ComboInput component on the manual-game form: as you type in Opposition or Venue, a dropdown filters to the matching values already in your club's history (drawn from both synced games AND past manual entries).",
    "Pick a known value with one click to avoid typos and inconsistent spellings (\"Bayswater\" vs \"Bayswater CC\" vs \"Bayswater Cricket Club\" would otherwise all be different oppositions in analytics).",
    "You can still enter a completely new value (e.g. for a defunct club not in any past data), when you do, a small ⚠ \"New value, double-check the spelling\" hint appears under the field so it's a deliberate choice rather than a typo.",
    "Backend endpoint /club-admin/manual-entries/known-values returns the distinct opposition + venue lists per org."
  ]
}
