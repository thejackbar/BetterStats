"""Diagnostic: why is a stand on the match page but not on the records page?

The match page reads `v_effective_partnerships` for one game and falls back to
the stored batter name when a batter has no `players` row. The records page
(`routers/records.py::get_club_records`) only keeps a stand when
`is_club_innings IS NOT FALSE` AND BOTH batters have a `players` row in the
club AND the game has a grade and season. A stand can pass the first read and
fail the second for any of those reasons; this prints which.

Read-only, writes nothing.

Usage from the backend container:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.diagnose_partnership <org_id_or_slug> <YYYY-MM-DD> [--runs N] [--days D]

`--runs` keeps only stands of that many runs; `--days` widens the date window
either side (default 1, since a match date can sit a day off the card).
"""

import argparse
import asyncio
import uuid
from datetime import date, timedelta

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services.club_grades import club_game_sql


async def _resolve_org(org_ref: str) -> str:
    """An org id, or a club slug looked up to one. A slug that matches nothing stops the run."""
    try:
        return str(uuid.UUID(org_ref))
    except ValueError:
        pass
    async with async_session_maker() as session:
        found = (await session.execute(
            text("SELECT id::text FROM organisations WHERE slug = :s"), {"s": org_ref})).scalar()
    if not found:
        raise SystemExit(f"No club with slug {org_ref!r}")
    return found


async def diagnose(org_ref: str, on: date, runs: int | None, days: int) -> None:
    org_id_str = await _resolve_org(org_ref)
    org = uuid.UUID(org_id_str)
    params = {
        "club_org": org,
        "org_id": org,
        "d0": on - timedelta(days=days),
        "d1": on + timedelta(days=days),
        "runs": runs,
    }
    async with async_session_maker() as session:
        rows = (await session.execute(text(f"""
            SELECT g.id::text AS game_id, g.played_at::text AS played_at, g.source AS game_source,
                   g.grade_id::text AS grade_id, gr.name AS grade_name, s.name AS season_name,
                   pt.innings_number, pt.wicket_number, pt.runs, pt.is_club_innings,
                   pt.source AS stand_source,
                   pt.batter1_id::text AS b1_id, pt.batter1_name AS b1_stored,
                   pt.batter2_id::text AS b2_id, pt.batter2_name AS b2_stored,
                   p1.organisation_id::text AS p1_org, COALESCE(p1.display_name_override, p1.name) AS p1_name,
                   p2.organisation_id::text AS p2_org, COALESCE(p2.display_name_override, p2.name) AS p2_name
            FROM v_effective_partnerships pt
            JOIN v_effective_games g ON g.id = pt.game_id
            LEFT JOIN grades gr ON gr.id = g.grade_id
            LEFT JOIN seasons s ON s.id = gr.season_id
            LEFT JOIN players p1 ON p1.id = pt.batter1_id
            LEFT JOIN players p2 ON p2.id = pt.batter2_id
            WHERE {club_game_sql('g')}
              AND g.played_at::date BETWEEN :d0 AND :d1
              AND (CAST(:runs AS int) IS NULL OR pt.runs = CAST(:runs AS int))
            ORDER BY g.played_at, pt.innings_number, pt.wicket_number
        """), params)).mappings().all()

        print(f"{len(rows)} stand(s) for org {org_id_str} between {params['d0']} and {params['d1']}"
              + (f" with {runs} runs" if runs is not None else ""))
        for r in rows:
            why = []
            if r["is_club_innings"] is False:
                why.append("is_club_innings is FALSE (stored as the opposition's innings)")
            if r["b1_id"] is None:
                why.append(f"batter 1 has no player id (stored name {r['b1_stored']!r})")
            elif r["p1_org"] != org_id_str:
                why.append(f"batter 1 player row belongs to org {r['p1_org']}")
            if r["b2_id"] is None:
                why.append(f"batter 2 has no player id (stored name {r['b2_stored']!r})")
            elif r["p2_org"] != org_id_str:
                why.append(f"batter 2 player row belongs to org {r['p2_org']}")
            if r["grade_id"] is None or r["grade_name"] is None:
                why.append("game has no grade")
            elif r["season_name"] is None:
                why.append("grade has no season")
            print(f"\n{r['played_at']} game={r['game_id']} ({r['game_source']}) "
                  f"grade={r['grade_name']!r} season={r['season_name']!r}")
            print(f"  innings {r['innings_number']} wicket {r['wicket_number']}: {r['runs']} runs  "
                  f"[{r['stand_source']}]  {r['p1_name'] or r['b1_stored']} + {r['p2_name'] or r['b2_stored']}")
            print("  records page: " + ("INCLUDED" if not why else "DROPPED because " + "; ".join(why)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("org_id", help="club id (UUID) or club slug")
    ap.add_argument("date", type=date.fromisoformat)
    ap.add_argument("--runs", type=int, default=None)
    ap.add_argument("--days", type=int, default=1)
    a = ap.parse_args()
    asyncio.run(diagnose(a.org_id, a.date, a.runs, a.days))
