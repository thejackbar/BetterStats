"""BetterIQ — post-match "What changed the game" review (analytics brief §16.8).

Read-only, per-game, from stored per-innings data (no live fetch):
- our score = SUM(batting_innings.runs); their score = SUM(bowling_spells.runs).
- top batting / bowling contributions, the best partnership, extras we conceded
  and a single-game collapse check (reconstructed from partnership runs).
- a rule-based synthesis of what swung the game.

Ceiling: we hold scorecards, not ball-by-ball, so "biggest over / win-probability
swing / turning point" (brief §16.8) are out of reach — the contribution and
collapse reads are the scorecard-reachable subset. The games universe uses the
canonical ownership predicate (``_OWNS_GAME``, mirroring
``aggregations._club_results``); every per-innings read is additionally scoped
to OUR players (``players.organisation_id``), per the shared-game rule.
"""
from __future__ import annotations

import uuid as _uuid
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.iq_filters import grade_canonical_label, grade_match_clause, season_member_clause_cross_club

# Canonical "this game is ours" predicate — mirrors aggregations._club_results
# (migrations 167/169). A shared fixture between two both-synced clubs is ONE
# `games` row whose grade may belong to whichever club synced it first, and a
# manual game may have no grade at all — so ownership is home/away org, the
# view's own organisation_id (manual games), the grade's season's org, or a
# recorded appearance by one of our players. Requires `g` = v_effective_games
# with grades LEFT JOINed as `gr` and seasons LEFT JOINed off g.season_id as
# `s`, and `:org` bound.
_OWNS_GAME = """(
    g.organisation_id = CAST(:org AS UUID)
    OR g.home_org_id = CAST(:org AS UUID)
    OR g.away_org_id = CAST(:org AS UUID)
    OR s.organisation_id = CAST(:org AS UUID)
    OR EXISTS (
        SELECT 1 FROM game_appearances oga
        JOIN players op ON op.id = oga.player_id
        WHERE oga.game_id = g.id AND op.organisation_id = CAST(:org AS UUID)
    )
)"""

# g.result is relative to whichever club's sync wrote it first, so on a shared
# fixture the opponent's WIN reads as ours. g.winning_team is the neutral
# winning-team name — re-derive WIN/LOSS against OUR home/away side, falling
# back to g.result (draw/tie, or a row the org backfill can't place). Same
# expression as aggregations._club_results.
_EFFECTIVE_RESULT = """CASE
    WHEN g.winning_team IS NULL THEN g.result
    WHEN g.home_org_id = CAST(:org AS UUID) AND g.winning_team = g.home_team THEN 'WIN'
    WHEN g.home_org_id = CAST(:org AS UUID) AND g.winning_team = g.away_team THEN 'LOSS'
    WHEN g.away_org_id = CAST(:org AS UUID) AND g.winning_team = g.away_team THEN 'WIN'
    WHEN g.away_org_id = CAST(:org AS UUID) AND g.winning_team = g.home_team THEN 'LOSS'
    ELSE g.result
END"""


def _ordinal(n: int) -> str:
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")


async def list_review_games(session: AsyncSession, org_id: str, limit: int = 40,
                            season_id: str | None = None, grade_id: str | None = None,
                            season_ids: list[str] | None = None) -> list[dict]:
    """Recent completed games to review — newest first (a lightweight picker).
    Optionally scoped to one season and/or grade (grade matched by NAME, the IQ
    filter convention; the season is year-expanded — see iq_filters) so the
    Overview's form/results follow the global filter. ``season_ids`` is an
    exact season-row filter (no year expansion) on the view's own ``season_id``
    for Compare mode; it composes with (rather than replaces) ``season_id``.

    Ownership uses the canonical ``_OWNS_GAME`` predicate (grades/seasons LEFT
    JOINed, season off ``g.season_id``) so a shared fixture first synced by the
    opponent and a grade-less manual game both list, and ``result`` is the
    re-derived ``_EFFECTIVE_RESULT`` so a shared game shows OUR W/L, not the
    first-syncing club's."""
    # Cross-club variant: a shared game the opponent synced first carries THEIR
    # season row, which the ownership predicate includes and a plain same-org
    # season filter would then drop again.
    clauses = season_member_clause_cross_club("g.season_id", season_id)
    params: dict = {"org": org_id, "limit": limit, "season": season_id, "grade": grade_id}
    if grade_id:
        clauses += f" AND {grade_match_clause(grade_canonical_label('gr', 'org'))}"
    if season_ids:
        clauses += (
            " AND (g.season_id = ANY(:season_ids) OR g.season_id IN ("
            "SELECT s5.id FROM seasons s5 WHERE s5.grassroots_id IS NOT NULL "
            "AND s5.grassroots_id IN (SELECT s6.grassroots_id FROM seasons s6 "
            "WHERE s6.id = ANY(:season_ids) AND s6.grassroots_id IS NOT NULL)))"
        )
        params["season_ids"] = [_uuid.UUID(str(x)) for x in season_ids]
    res = await session.execute(
        text(
            f"""
            SELECT g.id::text AS id, g.played_at, {_EFFECTIVE_RESULT} AS result,
                   g.venue, g.is_final,
                   g.opp_club_name AS opp, g.home_team, g.away_team, gr.name AS grade
            FROM v_effective_games g
            LEFT JOIN grades gr ON gr.id = g.grade_id
            LEFT JOIN seasons s ON s.id = g.season_id
            WHERE {_OWNS_GAME} AND g.played_at IS NOT NULL {clauses}
            ORDER BY g.played_at DESC NULLS LAST
            LIMIT :limit
            """
        ),
        params,
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
    # Same ownership predicate + result re-derivation as list_review_games — a
    # game that lists (shared fixture synced by the opponent first, grade-less
    # manual game) must also open, and open with OUR result.
    meta = (await session.execute(
        text(
            f"""
            SELECT g.id::text AS id, g.played_at, {_EFFECTIVE_RESULT} AS result,
                   g.venue, g.is_final,
                   g.opp_club_name AS opp, g.home_team, g.away_team, gr.name AS grade
            FROM v_effective_games g
            LEFT JOIN grades gr ON gr.id = g.grade_id
            LEFT JOIN seasons s ON s.id = g.season_id
            WHERE g.id = CAST(:gid AS UUID) AND {_OWNS_GAME}
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
            LEFT JOIN players b1 ON b1.id = p.batter1_id AND b1.organisation_id = CAST(:org AS UUID)
            LEFT JOIN players b2 ON b2.id = p.batter2_id AND b2.organisation_id = CAST(:org AS UUID)
            WHERE p.game_id = CAST(:gid AS UUID) AND p.is_club_innings IS TRUE
              AND p.wicket_number BETWEEN 1 AND 10 AND p.runs IS NOT NULL
              -- Same org-scope as the best-partnership read above: on a shared
              -- fixture is_club_innings IS TRUE marks BOTH clubs' stands, so an
              -- unscoped pull hands the collapse check an interleaved mix of
              -- the two sides' partnership runs.
              AND (b1.id IS NOT NULL OR b2.id IS NOT NULL)
            """
        ),
        {"gid": game_id, "org": org_id},
    )
    # Keyed on innings_number alone — safe ONLY because the org scope above
    # makes the rows single-club; without it two clubs' wicket maps for the
    # same innings number would merge into one dict and the 3-wicket spans
    # would straddle sides.
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
