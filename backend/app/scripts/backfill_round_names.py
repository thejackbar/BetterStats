"""Fill in ``games.round_name`` from Cricket Australia's own fixture list, then write the
premierships it makes visible.

WHY THIS EXISTS
---------------
Automatic premierships (services/premierships.py) need to know which stored game was a GRAND final.
``games.is_final`` cannot say: it is true of any round whose label contains "final". The label is on
the match-list entry the sync already fetches, so an ordinary Sync Now fills ``round_name`` for the
games it rediscovers. An incremental run only scans the seasons still in play, so a club's older
grand finals stay blank until a Full Rebuild. This is the cheap way to fill them: one CA call per
grade, one small column, nothing else touched.

By default only grades with at least one final are read (a season's final rounds sit in grades that
already hold an ``is_final`` game), which keeps the call count to a fraction of the club's history.

WHAT IT TOUCHES
---------------
``games.round_name`` for games under the named club's own grades or played by the club
(``home_org_id`` / ``away_org_id``), and with ``--premierships`` the club's automatic premiership
honours (services/premierships.reconcile). A hand-typed honour is never removed.

USAGE
-----
    python -m app.scripts.backfill_round_names <org-id-or-slug>                       # dry run
    python -m app.scripts.backfill_round_names <org-id-or-slug> --apply --premierships
    python -m app.scripts.backfill_round_names all --apply --premierships
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import grassroots_scores_client as gr
from app.services import premierships


async def _clubs(db, org_ref: str) -> list[dict]:
    if org_ref.lower() == "all":
        rows = (await db.execute(text(
            "SELECT id, name FROM organisations WHERE archived_at IS NULL ORDER BY name"))).mappings().all()
        return [dict(r) for r in rows]
    try:
        where, param = "id = CAST(:ref AS UUID)", str(uuid.UUID(org_ref))
    except ValueError:
        where, param = "LOWER(slug) = LOWER(:ref)", org_ref
    row = (await db.execute(
        text(f"SELECT id, name FROM organisations WHERE {where}"), {"ref": param})).mappings().first()
    return [dict(row)] if row else []


async def run_one(db, org: dict, apply: bool, with_premierships: bool) -> int:
    print(f"\nClub: {org['name']} ({org['id']})")
    # Grades (by raw CA guid) holding a final the club played in.
    grades = (await db.execute(text("""
        SELECT DISTINCT COALESCE(gr.grassroots_id, CAST(gr.id AS TEXT)) AS guid,
               gr.name AS grade_name, s.name AS season_name
          FROM games g
          JOIN grades gr ON gr.id = g.grade_id
          JOIN seasons s ON s.id = gr.season_id
         WHERE g.is_final = TRUE AND g.round_name IS NULL
           AND (g.home_org_id = CAST(:org AS UUID) OR g.away_org_id = CAST(:org AS UUID))
    """), {"org": str(org["id"])})).mappings().all()
    print(f"  {len(grades)} grade(s) hold a final with no round name yet — one CA call each …")

    wanted: dict[str, str] = {}
    for gd in grades:
        try:
            matches = await gr.get_grade_matches(gd["guid"])
        except Exception as e:  # a grade CA no longer serves is not fatal
            print(f"  ! {gd['season_name']} / {gd['grade_name']}: {e}")
            continue
        for m in matches:
            mid, rn = m.get("id"), ((m.get("round") or {}).get("name") or "").strip()
            if mid and rn:
                wanted[mid] = rn

    ids = []
    for mid in wanted:
        try:
            ids.append(uuid.UUID(mid))
        except ValueError:
            pass
    ours = (await db.execute(text("""
        SELECT id, round_name FROM games
         WHERE id = ANY(:ids)
           AND (home_org_id = CAST(:org AS UUID) OR away_org_id = CAST(:org AS UUID))
    """), {"ids": ids, "org": str(org["id"])})).mappings().all()
    todo = [r["id"] for r in ours if wanted.get(str(r["id"])) and r["round_name"] != wanted[str(r["id"])]]
    gf = sum(1 for i in todo if premierships.is_grand_final_round(wanted[str(i)]))
    print(f"  {'Updating' if apply else 'Would update'} {len(todo)} game(s); {gf} of them grand finals.")
    if apply:
        for i in todo:
            await db.execute(text("UPDATE games SET round_name = :rn WHERE id = :id"),
                             {"rn": wanted[str(i)], "id": i})
        await db.commit()
    if with_premierships:
        rep = await premierships.reconcile(db, org["id"], apply=apply)
        print("  Premierships:", {k: v for k, v in rep.items() if k not in ("preview",)})
    return len(todo)


async def run(org_ref: str, apply: bool, with_premierships: bool) -> int:
    async with async_session_maker() as db:
        clubs = await _clubs(db, org_ref)
        if not clubs:
            print(f"No club found for {org_ref!r} (pass an organisation id, public slug, or 'all').")
            return 1
        total = 0
        for org in clubs:
            try:
                total += await run_one(db, org, apply, with_premierships)
            except Exception as e:  # one club's bad data must not stop the sweep
                print(f"  ! {org['name']}: {e}")
                await db.rollback()
        print(f"\n{'Wrote' if apply else 'Would write'} {total} round name(s) across {len(clubs)} club(s).")
        if not apply:
            print("Dry run — re-run with --apply to write these.")
        return 0


def main() -> None:
    args = sys.argv[1:]
    apply = "--apply" in args
    with_prem = "--premierships" in args
    positional = [a for a in args if not a.startswith("--")]
    if not positional:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(run(positional[0], apply, with_prem)))


if __name__ == "__main__":
    main()
