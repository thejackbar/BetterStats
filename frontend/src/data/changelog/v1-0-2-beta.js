export default {
  "version": "v1.0.2 Beta",
  "date": "2026-05-28",
  "sortKey": "2026-05-28T00:01:08Z",
  "title": "Usage breadcrumbs. See what features people actually use",
  "items": [
    "New backend middleware drops a row in `usage_events` for every API call (route, status, duration, user, hashed IP, user-agent). Cheap, non-blocking. Written via a background task so request latency is unchanged.",
    "Frontend adds a tiny `/api/usage/event` beacon on every React Router navigation, so we also capture page views on marketing pages and other in-app routes that don't naturally hit a backend endpoint. Uses `navigator.sendBeacon` where available so it never blocks navigation.",
    "New super-admin-only page at /admin/usage: 7d/30d windows, total + unique-user/IP summary, top routes (by hits), top users, and a 100-row feed of recent events. Filter by API or page-view.",
    "Privacy: IP addresses are stored only as a 16-char SHA-256 prefix, never raw. Noisy endpoints (health, /uploads, the 60s notification poll, /usage/event itself) are skipped so the table stays readable."
  ]
}
