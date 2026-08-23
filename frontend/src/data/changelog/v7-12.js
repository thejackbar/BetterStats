export default {
  "version": "v7.12",
  "date": "2026-05-25",
  "sortKey": "2026-05-25T00:00:15Z",
  "title": "Finer-grained admin roles + Club Users page",
  "items": [
    "New Admin → Users page lets a club Main Admin invite club members and toggle 11 fine-grained capabilities per user: settings, players, merges, yearbooks, awards, sponsors, social posts, milestones, run sync, run hard refresh, manage users",
    "Existing club_admin users keep full access (treated as \"Main Admin\". All capabilities implicit). New \"club_member\" role gets only what is explicitly granted",
    "Sensitive endpoints now enforce capabilities server-side (merges, settings, logo upload, sync, hard refresh, user management). The nav hides links a user can't use",
    "Audit log records user-management actions too (create / update / remove)"
  ]
}
