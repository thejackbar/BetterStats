"""BetterIQ — post-match "What changed the game" review (analytics brief §16.8).

Read-only, per-game, from stored per-innings data (no live fetch):
- our score = SUM(batting_innings.runs); their score = SUM(bowling_spells.runs).
- top batting / bowling contributions, the best partnership, extras we conceded
  and a single-game collapse check (reconstructed from partnership runs).
- a rule-based synthesis of what swung the game.

Ceiling: we hold scorecards, not ball-by-ball, so "biggest over / win-probability
swing / turning point" (brief §16.8) are out of reach — the contribution and
collapse reads are the scorecard-reachable subset. Org-scoped via grades→seasons
over the ``v_effective_*`` views, like the rest of BetterIQ.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.iq_filters import season_grade_clause


def _ordinal(n: int) -> str:
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")


async def list_review_games(session: AsyncSession, org_id: str, limit: int = 40,
                            season_id: str | None = None, grade_id: str | None = None) -> list[dict]:
    """Recent completed games to review — newest first (a lightweight picker).
    Optionally scoped to one season and/or grade (grade matched by NAME, the IQ
    filter convention; the season is year-expanded — see iq_filters) so the
    Overview's form/results follow the global filter."""
    clauses = season_grade_clause(season_id, grade_id)
    res = await session.execute(
        text(
            f"""
            SELECT g.id::text AS id, g.played_at, g.result, g.venue, g.is_final,
                   g.opp_club_name AS opp, g.home_team, g.away_team, gr.name AS grade
            FROM v_effective_games g
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = CAST(:org AS UUID) AND g.played_at IS NOT NULL {clauses}
            ORDER BY g.played_at DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {"org": org_id, "limit": limit, "season": season_id, "grade": grade_id},
    )
    out = []
    for r in res.mappings():
        opp = r["opp"] or r["away_team"] or r["home_team"] or "Opponent"
        out.append({
            "game_id": r["id"],
            "date": r["played_at"].isoformat() if r["played_at"] else None,
            "opponent": opp,
            "result": r["result"],
            "venue": r["venue"],
            "is_final": bool(r["is_final"]),
            "grade": r["grade"],
        })
    return out


async def game_review(session: AsyncSession, org_id: str, game_id: str) -> dict | None:
    """One game's review: top contributions, best stand, extras, a collapse check
    and a plain-language synthesis of what changed the game."""
    meta = (await session.execute(
        text(
            """
            SELECT g.id::text AS id, g.played_at, g.result, g.venue, g.is_final,
                   g.opp_club_name AS opp, g.home_team, g.away_team, gr.name AS grade
            FROM v_effective_games g
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE g.id = CAST(:gid AS UUID) AND s.organisation_id = CAST(:org AS UUID)
            """
        ),
        {"gid": game_id, "org": org_id},
    )).mappings().first()
    if not meta:
        return None

    # Every per-game read below is scoped to OUR players: a match between two
    # both-synced clubs shares one games.id carrying BOTH clubs' rows, so an
    # unscoped sum/top-5 mixes the opponent's innings into ours (same fix as
    # iq._our_performers_vs).
    totals = (await session.execute(
        text(
            """
            SELECT
              (SELECT SUM(bi.runs) FROM v_effective_batting_innings bi
                 JOIN players p ON p.id = bi.player_id
                 WHERE bi.game_id = CAST(:gid AS UUID) AND bi.did_not_bat IS NOT TRUE
                   AND p.organisation_id = CAST(:org AS UUID)) AS our_runs,
              (SELECT COUNT(*) FROM v_effective_batting_innings bi
                 JOIN players p ON p.id = bi.player_id
                 WHERE bi.game_id = CAST(:gid AS UUID) AND bi.did_not_bat IS NOT TRUE
                   AND NOT bi.not_out AND bi.dismissal_type IS NOT NULL
                   AND p.organisation_id = CAST(:org AS UUID)) AS our_wkts_lost,
              (SELECT SUM(bs.runs) FROM v_effective_bowling_spells bs
                 JOIN players p ON p.id = bs.player_id
                 WHERE bs.game_id = CAST(:gid AS UUID)
                   AND p.organisation_id = CAST(:org AS UUID)) AS opp_runs,
              (SELECT SUM(bs.wickets) FROM v_effective_bowling_spells bs
                 JOIN players p ON p.id = bs.player_id
                 WHERE bs.game_id = CAST(:gid AS UUID)
                   AND p.organisation_id = CAST(:org AS UUID)) AS opp_wkts,
              (SELECT COALESCE(SUM(COALESCE(bs.wides, 0) + COALESCE(bs.no_balls, 0)), 0)
                 FROM v_effective_bowling_spells bs
                 JOIN players p ON p.id = bs.player_id
                 WHERE bs.game_id = CAST(:gid AS UUID)
                   AND p.organisation_id = CAST(:org AS UUID)) AS extras_conceded
            """
        ),
        {"gid": game_id, "org": org_id},
    )).mappings().first()

    bat = [dict(r) for r in (await session.execute(
        text(
            """
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   bi.runs, bi.balls, bi.fours, bi.sixes, bi.not_out, bi.batting_position
            FROM v_effective_batting_innings bi
            JOIN players p ON p.id = bi.player_id
            WHERE bi.game_id = CAST(:gid AS UUID) AND bi.did_not_bat IS NOT TRUE AND bi.runs IS NOT NULL
              AND p.organisation_id = CAST(:org AS UUID)
            ORDER BY bi.runs DESC NULLS LAST, bi.balls ASC NULLS LAST
            LIMIT 5
            """
        ),
        {"gid": game_id, "org": org_id},
    )).mappings()]

    bowl = [dict(r) for r in (await session.execute(
        text(
            """
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   bs.overs, bs.maidens, bs.runs, bs.wickets
            FROM v_effective_bowling_spells bs
            JOIN players p ON p.id = bs.player_id
            WHERE bs.game_id = CAST(:gid AS UUID)
              AND p.organisation_id = CAST(:org AS UUID)
            ORDER BY bs.wickets DESC NULLS LAST, bs.runs ASC NULLS LAST
            LIMIT 5
            """
        ),
        {"gid": game_id, "org": org_id},
    )).mappings()]

    bp = (await session.execute(
        text(
            """
            SELECT p.runs, p.wicket_number,
                   COALESCE(b1.display_name_override, b1.name) AS b1,
                   COALESCE(b2.display_name_override, b2.name) AS b2
            FROM v_effective_partnerships p
            LEFT JOIN players b1 ON b1.id = p.batter1_id AND b1.organisation_id = CAST(:org AS UUID)
            LEFT JOIN players b2 ON b2.id = p.batter2_id AND b2.organisation_id = CAST(:org AS UUID)
            WHERE p.game_id = CAST(:gid AS UUID) AND p.is_club_innings IS TRUE AND p.runs IS NOT NULL
              -- `is_club_innings` is set per club (sync stamps TRUE for whichever
              -- side is its own), so on a fixture between two synced clubs the one
              -- `games` row carries BOTH clubs' stands marked TRUE. Requiring a
              -- batter to resolve within our org is what keeps the opposition's
              -- best stand out of our match review.
              AND (b1.id IS NOT NULL OR b2.id IS NOT NULL)
            ORDER BY p.runs DESC NULLS LAST
            LIMIT 1
            """
        ),
        {"gid": game_id, "org": org_id},
    )).mappings().first()
    best_partnership = None
    if bp and (bp["b1"] or bp["b2"]):
        best_partnership = {
            "runs": int(bp["runs"]),
            "wicket": int(bp["wicket_number"]) if bp["wicket_number"] is not None else None,
            "batters": " & ".join([x for x in (bp["b1"], bp["b2"]) if x]),
        }

    # Single-game collapse check — worst 3-consecutive-wicket span from our
    # partnership runs (same reconstruction as iq_team._collapses).
    pr = await session.execute(
        text(
            """
            SELECT p.innings_number AS inn, p.wicket_number AS wk, p.runs AS runs
            FROM v_effective_partnerships p
            WHERE p.game_id = CAST(:gid AS UUID) AND p.is_club_innings IS TRUE
              AND p.wicket_number BETWEEN 1 AND 10 AND p.runs IS NOT NULL
            """
        ),
        {"gid": game_id},
    )
    by_inn: dict[int, dict[int, int]] = defaultdict(dict)
    for r in pr.mappings():
        by_inn[r["inn"]][int(r["wk"])] = int(r["runs"])
    collapse = None
    for wkmap in by_inn.values():
        for k in sorted(wkmap):
            if (k + 1) in wkmap and (k + 2) in wkmap:
                span = wkmap[k] + wkmap[k + 1] + wkmap[k + 2]
                if span <= 15 and (collapse is None or span < collapse["runs"]):
                    collapse = {"runs": span, "start_wicket": k, "wickets": 3}

    our_runs = int(totals["our_runs"]) if totals["our_runs"] is not None else None
    opp_runs = int(totals["opp_runs"]) if totals["opp_runs"] is not None else None
    extras = int(totals["extras_conceded"] or 0)
    opp = meta["opp"] or meta["away_team"] or meta["home_team"] or "the opposition"

    game = {
        "game_id": meta["id"],
        "date": meta["played_at"].isoformat() if meta["played_at"] else None,
        "opponent": opp,
        "result": meta["result"],
        "venue": meta["venue"],
        "is_final": bool(meta["is_final"]),
        "grade": meta["grade"],
        "our_score": (f"{our_runs}/{int(totals['our_wkts_lost'] or 0)}" if our_runs is not None else None),
        "their_score": (f"{opp_runs}/{int(totals['opp_wkts'] or 0)}" if opp_runs is not None else None),
    }

    # Plain-language synthesis (rule-based; the scorecard-reachable subset of §16.8).
    summary = []
    rmap = {"WIN": "Won", "LOSS": "Lost", "DRAW": "Drew with", "TIE": "Tied with"}
    if meta["result"] in rmap:
        line = f"{rmap[meta['result']]} {('against ' if meta['result'] in ('WIN', 'LOSS') else '')}{opp}"
        if game["our_score"] and game["their_score"]:
            line += f" — {game['our_score']} vs {game['their_score']}"
        summary.append(line + (".") if not line.endswith(".") else line)
    if bat:
        b0 = bat[0]
        no = "*" if b0["not_out"] else ""
        summary.append(f"{b0['name']} top-scored with {b0['runs']}{no}.")
    if bowl and (bowl[0]["wickets"] or 0) > 0:
        w0 = bowl[0]
        summary.append(f"{w0['name']} led the attack with {w0['wickets']}/{w0['runs']}.")
    if best_partnership and best_partnership["runs"] >= 40:
        summary.append(f"Best stand: {best_partnership['runs']} ({best_partnership['batters']}).")
    if collapse:
        summary.append(f"Wobble — 3 for {collapse['runs']} from the {_ordinal(collapse['start_wicket'])} wicket.")
    if extras >= 15:
        summary.append(f"Gave away {extras} in extras (wides + no-balls).")

    return {
        "game": game,
        "top_batting": bat,
        "top_bowling": bowl,
        "best_partnership": best_partnership,
        "extras_conceded": extras,
        "collapse": collapse,
        "summary": summary,
        "coverage": {
            "notes": [
                "Scores are reconstructed from stored per-innings data (our batting / our bowling), so they exclude some extras — close, not exact.",
                "Biggest-over and win-probability swings need ball-by-ball data we don't hold.",
            ]
        },
    }
