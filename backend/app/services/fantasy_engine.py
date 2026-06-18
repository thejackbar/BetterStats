"""BetterFantasyCricket engine — round generation, the priced pool, settlement.

The DB-bound half of the scoring/pricing core. It reads the club's real data
through the org-scoped ``v_effective_*`` views (so merges and manual adjustments
are respected) and writes the fantasy spine:

  - ``generate_rounds``  groups the season's games into weekly fantasy rounds
  - ``build_pool``       classifies each eligible player and prices them from
                         their recent record
  - ``settle_round``     computes per-player fantasy points for a round from the
                         scorecards, idempotently (safe to re-run after a re-sync)

Squad-level scoring (best 11, captain, transfer hit) and price movement live with
the salary-cap engine, which has the managers and squads. Pure points and role
maths come from ``fantasy_scoring``. Full design: docs/betterfantasycricket.md.

NOTE: not exercised in the build sandbox (no database). Verify on a deployed
environment after migration 087.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import fantasy_squad, fantasy_draft
from app.services.fantasy_scoring import (
    DEFAULT_SCORING, classify_role, score_player_round,
)

# Recent window (in seasons, inclusive of the current year) used to price form.
PRICE_WINDOW_YEARS = 3
# Price band the baseline maps into; tuned so a balanced 12 fits a 100 budget but
# the premiums can't all be afforded. Heuristic — easy to retune once a club plays.
PRICE_MIN, PRICE_MAX, PRICE_FLOOR, PRICE_K = 4.0, 15.0, 4.0, 0.12


def _grade_clause(included_grade_ids, alias: str = "g") -> str:
    """Optional ``AND <alias>.grade_id = ANY(:grades)`` when the season restricts
    which grades count. NULL/empty means every grade."""
    return f" AND {alias}.grade_id = ANY(:grades)" if included_grade_ids else ""


# ── Round generation ───────────────────────────────────────────────────────────

async def generate_rounds(session: AsyncSession, fs) -> int:
    """Group the season-year's games into weekly rounds (a club weekend = one
    ISO week) and upsert ``fantasy_rounds``. Idempotent on round_number; never
    rewrites a round already marked ``scored``. Returns the round count."""
    grades = fs.included_grade_ids or None
    rows = await session.execute(
        text(f"""
            SELECT g.played_at
            FROM v_effective_games g
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = CAST(:org AS UUID) AND s.year = :year
              AND g.played_at IS NOT NULL{_grade_clause(grades)}
            ORDER BY g.played_at
        """),
        {"org": str(fs.organisation_id), "year": fs.season_year, "grades": grades},
    )
    # Group play dates into ISO (year, week) buckets.
    weeks: dict[tuple[int, int], list] = defaultdict(list)
    for (played_at,) in rows.all():
        iso = played_at.isocalendar()
        weeks[(iso[0], iso[1])].append(played_at)
    if not weeks:
        return 0

    existing = await session.execute(
        text("SELECT round_number, status FROM fantasy_rounds WHERE fantasy_season_id = CAST(:fs AS UUID)"),
        {"fs": str(fs.id)},
    )
    scored = {r["round_number"] for r in existing.mappings() if r["status"] == "scored"}

    n = 0
    for n, key in enumerate(sorted(weeks), start=1):
        if n in scored:
            continue  # leave settled rounds untouched
        # games.played_at is a DATE, so the round window is date-keyed. We don't
        # hold kick-off times, so the lock is the start of the round's first day.
        dates = sorted(weeks[key])
        await session.execute(
            text("""
                INSERT INTO fantasy_rounds
                    (fantasy_season_id, organisation_id, round_number, name, lock_at, start_date, end_date, status)
                VALUES (CAST(:fs AS UUID), CAST(:org AS UUID), :n, :name, :lock_at, :start, :end, 'upcoming')
                ON CONFLICT (fantasy_season_id, round_number) DO UPDATE
                SET name = EXCLUDED.name, lock_at = EXCLUDED.lock_at,
                    start_date = EXCLUDED.start_date, end_date = EXCLUDED.end_date,
                    updated_at = NOW()
            """),
            {
                "fs": str(fs.id), "org": str(fs.organisation_id), "n": n,
                "name": f"Round {n}", "lock_at": datetime.combine(dates[0], time()),
                "start": dates[0], "end": dates[-1],
            },
        )
    return len(weeks)


# ── Pool build (role + price) ──────────────────────────────────────────────────

async def build_pool(session: AsyncSession, fs, reset: bool | None = None) -> int:
    """Classify and price every eligible player and upsert ``fantasy_pool_players``.

    Eligible = an active player who has turned out in the recent window (this
    season-year or the prior ``PRICE_WINDOW_YEARS - 1``). The recent window
    matters: a fantasy season is usually set up BEFORE the games begin, so a
    current-year-only gate would leave the pool empty pre-season; seeding from
    the last couple of seasons gives the squad you'd expect, and a rebuild once
    the season is underway naturally picks up anyone new. An admin role override
    (role_source = 'admin') is preserved on rebuild; the live ``current_price`` is
    kept once the season is live, but reset to the new baseline while the season
    is still in setup, so changing the pricing window updates the visible prices.
    ``reset`` overrides that default: the admin's explicit "recalculate prices"
    passes ``reset=True`` so a window change moves prices even mid-season.
    Returns the pool size."""
    window = max(1, int((fs.rules or {}).get("price_window_years", PRICE_WINDOW_YEARS)))
    recent_from = fs.season_year - (window - 1)
    reset_price = (fs.status in ("setup", "open")) if reset is None else bool(reset)
    rows = await session.execute(
        text("""
            SELECT p.id AS player_id, p.player_role, p.skill_positions,
                   COALESCE(SUM(pss.batting_innings), 0) AS bat_inns,
                   COALESCE(SUM(pss.bowling_innings), 0) AS bowl_inns,
                   COALESCE(SUM(pss.wickets), 0) AS wickets,
                   COALESCE(SUM(pss.catches_wk), 0) + COALESCE(SUM(pss.stumpings), 0) AS keeper_dis,
                   -- recent (form) window for pricing
                   COALESCE(SUM(pss.matches) FILTER (WHERE s.year >= :rfrom), 0) AS r_matches,
                   COALESCE(SUM(pss.runs) FILTER (WHERE s.year >= :rfrom), 0) AS r_runs,
                   COALESCE(SUM(pss.fours) FILTER (WHERE s.year >= :rfrom), 0) AS r_fours,
                   COALESCE(SUM(pss.sixes) FILTER (WHERE s.year >= :rfrom), 0) AS r_sixes,
                   COALESCE(SUM(pss.fifties) FILTER (WHERE s.year >= :rfrom), 0) AS r_fifties,
                   COALESCE(SUM(pss.hundreds) FILTER (WHERE s.year >= :rfrom), 0) AS r_hundreds,
                   COALESCE(SUM(pss.wickets) FILTER (WHERE s.year >= :rfrom), 0) AS r_wickets,
                   COALESCE(SUM(pss.maidens) FILTER (WHERE s.year >= :rfrom), 0) AS r_maidens,
                   COALESCE(SUM(pss.five_wicket_innings) FILTER (WHERE s.year >= :rfrom), 0) AS r_fivefor,
                   COALESCE(SUM(pss.catches) FILTER (WHERE s.year >= :rfrom), 0) AS r_catches,
                   COALESCE(SUM(pss.catches_wk) FILTER (WHERE s.year >= :rfrom), 0) AS r_catches_wk,
                   COALESCE(SUM(pss.stumpings) FILTER (WHERE s.year >= :rfrom), 0) AS r_stumpings,
                   COALESCE(SUM(pss.run_outs) FILTER (WHERE s.year >= :rfrom), 0) AS r_run_outs
            FROM players p
            JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
            JOIN seasons s ON s.id = pss.season_id AND s.organisation_id = CAST(:org AS UUID)
            WHERE p.organisation_id = CAST(:org AS UUID)
              AND p.status = 'active' AND COALESCE(p.is_player, true)
            GROUP BY p.id, p.player_role, p.skill_positions
            HAVING BOOL_OR(s.year >= :rfrom)
        """),
        {"org": str(fs.organisation_id), "year": fs.season_year, "rfrom": recent_from},
    )

    count = 0
    for r in rows.mappings():
        role, source = classify_role(
            player_role=r["player_role"], skill_positions=r["skill_positions"],
            bat_innings=int(r["bat_inns"]), wickets=int(r["wickets"]),
            bowl_innings=int(r["bowl_inns"]), keeper_dismissals=int(r["keeper_dis"]),
        )
        price = _baseline_price(r, role)
        await session.execute(
            text("""
                INSERT INTO fantasy_pool_players
                    (fantasy_season_id, organisation_id, player_id, role, role_source,
                     base_price, current_price)
                VALUES (CAST(:fs AS UUID), CAST(:org AS UUID), CAST(:pid AS UUID), :role, :source,
                        :price, :price)
                ON CONFLICT (fantasy_season_id, player_id) DO UPDATE SET
                    base_price = EXCLUDED.base_price,
                    current_price = CASE WHEN :reset THEN EXCLUDED.base_price
                                ELSE fantasy_pool_players.current_price END,
                    role = CASE WHEN fantasy_pool_players.role_source = 'admin'
                                THEN fantasy_pool_players.role ELSE EXCLUDED.role END,
                    role_source = CASE WHEN fantasy_pool_players.role_source = 'admin'
                                THEN 'admin' ELSE EXCLUDED.role_source END,
                    updated_at = NOW()
            """),
            {
                "fs": str(fs.id), "org": str(fs.organisation_id), "pid": str(r["player_id"]),
                "role": role, "source": source, "price": price, "reset": reset_price,
            },
        )
        count += 1
    return count


def _baseline_price(r, role: str) -> float:
    """Map a player's recent record to a starting price. Approximate fantasy
    points per game from season aggregates (per-innings milestones aren't in the
    aggregates, so fifties/hundreds/five-fors stand in), role-weighted, then
    scaled into the price band."""
    s = DEFAULT_SCORING
    m = float(s["off_role_multiplier"])
    bat_mult, bowl_mult, keep_mult = (
        (m, 1.0, 1.0) if role == "bowler" else
        (m, 1.0, m) if role == "keeper" else
        (1.0, 1.0, 1.0) if role == "allrounder" else
        (1.0, m, 1.0)
    )
    bat = (r["r_runs"] * s["run"] + r["r_fours"] * s["four"] + r["r_sixes"] * s["six"]
           + r["r_fifties"] * s["fifty"] + r["r_hundreds"] * s["hundred"])
    bowl = r["r_wickets"] * s["wicket"] + r["r_maidens"] * s["maiden"] + r["r_fivefor"] * s["five_wickets"]
    keep = r["r_catches_wk"] * s["catch"] + r["r_stumpings"] * s["stumping"]
    field = (r["r_catches"] - r["r_catches_wk"]) * s["catch"] + r["r_run_outs"] * s["run_out"]
    matches = max(int(r["r_matches"]), 1)
    weighted = bat * bat_mult + bowl * bowl_mult + keep * keep_mult + field + matches * s["appearance"]
    ppg = weighted / matches
    return round(min(max(PRICE_FLOOR + ppg * PRICE_K, PRICE_MIN), PRICE_MAX), 1)


async def classify_and_price_one(session: AsyncSession, fs, player_id) -> tuple[str, float]:
    """Role + baseline price for a single player, used when an admin adds a
    returning player to the pool by hand. Falls back to a batter at the floor
    price when there's no usable history."""
    window = max(1, int((fs.rules or {}).get("price_window_years", PRICE_WINDOW_YEARS)))
    recent_from = fs.season_year - (window - 1)
    row = (await session.execute(
        text("""
            SELECT p.player_role, p.skill_positions,
                   COALESCE(SUM(pss.batting_innings), 0) AS bat_inns,
                   COALESCE(SUM(pss.bowling_innings), 0) AS bowl_inns,
                   COALESCE(SUM(pss.wickets), 0) AS wickets,
                   COALESCE(SUM(pss.catches_wk), 0) + COALESCE(SUM(pss.stumpings), 0) AS keeper_dis,
                   COALESCE(SUM(pss.matches) FILTER (WHERE s.year >= :rfrom), 0) AS r_matches,
                   COALESCE(SUM(pss.runs) FILTER (WHERE s.year >= :rfrom), 0) AS r_runs,
                   COALESCE(SUM(pss.fours) FILTER (WHERE s.year >= :rfrom), 0) AS r_fours,
                   COALESCE(SUM(pss.sixes) FILTER (WHERE s.year >= :rfrom), 0) AS r_sixes,
                   COALESCE(SUM(pss.fifties) FILTER (WHERE s.year >= :rfrom), 0) AS r_fifties,
                   COALESCE(SUM(pss.hundreds) FILTER (WHERE s.year >= :rfrom), 0) AS r_hundreds,
                   COALESCE(SUM(pss.wickets) FILTER (WHERE s.year >= :rfrom), 0) AS r_wickets,
                   COALESCE(SUM(pss.maidens) FILTER (WHERE s.year >= :rfrom), 0) AS r_maidens,
                   COALESCE(SUM(pss.five_wicket_innings) FILTER (WHERE s.year >= :rfrom), 0) AS r_fivefor,
                   COALESCE(SUM(pss.catches) FILTER (WHERE s.year >= :rfrom), 0) AS r_catches,
                   COALESCE(SUM(pss.catches_wk) FILTER (WHERE s.year >= :rfrom), 0) AS r_catches_wk,
                   COALESCE(SUM(pss.stumpings) FILTER (WHERE s.year >= :rfrom), 0) AS r_stumpings,
                   COALESCE(SUM(pss.run_outs) FILTER (WHERE s.year >= :rfrom), 0) AS r_run_outs
            FROM players p
            LEFT JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
            LEFT JOIN seasons s ON s.id = pss.season_id AND s.organisation_id = CAST(:org AS UUID)
            WHERE p.id = CAST(:pid AS UUID)
            GROUP BY p.id, p.player_role, p.skill_positions
        """),
        {"org": str(fs.organisation_id), "pid": str(player_id), "rfrom": recent_from},
    )).mappings().first()
    if not row:
        return "batter", PRICE_MIN
    role, _src = classify_role(
        player_role=row["player_role"], skill_positions=row["skill_positions"],
        bat_innings=int(row["bat_inns"]), wickets=int(row["wickets"]),
        bowl_innings=int(row["bowl_inns"]), keeper_dismissals=int(row["keeper_dis"]),
    )
    return role, _baseline_price(row, role)


# ── Round settlement (player points) ───────────────────────────────────────────

async def _round_player_scores(session: AsyncSession, fs, rnd) -> dict[str, dict]:
    """Read-only: compute each player's fantasy points for a round's window from
    the scorecards, with no writes. Returns ``{player_id: {base, total,
    breakdown, games}}``. Shared by round settlement (which then persists) and the
    live preview (which doesn't), so the two can never disagree."""
    grades = fs.included_grade_ids or None
    base = {"org": str(fs.organisation_id), "year": fs.season_year,
            "start": rnd.start_date, "end": rnd.end_date, "grades": grades}

    games = await session.execute(
        text(f"""
            SELECT g.id
            FROM v_effective_games g
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = CAST(:org AS UUID) AND s.year = :year
              AND g.played_at::date BETWEEN :start AND :end{_grade_clause(grades)}
        """),
        base,
    )
    game_ids = [row[0] for row in games.all()]
    if not game_ids:
        return {}
    gp = {"gids": game_ids}

    batting = await session.execute(
        text("""
            SELECT bi.player_id, bi.game_id, bi.runs,
                   COALESCE(bi.fours, 0) AS fours, COALESCE(bi.sixes, 0) AS sixes,
                   (bi.did_not_bat IS NOT TRUE AND NOT bi.not_out AND bi.dismissal_type IS NOT NULL) AS out
            FROM v_effective_batting_innings bi
            WHERE bi.game_id = ANY(:gids) AND bi.did_not_bat IS NOT TRUE
        """), gp,
    )
    bowling = await session.execute(
        text("""
            SELECT bs.player_id, bs.game_id, bs.wickets, COALESCE(bs.maidens, 0) AS maidens
            FROM v_effective_bowling_spells bs WHERE bs.game_id = ANY(:gids)
        """), gp,
    )
    fielding = await session.execute(
        text("""
            SELECT fs.player_id, fs.game_id,
                   COALESCE(fs.catches, 0) AS catches, COALESCE(fs.catches_wk, 0) AS catches_wk,
                   COALESCE(fs.run_outs, 0) AS run_outs, COALESCE(fs.stumpings, 0) AS stumpings
            FROM v_effective_fielding_stats fs WHERE fs.game_id = ANY(:gids)
        """), gp,
    )
    appearances = await session.execute(
        text("SELECT player_id, game_id FROM game_appearances WHERE game_id = ANY(:gids)"), gp,
    )
    roles = await session.execute(
        text("SELECT player_id, role FROM fantasy_pool_players WHERE fantasy_season_id = CAST(:fs AS UUID)"),
        {"fs": str(fs.id)},
    )
    role_by_player = {str(r["player_id"]): r["role"] for r in roles.mappings()}

    # Assemble per (player, game): batting innings list, bowling list, fielding, played.
    games_by_player: dict[str, dict] = defaultdict(dict)

    def _cell(pid: str, gid) -> dict:
        g = games_by_player[pid].setdefault(gid, {
            "batting": [], "bowling": [], "catches_wk": 0, "stumpings": 0,
            "catches_nonwk": 0, "run_outs": 0, "played": True,
        })
        return g

    for b in batting.mappings():
        _cell(str(b["player_id"]), b["game_id"])["batting"].append(
            {"runs": b["runs"] or 0, "fours": b["fours"], "sixes": b["sixes"], "out": bool(b["out"])}
        )
    for w in bowling.mappings():
        _cell(str(w["player_id"]), w["game_id"])["bowling"].append(
            {"wickets": w["wickets"] or 0, "maidens": w["maidens"]}
        )
    for f in fielding.mappings():
        c = _cell(str(f["player_id"]), f["game_id"])
        c["catches_wk"] = f["catches_wk"]
        c["stumpings"] = f["stumpings"]
        c["catches_nonwk"] = max((f["catches"] or 0) - (f["catches_wk"] or 0), 0)
        c["run_outs"] = f["run_outs"]
    for a in appearances.mappings():
        _cell(str(a["player_id"]), a["game_id"])  # ensures the appearance point

    out: dict[str, dict] = {}
    for pid, by_game in games_by_player.items():
        role = role_by_player.get(pid, "batter")
        base_pts, total_pts, breakdown = score_player_round(list(by_game.values()), role, fs.scoring or DEFAULT_SCORING)
        out[pid] = {"base": base_pts, "total": total_pts, "breakdown": breakdown, "games": len(by_game)}
    return out


async def settle_round(session: AsyncSession, fs, rnd) -> int:
    """Compute each player's fantasy points for a round from the scorecards of the
    games in the round window, and upsert ``fantasy_player_round_scores``.
    Idempotent on (round, player). Marks the round ``scored`` and refreshes the
    pool's season totals. Returns the number of players scored."""
    by_player = await _round_player_scores(session, fs, rnd)
    if not by_player:
        await _mark_scored(session, rnd, 0)
        return 0

    scored = 0
    for pid, sc in by_player.items():
        base_pts, total_pts, breakdown = sc["base"], sc["total"], sc["breakdown"]
        await session.execute(
            text("""
                INSERT INTO fantasy_player_round_scores
                    (fantasy_season_id, round_id, player_id, base_points, total_points, breakdown, games_counted, computed_at)
                VALUES (CAST(:fs AS UUID), CAST(:rid AS UUID), CAST(:pid AS UUID), :base, :total, CAST(:bd AS JSONB), :games, NOW())
                ON CONFLICT (round_id, player_id) DO UPDATE SET
                    base_points = EXCLUDED.base_points, total_points = EXCLUDED.total_points,
                    breakdown = EXCLUDED.breakdown, games_counted = EXCLUDED.games_counted,
                    computed_at = NOW()
            """),
            {
                "fs": str(fs.id), "rid": str(rnd.id), "pid": pid,
                "base": base_pts, "total": total_pts,
                "bd": json.dumps(breakdown), "games": sc["games"],
            },
        )
        scored += 1

    await _refresh_pool_totals(session, fs, rnd)
    # Roll the per-player points up into each squad's best-11 round score + ladder.
    await fantasy_squad.score_squads_for_round(session, fs, rnd)
    # Fill any head-to-head draft fixtures for this round.
    await fantasy_draft.settle_h2h(session, fs, rnd)
    # The season is live once the first round settles — squad changes now go
    # through transfers, not a full rebuild.
    if fs.status in ("setup", "open"):
        await session.execute(
            text("UPDATE fantasy_seasons SET status = 'active', updated_at = NOW() WHERE id = CAST(:fs AS UUID)"),
            {"fs": str(fs.id)},
        )
        fs.status = "active"
    await _mark_scored(session, rnd, scored)
    return scored


async def _refresh_pool_totals(session: AsyncSession, fs, rnd) -> None:
    """Recompute each pool player's season total and this-round points from the
    per-round scores (so re-settling a corrected round self-heals the totals)."""
    await session.execute(
        text("""
            UPDATE fantasy_pool_players pp SET
                total_points = COALESCE(t.total, 0),
                last_round_points = COALESCE(lr.pts, 0),
                updated_at = NOW()
            FROM (SELECT player_id, SUM(total_points) AS total
                  FROM fantasy_player_round_scores
                  WHERE fantasy_season_id = CAST(:fs AS UUID) GROUP BY player_id) t
            LEFT JOIN (SELECT player_id, total_points AS pts
                       FROM fantasy_player_round_scores
                       WHERE round_id = CAST(:rid AS UUID)) lr ON lr.player_id = t.player_id
            WHERE pp.fantasy_season_id = CAST(:fs AS UUID) AND pp.player_id = t.player_id
        """),
        {"fs": str(fs.id), "rid": str(rnd.id)},
    )


async def _mark_scored(session: AsyncSession, rnd, _count: int) -> None:
    await session.execute(
        text("UPDATE fantasy_rounds SET status = 'scored', scored_at = NOW(), updated_at = NOW() WHERE id = CAST(:rid AS UUID)"),
        {"rid": str(rnd.id)},
    )
