"""List every match Grassroots discovery finds for a club but that never made
it into `games` — split into "204/no data" (Grassroots doesn't have this
match at all) vs "fetchable but missing" (a real gap in the sync itself).

Why this exists: `sync_grassroots_game_level_data` in sync.py silently drops
any match whose `/scores/matches/{id}` call 204s (see the loop at ~line 1585:
`if not scorecard: stats["gr_games_skipped_no_data"] += 1; continue`). The
docstring on that function claims 204s are "already handled by the PlayHQ
Partner sync path" — but that fallback path (`sync_game_level_data`) was
REMOVED from `sync_organisation` in the May 2026 Partner API audit (see
CLAUDE.md). So today, a 204'd match is gone with no fallback, and a Full
Rebuild re-hits the exact same 204 every time — it can never fix this class
of gap, which is why a club can show fewer matches/wickets than PlayHQ's own
count even right after a rebuild.

This script is READ-ONLY (no DB writes) and mirrors sync.py's discovery loop
closely enough to be trustworthy, but doesn't touch `games`/`players`/etc.

Usage from the backend container:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.list_skipped_matches <org_id> [grade_name_substring]

`grade_name_substring` (optional) narrows to grades whose name contains it
(case-insensitive) — e.g. "1st Grade" — to focus on one competition/season combo.
"""

import asyncio
import sys
import uuid

from sqlalchemy import select, text as sql_text

from app.models.db import Grade, Organisation, Season, async_session_maker
from app.services import grassroots_scores_client as gr


async def list_skipped(org_id_str: str, grade_filter: str | None = None) -> None:
    org_uuid = uuid.UUID(org_id_str)

    async with async_session_maker() as session:
        org = await session.get(Organisation, org_uuid)
        if not org:
            print(f"No organisation {org_id_str}")
            return

        grades_res = await session.execute(
            select(Grade.id, Grade.season_id, Grade.name, Grade.grassroots_id, Season.name, Season.year)
            .join(Season, Grade.season_id == Season.id)
            .where(Season.organisation_id == org_uuid)
        )
        grade_rows = grades_res.all()
        if grade_filter:
            grade_rows = [r for r in grade_rows if grade_filter.lower() in (r[2] or "").lower()]

        existing_res = await session.execute(
            sql_text(
                "SELECT g.id FROM games g "
                "JOIN grades gr ON gr.id = g.grade_id "
                "JOIN seasons s ON s.id = gr.season_id "
                "WHERE s.organisation_id = :oid"
            ),
            {"oid": str(org_uuid)},
        )
        existing_game_ids = {str(r[0]) for r in existing_res.all()}

    print(f"Org: {org.name} ({org.id})")
    print(f"Scanning {len(grade_rows)} grade(s)" + (f" matching {grade_filter!r}" if grade_filter else "") + "...\n")

    org_id_lower = str(org_uuid).lower()
    no_data_count = 0
    fetchable_missing_count = 0
    already_have_count = 0

    for grade_id, season_id, grade_name, grassroots_id, season_name, season_year in grade_rows:
        grade_guid = grassroots_id or str(grade_id)
        matches = await gr.get_grade_matches(grade_guid, force=True)
        our_matches = []
        for m in matches:
            teams = m.get("teams") or []
            our_team = next(
                (t for t in teams if (t.get("owningOrganisation") or {}).get("id", "").lower() == org_id_lower),
                None,
            )
            if our_team:
                our_matches.append((m, our_team, teams))

        if not our_matches:
            continue

        print(f"=== {season_name} ({season_year}) / {grade_name} — {len(our_matches)} of our matches discovered ===")
        for m, our_team, teams in our_matches:
            mid = m.get("id")
            if mid in existing_game_ids:
                already_have_count += 1
                continue

            opp_team = next((t for t in teams if t is not our_team), None)
            opp_name = ""
            if opp_team:
                opp_org = opp_team.get("owningOrganisation") or {}
                opp_name = opp_org.get("name") or opp_team.get("displayName") or opp_team.get("name") or "?"
            date = m.get("date") or (m.get("startTime") or "")[:10] or "?"
            status = m.get("status")

            scorecard = await gr.get_match_scorecard(mid)
            if not scorecard:
                no_data_count += 1
                print(f"  204/no-data   {date}  vs {opp_name:30s}  status={status}  match_id={mid}")
            else:
                fetchable_missing_count += 1
                print(f"  FETCHABLE!!   {date}  vs {opp_name:30s}  status={status}  match_id={mid}  <-- has a 200 scorecard but is NOT in our games table; this is a real sync bug, not a 204 gap")
        print()

    print("Summary:")
    print(f"  already in games table:        {already_have_count}")
    print(f"  204 / no data at Grassroots:    {no_data_count}  (expected gap — no fallback source exists since the PHQ Partner sync path was removed)")
    print(f"  fetchable but missing from DB:  {fetchable_missing_count}  (unexpected — investigate the per-game insert path for these match_ids)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m app.scripts.list_skipped_matches <org_id> [grade_name_substring]")
        sys.exit(1)
    org_arg = sys.argv[1]
    grade_arg = sys.argv[2] if len(sys.argv) > 2 else None
    asyncio.run(list_skipped(org_arg, grade_arg))
