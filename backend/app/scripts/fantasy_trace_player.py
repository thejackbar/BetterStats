"""Explain why a Fantasy pool player is on 0 when they have played. Read only.

Finds every club player whose name matches (or the id given), and for each one prints
who they are (ids, pool entry, how many teams picked them, any merges), every game
they have rows in, and the first scoring filter that game fails (not in the effective
games view, not the club's game, wrong season year, grade switched off, no round
covers the date, ...), plus what is stored for them per round.

    python -m app.scripts.fantasy_trace_player <org-id-or-slug> "<name or player id>"
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import fantasy_pool_check as chk


async def run(org: str, term: str) -> None:
    async with async_session_maker() as db:
        row = (await db.execute(text("SELECT id, name FROM organisations WHERE id::text = :o OR slug = :o"), {"o": org})).first()
        if row is None:
            raise SystemExit(f"no club matches {org!r}")
        t = await chk.trace_player(db, row[0], term)
        print(f"\n{row[1]}")
        if t.get("error"):
            print(" ", t["error"]); return
        print(f"  Season {t['season_year']}. Grades counted: " + ("all" if t["grade_scope"] is None else f"{len(t['grade_scope'])} grade row(s)"))
        print("  Rounds: " + "; ".join(f"R{r['n']} {r['status']} {r['start']}..{r['end']}" for r in t["rounds"]))
        if not t["players"]:
            print(f"\n  No club player matches {term!r}.")
        for p in t["players"]:
            print(f"\n  {p['name']}  [{p['id']}]")
            print(f"    grassroots_id={p['grassroots_id']}  playhq_id={p['playhq_id']}  is_player={p['is_player']}")
            print("    pool: " + (f"yes, role {p['pool']['role']} ({p['pool']['role_source']}), {float(p['pool']['total_points']):g} pts, picked in {p['picked_by']} team(s)" if p["pool"] else f"not in the pool (picked in {p['picked_by']} team(s))"))
            for m in p["merges"]:
                role = "merged INTO this record" if not m["was_removed"] else "was merged away"
                print(f"    merge #{m['id']} {m['merged_at']:%d %b %H:%M}: {m['removed_player_name']} -> {m['keep_player_name']} ({role}{', undone' if m['undone_at'] else ''})")
            if not p["games"]:
                print("    games: none. This record has no scorecard rows at all.")
            for g in p["games"]:
                print(f"    {g['date']}  {g['match']}  [{g['grade']}]  rows: {g['rows']}  round: {g['round'] or '-'}  =>  {g['verdict']}")
            print("    stored round points: " + (", ".join(f"R{s['round_number']}={float(s['total_points']):g}{' (typed in)' if s['manual'] else ''}" for s in p["stored"]) or "none"))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        raise SystemExit('usage: python -m app.scripts.fantasy_trace_player <org-id-or-slug> "<name or player id>"')
    asyncio.run(run(args[0], args[1]))
