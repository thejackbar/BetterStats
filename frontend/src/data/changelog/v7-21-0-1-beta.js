export default {
  "version": "v7.21.0.1 Beta",
  "date": "2026-05-27",
  "sortKey": "2026-05-27T00:01:00Z",
  "title": "Fix: manual entry \"valid string\" error + grade dropdown",
  "items": [
    "Saving a season or career adjustment with no Notes filled in returned \"Input should be a valid string\". The empty value was being converted to 0 instead of null. Fixed.",
    "Replaced the free-text Grade UUID input with a proper dropdown filtered to the chosen season, for both season adjustments and manual games.",
    "Changing the season now also clears the grade selection so you can't accidentally end up with a grade from a different season."
  ]
}
