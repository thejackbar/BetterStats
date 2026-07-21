"""List every club with at least one manually-uploaded scorecard (`manual_games`),
with a breakdown of how many came from the AI photo-upload flow
(/admin/upload-scorecard) vs typed straight into the Manual Games form.

Manual games are the ONLY per-game data an admin enters by hand — synced games
never touch this table (see the "Sync Architecture" note in CLAUDE.md) — so this
is a straight read of `manual_games` grouped by club, no other tables involved.

This script is READ-ONLY (no DB writes).

Usage from the backend container (via Cockpit's terminal, or any shell on the
box — see the "Server Deploy Command" note in CLAUDE.md for the compose
project name):
  cd /srv/docker
  export COMPOSE_PROJECT_NAME=bltbox_docker_app
  docker compose exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.list_club_scorecards

Add --all to also list clubs with zero scorecards (omitted by default so the
list stays short); add --csv to print CSV instead of a table (handy to pipe
into a file for a spreadsheet).
"""

import asyncio
import sys

from sqlalchemy import text as sql_text

from app.models.db import async_session_maker


async def list_club_scorecards(include_zero: bool = False, as_csv: bool = False) -> None:
    async with async_session_maker() as session:
        rows = (
            await session.execute(
                sql_text(
                    """
                    SELECT
                        o.id                                                          AS org_id,
                        o.name                                                        AS club,
                        o.slug                                                        AS slug,
                        COUNT(mg.id)                                                  AS total_scorecards,
                        COUNT(mg.id) FILTER (WHERE mg.extracted_payload IS NOT NULL)  AS via_photo_upload,
                        COUNT(mg.id) FILTER (WHERE mg.extracted_payload IS NULL)      AS typed_manually,
                        MIN(mg.created_at)                                            AS first_entered,
                        MAX(mg.created_at)                                            AS last_entered
                    FROM organisations o
                    LEFT JOIN manual_games mg ON mg.organisation_id = o.id
                    WHERE o.archived_at IS NULL
                    GROUP BY o.id, o.name, o.slug
                    HAVING COUNT(mg.id) > 0 OR :include_zero
                    ORDER BY total_scorecards DESC, o.name ASC
                    """
                ),
                {"include_zero": include_zero},
            )
        ).mappings().all()

        if not rows:
            print("No clubs found." if include_zero else "No club has entered any scorecards yet.")
            return

        if as_csv:
            print("club,slug,total_scorecards,via_photo_upload,typed_manually,first_entered,last_entered")
            for r in rows:
                print(
                    f'"{r["club"]}",{r["slug"] or ""},{r["total_scorecards"]},'
                    f'{r["via_photo_upload"]},{r["typed_manually"]},'
                    f'{r["first_entered"] or ""},{r["last_entered"] or ""}'
                )
            return

        name_w = max(len(r["club"]) for r in rows) + 2
        print(f'{"Club":<{name_w}}{"Total":>7}{"Photo":>8}{"Typed":>8}  {"First":<12}{"Last":<12}')
        print("-" * (name_w + 7 + 8 + 8 + 2 + 12 + 12))
        for r in rows:
            first = r["first_entered"].date().isoformat() if r["first_entered"] else "—"
            last = r["last_entered"].date().isoformat() if r["last_entered"] else "—"
            print(
                f'{r["club"]:<{name_w}}{r["total_scorecards"]:>7}{r["via_photo_upload"]:>8}'
                f'{r["typed_manually"]:>8}  {first:<12}{last:<12}'
            )
        print()
        print(f"{len(rows)} club(s) with at least one scorecard entered."
              if not include_zero else f"{len(rows)} club(s) total.")


if __name__ == "__main__":
    args = sys.argv[1:]
    asyncio.run(list_club_scorecards(include_zero="--all" in args, as_csv="--csv" in args))
