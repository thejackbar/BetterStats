"""One-off diagnostic: print the full reconciliation breakdown for one player.

Shows every imported_stats truth row for the player, the grade-scoped GR
totals fetch_gr_by_player_for_grade computes (PSGS core metrics + scorecard
narrow metrics separately, so a mismatch between them is visible), and the
resulting season deltas / career residual reconcile_player would produce.
Read-only — writes nothing.

Usage from the backend container:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.diagnose_reconcile <org_id> <player_id>
"""

import asyncio
import sys

from sqlalchemy import select

from app.models.db import ImportedStat, async_session_maker
from app.services import import_reconcile as recon


async def diagnose(org_id_str: str, player_id_str: str) -> None:
    import uuid
    org_uuid = uuid.UUID(org_id_str)
    player_uuid = uuid.UUID(player_id_str)

    async with async_session_maker() as session:
        rows = (
            await session.execute(
                select(ImportedStat).where(
                    ImportedStat.organisation_id == org_uuid,
                    ImportedStat.player_id == player_uuid,
                )
            )
        ).scalars().all()

        print(f"=== imported_stats rows for {player_id_str} ({len(rows)} row(s)) ===")
        for r in rows:
            print(f"  id={r.id} scope={r.scope} season_id={r.season_id} grade_label={r.grade_label!r} "
                  f"is_prior_bucket={r.is_prior_bucket} batch={r.import_batch_id}")
            print(f"    batting: innings={r.batting_innings} runs={r.batting_runs} "
                  f"fifties={r.batting_fifties} hundreds={r.batting_hundreds} "
                  f"fours={r.batting_fours} sixes={r.batting_sixes}")

        by_group: dict = {}
        for r in rows:
            key = recon._grade_key(r.grade_label)
            by_group.setdefault(key, []).append(r)

        for grade, grp_rows in by_group.items():
            print(f"\n=== group grade={grade!r} ({len(grp_rows)} row(s)) ===")
            club, import_seasons = recon.assemble_club_inputs([
                {"scope": r.scope, "season_id": r.season_id,
                 "is_prior_bucket": r.is_prior_bucket, "metrics": recon.imported_to_metrics(r)}
                for r in grp_rows
            ])
            print(f"club (assembled from {len(grp_rows)} row(s)): "
                  f"innings={club['batting_innings']} runs={club['runs']} "
                  f"fifties={club['fifties']} hundreds={club['hundreds']}")

            if grade is not None:
                gr_pool = await recon.fetch_gr_by_player_for_grade(session, org_uuid, [player_uuid], grade)
            else:
                gr_pool = await recon.fetch_gr_by_player(session, org_uuid, [player_uuid])
            gr = gr_pool.get(player_uuid, {"season_ids": set(), "totals": None})
            gr_totals = gr["totals"] if gr["totals"] is not None else recon._blank()
            print(f"gr (grade-scoped fetch): innings={gr_totals['batting_innings']} runs={gr_totals['runs']} "
                  f"fifties={gr_totals['fifties']} hundreds={gr_totals['hundreds']} "
                  f"fours={gr_totals['fours']} sixes={gr_totals['sixes']}")
            print(f"gr season_ids covered: {len(gr['season_ids'])}")

            season_deltas, career = recon.reconcile_player(club, gr_totals, import_seasons, gr["season_ids"])
            print(f"season_deltas: {len(season_deltas)}")
            if career:
                print(f"career residual: innings={career['batting_innings']} runs={career['runs']} "
                      f"fifties={career['fifties']} hundreds={career['hundreds']} "
                      f"fours={career['fours']} sixes={career['sixes']}")
            else:
                print("career residual: None")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python -m app.scripts.diagnose_reconcile <org_id> <player_id>")
        sys.exit(1)
    asyncio.run(diagnose(sys.argv[1], sys.argv[2]))
