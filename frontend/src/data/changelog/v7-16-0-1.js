export default {
  "version": "v7.16.0.1",
  "date": "2026-05-26",
  "sortKey": "2026-05-26T00:00:28Z",
  "title": "Fix: backend crash loop from duplicate Alembic revision 033",
  "items": [
    "Three migrations had shipped with the same revision id (033) — match_format, bowler_wickets columns, and families. Alembic refused to run with \"Multiple head revisions\", so the backend container restarted forever and every login returned a non-JSON 5xx (frontend showed the generic \"Login failed\"). Renumbered the latter two to 034 and 035 so the migration chain is linear again."
  ]
}
