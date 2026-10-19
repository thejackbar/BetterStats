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

import json
import uuid as _uuid
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.iq_filters import grade_scope_fragment, grade_canonical_label, grade_match_clause, season_member_clause_cross_club

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


def _innings_list(raw) -> list[dict]:
    """``games.innings_totals`` as a list of dicts. A raw ``text()`` read can hand
    the JSONB back as a string, and a game synced before migration 233 holds NULL."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    return [e for e in raw if isinstance(e, dict)] if isinstance(raw, list) else []


def exact_scores(innings_totals, our_innings: list[int]) -> dict | None:
    """OUR and THEIR true team totals (extras included) from Cricket Australia's
    own per-innings figures, or None when they can't be told apart reliably.

    ``SUM(batting_innings.runs)`` is the batters' runs alone, so it reads 10 to 25
    light, and a chase won with 101 batters' runs looks like a loss to 127. The
    stored ``runs_scored`` is the full innings total. All or nothing: every innings
    we batted in, and at least one of theirs, must carry a figure, or an exact
    number would be mixed with an approximate one."""
    entries = {}
    for e in _innings_list(innings_totals):
        try:
            entries[int(e.get("innings_number"))] = e
        except (TypeError, ValueError):
            continue
    ours = sorted(set(our_innings or []))
    if not entries or not ours:
        return None
    theirs = sorted(n for n in entries if n not in ours)
    if not theirs or any(n not in entries for n in ours):
        return None
    if any(entries[n].get("runs_scored") is None for n in ours + theirs):
        return None

    def side(nums):
        wkts = [entries[n].get("wickets") for n in nums]
        return (sum(int(entries[n]["runs_scored"]) for n in nums),
                sum(int(w) for w in wkts) if all(w is not None for w in wkts) else None,
                [int(entries[n]["runs_scored"]) for n in nums])

    o_runs, o_wkts, o_by = side(ours)
    t_runs, t_wkts, t_by = side(theirs)
    return {"our_runs": o_runs, "our_wkts": o_wkts, "our_by_innings": o_by,
            "their_runs": t_runs, "their_wkts": t_wkts, "their_by_innings": t_by,
            "our_innings": ours, "their_innings": theirs}


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
    # The club-wide Grade Type / Match Type filter. Match Review lists OUR
    # games, so the format half reads per fixture off `g` — a grade that plays
    # both a one-day and a two-day season splits correctly rather than filing
    # every game it ever played under one.
    clauses += grade_scope_fragment("gr.id", grade_id, game_alias="g")
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
                   g.opp_club_name AS opp, g.home_team, g.away_team, gr.name AS grade,
                   gg.innings_totals
            FROM v_effective_games g
            LEFT JOIN grades gr ON gr.id = g.grade_id
            LEFT JOIN seasons s ON s.id = g.season_id
            -- True per-innings totals (migration 233) live on the base table only;
            -- a manual game has no `games` row and reads NULL here.
            LEFT JOIN games gg ON gg.id = g.id
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
    our_wkts = int(totals["our_wkts_lost"] or 0)
    opp_wkts = int(totals["opp_wkts"] or 0)
    extras = int(totals["extras_conceded"] or 0)
    opp = meta["opp"] or meta["away_team"] or meta["home_team"] or "the opposition"

    # Prefer Cricket Australia's own innings totals (extras included) over the
    # batters-only reconstruction, which under-reads both sides and can show a
    # winning chase as the lower score.
    our_nums = [r[0] for r in (await session.execute(
        text(
            """
            SELECT DISTINCT bi.innings_number
            FROM v_effective_batting_innings bi
            JOIN players p ON p.id = bi.player_id
            WHERE bi.game_id = CAST(:gid AS UUID) AND bi.did_not_bat IS NOT TRUE
              AND p.organisation_id = CAST(:org AS UUID)
            """
        ),
        {"gid": game_id, "org": org_id},
    )).all() if r[0] is not None]
    exact = exact_scores(meta["innings_totals"], our_nums)
    if exact:
        our_runs, opp_runs = exact["our_runs"], exact["their_runs"]
        if exact["our_wkts"] is not None:
            our_wkts = exact["our_wkts"]
        if exact["their_wkts"] is not None:
            opp_wkts = exact["their_wkts"]

    game = {
        "game_id": meta["id"],
        "date": meta["played_at"].isoformat() if meta["played_at"] else None,
        "opponent": opp,
        "result": meta["result"],
        "venue": meta["venue"],
        "is_final": bool(meta["is_final"]),
        "grade": meta["grade"],
        "our_score": (f"{our_runs}/{our_wkts}" if our_runs is not None else None),
        "their_score": (f"{opp_runs}/{opp_wkts}" if opp_runs is not None else None),
        # False when only the batters-only reconstruction is held (extras missing).
        "score_exact": bool(exact),
    }

    # Plain-language synthesis (rule-based; the scorecard-reachable subset of §16.8).
    summary = []
    rmap = {"WIN": "Won", "LOSS": "Lost", "DRAW": "Drew with", "TIE": "Tied with"}
    if meta["result"] in rmap:
        line = f"{rmap[meta['result']]} {('against ' if meta['result'] in ('WIN', 'LOSS') else '')}{opp}"
        # An approximate score can contradict the result (a chase won on batters'
        # runs alone reads as the lower total), so only state it when it is exact.
        if game["our_score"] and game["their_score"] and exact:
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

    notes = [
        "Biggest-over and win-probability swings need ball-by-ball data we don't hold.",
    ]
    if not exact:
        notes.insert(0, "Scores are rebuilt from the batting and bowling cards, so they leave out extras and can read light. Run a sync to store the exact totals.")
    return {
        "game": game,
        "top_batting": bat,
        "top_bowling": bowl,
        "best_partnership": best_partnership,
        "extras_conceded": extras,
        "collapse": collapse,
        "summary": summary,
        "coverage": {"notes": notes},
    }


# ─── Completed-game performance card (Ask IQ: 3-2-1 votes, "who played well") ──

def _band(position) -> str | None:
    """Where a batter sat in the order. A top-order wicket changes a game more than
    a number 10's, so every wicket carries the band of the batter it removed."""
    if position is None:
        return None
    p = int(position)
    return "top order" if p <= 3 else "middle order" if p <= 7 else "tail"


def _wicket_value(position, runs) -> dict:
    """A wicket's standing: the batter's slot, and whether they were set. A set
    top-order batter is the most valuable wicket, a tail-ender new to the crease
    the least. A scorecard has no ball-by-ball, so this is slot plus score only."""
    band = _band(position)
    set_batter = runs is not None and int(runs) >= 30
    if band == "tail":
        tier = "low"
    elif band == "top order" or set_batter:
        tier = "high"
    else:
        tier = "medium"
    if band == "tail" and set_batter:
        tier = "medium"
    return {"batter_position": position, "band": band, "batter_runs": runs,
            "set_batter": set_batter, "value": tier}


async def list_recent_games(session: AsyncSession, org_id: str, *, limit: int = 10,
                            team: str | None = None, opponent: str | None = None,
                            from_date=None, to_date=None) -> list[dict]:
    """Completed games, newest first, each with the BetterSelect team the fixture was
    picked for ('3rd XI') beside the grade it was played in ('5th Grade'): a club's
    side number and its grade number often differ. ``team`` matches either."""
    res = await session.execute(
        text(
            f"""
            SELECT g.id::text AS id, g.played_at, {_EFFECTIVE_RESULT} AS result,
                   g.venue, g.opp_club_name AS opp, g.home_team, g.away_team,
                   gr.name AS grade, tm.name AS team_name
            FROM v_effective_games g
            LEFT JOIN grades gr ON gr.id = g.grade_id
            LEFT JOIN seasons s ON s.id = g.season_id
            LEFT JOIN LATERAL (
                SELECT t.name FROM fixtures f JOIN teams t ON t.id = f.team_id
                WHERE f.playhq_id = g.id::text AND f.organisation_id = CAST(:org AS UUID)
                LIMIT 1
            ) tm ON TRUE
            WHERE {_OWNS_GAME} AND g.played_at IS NOT NULL
              AND g.played_at <= CURRENT_DATE
              AND (CAST(:frm AS DATE) IS NULL OR g.played_at >= CAST(:frm AS DATE))
              AND (CAST(:to AS DATE) IS NULL OR g.played_at <= CAST(:to AS DATE))
              AND (CAST(:opp AS TEXT) IS NULL
                   OR LOWER(COALESCE(g.opp_club_name, '')) LIKE '%' || LOWER(CAST(:opp AS TEXT)) || '%')
              AND (CAST(:team AS TEXT) IS NULL
                   OR LOWER(COALESCE(tm.name, '')) LIKE '%' || LOWER(CAST(:team AS TEXT)) || '%'
                   OR LOWER(COALESCE(gr.name, '')) LIKE '%' || LOWER(CAST(:team AS TEXT)) || '%')
            ORDER BY g.played_at DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {"org": org_id, "limit": limit, "frm": from_date, "to": to_date,
         "opp": (opponent or None), "team": (team or None)},
    )
    return [{
        "game_id": r["id"],
        "date": r["played_at"].isoformat() if r["played_at"] else None,
        "opponent": r["opp"] or r["away_team"] or r["home_team"] or "Opponent",
        "result": r["result"], "venue": r["venue"],
        "grade": r["grade"], "team": r["team_name"],
    } for r in res.mappings()]


async def game_performances(session: AsyncSession, org_id: str, game_id: str) -> dict | None:
    """Everything needed to judge who played well in ONE completed game: the true
    result and scores, every one of OUR batters with their share of the total, every
    bowler with the quality of each wicket taken, and the fielders. Org-scoped to
    our own players throughout (a shared fixture carries both clubs' rows)."""
    review = await game_review(session, org_id, game_id)
    if review is None:
        return None
    game = review["game"]
    params = {"gid": game_id, "org": org_id}

    bat_rows = [dict(r) for r in (await session.execute(
        text(
            """
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   bi.innings_number, bi.batting_position, bi.runs, bi.balls, bi.fours, bi.sixes,
                   bi.not_out, bi.dismissal_type, bi.did_not_bat
            FROM v_effective_batting_innings bi
            JOIN players p ON p.id = bi.player_id
            WHERE bi.game_id = CAST(:gid AS UUID) AND p.organisation_id = CAST(:org AS UUID)
            ORDER BY bi.innings_number, bi.batting_position NULLS LAST
            """
        ), params)).mappings()]

    bowl_rows = [dict(r) for r in (await session.execute(
        text(
            """
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   bs.innings_number, bs.overs, bs.maidens, bs.runs, bs.wickets,
                   COALESCE(bs.wides, 0) AS wides, COALESCE(bs.no_balls, 0) AS no_balls
            FROM v_effective_bowling_spells bs
            JOIN players p ON p.id = bs.player_id
            WHERE bs.game_id = CAST(:gid AS UUID) AND p.organisation_id = CAST(:org AS UUID)
            ORDER BY bs.wickets DESC NULLS LAST, bs.runs ASC NULLS LAST
            """
        ), params)).mappings()]

    wicket_rows = [dict(r) for r in (await session.execute(
        text(
            """
            SELECT bw.bowler_id::text AS bowler_id, bw.batter_name, bw.batter_position,
                   bw.batter_runs, bw.batter_balls, bw.dismissal_type
            FROM v_effective_bowler_wickets bw
            JOIN players p ON p.id = bw.bowler_id
            WHERE bw.game_id = CAST(:gid AS UUID) AND p.organisation_id = CAST(:org AS UUID)
            ORDER BY bw.innings_number, bw.batter_position NULLS LAST
            """
        ), params)).mappings()]

    field_rows = [dict(r) for r in (await session.execute(
        text(
            """
            SELECT COALESCE(p.display_name_override, p.name) AS name,
                   COALESCE(fs.catches, 0) AS catches, COALESCE(fs.catches_wk, 0) AS catches_wk,
                   COALESCE(fs.run_outs, 0) AS run_outs, COALESCE(fs.stumpings, 0) AS stumpings
            FROM v_effective_fielding_stats fs
            JOIN players p ON p.id = fs.player_id
            WHERE fs.game_id = CAST(:gid AS UUID) AND p.organisation_id = CAST(:org AS UUID)
              AND (COALESCE(fs.catches, 0) + COALESCE(fs.run_outs, 0) + COALESCE(fs.stumpings, 0)) > 0
            """
        ), params)).mappings()]

    batted = [b for b in bat_rows if not b["did_not_bat"]]
    our_innings = sorted({b["innings_number"] for b in batted if b["innings_number"] is not None})
    batted_first = bool(our_innings) and our_innings[0] == 1
    our_total = None
    if game.get("our_score"):
        our_total = int(str(game["our_score"]).split("/")[0])
    their_total = int(str(game["their_score"]).split("/")[0]) if game.get("their_score") else None

    batting = []
    for b in batted:
        runs = b["runs"]
        entry = {
            "name": b["name"], "innings": b["innings_number"], "position": b["batting_position"],
            "band": _band(b["batting_position"]),
            "runs": runs, "balls": b["balls"], "fours": b["fours"], "sixes": b["sixes"],
            "not_out": bool(b["not_out"]),
            "how_out": None if b["not_out"] else b["dismissal_type"],
            "strike_rate": round(100 * runs / b["balls"], 1) if runs is not None and b["balls"] else None,
        }
        if our_total and runs is not None and len(our_innings) == 1:
            entry["share_of_team_total_pct"] = round(100 * runs / our_total)
        batting.append(entry)
    did_not_bat = [b["name"] for b in bat_rows if b["did_not_bat"]]

    by_bowler: dict[str, list[dict]] = defaultdict(list)
    for w in wicket_rows:
        by_bowler[w["bowler_id"]].append({
            "batter": w["batter_name"], "how": w["dismissal_type"],
            **_wicket_value(w["batter_position"], w["batter_runs"]),
        })
    bowling = []
    for b in bowl_rows:
        wk = by_bowler.get(b["player_id"], [])
        overs = float(b["overs"]) if b["overs"] is not None else None
        balls = (int(overs) * 6 + round((overs - int(overs)) * 10)) if overs is not None else None
        bowling.append({
            "name": b["name"], "innings": b["innings_number"], "overs": overs,
            "maidens": b["maidens"], "runs": b["runs"], "wickets": b["wickets"],
            "economy": round(6 * b["runs"] / balls, 2) if balls and b["runs"] is not None else None,
            "wides_and_no_balls": b["wides"] + b["no_balls"],
            "wickets_taken": wk,
            "high_value_wickets": sum(1 for x in wk if x["value"] == "high"),
            "tail_wickets": sum(1 for x in wk if x["band"] == "tail"),
        })

    context: dict = {"batted_first": batted_first if our_innings else None}
    result = game.get("result")
    if our_total is not None and their_total is not None and our_innings:
        if len(our_innings) == 1 and result == "WIN":
            if batted_first:
                context["how_won"] = f"defended {our_total}, won by {our_total - their_total} runs"
            else:
                wkts = int(str(game["our_score"]).split("/")[1])
                context["how_won"] = f"chased {their_total + 1} and got there with {10 - wkts} wickets in hand"
        elif len(our_innings) == 1 and result == "LOSS":
            context["how_lost"] = (f"set {our_total}, they made {their_total}" if batted_first
                                   else f"chasing {their_total + 1}, we made {our_total}")
    context["team_batting"] = (
        f"{our_total}" if our_total is not None else None)
    context["best_partnership"] = review.get("best_partnership")
    context["collapse"] = review.get("collapse")
    context["extras_conceded_wides_and_no_balls"] = review.get("extras_conceded")

    return {
        "game": game, "context": context,
        "batting": batting, "did_not_bat": did_not_bat,
        "bowling": bowling,
        "fielding": [{"name": f["name"], "catches": f["catches"] - f["catches_wk"],
                      "keeper_catches": f["catches_wk"], "run_outs": f["run_outs"],
                      "stumpings": f["stumpings"]} for f in field_rows],
        "coverage": review["coverage"]["notes"] + [
            "Our players only: the opposition's individual batting and bowling is not held.",
            "A wicket's value is the dismissed batter's slot in the order plus their score; there is no ball-by-ball.",
        ],
    }
