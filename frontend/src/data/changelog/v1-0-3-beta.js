export default {
  "version": "v1.0.3 Beta",
  "date": "2026-05-28",
  "sortKey": "2026-05-28T00:01:09Z",
  "title": "Usage page: role filter + charts (activity, feature mix, role split)",
  "items": [
    "Role filter. Everyone / Super admins / Club admins / Members / Anonymous. Resolves each user's highest-priority membership and filters Summary, Top routes, Top users, and Recent events accordingly. Anonymous = events with no logged-in user.",
    "Activity over time. Area chart showing API hits + page views per bucket (hourly for 24h window, daily for 7d/30d/90d). Both series overlaid for instant comparison.",
    "By feature: horizontal bar chart that rolls raw routes/paths up into meaningful buckets (Players, Yearbooks, StatLab, Marketing, Records, etc.) so you don't have to interpret a wall of /club-admin/players/{id}/refresh strings.",
    "By role. Small donut showing what proportion of activity comes from each user tier (helps answer \"are admins or members driving usage?\").",
    "Top users row now shows a role badge next to the name.",
    "Backend: new endpoints /club-admin/usage/timeseries, /by-feature, /by-role. Existing summary/top-routes/top-users/recent all accept ?role=... All super-admin only."
  ]
}
