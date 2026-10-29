"""Round-by-round rankings and winners for a Fantasy season.

Read only and derived on every call: nothing here is stored, so a corrected score, an unsettled round or a
re-settle changes the answer the next time it is asked. Every round that has been scored is ranked, so
rounds settled before this existed are covered with nothing to backfill.

Scope is one league's squads (the club-wide salary-cap league). Points are the squad round row's `points`,
which is the best-N total less any transfer hit, the same figure the ladder's GW column shows.

Ties: teams on the same points share a rank (1, 1, 3) and a tie for first is a shared win. A round whose top
score is 0 or less has no winner. A round is read only while its status is `scored`, so an unsettled round
drops out (see fantasy_engine.AUTO_SETTLE_SKIP).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def rank_round(rows: list[dict]) -> list[dict]:
    """Rank one round's rows by points, highest first. Equal points share a rank and the next rank skips
    (1, 1, 3). Ties inside a rank are ordered by team name so the table is stable between calls. Each row
    gets ``rank`` and ``winner`` (True for rank 1 with points above 0)."""
    ordered = sorted(rows, key=lambda r: (-float(r["points"]), (r.get("team_name") or "").lower(), str(r.get("squad_id"))))
    out: list[dict] = []
    prev_pts: Optional[float] = None
    prev_rank = 0
    for i, r in enumerate(ordered, start=1):
        pts = float(r["points"])
        rank = prev_rank if prev_pts is not None and pts == prev_pts else i
        prev_pts, prev_rank = pts, rank
        out.append({**r, "points": pts, "rank": rank, "winner": rank == 1 and pts > 0})
    return out


async def season_round_rankings(db: AsyncSession, season_id, league_id) -> list[dict]:
    """Every scored round of the season, oldest first, each with its full ranking.

    A team is ranked in a round it played: it has a row for that round with a stored lineup or points, and
    it had joined by then (``joined_round``). A row that only holds a pre-lock chip or transfer tally and
    never fielded a team is left out rather than shown on 0.
    """
    rows = (await db.execute(
        text("""
            SELECT r.id AS round_id, r.round_number, r.name, r.start_date, r.end_date,
                   s.id AS squad_id, s.team_name, m.display_name AS manager,
                   srs.points, srs.chip_used, srs.transfer_hit
            FROM fantasy_rounds r
            JOIN fantasy_squad_round_scores srs ON srs.round_id = r.id
            JOIN fantasy_squads s ON s.id = srs.squad_id
            JOIN fantasy_managers m ON m.id = s.manager_id
            WHERE r.fantasy_season_id = CAST(:fs AS UUID)
              AND r.status = 'scored'
              AND s.league_id = CAST(:lg AS UUID)
              AND (s.joined_round IS NULL OR s.joined_round <= r.round_number)
              AND (srs.points <> 0 OR jsonb_array_length(COALESCE(srs.lineup, '[]'::jsonb)) > 0)
            ORDER BY r.round_number
        """),
        {"fs": str(season_id), "lg": str(league_id)},
    )).mappings().all()

    by_round: dict[int, dict] = {}
    for r in rows:
        rnd = by_round.setdefault(r["round_number"], {
            "number": r["round_number"], "name": r["name"],
            "start_date": r["start_date"].isoformat() if r["start_date"] else None,
            "end_date": r["end_date"].isoformat() if r["end_date"] else None,
            "_rows": [],
        })
        rnd["_rows"].append({
            "squad_id": str(r["squad_id"]), "team_name": r["team_name"], "manager": r["manager"],
            "points": float(r["points"] or 0), "chip": r["chip_used"], "transfer_hit": int(r["transfer_hit"] or 0),
        })

    out = []
    for n in sorted(by_round):
        rnd = by_round[n]
        ranking = rank_round(rnd.pop("_rows"))
        winners = [r for r in ranking if r["winner"]]
        runner_up = next((r["points"] for r in ranking if r["rank"] > 1), None)
        top = ranking[0]["points"] if ranking else 0.0
        out.append({
            **rnd, "teams": len(ranking), "top_points": top, "ranking": ranking,
            "winners": [{k: w[k] for k in ("squad_id", "team_name", "manager", "points", "chip")} for w in winners],
            # How far clear the winner was of the next team; None for a shared win or a lone team.
            "margin": round(top - runner_up, 2) if winners and len(winners) == 1 and runner_up is not None else None,
        })
    return out


def win_tally(rounds: list[dict]) -> list[dict]:
    """Round wins per team across the given rounds, most wins first (a shared win counts for each team).
    Ties on wins break on more recent win, then team name."""
    tally: dict[str, dict] = {}
    for rnd in rounds:
        for w in rnd["winners"]:
            t = tally.setdefault(w["squad_id"], {
                "squad_id": w["squad_id"], "team_name": w["team_name"], "manager": w["manager"],
                "wins": 0, "rounds": [], "best_points": 0.0,
            })
            t["wins"] += 1
            t["rounds"].append(rnd["number"])
            t["best_points"] = max(t["best_points"], w["points"])
    return sorted(tally.values(), key=lambda t: (-t["wins"], -max(t["rounds"]), (t["team_name"] or "").lower()))


def winners_summary(rounds: list[dict]) -> dict:
    """The list view: one line per scored round (no full table) plus the win tally."""
    return {
        "rounds": [{k: v for k, v in rnd.items() if k != "ranking"} for rnd in rounds],
        "tally": win_tally(rounds),
    }
