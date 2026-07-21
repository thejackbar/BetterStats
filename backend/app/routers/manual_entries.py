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

import csv
import io
import json
import re
import uuid
from datetime import datetime, timezone, date as date_cls
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func, delete as sa_delete, text as _t
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_MANUAL_ENTRIES, require_cap
from app.models.db import (
    Grade,
    ManualBattingInnings,
    ManualBowlerWicket,
    ManualBowlingSpell,
    ManualCareerAdjustment,
    ManualEditLog,
    ManualFallOfWicket,
    ManualFieldingStat,
    ManualGame,
    ManualPartnership,
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

    @field_validator("bowling_best_figures", mode="before")
    @classmethod
    def _validate_bowling_figures(cls, v):
        # Reuses the same parser as the CSV import path so single-entry,
        # spreadsheet and bulk-CSV writes all agree on what's allowed.
        try:
            return _parse_bowling_figures(v)
        except ValueError as e:
            raise ValueError(str(e))


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
    # Opposition club's Grassroots org GUID (from the CA club search) — links the manual
    # game to head-to-head / BetterIQ opponent matching the same way a synced game does.
    opp_org_id: Optional[str] = None
    # Full both-team scorecard from the AI scorecard upload (renders the opposition half
    # of the match view; the opposition aren't stored as player rows).
    extracted_payload: Optional[dict] = None
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


@router.get("/known-values")
async def list_known_opposition_and_venues(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Distinct opposition club names + venues seen in this org's history,
    drawn from BOTH synced and manual games. Powers the typeahead on the
    manual-game form so admins pick a known value rather than typing
    'Bayswater' / 'Bayswater CC' / 'Bayswater Cricket Club' inconsistently."""
    # Opposition values: pull from games.opp_club_name (synced) + games.away_team
    # / home_team (where we can derive the OPPOSING side from the org), and
    # manual_games.opposition. Synced opposition is the most reliable source.
    opp_rows = await db.execute(_t("""
        WITH org_seasons AS (
            SELECT id FROM seasons WHERE organisation_id = :org_id
        ),
        org_games AS (
            SELECT g.opp_club_name, g.home_team, g.away_team, g.home_club, g.away_club
            FROM games g
            JOIN grades gr ON gr.id = g.grade_id
            WHERE gr.season_id IN (SELECT id FROM org_seasons)
        ),
        opps AS (
            SELECT DISTINCT opp_club_name AS name FROM org_games WHERE opp_club_name IS NOT NULL AND opp_club_name <> ''
            UNION
            SELECT DISTINCT home_club AS name FROM org_games WHERE home_club IS NOT NULL AND home_club <> ''
            UNION
            SELECT DISTINCT away_club AS name FROM org_games WHERE away_club IS NOT NULL AND away_club <> ''
            UNION
            SELECT DISTINCT opposition AS name FROM manual_games WHERE organisation_id = :org_id AND opposition IS NOT NULL AND opposition <> ''
        )
        SELECT name FROM opps WHERE name IS NOT NULL ORDER BY name
    """), {"org_id": str(club.id)})
    oppositions = [r[0] for r in opp_rows.all()]

    venue_rows = await db.execute(_t("""
        WITH org_seasons AS (
            SELECT id FROM seasons WHERE organisation_id = :org_id
        ),
        venues AS (
            SELECT DISTINCT g.venue
            FROM games g JOIN grades gr ON gr.id = g.grade_id
            WHERE gr.season_id IN (SELECT id FROM org_seasons) AND g.venue IS NOT NULL AND g.venue <> ''
            UNION
            SELECT DISTINCT venue FROM manual_games WHERE organisation_id = :org_id AND venue IS NOT NULL AND venue <> ''
        )
        SELECT venue FROM venues ORDER BY venue
    """), {"org_id": str(club.id)})
    venues = [r[0] for r in venue_rows.all()]

    return {"oppositions": oppositions, "venues": venues}


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


def _norm_nm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _as_uuid(v):
    if v is None:
        return None
    if isinstance(v, uuid.UUID):
        return v
    try:
        return uuid.UUID(str(v))
    except (ValueError, TypeError):
        return None


def _parse_dismissal(text: Optional[str], how_out: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Read a dismissal string into (method, fielder_name, bowler_name).

    Handles the usual scorecard shorthand: 'c Smith b Jones', 'c & b Jones',
    'st Brown b Jones', 'lbw b Jones', 'b Jones', 'run out (Smith)', 'not out'.
    Falls back to the model's structured how_out when the text doesn't parse."""
    s = re.sub(r"\s+", " ", (text or "").strip())
    sl = s.lower()
    if not sl or "not out" in sl or sl in ("dnb", "did not bat", "absent"):
        return (None, None, None)
    m = re.match(r"^c(?:aught)?\s*(?:&|and|\+)\s*b(?:owled)?\.?\s+(.+)$", s, re.I)
    if m:
        return ("caught", m.group(1).strip(), m.group(1).strip())
    m = re.match(r"^st(?:umped)?\.?\s+(.+?)\s+b(?:owled)?\.?\s+(.+)$", s, re.I)
    if m:
        return ("stumped", m.group(1).strip(), m.group(2).strip())
    m = re.match(r"^c(?:aught)?\.?\s+(.+?)\s+b(?:owled)?\.?\s+(.+)$", s, re.I)
    if m:
        return ("caught", m.group(1).strip(), m.group(2).strip())
    m = re.match(r"^lbw(?:\s+b(?:owled)?\.?\s+(.+))?$", s, re.I)
    if m:
        return ("lbw", None, (m.group(1) or "").strip() or None)
    m = re.match(r"^(?:run\s*out|ro)\b\s*\(?\s*([^)]*)\)?$", s, re.I)
    if m:
        return ("run out", (m.group(1) or "").strip() or None, None)
    m = re.match(r"^b(?:owled)?\.?\s+(.+)$", s, re.I)
    if m:
        return ("bowled", None, m.group(1).strip())
    ho = (how_out or "").strip().lower()
    if not ho or "not out" in ho or ho in ("dnb", "did not bat", "absent"):
        return (None, None, None)
    return (ho, None, None)


async def _replace_game_bowler_wickets(db: AsyncSession, game_id: uuid.UUID, org_id: uuid.UUID, payload: Optional[dict]):
    """Per-wicket bowler/fielder credit for our bowlers, from the opposition innings.

    For each opposition batter our side dismissed (the bowling rows in their innings are
    ours), read the dismissal → method/bowler/fielder, resolve the bowler to the player
    the reviewer matched on the bowling line (falling back to a roster match) and the
    catcher/stumper to a roster player, and write a manual_bowler_wickets row. Run outs
    and not-outs aren't bowler wickets. Derived, so wiped and rebuilt on every save."""
    await db.execute(sa_delete(ManualBowlerWicket).where(ManualBowlerWicket.manual_game_id == game_id))
    if not payload:
        return
    players = (await db.execute(select(Player).where(Player.organisation_id == org_id))).scalars().all()
    index = _build_match_index(players)
    org_pids = {p.id for p in players}

    def _resolve(name):
        if not name:
            return None
        m = _suggest_player(name, index)
        return m.id if m else None

    def _explicit(pid):
        """A reviewer-picked player id, only if it's one of our players."""
        u = _as_uuid(pid)
        return u if u in org_pids else None

    for inn in (payload.get("innings") or []):
        if inn.get("is_our_team"):
            continue  # only the opposition's innings → our bowlers' wickets
        inn_no = inn.get("innings_number") or 1
        bowl_by_name = {
            _norm_nm(b.get("name")): b.get("player_id")
            for b in (inn.get("bowling") or []) if b.get("player_id") and b.get("name")
        }
        for bt in (inn.get("batting") or []):
            if bt.get("did_not_bat"):
                continue
            method, fielder_nm, bowler_nm = _parse_dismissal(bt.get("dismissal_text"), bt.get("how_out"))
            bowler_nm = bowler_nm or bt.get("bowler")
            fielder_nm = fielder_nm or bt.get("fielder")
            if not method or method in ("not out", "run out"):
                continue  # not a bowler's wicket (run outs credit the fielder, handled in fielding)
            # A reviewer's explicit pick wins; otherwise match the bowling line, then the roster.
            bid = _explicit(bt.get("bowler_id"))
            if not bid:
                bid = _as_uuid(bowl_by_name.get(_norm_nm(bowler_nm))) if bowler_nm else None
                bid = bid or _resolve(bowler_nm)
            if not bid:
                continue  # bowler_id is NOT NULL — skip if we can't name the bowler
            fid = _explicit(bt.get("fielder_id"))
            if not fid and fielder_nm and method in ("caught", "stumped"):
                fid = _resolve(fielder_nm)
            db.add(ManualBowlerWicket(
                manual_game_id=game_id, innings_number=inn_no,
                bowler_id=_as_uuid(bid), fielder_id=_as_uuid(fid),
                batter_name=bt.get("name"), batter_position=bt.get("position"),
                batter_runs=bt.get("runs"), batter_balls=bt.get("balls"),
                dismissal_type=method, caught_behind=None,
            ))


def _which_out(out_name: Optional[str], b0: dict, b1: dict) -> int:
    """Of the two batters at the crease, which one (0 or 1) the fall-of-wicket row
    says is out. Falls back to the batter who's been in longer (slot 0)."""
    if not out_name:
        return 0
    on = _norm_nm(out_name)
    n0, n1 = _norm_nm(b0.get("name")), _norm_nm(b1.get("name"))
    if on and on == n0:
        return 0
    if on and on == n1:
        return 1
    digits = "".join(ch for ch in out_name if ch.isdigit())
    if digits:
        d = int(digits)
        if b0.get("position") == d:
            return 0
        if b1.get("position") == d:
            return 1
    if on and n1 and on in n1:
        return 1
    if on and n0 and on in n0:
        return 0
    return 0


async def _replace_game_fow_partnerships(db: AsyncSession, game_id: uuid.UUID, payload: Optional[dict]):
    """Store fall-of-wickets and per-wicket partnerships for an uploaded card.

    Reads the both-team extracted payload. Partnership runs come straight off the card's
    STAND column (falling back to the score difference), the batter pair is worked out by
    walking the batting order against the fall-of-wickets, and our batters resolve to a
    player_id while the opposition stay name-only. Derived, so it is wiped and rebuilt
    whenever the game is saved."""
    await db.execute(sa_delete(ManualFallOfWicket).where(ManualFallOfWicket.manual_game_id == game_id))
    await db.execute(sa_delete(ManualPartnership).where(ManualPartnership.manual_game_id == game_id))
    if not payload:
        return

    def _pid(v):
        try:
            return uuid.UUID(v) if v else None
        except (ValueError, TypeError):
            return None

    for inn in (payload.get("innings") or []):
        inn_no = inn.get("innings_number") or 1
        is_our = bool(inn.get("is_our_team"))
        bats = [b for b in (inn.get("batting") or [])
                if (b.get("name") or "").strip() and not b.get("did_not_bat")]
        fow = sorted(
            [f for f in (inn.get("fall_of_wickets") or []) if f.get("wicket") is not None],
            key=lambda f: f.get("wicket") or 0,
        )
        name_to_pid = {_norm_nm(b.get("name")): b.get("player_id") for b in bats if b.get("player_id")}

        for f in fow:
            out_name = f.get("batter_out")
            db.add(ManualFallOfWicket(
                manual_game_id=game_id, innings_number=inn_no, wicket_number=f.get("wicket"),
                score_at_fall=f.get("score"), overs_at_fall=None,
                player_id=_pid(name_to_pid.get(_norm_nm(out_name))) if out_name else None,
                batter_name=(out_name or None),
            ))

        if len(bats) >= 2 and fow:
            at = [0, 1]
            nxt = 2
            prev = 0
            for f in fow:
                i0, i1 = at[0], at[1]
                if i0 is None or i1 is None or i0 >= len(bats) or i1 >= len(bats):
                    break
                b0, b1 = bats[i0], bats[i1]
                score, stand = f.get("score"), f.get("stand")
                runs = stand if stand is not None else (
                    (score - prev) if (score is not None and prev is not None) else None
                )
                db.add(ManualPartnership(
                    manual_game_id=game_id, innings_number=inn_no, wicket_number=f.get("wicket"),
                    batter1_id=_pid(b0.get("player_id")), batter2_id=_pid(b1.get("player_id")),
                    runs=runs, balls=None,
                    batter1_runs=b0.get("runs"), batter2_runs=b1.get("runs"),
                    is_club_innings=is_our,
                ))
                out_idx = _which_out(f.get("batter_out"), b0, b1)
                at[out_idx] = nxt if nxt < len(bats) else None
                nxt += 1 if nxt < len(bats) else 0
                prev = score if score is not None else prev


# ─── AI scorecard upload (Upload Historical Scorecard) ───────────────────────


def _name_tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if t]


def _build_match_index(players: list[Player]) -> list[dict]:
    idx: list[dict] = []
    for p in players:
        name = (p.display_name_override or p.name or "").strip()
        toks = _name_tokens(name)
        if not toks:
            continue
        idx.append({"player": p, "tokens": toks, "last": toks[-1], "first_initial": toks[0][0]})
    return idx


def _suggest_player(name: str, index: list[dict]) -> Optional[Player]:
    """Best-effort match of a scorecard name (often 'Surname Initial') to a roster
    player. Returns one confident match or None — the reviewer confirms it."""
    toks = _name_tokens(name)
    if not toks:
        return None
    multis = [t for t in toks if len(t) >= 3]
    surname = max(multis, key=len) if multis else max(toks, key=len)
    initials = {t[0] for t in toks if t != surname}
    cands = [r for r in index if surname == r["last"] or surname in r["tokens"]]
    if not cands and len(surname) >= 4:
        cands = [r for r in index if any(surname in t or t in surname for t in r["tokens"])]
    if len(cands) == 1:
        return cands[0]["player"]
    if len(cands) > 1 and initials:
        narrowed = [r for r in cands if r["first_initial"] in initials]
        if len(narrowed) == 1:
            return narrowed[0]["player"]
    return None


@router.post("/scorecard/extract")
async def extract_scorecard_upload(
    files: list[UploadFile] = File(...),
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Read photographed scorecard(s) with Claude vision and return a structured,
    both-team scorecard for review. Writes nothing — the admin verifies the
    extraction, matches our players, picks the season/grade/opponent, then posts to
    POST /games like any other manual game."""
    from app.services import scorecard_ocr

    images: list[tuple[bytes, str]] = []
    for f in files[: scorecard_ocr.MAX_IMAGES]:
        raw = await f.read()
        if raw:
            images.append((raw, scorecard_ocr.guess_media_type(f.content_type, f.filename)))
    if not images:
        raise HTTPException(status_code=422, detail="No readable images were uploaded.")

    result = await scorecard_ocr.extract_scorecard(images, club.name)
    if not result.get("available"):
        raise HTTPException(status_code=503, detail=result.get("message") or "Scorecard reading is unavailable.")

    players = (await db.execute(select(Player).where(Player.organisation_id == club.id))).scalars().all()
    index = _build_match_index(players)

    # Suggest roster matches only for names that should be OURS: our batters (our
    # innings), our bowlers (the opposition's batting innings) and the fielders named
    # in opposition dismissals. Opposition batters/bowlers stay free text.
    our_names: set[str] = set()
    for inn in (result.get("innings") or []):
        if inn.get("is_our_team"):
            for b in inn.get("batting") or []:
                if b.get("name"):
                    our_names.add(b["name"])
        else:
            for b in inn.get("bowling") or []:
                if b.get("name"):
                    our_names.add(b["name"])
            for b in inn.get("batting") or []:
                if b.get("fielder"):
                    our_names.add(b["fielder"])

    result["suggestions"] = {nm: (str(m.id) if (m := _suggest_player(nm, index)) else "") for nm in our_names}
    result["roster"] = [
        {"id": str(p.id), "name": _player_display_name(p)}
        for p in sorted(players, key=lambda p: (p.display_name_override or p.name or "").lower())
    ]
    return result


@router.get("/scorecard/check-duplicate")
async def check_scorecard_duplicate(
    played_at: str,
    opponent: str = "",
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Find an existing game (synced OR manual) in this club on the given date, so the
    upload can warn before double-counting a match that's already in the data. Uploaded
    games roll into season/career totals (v_effective_player_season_stats) and show in
    every per-game surface, so the same match in both places double-counts."""
    try:
        d = date_cls.fromisoformat((played_at or "").strip())
    except Exception:
        return {"matches": []}
    rows = (await db.execute(_t("""
        SELECT g.id::text AS id, g.played_at, g.home_team, g.away_team,
               g.opp_club_name, g.source, gr.name AS grade
        FROM v_effective_games g
        LEFT JOIN grades gr ON gr.id = g.grade_id
        WHERE g.organisation_id = :org AND g.played_at = :d
        ORDER BY g.source
    """), {"org": str(club.id), "d": d})).mappings().all()
    opp_toks = [w for w in re.split(r"[^a-z0-9]+", (opponent or "").lower()) if len(w) > 2]

    def _likely(r) -> bool:
        if not opp_toks:
            return False
        hay = " ".join([r["opp_club_name"] or "", r["home_team"] or "", r["away_team"] or ""]).lower()
        return any(w in hay for w in opp_toks)

    matches = [{
        "id": r["id"],
        "played_at": r["played_at"].isoformat() if r["played_at"] else None,
        "opponent": r["opp_club_name"] or r["away_team"] or r["home_team"],
        "grade": r["grade"],
        "source": r["source"],  # 'api' (synced) | 'manual'
        "likely": _likely(r),
    } for r in rows]
    return {"matches": matches}


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
        opp_org_id=data.opp_org_id,
        extracted_payload=data.extracted_payload,
        created_by_user_id=current_user.id,
    )
    db.add(game)
    await db.flush()
    await _replace_game_children(db, game.id, data, club.id)
    await _replace_game_fow_partnerships(db, game.id, data.extracted_payload)
    await _replace_game_bowler_wickets(db, game.id, club.id, data.extracted_payload)
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
    # Only overwrite the scorecard-upload fields when the caller actually sends them,
    # so editing a photo-uploaded game through the ordinary Manual Games form (which
    # doesn't carry these) can't wipe the opponent link or the stored both-team card.
    if data.opp_org_id is not None:
        game.opp_org_id = data.opp_org_id
    if data.extracted_payload is not None:
        game.extracted_payload = data.extracted_payload
    game.updated_at = datetime.now(timezone.utc)
    await db.flush()

    await _replace_game_children(db, gid, data, club.id)
    if data.extracted_payload is not None:
        await _replace_game_fow_partnerships(db, gid, data.extracted_payload)
        await _replace_game_bowler_wickets(db, gid, club.id, data.extracted_payload)
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
    elif action == "import":
        # Undo bulk import → delete every row the import created.
        # Updates inside the same import aren't restored: we don't snapshot
        # the prior values per row, so the safer thing is to leave updates
        # in place and just remove the newly-created rows.
        after = log.after_json or {}
        if table == "manual_season_adjustments":
            ids = after.get("created_ids") or []
            for rid in ids:
                row = await db.get(ManualSeasonAdjustment, int(rid))
                if row and row.organisation_id == club.id:
                    await db.delete(row)
        elif table == "manual_games":
            ids = after.get("created_game_ids") or []
            for rid in ids:
                row = await db.get(ManualGame, _to_uuid(rid, "manual game"))
                if row and row.organisation_id == club.id:
                    await db.delete(row)
        else:
            raise HTTPException(status_code=400, detail=f"Cannot undo import on {table}")
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


# ─── CSV bulk import: per-season aggregates ──────────────────────────────────


SEASON_CSV_COLUMNS = [
    "player_name", "season_name", "grade_name",
    "games_played",
    "batting_innings", "batting_runs", "batting_not_outs", "batting_balls",
    "batting_fours", "batting_sixes", "batting_fifties", "batting_hundreds",
    "batting_ducks", "batting_high_score", "batting_high_score_not_out",
    "bowling_innings", "bowling_overs", "bowling_balls", "bowling_maidens",
    "bowling_runs", "bowling_wickets", "bowling_wides", "bowling_no_balls",
    "bowling_five_wicket_innings", "bowling_best_wickets", "bowling_best_figures",
    "fielding_catches", "fielding_catches_wk", "fielding_run_outs", "fielding_stumpings",
    "notes",
]

INT_COLS_SEASON = {
    "games_played", "batting_innings", "batting_runs", "batting_not_outs", "batting_balls",
    "batting_fours", "batting_sixes", "batting_fifties", "batting_hundreds", "batting_ducks",
    "batting_high_score", "bowling_innings", "bowling_balls", "bowling_maidens",
    "bowling_runs", "bowling_wickets", "bowling_wides", "bowling_no_balls",
    "bowling_five_wicket_innings", "bowling_best_wickets",
    "fielding_catches", "fielding_catches_wk", "fielding_run_outs", "fielding_stumpings",
}
FLOAT_COLS_SEASON = {"bowling_overs"}
BOOL_COLS_SEASON = {"batting_high_score_not_out"}
NULLABLE_INT_COLS_SEASON = {"batting_high_score", "bowling_best_wickets"}


def _parse_int(v, *, nullable=False) -> Optional[int]:
    if v is None or v == "":
        return None if nullable else 0
    return int(float(str(v).strip()))


def _parse_float(v) -> float:
    if v is None or v == "":
        return 0.0
    return float(str(v).strip())


def _parse_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    if v is None or v == "":
        return False
    return str(v).strip().lower() in {"1", "true", "yes", "y", "t"}


_BOWLING_FIGURES_RE = re.compile(r"^\s*(\d+)\s*[-/]\s*(\d+)\s*$")
_EXCEL_DATE_RE = re.compile(r"^\s*(\d+)[-/](Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", re.IGNORECASE)


def _parse_bowling_figures(v) -> Optional[str]:
    """Normalize 'best bowling figures' input.

    Accepts '4-25' or '4/25'; returns canonical '{wkts}-{runs}'. Empty/None
    returns None. Anything else (including Excel's silent '1-Jul' coercion
    of '1-7') raises ValueError with a clear message so the import surfaces
    the bad row rather than poisoning the leaderboard SQL downstream.
    """
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    m = _EXCEL_DATE_RE.match(s)
    if m:
        raise ValueError(
            f"'{s}' looks like Excel converted bowling figures into a date. "
            f"Re-enter as text (prefix with a single quote in Excel, e.g. '4-25) "
            f"or use the slash form like 4/25."
        )
    m = _BOWLING_FIGURES_RE.match(s)
    if not m:
        raise ValueError(
            f"Bowling figures must be in the form 'wkts-runs' (e.g. '4-25'), got '{s}'"
        )
    return f"{int(m.group(1))}-{int(m.group(2))}"


@router.get("/season-adjustments/template.csv")
async def season_adjustments_template(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(SEASON_CSV_COLUMNS)
    # One example row so the format is obvious
    w.writerow([
        "Smith, John", "Summer 2010/11", "1st Grade",
        10, 9, 250, 1, 180, 30, 5, 2, 0, 1, 75, "false",
        8, "40.0", 240, 4, 150, 12, 2, 0, 0, 4, "4-25",
        5, 0, 2, 0, "Source: club yearbook 2011",
    ])
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="season_adjustments_template.csv"'},
    )


def _build_player_lookup(players: list[Player]) -> dict[str, Player]:
    """Lower-cased name → Player, with simple ', ' variant matching."""
    out: dict[str, Player] = {}
    for p in players:
        name = (p.display_name_override or p.name or "").strip()
        if not name:
            continue
        out[name.lower()] = p
        # "Smith, John" ↔ "John Smith" — both find the same player
        if "," in name:
            last, first = [x.strip() for x in name.split(",", 1)]
            out[f"{first} {last}".lower()] = p
        else:
            parts = name.split()
            if len(parts) >= 2:
                out[f"{parts[-1]}, {' '.join(parts[:-1])}".lower()] = p
    return out


def _build_season_lookup(seasons: list[Season]) -> dict[str, Season]:
    return {(s.name or "").strip().lower(): s for s in seasons}


def _build_grade_lookup(grades: list[Grade]) -> dict[tuple[uuid.UUID, str], Grade]:
    """(season_id, grade-name-lowercased) → Grade, including display overrides."""
    out: dict[tuple[uuid.UUID, str], Grade] = {}
    for g in grades:
        if g.name:
            out[(g.season_id, g.name.strip().lower())] = g
        if g.display_name_override:
            out[(g.season_id, g.display_name_override.strip().lower())] = g
    return out


@router.post("/season-adjustments/import")
async def import_season_adjustments(
    file: UploadFile = File(...),
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    content = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise HTTPException(status_code=422, detail="CSV is empty or missing a header row")

    # Pre-fetch lookups so we don't re-query per row
    players = (await db.execute(select(Player).where(Player.organisation_id == club.id))).scalars().all()
    seasons = (await db.execute(select(Season).where(Season.organisation_id == club.id))).scalars().all()
    grades = (await db.execute(
        select(Grade).join(Season, Season.id == Grade.season_id).where(Season.organisation_id == club.id)
    )).scalars().all()
    player_lookup = _build_player_lookup(players)
    season_lookup = _build_season_lookup(seasons)
    grade_lookup = _build_grade_lookup(grades)

    errors: list[dict] = []
    created_ids: list[int] = []
    updated_ids: list[int] = []

    for row_num, raw in enumerate(reader, start=2):  # row 1 = header
        try:
            pname = (raw.get("player_name") or "").strip()
            sname = (raw.get("season_name") or "").strip()
            gname = (raw.get("grade_name") or "").strip()
            if not pname or not sname:
                raise ValueError("player_name and season_name are required")

            player = player_lookup.get(pname.lower())
            if not player:
                raise ValueError(f"Player not found: '{pname}'")
            season = season_lookup.get(sname.lower())
            if not season:
                raise ValueError(f"Season not found: '{sname}'")
            grade = None
            if gname:
                grade = grade_lookup.get((season.id, gname.lower()))
                if not grade:
                    raise ValueError(f"Grade '{gname}' not found in season '{sname}'")

            fields: dict = {}
            for col in SEASON_CSV_COLUMNS:
                if col in ("player_name", "season_name", "grade_name"):
                    continue
                val = raw.get(col)
                if col in INT_COLS_SEASON:
                    fields[col] = _parse_int(val, nullable=(col in NULLABLE_INT_COLS_SEASON))
                elif col in FLOAT_COLS_SEASON:
                    fields[col] = _parse_float(val)
                elif col in BOOL_COLS_SEASON:
                    fields[col] = _parse_bool(val)
                elif col == "bowling_best_figures":
                    fields[col] = _parse_bowling_figures(val)
                else:  # text fields: notes
                    fields[col] = (val or "").strip() or None

            # Upsert on the UNIQUE (player_id, season_id, grade_id) constraint
            existing_q = await db.execute(
                select(ManualSeasonAdjustment).where(
                    ManualSeasonAdjustment.player_id == player.id,
                    ManualSeasonAdjustment.season_id == season.id,
                    ManualSeasonAdjustment.grade_id.is_(None) if grade is None else ManualSeasonAdjustment.grade_id == grade.id,
                )
            )
            existing = existing_q.scalar_one_or_none()
            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
                existing.updated_at = datetime.now(timezone.utc)
                updated_ids.append(existing.id)
            else:
                row = ManualSeasonAdjustment(
                    organisation_id=club.id,
                    player_id=player.id,
                    season_id=season.id,
                    grade_id=grade.id if grade else None,
                    created_by_user_id=current_user.id,
                    **fields,
                )
                db.add(row)
                await db.flush()
                created_ids.append(row.id)
        except Exception as e:
            errors.append({"row": row_num, "error": str(e), "data": raw})

    summary = {
        "created": len(created_ids),
        "updated": len(updated_ids),
        "errors": len(errors),
        "errors_detail": errors[:50],  # first 50 errors only — protect against thousands
    }
    if created_ids or updated_ids:
        await _log_edit(
            db,
            org_id=club.id,
            user_id=current_user.id,
            action="import",
            target_table="manual_season_adjustments",
            target_id=f"bulk:{len(created_ids)}created+{len(updated_ids)}updated",
            summary=f"CSV import — season adjustments: {len(created_ids)} created, {len(updated_ids)} updated, {len(errors)} errors",
            before=None,
            after={"created_ids": created_ids, "updated_ids": updated_ids, "errors": errors[:20]},
        )
        await db.commit()
    return summary


# ─── CSV bulk import: per-game scorecards ────────────────────────────────────


GAME_CSV_COLUMNS = [
    "game_key", "played_at", "opposition", "venue", "season_name", "grade_name",
    "is_final", "match_format", "home_team", "away_team", "winning_team", "result",
    "player_name", "innings_number", "batting_position",
    "batting_runs", "batting_balls", "batting_fours", "batting_sixes",
    "batting_not_out", "did_not_bat", "dismissal_type",
    "bowling_overs", "bowling_maidens", "bowling_runs", "bowling_wickets",
    "bowling_wides", "bowling_no_balls",
    "fielding_catches", "fielding_catches_wk", "fielding_run_outs", "fielding_stumpings",
]


@router.get("/games/template.csv")
async def games_template(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(GAME_CSV_COLUMNS)
    # Example: one game with two players. Rows with the same game_key roll up
    # into a single manual_game record; game-level fields are read from the
    # FIRST row encountered for that key.
    w.writerow([
        "G1", "2010-11-13", "Bayswater", "Hyde Park", "Summer 2010/11", "1st Grade",
        "false", "40-over", "Applecross", "Bayswater", "Applecross", "Won by 50 runs",
        "Smith, John", 1, 1, 45, 60, 5, 1, "false", "false", "c Brown b Jones",
        "8.2", 2, 25, 3, 0, 0, 1, 0, 0, 0,
    ])
    w.writerow([
        "G1", "2010-11-13", "Bayswater", "Hyde Park", "Summer 2010/11", "1st Grade",
        "false", "40-over", "Applecross", "Bayswater", "Applecross", "Won by 50 runs",
        "Brown, Tom", 1, 2, 12, 20, 1, 0, "false", "false", "b Jones",
        "", "", "", "", "", "", "", "", "", "",
    ])
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="manual_games_template.csv"'},
    )


def _has_any_value(*vals) -> bool:
    return any(v not in (None, "", "0", 0) for v in vals)


@router.post("/games/import")
async def import_manual_games(
    file: UploadFile = File(...),
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    content = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise HTTPException(status_code=422, detail="CSV is empty or missing a header row")

    players = (await db.execute(select(Player).where(Player.organisation_id == club.id))).scalars().all()
    seasons = (await db.execute(select(Season).where(Season.organisation_id == club.id))).scalars().all()
    grades = (await db.execute(
        select(Grade).join(Season, Season.id == Grade.season_id).where(Season.organisation_id == club.id)
    )).scalars().all()
    player_lookup = _build_player_lookup(players)
    season_lookup = _build_season_lookup(seasons)
    grade_lookup = _build_grade_lookup(grades)

    # Group rows by game_key first so all rows of one game become one manual_game.
    rows = list(reader)
    by_game: dict[str, list[tuple[int, dict]]] = {}
    errors: list[dict] = []
    for row_num, raw in enumerate(rows, start=2):
        gk = (raw.get("game_key") or "").strip()
        if not gk:
            errors.append({"row": row_num, "error": "Missing game_key", "data": raw})
            continue
        by_game.setdefault(gk, []).append((row_num, raw))

    created_game_ids: list[str] = []

    for game_key, group in by_game.items():
        first_row_num, first = group[0]
        try:
            sname = (first.get("season_name") or "").strip()
            if not sname:
                raise ValueError("season_name is required (on the first row for this game_key)")
            season = season_lookup.get(sname.lower())
            if not season:
                raise ValueError(f"Season not found: '{sname}'")
            gname = (first.get("grade_name") or "").strip()
            grade = None
            if gname:
                grade = grade_lookup.get((season.id, gname.lower()))
                if not grade:
                    raise ValueError(f"Grade '{gname}' not found in season '{sname}'")
            played_at = None
            if first.get("played_at"):
                try:
                    played_at = date_cls.fromisoformat(first["played_at"].strip())
                except Exception:
                    raise ValueError(f"Invalid played_at date: {first['played_at']!r}")

            game = ManualGame(
                organisation_id=club.id,
                season_id=season.id,
                grade_id=grade.id if grade else None,
                played_at=played_at,
                home_team=(first.get("home_team") or "").strip() or None,
                away_team=(first.get("away_team") or "").strip() or None,
                opposition=(first.get("opposition") or "").strip() or None,
                venue=(first.get("venue") or "").strip() or None,
                result=(first.get("result") or "").strip() or None,
                winning_team=(first.get("winning_team") or "").strip() or None,
                is_final=_parse_bool(first.get("is_final")),
                match_format=(first.get("match_format") or "").strip() or None,
                notes=None,
                created_by_user_id=current_user.id,
            )
            db.add(game)
            await db.flush()
        except Exception as e:
            errors.append({"row": first_row_num, "error": f"Game '{game_key}': {e}", "data": first})
            continue

        # Children
        game_had_error = False
        for row_num, raw in group:
            try:
                pname = (raw.get("player_name") or "").strip()
                if not pname:
                    continue  # blank player rows are silently ignored
                player = player_lookup.get(pname.lower())
                if not player:
                    raise ValueError(f"Player not found: '{pname}'")
                innings_number = _parse_int(raw.get("innings_number")) or 1

                bruns = raw.get("batting_runs")
                bballs = raw.get("batting_balls")
                if _has_any_value(bruns, bballs, raw.get("dismissal_type"), raw.get("did_not_bat"), raw.get("batting_not_out")):
                    db.add(ManualBattingInnings(
                        manual_game_id=game.id,
                        player_id=player.id,
                        innings_number=innings_number,
                        batting_position=_parse_int(raw.get("batting_position"), nullable=True),
                        runs=_parse_int(bruns),
                        balls=_parse_int(bballs, nullable=True),
                        fours=_parse_int(raw.get("batting_fours")),
                        sixes=_parse_int(raw.get("batting_sixes")),
                        dismissal_type=(raw.get("dismissal_type") or "").strip() or None,
                        not_out=_parse_bool(raw.get("batting_not_out")),
                        did_not_bat=_parse_bool(raw.get("did_not_bat")),
                    ))

                bovers = raw.get("bowling_overs")
                bwkts = raw.get("bowling_wickets")
                bownruns = raw.get("bowling_runs")
                if _has_any_value(bovers, bwkts, bownruns):
                    db.add(ManualBowlingSpell(
                        manual_game_id=game.id,
                        player_id=player.id,
                        innings_number=innings_number,
                        overs=_parse_float(bovers) if bovers not in (None, "") else None,
                        maidens=_parse_int(raw.get("bowling_maidens")),
                        runs=_parse_int(bownruns),
                        wickets=_parse_int(bwkts),
                        wides=_parse_int(raw.get("bowling_wides")),
                        no_balls=_parse_int(raw.get("bowling_no_balls")),
                    ))

                fcatch = raw.get("fielding_catches")
                fro = raw.get("fielding_run_outs")
                fstump = raw.get("fielding_stumpings")
                fwk = raw.get("fielding_catches_wk")
                if _has_any_value(fcatch, fro, fstump, fwk):
                    db.add(ManualFieldingStat(
                        manual_game_id=game.id,
                        player_id=player.id,
                        catches=_parse_int(fcatch),
                        catches_wk=_parse_int(fwk),
                        run_outs=_parse_int(fro),
                        stumpings=_parse_int(fstump),
                    ))
            except Exception as e:
                errors.append({"row": row_num, "error": f"Game '{game_key}', player '{raw.get('player_name')}': {e}", "data": raw})
                game_had_error = True

        if game_had_error:
            # Roll back the game if any of its child rows errored, so partial
            # scorecards don't sneak in. The whole game_key needs to be fixed
            # and re-uploaded.
            await db.execute(sa_delete(ManualBattingInnings).where(ManualBattingInnings.manual_game_id == game.id))
            await db.execute(sa_delete(ManualBowlingSpell).where(ManualBowlingSpell.manual_game_id == game.id))
            await db.execute(sa_delete(ManualFieldingStat).where(ManualFieldingStat.manual_game_id == game.id))
            await db.delete(game)
            await db.flush()
        else:
            created_game_ids.append(str(game.id))

    summary = {
        "games_created": len(created_game_ids),
        "errors": len(errors),
        "errors_detail": errors[:50],
    }
    if created_game_ids:
        await _log_edit(
            db,
            org_id=club.id,
            user_id=current_user.id,
            action="import",
            target_table="manual_games",
            target_id=f"bulk:{len(created_game_ids)}games",
            summary=f"CSV import — manual games: {len(created_game_ids)} games created, {len(errors)} row errors",
            before=None,
            after={"created_game_ids": created_game_ids, "errors": errors[:20]},
        )
        await db.commit()
    return summary
