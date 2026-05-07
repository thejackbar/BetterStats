from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import logging
import uuid

logger = logging.getLogger(__name__)

from app.models.db import Game, Grade, Season, Organisation, BattingInnings, BowlingSpell, FieldingStat, Player, get_db
from app.services.aggregations import get_game_fall_of_wickets, get_game_partnerships
from app.services import playhq_partner_client

router = APIRouter(prefix="/games", tags=["games"])


def _filter_by_season(games: list, season_obj) -> list:
    """Filter PlayHQ partner API games to those matching a DB Season.
    Tries exact name match first, falls back to year-range match so that
    cross-year seasons (e.g. Summer 2024/25 spans Oct 2024 – Mar 2025) still work.
    """
    name = (season_obj.name or "").strip().lower()
    by_name = [g for g in games if g.get("season", "").strip().lower() == name]
    if by_name:
        return by_name
    # Fallback: match by the season's start year — games played in year Y or Y+1
    year = season_obj.year
    if year:
        return [
            g for g in games
            if g.get("played_at", "")[:4] in (str(year), str(year + 1))
        ]
    return []


@router.get("")
async def list_games(
    org_id: str,
    season_id: Optional[str] = Query(None),
    grade_id: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organisation, uuid.UUID(org_id))
    if org and org.playhq_id:
        db_seasons_res = await db.execute(
            select(Season).where(Season.organisation_id == uuid.UUID(org_id))
        )
        db_seasons = [{"id": str(s.id), "name": s.name} for s in db_seasons_res.scalars().all()]
        all_games = await playhq_partner_client.get_org_games(org.playhq_id, org.name, db_seasons=db_seasons)
        recent = [g for g in all_games if g.get("status") == "FINAL" and g.get("played_at")]
        if season_id:
            season_obj = await db.get(Season, uuid.UUID(season_id))
            if season_obj:
                recent = _filter_by_season(recent, season_obj)
        if grade_id:
            grade_obj = await db.get(Grade, uuid.UUID(grade_id))
            if grade_obj:
                recent = [g for g in recent if (g.get("grade") or {}).get("name", "").strip().lower() == grade_obj.name.strip().lower()]
        recent.sort(key=lambda x: x["played_at"], reverse=True)
        return recent[:limit]

    # Fallback: DB query (empty for most installs until games are synced)
    query = (
        select(Game, Grade, Season)
        .join(Grade, Grade.id == Game.grade_id)
        .join(Season, Season.id == Grade.season_id)
        .where(Season.organisation_id == uuid.UUID(org_id))
    )
    if season_id:
        query = query.where(Season.id == uuid.UUID(season_id))
    if grade_id:
        query = query.where(Grade.id == uuid.UUID(grade_id))
    query = query.order_by(Game.played_at.desc()).limit(limit)
    result = await db.execute(query)
    return [
        {
            "id": str(game.id),
            "played_at": game.played_at.isoformat() if game.played_at else None,
            "home_team": game.home_team,
            "away_team": game.away_team,
            "result": game.result,
            "winning_team": game.winning_team,
            "grade": {"id": str(grade.id), "name": grade.name},
            "season": {"id": str(season.id), "name": season.name, "year": season.year},
        }
        for game, grade, season in result.all()
    ]


@router.get("/playhq/{playhq_game_id}")
async def get_playhq_game(
    playhq_game_id: str,
    org_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organisation, uuid.UUID(org_id))
    if not org or not org.playhq_id:
        raise HTTPException(status_code=404, detail="Organisation not found or no PlayHQ ID")
    db_seasons_res = await db.execute(
        select(Season).where(Season.organisation_id == org.id)
    )
    db_seasons = [{"id": str(s.id), "name": s.name} for s in db_seasons_res.scalars().all()]
    all_games = await playhq_partner_client.get_org_games(org.playhq_id, org.name, db_seasons=db_seasons)
    game = next((g for g in all_games if str(g.get("id", "")) == playhq_game_id), None)
    if not game:
        logger.warning(f"PlayHQ game {playhq_game_id!r} not found in {len(all_games)} games for org {org.id}")
        raise HTTPException(status_code=404, detail="Game not found")
    return game


@router.get("/playhq/{playhq_game_id}/scorecard")
async def get_playhq_scorecard(
    playhq_game_id: str,
    org_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organisation, uuid.UUID(org_id))
    if not org or not org.playhq_id:
        raise HTTPException(status_code=404, detail="Organisation not found or no PlayHQ ID")
    db_seasons_res = await db.execute(
        select(Season).where(Season.organisation_id == org.id)
    )
    db_seasons = [{"id": str(s.id), "name": s.name} for s in db_seasons_res.scalars().all()]
    all_games = await playhq_partner_client.get_org_games(org.playhq_id, org.name, db_seasons=db_seasons)
    matched = next((g for g in all_games if str(g.get("id", "")) == playhq_game_id), None)
    game_url = matched.get("url", "") if matched else ""
    try:
        scorecard = await playhq_partner_client.get_fixture_scorecard(playhq_game_id, game_url=game_url)
    except Exception as e:
        logger.warning(f"PlayHQ scorecard fetch failed for {playhq_game_id}: {e}")
        raise HTTPException(status_code=502, detail=f"PlayHQ scorecard unavailable: {e}")
    return scorecard


@router.get("/{game_id}/scorecard")
async def get_scorecard(game_id: str, db: AsyncSession = Depends(get_db)):
    game = await db.get(Game, uuid.UUID(game_id))
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Derive innings-team mapping from raw_payload if available
    innings_teams: dict[int, str] = {}
    if game.raw_payload:
        for inn in game.raw_payload.get("innings", []):
            inn_num = inn.get("inningsNumber", 1)
            team_name = (inn.get("team") or {}).get("name", "")
            if team_name:
                innings_teams[inn_num] = team_name

    # Batting — ordered by innings_number then batting_position
    bat_result = await db.execute(
        select(BattingInnings, Player)
        .join(Player, Player.id == BattingInnings.player_id)
        .where(BattingInnings.game_id == uuid.UUID(game_id))
        .order_by(BattingInnings.innings_number, BattingInnings.batting_position)
    )
    batting = [
        {
            "player_id": str(p.id),
            "player_name": p.name,
            "innings_number": bi.innings_number or 1,
            "runs": bi.runs,
            "balls": bi.balls,
            "fours": bi.fours,
            "sixes": bi.sixes,
            "strike_rate": float(bi.strike_rate) if bi.strike_rate else None,
            "dismissal_type": bi.dismissal_type,
            "not_out": bi.not_out,
            "batting_position": bi.batting_position,
        }
        for bi, p in bat_result.all()
    ]

    # Bowling — ordered by innings_number then wickets desc
    bowl_result = await db.execute(
        select(BowlingSpell, Player)
        .join(Player, Player.id == BowlingSpell.player_id)
        .where(BowlingSpell.game_id == uuid.UUID(game_id))
        .order_by(BowlingSpell.innings_number, BowlingSpell.wickets.desc())
    )
    bowling = [
        {
            "player_id": str(p.id),
            "player_name": p.name,
            "innings_number": bs.innings_number or 1,
            "overs": float(bs.overs) if bs.overs else None,
            "maidens": bs.maidens,
            "runs": bs.runs,
            "wickets": bs.wickets,
            "wides": bs.wides,
            "no_balls": bs.no_balls,
            "economy": float(bs.economy) if bs.economy else None,
        }
        for bs, p in bowl_result.all()
    ]

    # Fielding
    field_result = await db.execute(
        select(FieldingStat, Player)
        .join(Player, Player.id == FieldingStat.player_id)
        .where(FieldingStat.game_id == uuid.UUID(game_id))
    )
    fielding = [
        {
            "player_id": str(p.id),
            "player_name": p.name,
            "catches": fs.catches,
            "run_outs": fs.run_outs,
            "stumpings": fs.stumpings,
        }
        for fs, p in field_result.all()
    ]

    fow = await get_game_fall_of_wickets(db, game_id)
    partnerships = await get_game_partnerships(db, game_id)

    grade = await db.get(Grade, game.grade_id)
    season = await db.get(Season, grade.season_id) if grade else None

    return {
        "id": str(game.id),
        "played_at": game.played_at.isoformat() if game.played_at else None,
        "home_team": game.home_team,
        "away_team": game.away_team,
        "result": game.result,
        "winning_team": game.winning_team,
        "innings_teams": innings_teams,
        "grade": {"id": str(grade.id), "name": grade.name} if grade else None,
        "season": {"id": str(season.id), "name": season.name} if season else None,
        "batting": batting,
        "bowling": bowling,
        "fielding": fielding,
        "fall_of_wickets": [
            {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in row.items()}
            for row in fow
        ],
        "partnerships": [
            {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in row.items()}
            for row in partnerships
        ],
    }
