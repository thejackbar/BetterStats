from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import uuid

from app.models.db import Game, Grade, Season, BattingInnings, BowlingSpell, FieldingStat, Player, get_db
from app.services.aggregations import get_game_fall_of_wickets, get_game_partnerships

router = APIRouter(prefix="/games", tags=["games"])


@router.get("")
async def list_games(
    org_id: str,
    season_id: Optional[str] = Query(None),
    grade_id: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
):
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

    games = []
    for game, grade, season in result.all():
        games.append({
            "id": str(game.id),
            "played_at": game.played_at.isoformat() if game.played_at else None,
            "home_team": game.home_team,
            "away_team": game.away_team,
            "result": game.result,
            "winning_team": game.winning_team,
            "grade": {"id": str(grade.id), "name": grade.name},
            "season": {"id": str(season.id), "name": season.name, "year": season.year},
        })
    return games


@router.get("/{game_id}/scorecard")
async def get_scorecard(game_id: str, db: AsyncSession = Depends(get_db)):
    game = await db.get(Game, uuid.UUID(game_id))
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Batting
    bat_result = await db.execute(
        select(BattingInnings, Player)
        .join(Player, Player.id == BattingInnings.player_id)
        .where(BattingInnings.game_id == uuid.UUID(game_id))
        .order_by(BattingInnings.batting_position)
    )
    batting = [
        {
            "player_id": str(p.id),
            "player_name": p.name,
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

    # Bowling
    bowl_result = await db.execute(
        select(BowlingSpell, Player)
        .join(Player, Player.id == BowlingSpell.player_id)
        .where(BowlingSpell.game_id == uuid.UUID(game_id))
        .order_by(BowlingSpell.wickets.desc())
    )
    bowling = [
        {
            "player_id": str(p.id),
            "player_name": p.name,
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

    # Fall of Wickets
    fow = await get_game_fall_of_wickets(db, game_id)

    # Partnerships
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
