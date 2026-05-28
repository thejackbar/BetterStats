export default {
  "version": "v7.15.0",
  "date": "2026-05-26",
  "sortKey": "2026-05-26T00:00:23Z",
  "title": "StatLab: report fixes, customise drawer, admin-approved saved reports",
  "items": [
    "Wicket collapse reports (5/6/7/8/9-wkt) now only show games with complete fall-of-wickets data — no more false positives from sparse FOW records",
    "Unusual dismissals no longer include \"Retired Not Out\" (still includes hit wicket, retired hurt, handled, obstructed, timed out)",
    "Highest C&B count: now two reports — batter view (\"dismissed C&B\") and bowler view (\"C&B wickets taken\") for clarity",
    "Most Ducks Inflicted / Most Golden Ducks Inflicted: re-joined on (game, innings, batting position) so batters aren't silently dropped when their name spelling differs between the bowler and batting tables",
    "Overs now display to 1 decimal place (e.g. \"5.3\" not \"5.30\") consistently across StatLab",
    "Most Balls Bowled in a Match: drops the Overs column, shows balls only across both innings of the match",
    "Most Wickets in a Match: moved from Match to Bowling category where it belongs",
    "Most 90s / Most 40s: split into a count-per-player report and a separate \"Scores in the 90s/40s\" individual-scores list",
    "Customise Query drawer: renamed from \"+ Build custom query\", with helper text clarifying you're tweaking the current report's sort/filters/context",
    "Customise Query: highlights active fields with an accent dot and ring so you can see at a glance what's been modified from the report's defaults",
    "Saved Reports approval: club-visibility saves now go to an admin approval queue first — admins review them under Admin → Saved Reports, then they appear publicly. Private reports skip the queue.",
    "New MANAGE_REPORTS capability — granted to super_admin and club_admin by default; can be granted to club members for distributed approval",
    "Notification bell counts pending report approvals for admins"
  ]
}
