"""Fill in ``games.innings_totals`` from Cricket Australia's own scorecards.

WHY THIS EXISTS
---------------
``games.innings_totals`` (migration 233) holds each innings' TRUE total —
the batters' runs PLUS extras — straight off Grassroots' own
``innings[].runsScored``. It was added prospectively, with no backfill, and
the migration says so plainly: a game synced before it shipped keeps NULL and
every reader falls back to ``SUM(batting_innings.runs)``, which is the
batters' runs alone and so reads roughly 10-25 runs light.

That was a fair trade while the only consumer was BetterIQ, where it is a
small consistent bias across an average. It is NOT a fair trade for the club
record book (``services/club_records.py``), which ranks these figures
DIRECTLY against each other:

- a HIGHEST-total board under-ranks every approximate game, so a genuine club
  record from 2011 can be beaten by a smaller modern score;
- a LOWEST-total board does the opposite, and a bat-only sum can invent a
  club-worst innings that never happened.

The skew runs in opposite directions on the two boards, which is exactly why
it cannot be corrected by a constant. The only fix is the real figure.

The sync writes it for new games, and self-heals an already-synced game it
revisits (``services/sync.py`` — the ``existing_innings_totals is None``
branch), so an ordinary Sync Now fills in the current season. This script is
the retroactive half, for the seasons an incremental run no longer scans.

A club onboarded after migration 233 shipped has nothing to fix.

WHAT IT TOUCHES
---------------
``games.innings_totals`` only, and only where it is currently NULL and CA
actually returns a scorecard. It never writes a per-innings row, never
touches a player's figures, and never overwrites a total already stored — so
it is safe to re-run and safe to interrupt.

Resume-friendly by construction: the NULL check IS the cursor, so a re-run
picks up exactly where a failed one stopped.

    python -m app.scripts.backfill_innings_totals <org-id|all> [--apply]
    python -m app.scripts.backfill_innings_totals <org-id> --apply --all-seasons

DRY RUN BY DEFAULT. Without ``--apply`` it reports what it would fill and
writes nothing.

HOW FAR BACK
------------
By default the club's ten most recent seasons, which is what a record book
is mostly read against and what keeps a first run to a sane number of CA
calls. ``--all-seasons`` does the full history — worth it for a club that
wants its all-time record book exact, which is the whole point of the
feature, just slower.
"""
import argparse
import asyncio
import json
import sys
import uuid

from sqlalchemy import text as sql_text

from app.models.db import async_session_maker
from app.services.grassroots_scores_client import get_match_scorecard
from app.services.sync import _extract_innings_totals

DEFAULT_SEASON_LIMIT = 10


async def _org_id(session, arg: str) -> uuid.UUID | None:
    """Accept an org id or a slug, the way every other club script does."""
    try:
        return uuid.UUID(arg)
    except (ValueError, TypeError):
        pass
    row = (await session.execute(
        sql_text("SELECT id FROM organisations WHERE slug = :s"), {"s": arg}
    )).first()
    return row[0] if row else None


async def backfill_for_org(arg: str, *, apply: bool = False,
                           all_seasons: bool = False) -> tuple[int, int]:
    async with async_session_maker() as session:
        org_id = await _org_id(session, arg)
        if not org_id:
            print(f"  !! no organisation matches {arg!r}")
            return (0, 0)

        # Only OUR OWN grades' games: a grade match list is competition-wide
        # and names plenty of fixtures that are not ours.
        season_filter = ""
        params: dict = {"org": org_id}
        if not all_seasons:
            season_filter = """
                AND s.id IN (
                    SELECT id FROM seasons WHERE organisation_id = :org
                    ORDER BY year DESC NULLS LAST, name DESC LIMIT :lim
                )"""
            params["lim"] = DEFAULT_SEASON_LIMIT

        rows = (await session.execute(sql_text(f"""
            SELECT g.id, g.played_at, s.name AS season_name
            FROM games g
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = :org
              AND g.innings_totals IS NULL
              -- A washout has no innings to total. Asking CA for its
              -- scorecard spends a call to be told nothing.
              AND g.result IS NOT NULL
              {season_filter}
            ORDER BY g.played_at DESC
        """), params)).all()

    if not rows:
        print("  nothing to fill — every game already carries its innings totals")
        return (0, 0)

    print(f"  {len(rows)} game(s) with no stored innings totals")
    filled = missing = 0

    for gid, played_at, season_name in rows:
        try:
            card = await get_match_scorecard(str(gid))
        except Exception as exc:
            print(f"    !! {gid} ({season_name}): fetch failed — {exc}")
            missing += 1
            continue
        if not card:
            # A PlayHQ-namespace game 204s here, which is a clean "not mine"
            # rather than an error — see the data-source notes in CLAUDE.md.
            missing += 1
            continue

        totals = _extract_innings_totals(card)
        if not totals:
            missing += 1
            continue

        filled += 1
        if not apply:
            continue
        async with async_session_maker() as session:
            # `IS NULL` in the WHERE as well as the SELECT: another run (or a
            # sync) may have filled it in between, and a stored total is
            # never overwritten.
            await session.execute(sql_text(
                "UPDATE games SET innings_totals = CAST(:it AS JSONB) "
                "WHERE id = :gid AND innings_totals IS NULL"),
                {"it": json.dumps(totals), "gid": gid})
            await session.commit()

    verb = "filled" if apply else "would fill"
    print(f"  {verb} {filled}; {missing} game(s) CA could not answer for")
    return (filled, missing)


async def backfill_all(*, apply: bool, all_seasons: bool) -> None:
    async with async_session_maker() as session:
        orgs = [(r[0], r[1]) for r in (await session.execute(
            sql_text("SELECT id, name FROM organisations "
                     "WHERE archived_at IS NULL ORDER BY name"))).all()]
    print(f"Backfilling innings totals for {len(orgs)} organisations...\n")
    failed: list[str] = []
    for i, (oid, name) in enumerate(orgs, 1):
        print(f"=== [{i}/{len(orgs)}] {name} ({oid}) ===")
        try:
            await backfill_for_org(str(oid), apply=apply, all_seasons=all_seasons)
        except Exception as exc:  # one club's failure must not abort the rest
            failed.append(f"{name} ({oid}): {exc}")
            print(f"  !! org failed: {exc}")
    print(f"\nAll organisations done. {len(failed)} failed.")
    for f in failed:
        print(f"  - {f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("org", nargs="?", default="all",
                    help="organisation id or slug, or 'all'")
    ap.add_argument("--apply", action="store_true",
                    help="write the totals (default is a dry run)")
    ap.add_argument("--all-seasons", action="store_true",
                    help="every season, not just the ten most recent")
    args = ap.parse_args()
    if not args.apply:
        print("DRY RUN — nothing will be written. Add --apply to fill them in.\n")
    if args.org.lower() == "all":
        asyncio.run(backfill_all(apply=args.apply, all_seasons=args.all_seasons))
    else:
        asyncio.run(backfill_for_org(
            args.org, apply=args.apply, all_seasons=args.all_seasons))


if __name__ == "__main__":
    main()
