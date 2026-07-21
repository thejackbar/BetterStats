"""Backfill `games.home_org_id` / `away_org_id` for an organisation.

Migration 167 added these columns and sync.py now populates them going
forward (on every sync, not just for brand-new matches — see sync.py's
self-heal update), but that still needs a Sync Now to run before an already
broken club's Games list / opposition stats correct themselves. This script
derives the columns directly from data we already hold — NO Grassroots API
calls, so it's near-instant even for a club with thousands of games — by
matching each of our players' recorded `game_appearances.team_name` against
the game's own `home_team`/`away_team` text.

Scope: only fixes games where at least one of our players has a recorded
appearance. A game under our own grade with ZERO appearances (a rarer,
separate roster-resolution gap) isn't touched here — that case needs the raw
Grassroots roster and self-heals on the club's next ordinary Sync Now
instead (sync.py resolves home/away directly from the API response, not from
our own appearances).

Idempotent and non-destructive — only ever UPDATEs games.home_org_id/
away_org_id, and only when the derived value actually differs from what's
stored, so a re-run (or running it on a club that's already correct) is a
fast no-op.

Usage from the backend container:
  # one club:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.backfill_game_org_ids <org_id>
  # every club (no arg, or "all"):
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.backfill_game_org_ids all
"""

import asyncio
import sys
import uuid

from sqlalchemy import text as sql_text

from app.models.db import async_session_maker


async def backfill_for_org(org_id_str: str) -> None:
    org_id = uuid.UUID(org_id_str)

    async with async_session_maker() as session:
        rows = await session.execute(
            sql_text("""
                SELECT
                    g.id,
                    g.home_team,
                    g.away_team,
                    g.home_org_id,
                    g.away_org_id,
                    -- MODE() picks the most-common team_name recorded for our
                    -- players in this game — should always be unanimous, but
                    -- a defensive tie-break beats crashing on a data glitch.
                    MODE() WITHIN GROUP (ORDER BY ga.team_name) AS our_team_name
                FROM games g
                JOIN game_appearances ga ON ga.game_id = g.id
                JOIN players p ON p.id = ga.player_id AND p.organisation_id = :org_id
                WHERE ga.team_name IS NOT NULL
                GROUP BY g.id, g.home_team, g.away_team, g.home_org_id, g.away_org_id
            """),
            {"org_id": str(org_id)},
        )
        candidates = rows.all()

        updates: list[dict] = []
        skipped_ambiguous = 0
        for gid, home_team, away_team, home_org_id, away_org_id, our_team_name in candidates:
            is_home = our_team_name == home_team
            is_away = our_team_name == away_team
            if not is_home and not is_away:
                skipped_ambiguous += 1
                continue
            new_home = org_id if is_home else home_org_id
            new_away = org_id if is_away else away_org_id
            if new_home != home_org_id or new_away != away_org_id:
                updates.append({"gid": gid, "home_org_id": new_home, "away_org_id": new_away})

        for u in updates:
            await session.execute(
                sql_text(
                    "UPDATE games SET home_org_id = :home_org_id, away_org_id = :away_org_id "
                    "WHERE id = :gid"
                ),
                u,
            )
        if updates:
            await session.commit()

    print(
        f"org {org_id}: {len(candidates)} games with our appearances scanned, "
        f"{len(updates)} updated, {skipped_ambiguous} skipped (team_name matched neither side)."
    )


async def backfill_all() -> None:
    """Backfill every organisation, sequentially. Idempotent — a failed or
    partial run can always be re-run safely."""
    async with async_session_maker() as session:
        orgs_rows = await session.execute(sql_text("SELECT id, name FROM organisations ORDER BY name"))
        orgs = [(r[0], r[1]) for r in orgs_rows.all()]
    print(f"Backfilling home_org_id/away_org_id for {len(orgs)} organisations...\n")
    failed: list[str] = []
    for idx, (oid, name) in enumerate(orgs, start=1):
        print(f"=== [{idx}/{len(orgs)}] {name} ({oid}) ===")
        try:
            await backfill_for_org(str(oid))
        except Exception as exc:  # one club's failure must not abort the rest
            failed.append(f"{name} ({oid}): {exc}")
            print(f"  !! org failed: {exc}")
    print(f"\nAll organisations done. {len(failed)} failed.")
    for f in failed:
        print(f"  - {f}")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    if arg.lower() == "all":
        asyncio.run(backfill_all())
    else:
        asyncio.run(backfill_for_org(arg))
