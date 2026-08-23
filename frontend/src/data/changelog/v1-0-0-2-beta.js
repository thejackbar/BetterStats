export default {
  "version": "v1.0.0.2 Beta",
  "date": "2026-05-27",
  "sortKey": "2026-05-27T00:01:05Z",
  "title": "Fix: Partnership Records \"Grade Match\" dropdown showed \"[object Object]\"",
  "items": [
    "The /club-admin/grades endpoint was upgraded to return rich objects ({ original_name, display_name, display_name_override, games }) for the AdminGrades rename UI, but the Partnership Records \"Grade Match\" panel still treated the response as an array of strings, so every datalist option rendered \"[object Object]\" and every grade looked unmatched.",
    "AdminPartnershipRecords now normalises the response to display_name strings at both call sites, restoring the autocomplete suggestions and the matched/unmatched count.",
    "Cleaned up two stale duplicates while in the area: a second adminListGrades in lib/api.js and an unreachable second @router.get(\"/grades\") in club_admin.py (FastAPI was silently using the first)."
  ]
}
