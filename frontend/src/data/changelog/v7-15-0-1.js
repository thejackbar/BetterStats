export default {
  "version": "v7.15.0.1",
  "date": "2026-05-26",
  "sortKey": "2026-05-26T00:00:24Z",
  "title": "Fix: Most Consecutive Hundreds 500",
  "items": [
    "Most Consecutive Hundreds and Most Consecutive Scores Without a Century were returning Internal Server Error. Their signatures were missing the `offset` pagination parameter so the body threw NameError. Both signatures fixed."
  ]
}
