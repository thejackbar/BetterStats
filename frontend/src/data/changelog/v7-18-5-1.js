export default {
  "version": "v7.18.5.1",
  "date": "2026-05-27",
  "sortKey": "2026-05-27T00:00:45Z",
  "title": "Fix: saving a StatLab query no longer 500s",
  "items": [
    "The capability check for saving reports was querying ClubMembership.org_id, but the column is club_id. Every Save This Query click hit an Internal Server Error. Fixed."
  ]
}
