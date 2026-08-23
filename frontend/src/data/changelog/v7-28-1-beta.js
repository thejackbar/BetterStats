export default {
  "version": "v7.28.1 Beta",
  "date": "2026-05-30",
  "sortKey": "2026-05-30T12:00:00Z",
  "title": "Availability Periods. Set a player un/available for a whole date range",
  "items": [
    "New Availability Periods panel on the Availability page: mark a player available, unavailable or maybe across a span of dates in one action, e.g. 'injured 1 Jun–15 Jul', instead of clicking every fixture date. Leave the end date blank for open-ended (out until further notice)",
    "A period auto-covers every fixture in its range, including ones synced in later, and takes an optional reason (Injured, Travelling, Work, Suspended…) shown on the period and in the cell tooltip",
    "Period-driven cells show with a dashed border so you can tell them apart from an explicit answer, and clicking a cell always overrides the period for that one date",
    "Selection respects periods too: a player covered by an 'unavailable' period shows as unavailable in the selection pool and sorts to the bottom, so you won't accidentally pick someone who's out"
  ]
}
