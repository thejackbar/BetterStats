export default {
  "version": "v7.17.1.7",
  "date": "2026-05-26",
  "sortKey": "2026-05-26T00:00:38Z",
  "title": "Fix: notifications 500 (column typo) + saved-report alerts",
  "items": [
    "notifications/summary (and /count) were silently 500ing because the helper used ClubMembership.org_id. The column is club_id. Restored upcoming milestones + made Dismiss properly mark the changelog as seen.",
    "Modal now also surfaces pending saved-report approvals under Needs Attention, alongside player sync requests"
  ]
}
