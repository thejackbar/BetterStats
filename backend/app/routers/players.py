from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func
from pydantic import BaseModel
from typing import Optional
import uuid

from app.models.db import (
    Player, User, PlayerSyncRequest, Team,
    BattingInnings, BowlingSpell, FieldingStat, Game,
    Fixture, FixtureLineup, PlayerAvailability, get_db,
)
from app.routers.auth import get_current_user
from app.auth.capabilities import require_cap, MANAGE_PLAYERS
from app.services.aggregations import (
    get_career_batting, get_career_bowling, get_career_fielding,
    get_career_batting_from_innings, get_career_bowling_from_spells, get_career_fielding_from_stats,
    get_player_batting_innings, get_player_bowling_spells,
    get_dismissal_breakdown, get_batting_by_position, get_batting_by_grade,
    get_bowling_by_grade, get_player_team_breakdown,
    get_bowling_dismissal_breakdown, get_bowling_by_batter_position,
    get_season_by_season, get_player_milestones, get_player_partnerships,
    get_player_activity, get_upcoming_milestones_for_org,
    get_player_rankings, get_player_by_venue, get_player_by_opposition,
)
from app.services.milestone_rules import (
    crossed_thresholds, is_displayable, next_threshold, reach_window,
)

router = APIRouter(prefix="/players", tags=["players"])


def _str_keys(d: dict | None) -> dict | None:
    if not d:
        return d
    return {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in d.items()}


@router.get("")
async def list_players(
    org_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Player)
        .where(Player.organisation_id == uuid.UUID(org_id))
        .order_by(func.coalesce(Player.display_name_override, Player.name))
    )
    players = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "display_name": p.display_name,
            "claimed": p.claimed,
            "photo_url": p.photo_url,
            "player_role": p.player_role,
        }
        for p in players
    ]


@router.get("/{player_id}")
async def get_player(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return {
        "id": str(player.id),
        "name": player.name,
        "display_name": player.display_name,
        "organisation_id": str(player.organisation_id),
        "claimed": player.claimed,
        "playhq_id": player.playhq_id,
        "is_overseas": player.is_overseas,
        "overseas_country": player.overseas_country,
    }


@router.get("/{player_id}/stats")
async def get_player_stats(
    player_id: str,
    season_id: Optional[str] = Query(None),
    grade_id: Optional[str] = Query(None),
    last_n_games: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    use_game_filter = last_n_games or start_date or end_date
    if use_game_filter:
        try:
            batting = await get_career_batting_from_innings(db, player_id, last_n_games, start_date, end_date)
            bowling = await get_career_bowling_from_spells(db, player_id, last_n_games, start_date, end_date)
            fielding = await get_career_fielding_from_stats(db, player_id, last_n_games, start_date, end_date)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Stats query failed: {exc}")
    else:
        batting = await get_career_batting(db, player_id, season_id)
        bowling = await get_career_bowling(db, player_id, season_id)
        fielding = await get_career_fielding(db, player_id, season_id)
    batting_innings = await get_player_batting_innings(db, player_id, season_id, grade_id)
    bowling_spells = await get_player_bowling_spells(db, player_id, season_id, grade_id)

    return {
        "player": {"id": str(player.id), "name": player.name, "display_name": player.display_name, "claimed": player.claimed, "organisation_id": str(player.organisation_id), "playhq_id": player.playhq_id, "photo_url": player.photo_url, "is_overseas": player.is_overseas, "overseas_country": player.overseas_country},
        "career_batting": _str_keys(batting),
        "career_bowling": _str_keys(bowling),
        "career_fielding": _str_keys(fielding),
        "batting_innings": [_str_keys(i) for i in batting_innings],
        "bowling_spells": [_str_keys(s) for s in bowling_spells],
    }


@router.get("/{player_id}/dismissals")
async def get_player_dismissals(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await get_dismissal_breakdown(db, player_id)


@router.get("/{player_id}/by-position")
async def get_player_by_position(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await get_batting_by_position(db, player_id)


@router.get("/{player_id}/by-grade")
async def get_player_by_grade(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await get_batting_by_grade(db, player_id, str(player.organisation_id))


@router.get("/{player_id}/bowling-by-grade")
async def get_player_bowling_by_grade(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await get_bowling_by_grade(db, player_id, str(player.organisation_id))


@router.get("/{player_id}/bowling-dismissals")
async def get_player_bowling_dismissals(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await get_bowling_dismissal_breakdown(db, player_id)


@router.get("/{player_id}/bowling-by-batter-position")
async def get_player_bowling_by_batter_position(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await get_bowling_by_batter_position(db, player_id)


@router.get("/{player_id}/by-venue")
async def get_player_by_venue_endpoint(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await get_player_by_venue(db, player_id)


@router.get("/{player_id}/by-opposition")
async def get_player_by_opposition_endpoint(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await get_player_by_opposition(db, player_id)


@router.get("/{player_id}/team-breakdown")
async def get_player_team_breakdown_endpoint(
    player_id: str,
    season_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await get_player_team_breakdown(
        db, player_id, str(player.organisation_id), season_id
    )


@router.get("/{player_id}/rankings")
async def get_player_rankings_endpoint(
    player_id: str,
    season_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await get_player_rankings(db, player_id, str(player.organisation_id), season_id)


@router.get("/{player_id}/seasons")
async def get_player_seasons(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await get_season_by_season(db, player_id)


@router.get("/{player_id}/milestones")
async def get_player_milestones_endpoint(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    rows = await get_player_milestones(db, player_id)
    # Filter out pre-existing rows that don't match the current threshold scheme
    # (10/25 matches, 100/250 runs, etc.) — they stay in the DB, just hidden.
    milestones = [
        _str_keys(r) for r in rows
        if is_displayable(r["milestone_type"], r["milestone_value"])
    ]

    # Append computed per-grade match milestones (not stored in DB).
    breakdown = await get_player_team_breakdown(db, player_id, str(player.organisation_id))
    grade_rows = sorted(breakdown.get("rows", []), key=lambda r: r.get("grade_name") or "")
    for row in grade_rows:
        matches_in_grade = int(row.get("matches") or 0)
        grade_name = row.get("grade_name")
        if not grade_name:
            continue
        for threshold in crossed_thresholds("grade_matches", matches_in_grade):
            milestones.append({
                "id": None,
                "milestone_type": "grade_matches",
                "milestone_value": threshold,
                "achieved_at": None,
                "detail": grade_name,
                "game_id": None,
            })

    return milestones


@router.get("/{player_id}/partnerships")
async def get_player_partnerships_endpoint(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    rows = await get_player_partnerships(db, player_id)
    return [_str_keys(r) for r in rows]


@router.get("/{player_id}/activity")
async def get_player_activity_endpoint(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await get_player_activity(db, player_id)


@router.get("/{player_id}/upcoming-milestones")
async def get_player_upcoming_milestones(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    agg_res = await db.execute(
        text("""
            SELECT
                COALESCE(SUM(runs), 0)    AS total_runs,
                COALESCE(SUM(wickets), 0) AS total_wickets,
                COALESCE(SUM(matches), 0) AS total_matches,
                COALESCE(SUM(catches), 0) AS total_catches
            FROM player_season_stats WHERE player_id=:pid
        """),
        {"pid": player_id}
    )
    agg = dict(agg_res.mappings().first() or {})
    totals = {
        "runs":    int(agg.get("total_runs")    or 0),
        "wickets": int(agg.get("total_wickets") or 0),
        "matches": int(agg.get("total_matches") or 0),
        "catches": int(agg.get("total_catches") or 0),
    }

    upcoming = []
    for mt, current in totals.items():
        target = next_threshold(mt, current)
        if target is None:
            continue
        needed = target - current
        if needed > reach_window(mt, target):
            continue
        upcoming.append({"type": mt, "current": current, "target": target, "needed": needed})

    # Per-grade match milestones — uses the same merge-aware breakdown the
    # Team tab does so canonical/merged grade names line up.
    breakdown = await get_player_team_breakdown(db, player_id, str(player.organisation_id))
    for row in breakdown.get("rows", []):
        matches_in_grade = int(row.get("matches") or 0)
        grade_name = row.get("grade_name")
        if not grade_name or matches_in_grade <= 0:
            continue
        target = next_threshold("grade_matches", matches_in_grade)
        if target is None:
            continue
        needed = target - matches_in_grade
        if needed > reach_window("grade_matches", target):
            continue
        upcoming.append({
            "type": "matches",
            "current": matches_in_grade,
            "target": target,
            "needed": needed,
            "label": f"MATCHES — {grade_name}",
            "grade_name": grade_name,
        })

    upcoming.sort(key=lambda m: m.get("needed", 9999))
    return upcoming


@router.get("/{player_id}/captain-stats")
async def get_player_captain_stats(player_id: str, db: AsyncSession = Depends(get_db)):
    pid = uuid.UUID(player_id)

    summary_res = await db.execute(text("""
        SELECT
            COUNT(DISTINCT ga.game_id) AS games_captained,
            SUM(CASE WHEN g.result = 'WIN' THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN g.result = 'LOSS' THEN 1 ELSE 0 END) AS losses,
            SUM(CASE WHEN g.result IS NULL OR g.result NOT IN ('WIN', 'LOSS') THEN 1 ELSE 0 END) AS draws
        FROM game_appearances ga
        JOIN v_effective_games g ON g.id = ga.game_id
        WHERE ga.player_id = :pid AND ga.is_captain = TRUE
    """), {"pid": pid})
    summary = dict(summary_res.mappings().first() or {})

    bat_cap_res = await db.execute(text("""
        SELECT
            COUNT(*) AS innings,
            COALESCE(SUM(bi.runs), 0) AS runs,
            MAX(bi.runs) AS high_score,
            ROUND(SUM(bi.runs)::numeric / NULLIF(COUNT(*) - SUM(bi.not_out::int), 0), 2) AS average,
            SUM(CASE WHEN bi.runs >= 50 AND bi.runs < 100 THEN 1 ELSE 0 END) AS fifties,
            SUM(CASE WHEN bi.runs >= 100 THEN 1 ELSE 0 END) AS hundreds
        FROM v_effective_batting_innings bi
        JOIN game_appearances ga ON ga.game_id = bi.game_id AND ga.player_id = bi.player_id AND ga.is_captain = TRUE
        WHERE bi.player_id = :pid
          AND NOT COALESCE(bi.did_not_bat, FALSE)
          AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
    """), {"pid": pid})
    bat_cap = dict(bat_cap_res.mappings().first() or {})

    bat_not_res = await db.execute(text("""
        SELECT
            COUNT(*) AS innings,
            COALESCE(SUM(bi.runs), 0) AS runs,
            MAX(bi.runs) AS high_score,
            ROUND(SUM(bi.runs)::numeric / NULLIF(COUNT(*) - SUM(bi.not_out::int), 0), 2) AS average,
            SUM(CASE WHEN bi.runs >= 50 AND bi.runs < 100 THEN 1 ELSE 0 END) AS fifties,
            SUM(CASE WHEN bi.runs >= 100 THEN 1 ELSE 0 END) AS hundreds
        FROM v_effective_batting_innings bi
        LEFT JOIN game_appearances ga ON ga.game_id = bi.game_id AND ga.player_id = bi.player_id AND ga.is_captain = TRUE
        WHERE bi.player_id = :pid
          AND NOT COALESCE(bi.did_not_bat, FALSE)
          AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
          AND ga.game_id IS NULL
    """), {"pid": pid})
    bat_not = dict(bat_not_res.mappings().first() or {})

    bowl_cap_res = await db.execute(text("""
        SELECT
            COUNT(DISTINCT bs.game_id) AS games,
            COALESCE(SUM(bs.wickets), 0) AS wickets,
            ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.wickets), 0), 2) AS average,
            ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.overs), 0), 2) AS economy
        FROM v_effective_bowling_spells bs
        JOIN game_appearances ga ON ga.game_id = bs.game_id AND ga.player_id = bs.player_id AND ga.is_captain = TRUE
        WHERE bs.player_id = :pid
    """), {"pid": pid})
    bowl_cap = dict(bowl_cap_res.mappings().first() or {})

    bowl_not_res = await db.execute(text("""
        SELECT
            COUNT(DISTINCT bs.game_id) AS games,
            COALESCE(SUM(bs.wickets), 0) AS wickets,
            ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.wickets), 0), 2) AS average,
            ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.overs), 0), 2) AS economy
        FROM v_effective_bowling_spells bs
        LEFT JOIN game_appearances ga ON ga.game_id = bs.game_id AND ga.player_id = bs.player_id AND ga.is_captain = TRUE
        WHERE bs.player_id = :pid
          AND ga.game_id IS NULL
    """), {"pid": pid})
    bowl_not = dict(bowl_not_res.mappings().first() or {})

    by_season_res = await db.execute(text("""
        WITH captain_games AS (
            SELECT ga.game_id, g.result, s.name AS season_name, s.year AS season_year
            FROM game_appearances ga
            JOIN v_effective_games g ON g.id = ga.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE ga.player_id = :pid AND ga.is_captain = TRUE
        ),
        bat_per_game AS (
            SELECT bi.game_id, SUM(bi.runs) AS runs, COUNT(*) AS innings,
                   SUM(bi.not_out::int) AS not_outs
            FROM v_effective_batting_innings bi
            WHERE bi.player_id = :pid
              AND bi.game_id IN (SELECT game_id FROM captain_games)
              AND NOT COALESCE(bi.did_not_bat, FALSE)
              AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
            GROUP BY bi.game_id
        ),
        bowl_per_game AS (
            SELECT bs.game_id, SUM(bs.wickets) AS wickets, SUM(bs.runs) AS bowl_runs
            FROM v_effective_bowling_spells bs
            WHERE bs.player_id = :pid
              AND bs.game_id IN (SELECT game_id FROM captain_games)
            GROUP BY bs.game_id
        )
        SELECT
            cg.season_name,
            cg.season_year,
            COUNT(cg.game_id) AS games_captained,
            SUM(CASE WHEN cg.result = 'WIN' THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN cg.result = 'LOSS' THEN 1 ELSE 0 END) AS losses,
            SUM(CASE WHEN cg.result IS NULL OR cg.result NOT IN ('WIN', 'LOSS') THEN 1 ELSE 0 END) AS draws,
            COALESCE(SUM(bat.runs), 0) AS batting_runs,
            COALESCE(SUM(bat.innings), 0) AS batting_innings,
            ROUND(SUM(bat.runs)::numeric / NULLIF(SUM(bat.innings) - SUM(bat.not_outs), 0), 2) AS batting_avg,
            COALESCE(SUM(bowl.wickets), 0) AS bowling_wickets,
            ROUND(SUM(bowl.bowl_runs)::numeric / NULLIF(SUM(bowl.wickets), 0), 2) AS bowling_avg
        FROM captain_games cg
        LEFT JOIN bat_per_game bat ON bat.game_id = cg.game_id
        LEFT JOIN bowl_per_game bowl ON bowl.game_id = cg.game_id
        GROUP BY cg.season_name, cg.season_year
        ORDER BY cg.season_year DESC NULLS LAST
    """), {"pid": pid})
    by_season = [dict(r) for r in by_season_res.mappings()]
    for row in by_season:
        row["season_year"] = row.get("season_year")

    return {
        "summary": summary,
        "batting_as_captain": bat_cap,
        "batting_not_captain": bat_not,
        "bowling_as_captain": bowl_cap,
        "bowling_not_captain": bowl_not,
        "by_season": by_season,
    }


class SyncRequestCreate(BaseModel):
    note: Optional[str] = None


@router.post("/{player_id}/request-sync")
async def request_player_sync(
    player_id: str,
    body: SyncRequestCreate = SyncRequestCreate(),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Prevent duplicate pending requests
    existing = await db.execute(
        text("""
            SELECT id FROM player_sync_requests
            WHERE player_id = :pid AND status = 'pending'
            LIMIT 1
        """),
        {"pid": player_id},
    )
    if existing.fetchone():
        return {"status": "already_pending"}

    req = PlayerSyncRequest(
        player_id=player.id,
        org_id=player.organisation_id,
        requester_note=body.note,
        status="pending",
    )
    db.add(req)
    await db.commit()
    return {"status": "requested"}


class PlayerRename(BaseModel):
    name: str


@router.patch("/{player_id}")
async def rename_player(
    player_id: str,
    body: PlayerRename,
    db: AsyncSession = Depends(get_db),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    old_name = player.name
    player.name = name
    # Keep player_achievements rows in sync for unlinked records
    await db.execute(
        text("UPDATE player_achievements SET player_name = :new WHERE player_id = :pid"),
        {"new": name, "pid": player_id},
    )
    await db.commit()
    return {"status": "renamed", "old_name": old_name, "new_name": name}


class PlayerProfileUpdate(BaseModel):
    # All editable management fields. Callers (the legacy modal and the new
    # BetterSelect Players screen) send a subset — only provided fields update.
    display_name_override: Optional[str] = None
    player_role: Optional[str] = None
    skill_positions: Optional[list[str]] = None  # e.g. ["BAT", "WKT"]
    batting_hand: Optional[str] = None
    bowling_action: Optional[str] = None
    bowling_type: Optional[str] = None
    is_opening_batsman: Optional[bool] = None
    gender: Optional[str] = None
    is_player: Optional[bool] = None
    status: Optional[str] = None                  # active | inactive
    email: Optional[str] = None
    phone: Optional[str] = None
    squad_team_id: Optional[str] = None
    is_overseas: Optional[bool] = None
    overseas_country: Optional[str] = None


def _profile_fields(player: Player) -> dict:
    """The editable management fields, shared by GET and PATCH responses."""
    return {
        "id": str(player.id),
        "name": player.name,
        "display_name": player.display_name,
        "display_name_override": player.display_name_override,
        "player_role": player.player_role,
        "skill_positions": player.skill_positions or [],
        "batting_hand": player.batting_hand,
        "bowling_action": player.bowling_action,
        "bowling_type": player.bowling_type,
        "is_opening_batsman": player.is_opening_batsman,
        "gender": player.gender,
        "is_player": player.is_player,
        "status": player.status,
        "email": player.email,
        "phone": player.phone,
        "photo_url": player.photo_url,
        "playhq_id": player.playhq_id,
        "squad_team_id": str(player.squad_team_id) if player.squad_team_id else None,
        "is_overseas": player.is_overseas,
        "overseas_country": player.overseas_country,
    }


async def _squad_obj(db: AsyncSession, player: Player) -> Optional[dict]:
    """The player's assigned selection-pool team as {id, name}, or None."""
    if not player.squad_team_id:
        return None
    try:
        team = await db.get(Team, player.squad_team_id)
        if team:
            return {"id": str(team.id), "name": team.name}
    except Exception:
        pass
    return None


def _fmt_date_label(d) -> str:
    try:
        return d.strftime("%a %-d %b")
    except Exception:
        return d.isoformat() if d else ""


async def _snapshot(db: AsyncSession, player: Player) -> dict:
    """Selection-relevant signal for the profile panel.

    Every piece is wrapped in try/except and defaults to []/0/None so a schema
    mismatch on any stats table never 500s the whole profile.
    """
    snap = {
        "availability_next": [],
        "recent_batting": [],
        "recent_bowling": [],
        "season_catches": 0,
        "last_picked": None,
    }

    # availability_next — next ~4 upcoming fixture dates with this player's
    # recorded status (same source the matrix uses: Fixture.played_on, joined to
    # PlayerAvailability on avail_date). Defaults to NO_RESPONSE.
    try:
        from datetime import date as _date
        fx_res = await db.execute(
            select(Fixture.played_on)
            .where(
                Fixture.organisation_id == player.organisation_id,
                Fixture.played_on.isnot(None),
                Fixture.played_on >= _date.today(),
            )
            .order_by(Fixture.played_on.asc())
        )
        dates = []
        for (d,) in fx_res.all():
            if d and d not in dates:
                dates.append(d)
            if len(dates) >= 4:
                break
        if dates:
            av_res = await db.execute(
                select(PlayerAvailability.avail_date, PlayerAvailability.status).where(
                    PlayerAvailability.player_id == player.id,
                    PlayerAvailability.avail_date.in_(dates),
                )
            )
            by_date = {d: s for (d, s) in av_res.all()}
            snap["availability_next"] = [
                {
                    "date": d.isoformat(),
                    "label": _fmt_date_label(d),
                    "status": by_date.get(d, "NO_RESPONSE"),
                }
                for d in dates
            ]
    except Exception:
        snap["availability_next"] = []

    # recent_batting — last 5 scores, most-recent-first (by game date).
    try:
        b_res = await db.execute(
            select(BattingInnings.runs)
            .join(Game, Game.id == BattingInnings.game_id)
            .where(BattingInnings.player_id == player.id)
            .order_by(Game.played_at.desc().nullslast(), BattingInnings.id.desc())
            .limit(5)
        )
        snap["recent_batting"] = [int(r or 0) for (r,) in b_res.all()]
    except Exception:
        snap["recent_batting"] = []

    # recent_bowling — last 5 {wickets, runs}, most-recent-first.
    try:
        bw_res = await db.execute(
            select(BowlingSpell.wickets, BowlingSpell.runs)
            .join(Game, Game.id == BowlingSpell.game_id)
            .where(BowlingSpell.player_id == player.id)
            .order_by(Game.played_at.desc().nullslast(), BowlingSpell.id.desc())
            .limit(5)
        )
        snap["recent_bowling"] = [
            {"wickets": int(w or 0), "runs": int(r or 0)} for (w, r) in bw_res.all()
        ]
    except Exception:
        snap["recent_bowling"] = []

    # season_catches — total catches across recorded fielding rows.
    try:
        c_res = await db.execute(
            select(func.coalesce(func.sum(FieldingStat.catches), 0)).where(
                FieldingStat.player_id == player.id
            )
        )
        snap["season_catches"] = int(c_res.scalar() or 0)
    except Exception:
        snap["season_catches"] = 0

    # last_picked — most recent fixture this player was named in.
    try:
        lp_res = await db.execute(
            select(Fixture.round, Fixture.opponent_name, Fixture.played_on)
            .join(FixtureLineup, FixtureLineup.fixture_id == Fixture.id)
            .where(FixtureLineup.player_id == player.id)
            .order_by(Fixture.played_on.desc().nullslast())
            .limit(1)
        )
        row = lp_res.first()
        if row:
            rnd, opp, played = row
            snap["last_picked"] = {
                "round": rnd,
                "opponent": opp,
                "date": played.isoformat() if played else None,
            }
    except Exception:
        snap["last_picked"] = None

    return snap


async def _full_profile(db: AsyncSession, player: Player) -> dict:
    data = _profile_fields(player)
    data["squad"] = await _squad_obj(db, player)
    data["snapshot"] = await _snapshot(db, player)
    return data


@router.get("/{player_id}/profile")
async def get_player_profile(
    player_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_cap(MANAGE_PLAYERS)),
):
    """All editable management fields + assigned squad + selection snapshot."""
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await _full_profile(db, player)


@router.patch("/{player_id}/profile")
async def update_player_profile(
    player_id: str,
    body: PlayerProfileUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_cap(MANAGE_PLAYERS)),
):
    """Update admin-managed player attributes; returns the same shape as GET."""
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in (None, "active", "inactive"):
        raise HTTPException(status_code=400, detail="status must be 'active' or 'inactive'")
    # squad_team_id arrives as a string (or None to unassign) — coerce to UUID.
    if "squad_team_id" in data:
        val = data.pop("squad_team_id")
        player.squad_team_id = uuid.UUID(val) if val else None
    for key, value in data.items():
        setattr(player, key, value)
    await db.commit()
    await db.refresh(player)
    return await _full_profile(db, player)


@router.post("/{player_id}/claim")
async def claim_player_profile(
    player_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    if player.claimed:
        raise HTTPException(status_code=409, detail="Profile already claimed")

    player.claimed = True
    player.user_id = current_user.id
    await db.commit()
    return {"status": "claimed", "player_id": player_id}
