"""Shared BetterSelect selection-pool assembly.

Extracted from ``routers/selection.py`` so BetterIQ's selection analysis can
reuse the **exact** eligibility model — recency wall, women's/men's gender wall,
squad tier (same-XI / promotion / drop-down) and per-date availability — instead
of re-deriving it and drifting (which produced ghosts like a women's player or a
years-dormant name appearing as a "promote" suggestion for a men's 2nd XI).

``routers/selection`` delegates ``GET /selection/{fixture_id}`` to
``assemble_selection`` here; BetterIQ calls the same function.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import FixtureLineup, Grade, Player, Team
from app.routers.availability import DEFAULT_DORMANCY_MONTHS, months_ago, resolve_period_statuses

# Autofill scoring constants ─────────────────────────────────────────────────
# Window for "recent form" — last N batting innings & bowling spells per player.
RECENT_FORM_GAMES = 4
RECENT_FORM_WEIGHT = 0.6
SEASON_FORM_WEIGHT = 0.4
# A wicket is worth ~25 runs in cricket's standard equivalence.
WICKET_RUN_EQUIV = 25.0
# Hard activity wall for autofill eligibility (12-month cutoff).
AUTOFILL_RECENCY_MONTHS = 12


def _compute_score(skill_positions: list[str] | None,
                   recent_bat: dict | None,
                   recent_bowl: dict | None,
                   season: dict | None) -> float:
    """Composite form score: 60% last-4 innings + 40% season-to-date, with the
    underlying stat chosen by role. Output is on the runs-per-innings scale."""
    skills = {s.upper() for s in (skill_positions or []) if s}

    bat_recent = 0.0
    if recent_bat and recent_bat.get("innings"):
        bat_recent = float(recent_bat["total_runs"] or 0) / recent_bat["innings"]
    bat_season = float(season["batting_average"]) if (season and season.get("batting_average") is not None) else 0.0
    bat_score = RECENT_FORM_WEIGHT * bat_recent + SEASON_FORM_WEIGHT * bat_season

    bowl_recent = 0.0
    if recent_bowl and recent_bowl.get("innings"):
        bowl_recent = (float(recent_bowl["total_wickets"] or 0) / recent_bowl["innings"]) * WICKET_RUN_EQUIV
    bowl_season = 0.0
    if season and season.get("wickets") and season.get("bowling_innings"):
        bowl_season = (float(season["wickets"]) / float(season["bowling_innings"])) * WICKET_RUN_EQUIV
    bowl_score = RECENT_FORM_WEIGHT * bowl_recent + SEASON_FORM_WEIGHT * bowl_season

    is_bowler_only = "BWL" in skills and not (skills & {"BAT", "WKT", "ALL"})
    if is_bowler_only:
        return bowl_score
    if "ALL" in skills or ("BWL" in skills and skills & {"BAT", "WKT"}):
        return (bat_score + bowl_score) / 2.0
    return bat_score


def _tier_for(fx_seq: int | None, sq_seq: int | None) -> int | None:
    """Tier 1 = same XI, 2 = one grade below (promotion), 3 = one grade above
    (drop-down). None = too far / unranked — excluded from autofill."""
    if not fx_seq or not sq_seq:
        return None
    if sq_seq == fx_seq:
        return 1
    if sq_seq == fx_seq + 1:
        return 2
    if sq_seq == fx_seq - 1:
        return 3
    return None


async def _recent_batting_form(db: AsyncSession, org_id) -> dict[str, dict]:
    """Per-player last-N batting innings: {total_runs, innings}. Excludes
    DNB/absent so a no-show doesn't drag the average down."""
    rows = await db.execute(
        text(
            """
            WITH ranked AS (
                SELECT ba.player_id, COALESCE(ba.runs, 0) AS runs,
                       ROW_NUMBER() OVER (PARTITION BY ba.player_id ORDER BY g.played_at DESC NULLS LAST) AS rn
                FROM batting_innings ba
                JOIN games g ON ba.game_id = g.id
                JOIN players p ON ba.player_id = p.id
                WHERE p.organisation_id = :org
                  AND COALESCE(ba.did_not_bat, false) = false
                  AND (ba.dismissal_type IS NULL
                       OR LOWER(ba.dismissal_type) NOT IN ('absent', 'did not bat', 'dnb'))
                  AND g.played_at IS NOT NULL
            )
            SELECT player_id, SUM(runs)::float AS total_runs, COUNT(*)::int AS innings
            FROM ranked WHERE rn <= :n GROUP BY player_id
            """
        ),
        {"org": org_id, "n": RECENT_FORM_GAMES},
    )
    return {str(pid): {"total_runs": runs, "innings": inns} for pid, runs, inns in rows.fetchall()}


async def _recent_bowling_form(db: AsyncSession, org_id) -> dict[str, dict]:
    """Per-player last-N bowling spells: {total_wickets, innings}."""
    rows = await db.execute(
        text(
            """
            WITH ranked AS (
                SELECT bs.player_id, COALESCE(bs.wickets, 0) AS wickets,
                       ROW_NUMBER() OVER (PARTITION BY bs.player_id ORDER BY g.played_at DESC NULLS LAST) AS rn
                FROM bowling_spells bs
                JOIN games g ON bs.game_id = g.id
                JOIN players p ON bs.player_id = p.id
                WHERE p.organisation_id = :org
                  AND g.played_at IS NOT NULL
            )
            SELECT player_id, SUM(wickets)::float AS total_wickets, COUNT(*)::int AS innings
            FROM ranked WHERE rn <= :n GROUP BY player_id
            """
        ),
        {"org": org_id, "n": RECENT_FORM_GAMES},
    )
    return {str(pid): {"total_wickets": wkts, "innings": inns} for pid, wkts, inns in rows.fetchall()}


async def _latest_season_stats(db: AsyncSession, org_id) -> dict[str, dict]:
    """Per-player most-recent season's aggregate stats."""
    rows = await db.execute(
        text(
            """
            SELECT DISTINCT ON (pss.player_id)
                pss.player_id,
                pss.batting_average, pss.runs, pss.batting_innings,
                pss.wickets, pss.bowling_innings
            FROM player_season_stats pss
            JOIN seasons s ON pss.season_id = s.id
            JOIN players p ON pss.player_id = p.id
            -- Scope to this org's seasons. Without it, a dual-club player
            -- (shared CA participant GUID) could resolve their "latest season"
            -- form snapshot to another club's season (see migration 060).
            WHERE p.organisation_id = :org AND s.organisation_id = :org
            ORDER BY pss.player_id, s.year DESC NULLS LAST
            """
        ),
        {"org": org_id},
    )
    out: dict[str, dict] = {}
    for pid, bavg, runs, batt_inn, wkts, bowl_inn in rows.fetchall():
        out[str(pid)] = {
            "batting_average": bavg, "runs": runs, "batting_innings": batt_inn,
            "wickets": wkts, "bowling_innings": bowl_inn,
        }
    return out


async def assemble_selection(db: AsyncSession, club, fx) -> dict:
    """A fixture's lineup + the pickable pool with per-date availability,
    recency, squad tier, gender wall and a composite form score per player.

    Identical to the data BetterSelect's selection board is built from.
    """
    # Existing lineup for this fixture.
    lu_res = await db.execute(select(FixtureLineup).where(FixtureLineup.fixture_id == fx.id))
    lineup_rows = lu_res.scalars().all()
    lineup = {str(r.player_id): r for r in lineup_rows}

    months = club.dormancy_months if club.dormancy_months else DEFAULT_DORMANCY_MONTHS
    cutoff = months_ago(date.today(), months)

    # last_played per player (recency).
    last_played: dict[str, date] = {}
    lp_res = await db.execute(
        text(
            "SELECT ga.player_id, MAX(g.played_at) FROM game_appearances ga "
            "JOIN games g ON ga.game_id = g.id "
            "JOIN players p ON ga.player_id = p.id "
            "WHERE p.organisation_id = :org GROUP BY ga.player_id"
        ),
        {"org": club.id},
    )
    for pid, lp in lp_res.fetchall():
        last_played[str(pid)] = lp

    # Squads: manual membership unioned with recent appearance team-names.
    squads: dict[str, set] = {}
    sq_res = await db.execute(
        text(
            "SELECT DISTINCT ga.player_id, ga.team_name FROM game_appearances ga "
            "JOIN games g ON ga.game_id = g.id "
            "JOIN players p ON ga.player_id = p.id "
            "WHERE p.organisation_id = :org AND ga.team_name IS NOT NULL "
            "AND ga.team_name <> '' AND g.played_at >= :cutoff"
        ),
        {"org": club.id, "cutoff": cutoff},
    )
    for pid, name in sq_res.fetchall():
        squads.setdefault(str(pid), set()).add(name.strip())
    mem_res = await db.execute(
        text(
            "SELECT tm.player_id, t.name FROM team_members tm "
            "JOIN teams t ON tm.team_id = t.id "
            "WHERE tm.organisation_id = :org AND t.name IS NOT NULL AND t.name <> ''"
        ),
        {"org": club.id},
    )
    for pid, name in mem_res.fetchall():
        squads.setdefault(str(pid), set()).add(name.strip())

    # Availability for this fixture's playing date (explicit answer wins; period fallback).
    avail: dict[str, str] = {}
    avail_reason: dict[str, str] = {}
    if fx.played_on:
        av_res = await db.execute(
            text(
                "SELECT player_id, status FROM player_availability "
                "WHERE organisation_id = :org AND avail_date = :d"
            ),
            {"org": club.id, "d": fx.played_on},
        )
        for pid, status in av_res.fetchall():
            avail[str(pid)] = status
        period_map = await resolve_period_statuses(db, club.id, [fx.played_on])
        for pid, info in period_map.get(fx.played_on.isoformat(), {}).items():
            if pid not in avail:
                avail[pid] = info["status"]
                if info.get("reason"):
                    avail_reason[pid] = info["reason"]

    # Players already selected for ANOTHER fixture on the same date (clash).
    clash: dict[str, list] = {}
    if fx.played_on:
        cl_res = await db.execute(
            text(
                "SELECT fl.player_id, COALESCE(t.name, f.label, f.opponent_name) AS where_ "
                "FROM fixture_lineups fl "
                "JOIN fixtures f ON fl.fixture_id = f.id "
                "LEFT JOIN teams t ON f.team_id = t.id "
                "WHERE fl.organisation_id = :org AND f.id <> :fid "
                "AND f.played_on = :d"
            ),
            {"org": club.id, "fid": fx.id, "d": fx.played_on},
        )
        for pid, where_ in cl_res.fetchall():
            clash.setdefault(str(pid), []).append(where_ or "another fixture")

    pl_res = await db.execute(
        select(Player).where(Player.organisation_id == club.id, Player.is_player.is_(True))
    )
    players = pl_res.scalars().all()

    # Fixture's team sequence + grade gender, for autofill tier + gender wall.
    fx_team_seq: int | None = None
    if fx.team_id:
        fx_team_obj = await db.get(Team, fx.team_id)
        if fx_team_obj and (fx_team_obj.sequence or 0) > 0:
            fx_team_seq = fx_team_obj.sequence
    fx_is_women = False
    if fx.grade_id:
        fx_grade_obj = await db.get(Grade, fx.grade_id)
        if fx_grade_obj:
            fx_is_women = (fx_grade_obj.fee_format == "women")

    # Per-squad-team metadata: sequence + women's-grade flag.
    squad_meta: dict[str, tuple[int, bool]] = {}
    sq_meta_res = await db.execute(
        select(Team.id, Team.sequence, Grade.fee_format)
        .select_from(Team)
        .outerjoin(Grade, Team.grade_id == Grade.id)
        .where(Team.organisation_id == club.id)
    )
    for tid, seq, fee in sq_meta_res.fetchall():
        squad_meta[str(tid)] = (seq or 0, fee == "women")

    recent_bat = await _recent_batting_form(db, club.id)
    recent_bowl = await _recent_bowling_form(db, club.id)
    season_stats = await _latest_season_stats(db, club.id)

    autofill_cutoff = months_ago(date.today(), AUTOFILL_RECENCY_MONTHS)
    _fixture_team_id = str(fx.team_id) if fx.team_id else None

    pool = []
    for p in players:
        pid = str(p.id)
        lp = last_played.get(pid)
        dormant = bool(lp) and lp < cutoff
        manual_inactive = p.status == "inactive"
        sq_tid = str(p.squad_team_id) if p.squad_team_id else None
        sq_seq, sq_is_women = squad_meta.get(sq_tid, (0, False)) if sq_tid else (0, False)

        squad_match = bool(_fixture_team_id and sq_tid == _fixture_team_id)
        if fx_team_seq:
            tier = _tier_for(fx_team_seq, sq_seq)
        else:
            tier = 1 if squad_match else None

        gender_ok = (fx_is_women == sq_is_women)
        recent_ok = bool(lp) and lp >= autofill_cutoff
        score = _compute_score(p.skill_positions, recent_bat.get(pid), recent_bowl.get(pid), season_stats.get(pid))

        pool.append({
            "id": pid,
            "display_name": p.display_name,
            "player_role": p.player_role,
            "skill_positions": p.skill_positions or [],
            "squads": sorted(squads.get(pid, [])),
            "squad_team_id": sq_tid,
            "availability": avail.get(pid, "NO_RESPONSE"),
            "availability_reason": avail_reason.get(pid),
            "last_played": lp.isoformat() if lp else None,
            "photo_url": p.photo_url,
            "batting_hand": p.batting_hand,
            "bowling_action": p.bowling_action,
            "bowling_type": p.bowling_type,
            "is_opening_batsman": p.is_opening_batsman,
            "gender": p.gender,
            "is_dormant": dormant and not manual_inactive,
            "is_inactive": manual_inactive,
            "is_current": not manual_inactive and not dormant,
            "selected": pid in lineup,
            "clash": clash.get(pid, []),
            "squad_match": squad_match,
            "tier": tier,
            "gender_ok": gender_ok,
            "recent_ok": recent_ok,
            "score": round(score, 2),
            "autofill_eligible": bool(tier in (1, 2, 3) and recent_ok and gender_ok and not manual_inactive),
        })

    _AVAIL_RANK = {"AVAILABLE": 0, "MAYBE": 1, "NO_RESPONSE": 2, "UNAVAILABLE": 3}
    pool.sort(key=lambda e: (
        e["tier"] if e["tier"] is not None else 99,
        -(e["score"] or 0.0),
        _AVAIL_RANK.get(e["availability"], 9),
        (e["display_name"] or "").lower(),
    ))

    return {
        "fixture": {
            "id": str(fx.id),
            "label": fx.label,
            "opponent_name": fx.opponent_name,
            "home_away": fx.home_away,
            "played_on": fx.played_on.isoformat() if fx.played_on else None,
            "end_on": fx.end_on.isoformat() if fx.end_on else None,
            "start_time": fx.start_time,
            "round": fx.round,
            "venue": fx.venue,
            "home_team": fx.home_team,
            "away_team": fx.away_team,
            "team_id": str(fx.team_id) if fx.team_id else None,
            "grade_id": str(fx.grade_id) if fx.grade_id else None,
        },
        "lineup": [
            {
                "player_id": str(r.player_id),
                "batting_order": r.batting_order,
                "is_captain": r.is_captain,
                "is_wicket_keeper": r.is_wicket_keeper,
            }
            for r in sorted(lineup_rows, key=lambda r: (r.batting_order or 999))
        ],
        "pool": pool,
        "dormancy_months": months,
        "default_team_size": club.default_team_size if club.default_team_size is not None else 11,
    }
