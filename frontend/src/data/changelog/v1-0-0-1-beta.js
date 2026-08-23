export default {
  "version": "v1.0.0.1 Beta",
  "date": "2026-05-27",
  "sortKey": "2026-05-27T00:01:04Z",
  "title": "Hotfix: migration 038 failed on JSON vs JSONB coercion",
  "items": [
    "Migration 038 (v_effective_games view) failed on deploy because games.raw_payload is JSONB in the actual DB while the view tried to UNION it with a NULL::json. PostgreSQL refuses to coerce json to jsonb across a UNION.",
    "Fixed by casting NULL::jsonb (matching the real column type). Backend container now starts cleanly and login works again."
  ]
}
