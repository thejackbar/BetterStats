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

from sqlalchemy import select, text

from app.models.db import ImportedStat, ImportEffectiveDelta, async_session_maker
from app.services import import_reconcile as recon
from app.services.aggregations import _GRADE_MATCH, _IMPORT_GRADE_MATCH, get_batting_leaderboard_extended


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

            if grade is not None:
                print(f"\n--- cross-check for grade={grade!r} ---")
                narrow = await recon._scorecard_narrow_metrics(session, org_uuid, [player_uuid], grade)
                print(f"_scorecard_narrow_metrics raw: {narrow.get(player_uuid)}")

                # Which real `grades` rows does _GRADE_MATCH resolve this label to?
                matched_grades = (
                    await session.execute(
                        text(f"""
                            SELECT gr.id, gr.name, gr.display_name_override, s.year
                            FROM grades gr JOIN seasons s ON s.id = gr.season_id
                            WHERE s.organisation_id = CAST(:org_id AS UUID) AND {_GRADE_MATCH}
                            ORDER BY s.year
                        """),
                        {"org_id": str(org_uuid), "grade_name": grade},
                    )
                ).mappings().all()
                print(f"matched grades ({len(matched_grades)}): "
                      f"{[(g['name'], g['display_name_override'], g['year']) for g in matched_grades]}")

                # Raw count + fifties straight off batting_innings for those grade ids,
                # same predicate as the leaderboard's own qualifying CTE.
                raw = (
                    await session.execute(
                        text("""
                            SELECT COUNT(*) AS innings,
                                COALESCE(SUM(CASE WHEN bi.runs >= 50 AND bi.runs < 100 THEN 1 ELSE 0 END), 0) AS fifties,
                                COALESCE(SUM(CASE WHEN bi.runs >= 100 THEN 1 ELSE 0 END), 0) AS hundreds
                            FROM batting_innings bi
                            JOIN games g ON g.id = bi.game_id
                            WHERE bi.player_id = CAST(:pid AS UUID)
                              AND g.grade_id = ANY(CAST(:gids AS UUID[]))
                              AND NOT COALESCE(bi.did_not_bat, FALSE)
                              AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
                        """),
                        {"pid": str(player_uuid), "gids": [str(g["id"]) for g in matched_grades]},
                    )
                ).mappings().first()
                print(f"raw batting_innings (base table, not v_effective_*) for matched grade ids: {dict(raw)}")

                veff = (
                    await session.execute(
                        text("""
                            SELECT COUNT(*) AS innings,
                                COALESCE(SUM(CASE WHEN bi.runs >= 50 AND bi.runs < 100 THEN 1 ELSE 0 END), 0) AS fifties,
                                COALESCE(SUM(CASE WHEN bi.runs >= 100 THEN 1 ELSE 0 END), 0) AS hundreds
                            FROM v_effective_batting_innings bi
                            JOIN v_effective_games g ON g.id = bi.game_id
                            WHERE bi.player_id = CAST(:pid AS UUID)
                              AND g.grade_id = ANY(CAST(:gids AS UUID[]))
                              AND NOT COALESCE(bi.did_not_bat, FALSE)
                              AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
                        """),
                        {"pid": str(player_uuid), "gids": [str(g["id"]) for g in matched_grades]},
                    )
                ).mappings().first()
                print(f"v_effective_batting_innings for matched grade ids: {dict(veff)}")

                # The ACTUAL leaderboard function, called exactly like the live
                # endpoint would (no hand-reconstructed SQL), filtered to this player.
                board = await get_batting_leaderboard_extended(
                    session, str(org_uuid), None, None, "total_runs", 5000, 0, grade,
                )
                mine = next((r for r in board if str(r["player_id"]) == str(player_uuid)), None)
                print(f"\nget_batting_leaderboard_extended(grade_name={grade!r}) row for this player: {mine}")
                print(f"(leaderboard returned {len(board)} players total for this grade)")

                # The exact qualifying-CTE shape the leaderboard uses (inline
                # _GRADE_MATCH, not a precomputed grade-id list), filtered to
                # this player only, to catch any inline-vs-precomputed drift.
                inline = (
                    await session.execute(
                        text(f"""
                            SELECT bi.player_id, bi.game_id, bi.runs
                            FROM v_effective_batting_innings bi
                            JOIN v_effective_games g ON g.id = bi.game_id
                            JOIN grades gr ON gr.id = g.grade_id
                            WHERE {_GRADE_MATCH}
                              AND NOT COALESCE(bi.did_not_bat, FALSE)
                              AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
                              AND bi.player_id = CAST(:pid AS UUID)
                        """),
                        {"org_id": str(org_uuid), "grade_name": grade, "pid": str(player_uuid)},
                    )
                ).mappings().all()
                fifties_inline = sum(1 for r in inline if 50 <= r["runs"] < 100)
                hundreds_inline = sum(1 for r in inline if r["runs"] >= 100)
                distinct_games = len({r["game_id"] for r in inline})
                print(f"inline-_GRADE_MATCH qualifying CTE (leaderboard's exact shape, filtered to this player): "
                      f"innings={len(inline)} distinct_games={distinct_games} fifties={fifties_inline} hundreds={hundreds_inline}")

                # What's ACTUALLY sitting in import_effective_deltas right now for
                # this player (every row, any grade_label) — not a fresh recompute.
                # If this doesn't match the "career residual" printed above, the
                # stored deltas are stale relative to current GR/scorecard coverage
                # and reconcile_imports needs re-running.
                stored = (
                    await session.execute(
                        select(ImportEffectiveDelta).where(
                            ImportEffectiveDelta.organisation_id == org_uuid,
                            ImportEffectiveDelta.player_id == player_uuid,
                        )
                    )
                ).scalars().all()
                print(f"\nstored import_effective_deltas rows ({len(stored)}):")
                for d in stored:
                    print(f"  id={d.id} scope={d.scope} season_id={d.season_id} grade_label={d.grade_label!r} "
                          f"innings={d.batting_innings} runs={d.runs} fifties={d.fifties} hundreds={d.hundreds}")

                # The exact import_totals CTE the leaderboard runs (SUM over
                # _IMPORT_GRADE_MATCH), filtered to this player only — the live
                # "it" side of the blend, straight from the stored table.
                it_cte = (
                    await session.execute(
                        text(f"""
                            SELECT
                                COALESCE(SUM(ied.batting_innings), 0) AS innings,
                                COALESCE(SUM(ied.runs), 0) AS total_runs,
                                COALESCE(SUM(ied.fifties), 0) AS fifties,
                                COALESCE(SUM(ied.hundreds), 0) AS hundreds
                            FROM import_effective_deltas ied
                            WHERE ied.organisation_id = CAST(:org_id AS UUID)
                              AND ied.player_id = CAST(:pid AS UUID)
                              AND {_IMPORT_GRADE_MATCH}
                        """),
                        {"org_id": str(org_uuid), "grade_name": grade, "pid": str(player_uuid)},
                    )
                ).mappings().first()
                print(f"leaderboard's import_totals CTE (_IMPORT_GRADE_MATCH), filtered to this player: {dict(it_cte)}")
                print(f"=> q + it should be: innings={len(inline)}+{it_cte['innings']}="
                      f"{len(inline) + it_cte['innings']}  fifties={fifties_inline}+{it_cte['fifties']}="
                      f"{fifties_inline + it_cte['fifties']}  hundreds={hundreds_inline}+{it_cte['hundreds']}="
                      f"{hundreds_inline + it_cte['hundreds']}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python -m app.scripts.diagnose_reconcile <org_id> <player_id>")
        sys.exit(1)
    asyncio.run(diagnose(sys.argv[1], sys.argv[2]))
