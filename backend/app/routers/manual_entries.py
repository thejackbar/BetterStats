"""Manual entry routes — admin-entered historical stats.

All writes are append-only to the audit log (`manual_edit_logs`) and
fully reversible via the undo endpoint. Sync never touches these tables.

Three entry types:
  - manual_games (+ children) — full or partial scorecards
  - manual_season_adjustments — per-player-per-season totals
  - manual_career_adjustments — per-player career deltas

Each entry path enforces:
  - the player/season/grade belongs to the caller's org
  - the caller holds MANAGE_MANUAL_ENTRIES capability
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_MANUAL_ENTRIES, require_cap
from app.models.db import (
    Grade,
    ManualBattingInnings,
    ManualBowlingSpell,
    ManualCareerAdjustment,
    ManualEditLog,
    ManualFieldingStat,
    ManualGame,
    ManualSeasonAdjustment,
    Organisation,
    Player,
    Season,
    User,
    get_db,
)
from app.routers.auth import get_current_club, get_current_user

router = APIRouter(prefix="/club-admin/manual-entries", tags=["manual-entries"])


# ─── Pydantic schemas ────────────────────────────────────────────────────────


class _AggregateFields(BaseModel):
    """Shared fields across season + career adjustments."""

    games_played: int = 0
    batting_innings: int = 0
    batting_runs: int = 0
    batting_not_outs: int = 0
    batting_balls: int = 0
    batting_fours: int = 0
    batting_sixes: int = 0
    batting_fifties: int = 0
    batting_hundreds: int = 0
    batting_ducks: int = 0
    batting_high_score: Optional[int] = None
    batting_high_score_not_out: bool = False
    bowling_innings: int = 0
    bowling_overs: float = 0
    bowling_balls: int = 0
    bowling_maidens: int = 0
    bowling_runs: int = 0
    bowling_wickets: int = 0
    bowling_five_wicket_innings: int = 0
    bowling_best_wickets: Optional[int] = None
    bowling_best_figures: Optional[str] = None
    fielding_catches: int = 0
    fielding_catches_wk: int = 0
    fielding_run_outs: int = 0
    fielding_stumpings: int = 0
    notes: Optional[str] = None


class SeasonAdjustmentIn(_AggregateFields):
    player_id: str
    season_id: str
    grade_id: Optional[str] = None
    bowling_wides: int = 0
    bowling_no_balls: int = 0


class CareerAdjustmentIn(_AggregateFields):
    player_id: str


class ManualBattingIn(BaseModel):
    player_id: str
    innings_number: int = 1
    batting_position: Optional[int] = None
    runs: int = 0
    balls: Optional[int] = None
    fours: int = 0
    sixes: int = 0
    strike_rate: Optional[float] = None
    dismissal_type: Optional[str] = None
    not_out: bool = False
    did_not_bat: bool = False


class ManualBowlingIn(BaseModel):
    player_id: str
    innings_number: int = 1
    overs: Optional[float] = None
    maidens: int = 0
    runs: int = 0
    wickets: int = 0
    wides: int = 0
    no_balls: int = 0
    economy: Optional[float] = None


class ManualFieldingIn(BaseModel):
    player_id: str
    catches: int = 0
    catches_wk: int = 0
    run_outs: int = 0
    stumpings: int = 0


class ManualGameIn(BaseModel):
    season_id: str
    grade_id: Optional[str] = None
    played_at: Optional[str] = None  # YYYY-MM-DD
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    opposition: Optional[str] = None
    venue: Optional[str] = None
    result: Optional[str] = None
    winning_team: Optional[str] = None
    is_final: bool = False
    match_format: Optional[str] = None
    notes: Optional[str] = None
    batting_innings: list[ManualBattingIn] = Field(default_factory=list)
    bowling_spells: list[ManualBowlingIn] = Field(default_factory=list)
    fielding_stats: list[ManualFieldingIn] = Field(default_factory=list)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _to_uuid(s: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(s)
    except Exception:
        raise HTTPException(status_code=422, detail=f"Invalid {label} id")


async def _assert_player_in_org(db: AsyncSession, player_id: uuid.UUID, org_id: uuid.UUID) -> Player:
    player = await db.get(Player, player_id)
    if not player or player.organisation_id != org_id:
        raise HTTPException(status_code=404, detail="Player not in your club")
    return player


async def _assert_season_in_org(db: AsyncSession, season_id: uuid.UUID, org_id: uuid.UUID) -> Season:
    season = await db.get(Season, season_id)
    if not season or season.organisation_id != org_id:
        raise HTTPException(status_code=404, detail="Season not in your club")
    return season


async def _assert_grade_in_season(db: AsyncSession, grade_id: uuid.UUID, season_id: uuid.UUID) -> Grade:
    grade = await db.get(Grade, grade_id)
    if not grade or grade.season_id != season_id:
        raise HTTPException(status_code=404, detail="Grade not in the chosen season")
    return grade


def _row_to_dict(row) -> dict:
    """Convert an SQLAlchemy row's __dict__ to a JSON-serializable dict.

    Strips SQLAlchemy internals; converts UUID/Date/Decimal to strings/floats.
    """
    out = {}
    for k, v in row.__dict__.items():
        if k.startswith("_"):
            continue
        if isinstance(v, uuid.UUID):
            out[k] = str(v)
        elif hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif hasattr(v, "__float__") and not isinstance(v, (int, float, bool)):
            out[k] = float(v)
        else:
            out[k] = v
    return out


async def _log_edit(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: Optional[uuid.UUID],
    action: str,
    target_table: str,
    target_id: str,
    summary: str,
    before: Optional[dict],
    after: Optional[dict],
) -> ManualEditLog:
    entry = ManualEditLog(
        organisation_id=org_id,
        user_id=user_id,
        action=action,
        target_table=target_table,
        target_id=target_id,
        summary=summary,
        before_json=before,
        after_json=after,
    )
    db.add(entry)
    await db.flush()
    return entry


def _player_display_name(player: Player) -> str:
    return player.display_name_override or player.name


# ─── Lookup helpers ──────────────────────────────────────────────────────────


@router.get("/grades")
async def list_grades_with_season(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Per-org grade list keyed by id, with season_id, so the admin UI can
    populate a grade dropdown filtered by the chosen season."""
    rows = await db.execute(
        select(Grade, Season)
        .join(Season, Season.id == Grade.season_id)
        .where(Season.organisation_id == club.id)
        .order_by(Season.name, Grade.name)
    )
    return [
        {
            "id": str(g.id),
            "name": g.display_name_override or g.name,
            "season_id": str(s.id),
            "season_name": s.name,
        }
        for g, s in rows.all()
    ]


# ─── Season adjustments ──────────────────────────────────────────────────────


@router.get("/season-adjustments")
async def list_season_adjustments(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(ManualSeasonAdjustment, Player, Season)
        .join(Player, Player.id == ManualSeasonAdjustment.player_id)
        .join(Season, Season.id == ManualSeasonAdjustment.season_id)
        .where(ManualSeasonAdjustment.organisation_id == club.id)
        .order_by(ManualSeasonAdjustment.created_at.desc())
    )
    out = []
    for adj, player, season in rows.all():
        out.append({
            **_row_to_dict(adj),
            "player_name": _player_display_name(player),
            "season_name": season.name,
        })
    return out


@router.post("/season-adjustments")
async def create_season_adjustment(
    data: SeasonAdjustmentIn,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    player_id = _to_uuid(data.player_id, "player")
    season_id = _to_uuid(data.season_id, "season")
    grade_id = _to_uuid(data.grade_id, "grade") if data.grade_id else None
    player = await _assert_player_in_org(db, player_id, club.id)
    season = await _assert_season_in_org(db, season_id, club.id)
    if grade_id:
        await _assert_grade_in_season(db, grade_id, season_id)

    existing = await db.execute(
        select(ManualSeasonAdjustment).where(
            ManualSeasonAdjustment.player_id == player_id,
            ManualSeasonAdjustment.season_id == season_id,
            ManualSeasonAdjustment.grade_id.is_(grade_id) if grade_id is None else ManualSeasonAdjustment.grade_id == grade_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="An adjustment already exists for this player/season/grade — edit it instead.",
        )

    payload = data.model_dump()
    payload.pop("player_id", None)
    payload.pop("season_id", None)
    payload.pop("grade_id", None)

    adj = ManualSeasonAdjustment(
        organisation_id=club.id,
        player_id=player_id,
        season_id=season_id,
        grade_id=grade_id,
        created_by_user_id=current_user.id,
        **payload,
    )
    db.add(adj)
    await db.flush()
    summary = f"Added season adjustment for {_player_display_name(player)} ({season.name})"
    await _log_edit(
        db,
        org_id=club.id,
        user_id=current_user.id,
        action="create",
        target_table="manual_season_adjustments",
        target_id=str(adj.id),
        summary=summary,
        before=None,
        after=_row_to_dict(adj),
    )
    await db.commit()
    return _row_to_dict(adj)


@router.patch("/season-adjustments/{adj_id}")
async def update_season_adjustment(
    adj_id: int,
    data: SeasonAdjustmentIn,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    adj = await db.get(ManualSeasonAdjustment, adj_id)
    if not adj or adj.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Adjustment not found")
    before = _row_to_dict(adj)

    payload = data.model_dump()
    payload.pop("player_id", None)
    payload.pop("season_id", None)
    payload.pop("grade_id", None)
    for k, v in payload.items():
        setattr(adj, k, v)
    adj.updated_at = datetime.now(timezone.utc)
    await db.flush()

    player = await db.get(Player, adj.player_id)
    season = await db.get(Season, adj.season_id)
    summary = f"Updated season adjustment for {_player_display_name(player)} ({season.name})"
    await _log_edit(
        db,
        org_id=club.id,
        user_id=current_user.id,
        action="update",
        target_table="manual_season_adjustments",
        target_id=str(adj.id),
        summary=summary,
        before=before,
        after=_row_to_dict(adj),
    )
    await db.commit()
    return _row_to_dict(adj)


@router.delete("/season-adjustments/{adj_id}")
async def delete_season_adjustment(
    adj_id: int,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    adj = await db.get(ManualSeasonAdjustment, adj_id)
    if not adj or adj.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Adjustment not found")
    before = _row_to_dict(adj)
    player = await db.get(Player, adj.player_id)
    season = await db.get(Season, adj.season_id)
    summary = f"Deleted season adjustment for {_player_display_name(player)} ({season.name})"
    await db.delete(adj)
    await db.flush()
    await _log_edit(
        db,
        org_id=club.id,
        user_id=current_user.id,
        action="delete",
        target_table="manual_season_adjustments",
        target_id=str(adj_id),
        summary=summary,
        before=before,
        after=None,
    )
    await db.commit()
    return {"deleted": True}


# ─── Career adjustments ──────────────────────────────────────────────────────


@router.get("/career-adjustments")
async def list_career_adjustments(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(ManualCareerAdjustment, Player)
        .join(Player, Player.id == ManualCareerAdjustment.player_id)
        .where(ManualCareerAdjustment.organisation_id == club.id)
        .order_by(ManualCareerAdjustment.created_at.desc())
    )
    out = []
    for adj, player in rows.all():
        out.append({**_row_to_dict(adj), "player_name": _player_display_name(player)})
    return out


@router.post("/career-adjustments")
async def create_career_adjustment(
    data: CareerAdjustmentIn,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    player_id = _to_uuid(data.player_id, "player")
    player = await _assert_player_in_org(db, player_id, club.id)
    existing = await db.execute(
        select(ManualCareerAdjustment).where(
            ManualCareerAdjustment.player_id == player_id,
            ManualCareerAdjustment.organisation_id == club.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="A career adjustment already exists for this player — edit it instead.",
        )

    payload = data.model_dump()
    payload.pop("player_id", None)
    adj = ManualCareerAdjustment(
        organisation_id=club.id,
        player_id=player_id,
        created_by_user_id=current_user.id,
        **payload,
    )
    db.add(adj)
    await db.flush()
    summary = f"Added career adjustment for {_player_display_name(player)}"
    await _log_edit(
        db,
        org_id=club.id,
        user_id=current_user.id,
        action="create",
        target_table="manual_career_adjustments",
        target_id=str(adj.id),
        summary=summary,
        before=None,
        after=_row_to_dict(adj),
    )
    await db.commit()
    return _row_to_dict(adj)


@router.patch("/career-adjustments/{adj_id}")
async def update_career_adjustment(
    adj_id: int,
    data: CareerAdjustmentIn,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    adj = await db.get(ManualCareerAdjustment, adj_id)
    if not adj or adj.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Adjustment not found")
    before = _row_to_dict(adj)
    payload = data.model_dump()
    payload.pop("player_id", None)
    for k, v in payload.items():
        setattr(adj, k, v)
    adj.updated_at = datetime.now(timezone.utc)
    await db.flush()
    player = await db.get(Player, adj.player_id)
    summary = f"Updated career adjustment for {_player_display_name(player)}"
    await _log_edit(
        db,
        org_id=club.id,
        user_id=current_user.id,
        action="update",
        target_table="manual_career_adjustments",
        target_id=str(adj.id),
        summary=summary,
        before=before,
        after=_row_to_dict(adj),
    )
    await db.commit()
    return _row_to_dict(adj)


@router.delete("/career-adjustments/{adj_id}")
async def delete_career_adjustment(
    adj_id: int,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    adj = await db.get(ManualCareerAdjustment, adj_id)
    if not adj or adj.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Adjustment not found")
    before = _row_to_dict(adj)
    player = await db.get(Player, adj.player_id)
    summary = f"Deleted career adjustment for {_player_display_name(player)}"
    await db.delete(adj)
    await db.flush()
    await _log_edit(
        db,
        org_id=club.id,
        user_id=current_user.id,
        action="delete",
        target_table="manual_career_adjustments",
        target_id=str(adj_id),
        summary=summary,
        before=before,
        after=None,
    )
    await db.commit()
    return {"deleted": True}


# ─── Manual games ────────────────────────────────────────────────────────────


@router.get("/games")
async def list_manual_games(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(ManualGame, Season)
        .join(Season, Season.id == ManualGame.season_id)
        .where(ManualGame.organisation_id == club.id)
        .order_by(ManualGame.played_at.desc().nullslast(), ManualGame.created_at.desc())
    )
    out = []
    for game, season in rows.all():
        d = _row_to_dict(game)
        d["season_name"] = season.name
        # Player count = unique players across any of the three child tables
        count_rows = await db.execute(
            select(func.count(func.distinct(ManualBattingInnings.player_id)))
            .where(ManualBattingInnings.manual_game_id == game.id)
        )
        d["batting_count"] = count_rows.scalar() or 0
        out.append(d)
    return out


@router.get("/games/{game_id}")
async def get_manual_game(
    game_id: str,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    gid = _to_uuid(game_id, "manual game")
    game = await db.get(ManualGame, gid)
    if not game or game.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Manual game not found")

    batting = (await db.execute(
        select(ManualBattingInnings, Player)
        .join(Player, Player.id == ManualBattingInnings.player_id)
        .where(ManualBattingInnings.manual_game_id == gid)
        .order_by(ManualBattingInnings.batting_position.asc().nullslast())
    )).all()
    bowling = (await db.execute(
        select(ManualBowlingSpell, Player)
        .join(Player, Player.id == ManualBowlingSpell.player_id)
        .where(ManualBowlingSpell.manual_game_id == gid)
    )).all()
    fielding = (await db.execute(
        select(ManualFieldingStat, Player)
        .join(Player, Player.id == ManualFieldingStat.player_id)
        .where(ManualFieldingStat.manual_game_id == gid)
    )).all()

    return {
        **_row_to_dict(game),
        "batting_innings": [{**_row_to_dict(r), "player_name": _player_display_name(p)} for r, p in batting],
        "bowling_spells": [{**_row_to_dict(r), "player_name": _player_display_name(p)} for r, p in bowling],
        "fielding_stats": [{**_row_to_dict(r), "player_name": _player_display_name(p)} for r, p in fielding],
    }


async def _replace_game_children(
    db: AsyncSession,
    game_id: uuid.UUID,
    data: ManualGameIn,
    org_id: uuid.UUID,
):
    # Validate all players belong to org first
    all_player_ids = set()
    for x in data.batting_innings:
        all_player_ids.add(_to_uuid(x.player_id, "player"))
    for x in data.bowling_spells:
        all_player_ids.add(_to_uuid(x.player_id, "player"))
    for x in data.fielding_stats:
        all_player_ids.add(_to_uuid(x.player_id, "player"))
    for pid in all_player_ids:
        await _assert_player_in_org(db, pid, org_id)

    # Wipe + reinsert all three child tables. Safe under same transaction.
    await db.execute(sa_delete(ManualBattingInnings).where(ManualBattingInnings.manual_game_id == game_id))
    await db.execute(sa_delete(ManualBowlingSpell).where(ManualBowlingSpell.manual_game_id == game_id))
    await db.execute(sa_delete(ManualFieldingStat).where(ManualFieldingStat.manual_game_id == game_id))

    for x in data.batting_innings:
        db.add(ManualBattingInnings(
            manual_game_id=game_id,
            player_id=_to_uuid(x.player_id, "player"),
            innings_number=x.innings_number,
            batting_position=x.batting_position,
            runs=x.runs,
            balls=x.balls,
            fours=x.fours,
            sixes=x.sixes,
            strike_rate=x.strike_rate,
            dismissal_type=x.dismissal_type,
            not_out=x.not_out,
            did_not_bat=x.did_not_bat,
        ))
    for x in data.bowling_spells:
        db.add(ManualBowlingSpell(
            manual_game_id=game_id,
            player_id=_to_uuid(x.player_id, "player"),
            innings_number=x.innings_number,
            overs=x.overs,
            maidens=x.maidens,
            runs=x.runs,
            wickets=x.wickets,
            wides=x.wides,
            no_balls=x.no_balls,
            economy=x.economy,
        ))
    for x in data.fielding_stats:
        db.add(ManualFieldingStat(
            manual_game_id=game_id,
            player_id=_to_uuid(x.player_id, "player"),
            catches=x.catches,
            catches_wk=x.catches_wk,
            run_outs=x.run_outs,
            stumpings=x.stumpings,
        ))


def _parse_date(s: Optional[str]):
    if not s:
        return None
    from datetime import date
    try:
        return date.fromisoformat(s)
    except Exception:
        raise HTTPException(status_code=422, detail=f"Invalid played_at date: {s}")


@router.post("/games")
async def create_manual_game(
    data: ManualGameIn,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    season_id = _to_uuid(data.season_id, "season")
    grade_id = _to_uuid(data.grade_id, "grade") if data.grade_id else None
    await _assert_season_in_org(db, season_id, club.id)
    if grade_id:
        await _assert_grade_in_season(db, grade_id, season_id)

    game = ManualGame(
        organisation_id=club.id,
        season_id=season_id,
        grade_id=grade_id,
        played_at=_parse_date(data.played_at),
        home_team=data.home_team,
        away_team=data.away_team,
        opposition=data.opposition,
        venue=data.venue,
        result=data.result,
        winning_team=data.winning_team,
        is_final=data.is_final,
        match_format=data.match_format,
        notes=data.notes,
        created_by_user_id=current_user.id,
    )
    db.add(game)
    await db.flush()
    await _replace_game_children(db, game.id, data, club.id)
    await db.flush()
    summary = (
        f"Added manual game ({data.played_at or 'date unknown'})"
        + (f" vs {data.opposition}" if data.opposition else "")
    )
    after = _row_to_dict(game)
    after["children"] = data.model_dump()
    await _log_edit(
        db,
        org_id=club.id,
        user_id=current_user.id,
        action="create",
        target_table="manual_games",
        target_id=str(game.id),
        summary=summary,
        before=None,
        after=after,
    )
    await db.commit()
    return _row_to_dict(game)


@router.patch("/games/{game_id}")
async def update_manual_game(
    game_id: str,
    data: ManualGameIn,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    gid = _to_uuid(game_id, "manual game")
    game = await db.get(ManualGame, gid)
    if not game or game.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Manual game not found")
    before = _row_to_dict(game)
    # snapshot children for undo
    old_batting = (await db.execute(
        select(ManualBattingInnings).where(ManualBattingInnings.manual_game_id == gid)
    )).scalars().all()
    old_bowling = (await db.execute(
        select(ManualBowlingSpell).where(ManualBowlingSpell.manual_game_id == gid)
    )).scalars().all()
    old_fielding = (await db.execute(
        select(ManualFieldingStat).where(ManualFieldingStat.manual_game_id == gid)
    )).scalars().all()
    before["children"] = {
        "batting_innings": [_row_to_dict(r) for r in old_batting],
        "bowling_spells": [_row_to_dict(r) for r in old_bowling],
        "fielding_stats": [_row_to_dict(r) for r in old_fielding],
    }

    season_id = _to_uuid(data.season_id, "season")
    grade_id = _to_uuid(data.grade_id, "grade") if data.grade_id else None
    await _assert_season_in_org(db, season_id, club.id)
    if grade_id:
        await _assert_grade_in_season(db, grade_id, season_id)

    game.season_id = season_id
    game.grade_id = grade_id
    game.played_at = _parse_date(data.played_at)
    game.home_team = data.home_team
    game.away_team = data.away_team
    game.opposition = data.opposition
    game.venue = data.venue
    game.result = data.result
    game.winning_team = data.winning_team
    game.is_final = data.is_final
    game.match_format = data.match_format
    game.notes = data.notes
    game.updated_at = datetime.now(timezone.utc)
    await db.flush()

    await _replace_game_children(db, gid, data, club.id)
    await db.flush()
    after = _row_to_dict(game)
    after["children"] = data.model_dump()
    summary = (
        f"Updated manual game ({data.played_at or 'date unknown'})"
        + (f" vs {data.opposition}" if data.opposition else "")
    )
    await _log_edit(
        db,
        org_id=club.id,
        user_id=current_user.id,
        action="update",
        target_table="manual_games",
        target_id=str(gid),
        summary=summary,
        before=before,
        after=after,
    )
    await db.commit()
    return after


@router.delete("/games/{game_id}")
async def delete_manual_game(
    game_id: str,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    gid = _to_uuid(game_id, "manual game")
    game = await db.get(ManualGame, gid)
    if not game or game.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Manual game not found")
    before = _row_to_dict(game)
    old_batting = (await db.execute(
        select(ManualBattingInnings).where(ManualBattingInnings.manual_game_id == gid)
    )).scalars().all()
    old_bowling = (await db.execute(
        select(ManualBowlingSpell).where(ManualBowlingSpell.manual_game_id == gid)
    )).scalars().all()
    old_fielding = (await db.execute(
        select(ManualFieldingStat).where(ManualFieldingStat.manual_game_id == gid)
    )).scalars().all()
    before["children"] = {
        "batting_innings": [_row_to_dict(r) for r in old_batting],
        "bowling_spells": [_row_to_dict(r) for r in old_bowling],
        "fielding_stats": [_row_to_dict(r) for r in old_fielding],
    }
    summary = f"Deleted manual game ({game.played_at or 'date unknown'})"
    await db.delete(game)  # cascade wipes children
    await db.flush()
    await _log_edit(
        db,
        org_id=club.id,
        user_id=current_user.id,
        action="delete",
        target_table="manual_games",
        target_id=game_id,
        summary=summary,
        before=before,
        after=None,
    )
    await db.commit()
    return {"deleted": True}


# ─── Audit log + undo ────────────────────────────────────────────────────────


@router.get("/audit")
async def list_audit(
    limit: int = 200,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    limit = max(1, min(limit, 1000))
    rows = await db.execute(
        select(ManualEditLog, User.display_name, User.email)
        .outerjoin(User, User.id == ManualEditLog.user_id)
        .where(ManualEditLog.organisation_id == club.id)
        .order_by(ManualEditLog.created_at.desc())
        .limit(limit)
    )
    out = []
    for log, name, email in rows.all():
        out.append({
            **_row_to_dict(log),
            "user_name": name or email or "system",
        })
    return out


async def _restore_aggregate(
    db: AsyncSession,
    model_cls,
    target_id: str,
    snapshot: dict,
    org_id: uuid.UUID,
):
    """Insert a previously-deleted aggregate adjustment row back from its snapshot."""
    if snapshot.get("organisation_id") != str(org_id):
        raise HTTPException(status_code=403, detail="Audit row belongs to a different org")
    fields = {k: v for k, v in snapshot.items() if k not in {"id", "created_at", "updated_at"}}
    if "player_id" in fields and isinstance(fields["player_id"], str):
        fields["player_id"] = uuid.UUID(fields["player_id"])
    if "season_id" in fields and isinstance(fields.get("season_id"), str):
        fields["season_id"] = uuid.UUID(fields["season_id"])
    if "grade_id" in fields and isinstance(fields.get("grade_id"), str):
        fields["grade_id"] = uuid.UUID(fields["grade_id"])
    if "organisation_id" in fields and isinstance(fields.get("organisation_id"), str):
        fields["organisation_id"] = uuid.UUID(fields["organisation_id"])
    if "created_by_user_id" in fields and isinstance(fields.get("created_by_user_id"), str):
        fields["created_by_user_id"] = uuid.UUID(fields["created_by_user_id"])
    db.add(model_cls(**fields))


async def _restore_manual_game(db: AsyncSession, snapshot: dict, org_id: uuid.UUID):
    if snapshot.get("organisation_id") != str(org_id):
        raise HTTPException(status_code=403, detail="Audit row belongs to a different org")
    children = snapshot.pop("children", {}) or {}
    fields = {k: v for k, v in snapshot.items() if k not in {"created_at", "updated_at"}}
    for fk in ("id", "organisation_id", "season_id", "grade_id", "created_by_user_id"):
        if fields.get(fk) and isinstance(fields[fk], str):
            fields[fk] = uuid.UUID(fields[fk])
    if isinstance(fields.get("played_at"), str):
        from datetime import date
        try:
            fields["played_at"] = date.fromisoformat(fields["played_at"])
        except Exception:
            fields["played_at"] = None
    db.add(ManualGame(**fields))
    await db.flush()
    game_uuid = fields["id"]
    for r in children.get("batting_innings", []):
        rfields = {k: v for k, v in r.items() if k != "id"}
        rfields["manual_game_id"] = game_uuid
        if isinstance(rfields.get("player_id"), str):
            rfields["player_id"] = uuid.UUID(rfields["player_id"])
        db.add(ManualBattingInnings(**rfields))
    for r in children.get("bowling_spells", []):
        rfields = {k: v for k, v in r.items() if k != "id"}
        rfields["manual_game_id"] = game_uuid
        if isinstance(rfields.get("player_id"), str):
            rfields["player_id"] = uuid.UUID(rfields["player_id"])
        db.add(ManualBowlingSpell(**rfields))
    for r in children.get("fielding_stats", []):
        rfields = {k: v for k, v in r.items() if k != "id"}
        rfields["manual_game_id"] = game_uuid
        if isinstance(rfields.get("player_id"), str):
            rfields["player_id"] = uuid.UUID(rfields["player_id"])
        db.add(ManualFieldingStat(**rfields))


@router.post("/audit/{log_id}/undo")
async def undo_edit(
    log_id: int,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    log = await db.get(ManualEditLog, log_id)
    if not log or log.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Audit entry not found")
    if log.undone_at is not None:
        raise HTTPException(status_code=409, detail="This change has already been undone")

    table = log.target_table
    action = log.action
    target_id = log.target_id

    if action == "create":
        # Undo create → delete the row
        if table == "manual_season_adjustments":
            row = await db.get(ManualSeasonAdjustment, int(target_id))
            if row and row.organisation_id == club.id:
                await db.delete(row)
        elif table == "manual_career_adjustments":
            row = await db.get(ManualCareerAdjustment, int(target_id))
            if row and row.organisation_id == club.id:
                await db.delete(row)
        elif table == "manual_games":
            row = await db.get(ManualGame, _to_uuid(target_id, "manual game"))
            if row and row.organisation_id == club.id:
                await db.delete(row)
        else:
            raise HTTPException(status_code=400, detail=f"Cannot undo create on {table}")
    elif action == "delete":
        # Undo delete → re-insert from before snapshot
        if not log.before_json:
            raise HTTPException(status_code=400, detail="No snapshot available for this entry")
        snap = dict(log.before_json)
        if table == "manual_season_adjustments":
            await _restore_aggregate(db, ManualSeasonAdjustment, target_id, snap, club.id)
        elif table == "manual_career_adjustments":
            await _restore_aggregate(db, ManualCareerAdjustment, target_id, snap, club.id)
        elif table == "manual_games":
            await _restore_manual_game(db, snap, club.id)
        else:
            raise HTTPException(status_code=400, detail=f"Cannot undo delete on {table}")
    elif action == "update":
        # Undo update → restore before snapshot
        if not log.before_json:
            raise HTTPException(status_code=400, detail="No snapshot available for this entry")
        snap = dict(log.before_json)
        if table == "manual_season_adjustments":
            row = await db.get(ManualSeasonAdjustment, int(target_id))
            if not row or row.organisation_id != club.id:
                raise HTTPException(status_code=404, detail="Target row no longer exists")
            for k, v in snap.items():
                if k in {"id", "created_at", "updated_at", "organisation_id", "player_id", "season_id", "grade_id"}:
                    continue
                setattr(row, k, v)
            row.updated_at = datetime.now(timezone.utc)
        elif table == "manual_career_adjustments":
            row = await db.get(ManualCareerAdjustment, int(target_id))
            if not row or row.organisation_id != club.id:
                raise HTTPException(status_code=404, detail="Target row no longer exists")
            for k, v in snap.items():
                if k in {"id", "created_at", "updated_at", "organisation_id", "player_id"}:
                    continue
                setattr(row, k, v)
            row.updated_at = datetime.now(timezone.utc)
        elif table == "manual_games":
            row = await db.get(ManualGame, _to_uuid(target_id, "manual game"))
            if not row or row.organisation_id != club.id:
                raise HTTPException(status_code=404, detail="Target row no longer exists")
            children = snap.pop("children", {}) or {}
            from datetime import date
            for k, v in snap.items():
                if k in {"id", "created_at", "updated_at", "organisation_id"}:
                    continue
                if k == "played_at" and isinstance(v, str):
                    try:
                        v = date.fromisoformat(v)
                    except Exception:
                        v = None
                if k in {"season_id", "grade_id"} and isinstance(v, str):
                    v = uuid.UUID(v)
                setattr(row, k, v)
            row.updated_at = datetime.now(timezone.utc)
            # Replace children with snapshot
            await db.execute(sa_delete(ManualBattingInnings).where(ManualBattingInnings.manual_game_id == row.id))
            await db.execute(sa_delete(ManualBowlingSpell).where(ManualBowlingSpell.manual_game_id == row.id))
            await db.execute(sa_delete(ManualFieldingStat).where(ManualFieldingStat.manual_game_id == row.id))
            for r in children.get("batting_innings", []):
                rfields = {k: v for k, v in r.items() if k != "id"}
                rfields["manual_game_id"] = row.id
                if isinstance(rfields.get("player_id"), str):
                    rfields["player_id"] = uuid.UUID(rfields["player_id"])
                db.add(ManualBattingInnings(**rfields))
            for r in children.get("bowling_spells", []):
                rfields = {k: v for k, v in r.items() if k != "id"}
                rfields["manual_game_id"] = row.id
                if isinstance(rfields.get("player_id"), str):
                    rfields["player_id"] = uuid.UUID(rfields["player_id"])
                db.add(ManualBowlingSpell(**rfields))
            for r in children.get("fielding_stats", []):
                rfields = {k: v for k, v in r.items() if k != "id"}
                rfields["manual_game_id"] = row.id
                if isinstance(rfields.get("player_id"), str):
                    rfields["player_id"] = uuid.UUID(rfields["player_id"])
                db.add(ManualFieldingStat(**rfields))
        else:
            raise HTTPException(status_code=400, detail=f"Cannot undo update on {table}")
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

    log.undone_at = datetime.now(timezone.utc)
    log.undone_by_user_id = current_user.id
    await db.commit()
    return {"undone": True}
