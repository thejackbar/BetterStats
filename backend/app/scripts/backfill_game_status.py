"""Fill in ``games.status`` from Cricket Australia's own fixture list.

WHY THIS EXISTS
---------------
A player's matches-played figure comes straight from CA's aggregate API, and
CA counts a player as having played the moment he is named in the side —
washout or not. So a club that named a team for three rained-off Saturdays
sees those three on every one of those players' records.

Migration 266 corrects that by netting off any abandoned or cancelled fixture
a player was named in and recorded nothing at all in. It needs to know which
fixtures those were, which is what ``games.status`` holds. The column is new,
so every game synced before it existed reads NULL and goes on counting.

The sync writes it now, for new fixtures and (via the bulk pass beside
``is_final`` and ``match_format``) for every game each run rediscovers. So a
club's CURRENT season corrects itself on an ordinary Sync Now, with no Full
Rebuild and no extra API call — the status is already on the match-list entry
the discovery loop fetches. This script is the retroactive half, for the
seasons an incremental run no longer scans.

A club onboarded after this shipped has nothing to fix.

HOW FAR BACK
------------
Every season by default, unlike ``backfill_match_format``, whose default is
narrow because it is correcting money that only matters for the season a club
is collecting in. This corrects a career total, and a career total is read
back to whenever the club's records start. It is one CA call per grade and
writes one small column, so the whole history is affordable.

``--season YYYY`` narrows it when only one year is in question.

WHAT IT TOUCHES
---------------
``games.status`` only, for games under the named club's own grades. A grade
match list is competition-wide and names plenty of fixtures that are not ours,
so the write is restricted to games we actually hold under this club.

Nothing else has to run afterwards. The matches figure is corrected on read by
``v_effective_player_season_stats``, so the profile is right on the next page
load. The one exception is a club whose season rows came from "Fix Missing
Totals" (``source = 'backfill'``) rather than from CA: those hold a stored
count computed from per-game rows, so re-run that once this has been applied.
The script says so when it finds any.

USAGE
-----
    python -m app.scripts.backfill_game_status <org-id-or-slug>            # dry run
    python -m app.scripts.backfill_game_status <org-id-or-slug> --apply
    python -m app.scripts.backfill_game_status <org-id-or-slug> --apply --season 2025
    python -m app.scripts.backfill_game_status all --apply                 # every club
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from collections import Counter

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import grassroots_scores_client as gr
from app.services.game_status import NOT_PLAYED_STATUSES


async def _clubs(db, org_ref: str) -> list[dict]:
    if org_ref.lower() == "all":
        rows = (await db.execute(text(
            "SELECT id, name FROM organisations "
            "WHERE archived_at IS NULL ORDER BY name"
        ))).mappings().all()
        return [dict(r) for r in rows]
    try:
        where, param = "id = CAST(:ref AS UUID)", str(uuid.UUID(org_ref))
    except ValueError:
        where, param = "LOWER(slug) = LOWER(:ref)", org_ref
    row = (await db.execute(
        text(f"SELECT id, name FROM organisations WHERE {where}"), {"ref": param},
    )).mappings().first()
    return [dict(row)] if row else []


async def run_one(db, org: dict, apply: bool, season_year: int | None) -> tuple[int, int]:
    """Returns (games updated, games that became not-played)."""
    print(f"\nClub: {org['name']} ({org['id']})")

    season_clause = "AND s.year = :yr" if season_year is not None else ""
    # COALESCE(grassroots_id, id) is the raw CA grade GUID — the per-club uuid5
    # id minted on a cross-club grade collision is ours alone and means nothing
    # to /scores/grades/{id}/matches.
    grades = (await db.execute(
        text(f"""
            SELECT COALESCE(g.grassroots_id, CAST(g.id AS TEXT)) AS guid,
                   g.name AS grade_name,
                   s.name AS season_name
              FROM grades g
              JOIN seasons s ON s.id = g.season_id
             WHERE s.organisation_id = CAST(:org AS UUID) {season_clause}
             ORDER BY s.year DESC NULLS LAST, g.name
        """),
        {"org": str(org["id"]), "yr": season_year},
    )).mappings().all()

    if not grades:
        print("  No grades in scope.")
        return 0, 0

    print(f"  Scanning {len(grades)} grade(s) — one CA call each …")

    # match id → status, gathered across every grade before a single write: two
    # clubs in one grade share a match row, and one fixture can be reached
    # through more than one of our grades.
    wanted: dict[str, str] = {}
    for gd in grades:
        try:
            matches = await gr.get_grade_matches(gd["guid"])
        except Exception as e:  # a grade CA no longer serves is not fatal
            print(f"  ! {gd['season_name']} / {gd['grade_name']}: {e}")
            continue
        for m in matches:
            mid = m.get("id")
            st = (m.get("status") or "").strip().upper()
            if mid and st:
                wanted[mid] = st

    if not wanted:
        print("  CA reported no statuses at all — nothing to do.")
        return 0, 0

    ids = []
    for mid in wanted:
        try:
            ids.append(uuid.UUID(mid))
        except ValueError:
            pass

    ours = (await db.execute(
        text("""
            SELECT gm.id, gm.status
              FROM games gm
              JOIN grades g ON g.id = gm.grade_id
              JOIN seasons s ON s.id = g.season_id
             WHERE s.organisation_id = CAST(:org AS UUID)
               AND gm.id = ANY(:ids)
        """),
        {"org": str(org["id"]), "ids": ids},
    )).mappings().all()

    changes: dict[str, list[uuid.UUID]] = {}
    unchanged = 0
    for row in ours:
        st = wanted.get(str(row["id"]))
        if st and row["status"] != st:
            changes.setdefault(st, []).append(row["id"])
        else:
            unchanged += 1

    not_played = sum(len(v) for s, v in changes.items() if s in NOT_PLAYED_STATUSES)
    print(f"  Games held under this club's grades: {len(ours)} (unchanged: {unchanged})")
    if not changes:
        print("  Every game already matches CA. Nothing to change.")
        return 0, 0

    total = sum(len(v) for v in changes)
    print(f"  {'Updating' if apply else 'Would update'} {total} game(s): "
          + ", ".join(f"{s}×{len(v)}" for s, v in
                      sorted(changes.items(), key=lambda kv: -len(kv[1]))))
    if not_played:
        print(f"  {not_played} of those were called off — those stop counting "
              "towards the matches played of anyone named in them.")

    if not apply:
        return 0, not_played

    for st, gids in changes.items():
        await db.execute(
            text("UPDATE games SET status = :st WHERE id = ANY(:ids)"),
            {"st": st, "ids": gids},
        )
    await db.commit()

    # A club whose aggregates came from "Fix Missing Totals" holds a STORED
    # match count rather than reading CA's, so the view's correction cannot
    # reach it. Say so rather than leaving it quietly wrong.
    if not_played:
        stored = (await db.execute(
            text("""
                SELECT COUNT(*) FROM player_season_stats pss
                  JOIN seasons s ON s.id = pss.season_id
                 WHERE s.organisation_id = CAST(:org AS UUID)
                   AND pss.source = 'backfill'
            """),
            {"org": str(org["id"])},
        )).scalar() or 0
        if stored:
            print(f"  NOTE: {stored} season row(s) here came from Fix Missing Totals, "
                  "which stores its own match count. Re-run that for this club.")
    return total, not_played


async def run(org_ref: str, apply: bool, season_year: int | None) -> int:
    async with async_session_maker() as db:
        clubs = await _clubs(db, org_ref)
        if not clubs:
            print(f"No club found for {org_ref!r} (pass an organisation id, public slug, or 'all').")
            return 1

        totals = Counter()
        for org in clubs:
            try:
                updated, not_played = await run_one(db, org, apply, season_year)
            except Exception as e:  # one club's bad data must not stop the sweep
                print(f"  ! {org['name']}: {e}")
                await db.rollback()
                continue
            totals["updated"] += updated
            totals["not_played"] += not_played

        print(f"\n{'Wrote' if apply else 'Would write'} {totals['updated']} status(es) "
              f"across {len(clubs)} club(s); {totals['not_played']} fixture(s) called off.")
        if not apply:
            print("Dry run — re-run with --apply to write these.")
        return 0


def main() -> None:
    args = sys.argv[1:]
    apply = "--apply" in args
    season_year = None
    if "--season" in args:
        i = args.index("--season")
        if i + 1 >= len(args):
            print("--season needs a year, e.g. --season 2025")
            raise SystemExit(2)
        try:
            season_year = int(args[i + 1])
        except ValueError:
            print(f"--season wants a 4-digit year, got {args[i + 1]!r}")
            raise SystemExit(2)
        del args[i:i + 2]
    positional = [a for a in args if not a.startswith("--")]
    if not positional:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(run(positional[0], apply, season_year)))


if __name__ == "__main__":
    main()
