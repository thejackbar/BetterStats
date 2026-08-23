export default {
  "version": "v7.16.0.2",
  "date": "2026-05-26",
  "sortKey": "2026-05-26T00:00:29Z",
  "title": "Fix: Admin → Families autocomplete clipped + page reload on every edit",
  "items": [
    "Player-search dropdown in the \"Add member\" row is no longer clipped to a couple of pixels. The family card was wrapped in overflow-hidden which hid the absolute-positioned suggestions list.",
    "Editing a member (add / remove / rename family / save relationship) no longer unmounts and reloads the entire page. The \"Loading…\" spinner now only shows on the initial load; subsequent refreshes happen in the background so expanded cards and in-progress edits survive.",
    "Removed an unstable dependency (the toast helper) from the data-fetching effect that was retriggering reloads whenever any toast appeared anywhere in the app."
  ]
}
