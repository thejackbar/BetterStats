export default {
  "version": "v7.10",
  "date": "2026-05-25",
  "sortKey": "2026-05-25T00:00:13Z",
  "title": "Sync-failure alerts + rate limiting on expensive endpoints",
  "items": [
    "Bell icon turns red when any scheduled sync has failed since your last visit. The notification panel now shows a \"Sync Failures\" callout at the top with the latest error and a one-click jump to Admin → Sync",
    "Rate limits: Hard Refresh is capped at 1 per hour per club, narrative generation at 5 per hour per club. Server returns 429 with a Retry-After header if exceeded. Protects against accidental button-mashing and runaway costs"
  ]
}
