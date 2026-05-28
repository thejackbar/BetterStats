export default {
  "version": "v7.19.3.1",
  "date": "2026-05-27",
  "sortKey": "2026-05-27T00:00:52Z",
  "title": "Fix: Merge Players now surfaces same-name duplicates across non-overlapping seasons",
  "items": [
    "Removed the \"disjoint playing eras\" guard from the Merge Players suggestion engine. It was suppressing genuine duplicates in two common cases: junior players who get re-registered with a new participant ID each season (so the two records never share a season), and senior players who return to the club after a long break.",
    "Same-name pairs are now always surfaced as merge candidates regardless of when each record played; the human admin remains the final arbiter on Merge vs Ignore."
  ]
}
