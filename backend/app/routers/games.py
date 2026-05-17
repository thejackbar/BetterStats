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


async def _enrich_scorecard_player_ids(
    scorecard: dict,
    org: Organisation,
    db: AsyncSession,
) -> None:
    """Add player_id to batting/bowling rows whose playhq_appearance_id matches a DB Player."""
    appearance_ids = set()
    for innings in (scorecard.get("innings") or []):
        for row in innings.get("batting", []) + innings.get("bowling", []):
            if row.get("playhq_appearance_id"):
                appearance_ids.add(row["playhq_appearance_id"])
    if not appearance_ids:
        return
    result = await db.execute(
        select(Player).where(
            Player.organisation_id == org.id,
            Player.playhq_id.in_(appearance_ids),
        )
    )
    playhq_to_db: dict[str, str] = {p.playhq_id: str(p.id) for p in result.scalars().all()}
    for innings in (scorecard.get("innings") or []):
        for row in innings.get("batting", []) + innings.get("bowling", []):
            phq_id = row.get("playhq_appearance_id")
            if phq_id:
                row["player_id"] = playhq_to_db.get(phq_id)


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
        all_games = await playhq_partner_client.get_org_games(org.playhq_id, org.name, db_seasons=db_seasons, grassroots_org_id=str(org.id))
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
            "grade": {"id": str(grade.id), "name": grade.display_name, "raw_name": grade.name},
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
    all_games = await playhq_partner_client.get_org_games(org.playhq_id, org.name, db_seasons=db_seasons, grassroots_org_id=str(org.id))
    game = next((g for g in all_games if str(g.get("id", "")) == playhq_game_id), None)
    if not game:
        logger.warning(f"PlayHQ game {playhq_game_id!r} not found in {len(all_games)} games for org {org.id}")
        raise HTTPException(status_code=404, detail="Game not found")
    return game


@router.get("/playhq/{playhq_game_id}/scorecard/debug")
async def debug_playhq_scorecard(
    playhq_game_id: str,
    org_id: str = Query(...),
):
    """Return raw PlayHQ REST period/team structure alongside parsed innings count."""
    from app.services.playhq_partner_client import BASE_URL, _get, _parse_summary_rest
    try:
        raw = await _get(f"{BASE_URL}/v2/games/{playhq_game_id}/summary")
    except Exception as e:
        return {"error": str(e), "fixture_id": playhq_game_id, "hint": "PlayHQ API call failed — check fixture ID is a PlayHQ game ID, not an internal DB UUID"}
    data = raw.get("data") or {}
    if not data:
        return {"error": "PlayHQ returned empty data", "raw_keys": list(raw.keys()), "fixture_id": playhq_game_id}
    periods_summary = [
        {
            "name": p.get("name"),
            "teams": [
                {"id": t.get("id"), "name": t.get("name"), "discipline": t.get("discipline")}
                for t in (p.get("teams") or [])
            ],
        }
        for p in (data.get("periods") or [])
    ]
    try:
        parsed = _parse_summary_rest(data)
    except Exception as e:
        parsed = {"innings": [], "parse_error": str(e)}
    return {
        "fixture_id": playhq_game_id,
        "periods_count": len(periods_summary),
        "periods": periods_summary,
        "teams_top_level": [{"id": t.get("id"), "name": t.get("name")} for t in (data.get("teams") or [])],
        "parsed_innings_count": len(parsed.get("innings", [])),
        "parsed_innings": [
            {"innings_number": inn["innings_number"], "batting_team": inn["batting_team"], "bowling_team": inn["bowling_team"], "batting_rows": len(inn["batting"]), "bowling_rows": len(inn["bowling"])}
            for inn in parsed.get("innings", [])
        ],
        "parse_error": parsed.get("parse_error"),
    }


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
    all_games = await playhq_partner_client.get_org_games(org.playhq_id, org.name, db_seasons=db_seasons, grassroots_org_id=str(org.id))
    matched = next((g for g in all_games if str(g.get("id", "")) == playhq_game_id), None)
    game_url = matched.get("url", "") if matched else ""
    try:
        scorecard = await playhq_partner_client.get_fixture_scorecard(playhq_game_id, game_url=game_url)
        await _enrich_scorecard_player_ids(scorecard, org, db)
    except Exception as e:
        logger.warning(f"PlayHQ scorecard fetch failed for {playhq_game_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Scorecard unavailable: {e}")

    # Flatten innings-nested structure into the same shape the frontend expects
    batting_flat = []
    bowling_flat = []
    innings_totals: dict[int, dict] = {}
    for inn in (scorecard.get("innings") or []):
        n = inn.get("innings_number", 1)
        innings_totals[n] = {
            "runs": inn.get("total_runs"),
            "wickets": inn.get("total_wickets"),
            "batting_team": inn.get("batting_team", ""),
        }
        for row in (inn.get("batting") or []):
            batting_flat.append({
                "innings_number": n,
                "player_id": row.get("player_id"),
                "player_name": row.get("name"),
                "runs": row.get("runs"),
                "balls": row.get("balls"),
                "fours": row.get("fours"),
                "sixes": row.get("sixes"),
                "strike_rate": row.get("strike_rate"),
                "dismissal_type": row.get("how_out"),
                "not_out": row.get("not_out", False),
            })
        for row in (inn.get("bowling") or []):
            bowling_flat.append({
                "innings_number": n,
                "player_id": row.get("player_id"),
                "player_name": row.get("name"),
                "overs": row.get("overs"),
                "maidens": row.get("maidens"),
                "runs": row.get("runs"),
                "wickets": row.get("wickets"),
                "wides": row.get("wides"),
                "no_balls": row.get("no_balls"),
                "economy": row.get("economy"),
            })

    meta = matched or {}
    return {
        "id": playhq_game_id,
        "home_team": meta.get("home_team"),
        "away_team": meta.get("away_team"),
        "played_at": meta.get("played_at"),
        "result": meta.get("result"),
        "winning_team": meta.get("winning_team"),
        "grade": meta.get("grade"),
        "season": meta.get("season"),
        "innings_totals": innings_totals,
        "batting": batting_flat,
        "bowling": bowling_flat,
        "fielding": [],
        "fall_of_wickets": scorecard.get("fall_of_wickets") or [],
        "partnerships": scorecard.get("partnerships") or [],
    }


@router.get("/{game_id}/scorecard")
async def get_scorecard(
    game_id: str,
    db: AsyncSession = Depends(get_db),
):
    game = await db.get(Game, uuid.UUID(game_id))
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    grade = await db.get(Grade, game.grade_id) if game.grade_id else None
    season = await db.get(Season, grade.season_id) if grade else None

    # Batting with player names via join
    batting_res = await db.execute(
        select(BattingInnings, Player)
        .outerjoin(Player, Player.id == BattingInnings.player_id)
        .where(BattingInnings.game_id == game.id)
        .order_by(BattingInnings.innings_number, BattingInnings.batting_position)
    )
    batting_rows = batting_res.all()

    # Bowling with player names via join
    bowling_res = await db.execute(
        select(BowlingSpell, Player)
        .outerjoin(Player, Player.id == BowlingSpell.player_id)
        .where(BowlingSpell.game_id == game.id)
        .order_by(BowlingSpell.innings_number)
    )
    bowling_rows = bowling_res.all()

    # Fielding with player names via join
    fielding_res = await db.execute(
        select(FieldingStat, Player)
        .outerjoin(Player, Player.id == FieldingStat.player_id)
        .where(FieldingStat.game_id == game.id)
    )
    fielding_rows = fielding_res.all()

    # Build innings summary map (totals per innings)
    innings_meta: dict[int, dict] = {}
    for bi, p in batting_rows:
        n = bi.innings_number or 1
        if n not in innings_meta:
            innings_meta[n] = {"batting_team": None, "bowling_team": None}

    batting_flat = [
        {
            "innings_number": bi.innings_number or 1,
            "player_id": str(bi.player_id) if bi.player_id else None,
            "player_name": p.display_name if p else None,
            "runs": bi.runs,
            "balls": bi.balls,
            "fours": bi.fours,
            "sixes": bi.sixes,
            "strike_rate": float(bi.strike_rate) if bi.strike_rate is not None else None,
            "dismissal_type": bi.dismissal_type,
            "not_out": bi.not_out,
            "batting_position": bi.batting_position,
            "did_not_bat": bool(bi.did_not_bat),
        }
        for bi, p in batting_rows
    ]

    bowling_flat = [
        {
            "innings_number": bs.innings_number or 1,
            "player_id": str(bs.player_id) if bs.player_id else None,
            "player_name": p.display_name if p else None,
            "overs": float(bs.overs) if bs.overs is not None else None,
            "maidens": bs.maidens,
            "runs": bs.runs,
            "wickets": bs.wickets,
            "wides": bs.wides,
            "no_balls": bs.no_balls,
            "economy": float(bs.economy) if bs.economy is not None else None,
        }
        for bs, p in bowling_rows
    ]

    fielding_flat = [
        {
            "player_id": str(fs.player_id) if fs.player_id else None,
            "player_name": p.display_name if p else None,
            "catches": fs.catches,
            "run_outs": fs.run_outs,
            "stumpings": fs.stumpings,
        }
        for fs, p in fielding_rows
        if (fs.catches or 0) + (fs.run_outs or 0) + (fs.stumpings or 0) > 0
    ]

    # Derive innings totals from batting data for the summary strip
    innings_totals: dict[int, dict] = {}
    for row in batting_flat:
        if row["did_not_bat"]:
            continue
        n = row["innings_number"]
        if n not in innings_totals:
            innings_totals[n] = {"runs": 0, "wickets": 0, "extras": 0, "team": None}
        innings_totals[n]["runs"] += row["runs"] or 0
        if not row["not_out"] and row["dismissal_type"]:
            innings_totals[n]["wickets"] += 1

    # Add extras (wides + no-balls) from bowling per innings
    for row in bowling_flat:
        n = row["innings_number"]
        if n not in innings_totals:
            innings_totals[n] = {"runs": 0, "wickets": 0, "extras": 0, "team": None}
        innings_totals[n].setdefault("extras", 0)
        innings_totals[n]["extras"] += (row["wides"] or 0) + (row["no_balls"] or 0)

    fow = await get_game_fall_of_wickets(db, game.id)
    partnerships = await get_game_partnerships(db, game.id)

    return {
        "id": str(game.id),
        "home_team": game.home_team,
        "away_team": game.away_team,
        "played_at": game.played_at.isoformat() if game.played_at else None,
        "result": game.result,
        "winning_team": game.winning_team,
        "grade": {"id": str(grade.id), "name": grade.display_name, "raw_name": grade.name} if grade else None,
        "season": {"id": str(season.id), "name": season.name} if season else None,
        "innings_totals": innings_totals,
        "batting": batting_flat,
        "bowling": bowling_flat,
        "fielding": fielding_flat,
        "fall_of_wickets": fow,
        "partnerships": partnerships,
    }
