"""BetterFantasyCricket API — an internal club fantasy cricket league.

Players are the club's own playing list; matches are the club's own fixtures
across every grade. Fantasy points are computed from the per-innings stats we
already hold (batting, bowling, fielding, dismissals), so no new data feed is
needed. Full design: docs/betterfantasycricket.md.

Everything is scoped to the caller's club (get_current_club) and gated by the
MANAGE_FANTASY capability. The whole router is module-gated by
require_module("fantasy") at include time (main.py).

This is the admin surface: season setup, the priced pool, round generation and
settlement. The member-facing play (squad build, transfers, ladder, draft) and
its public router land in later phases per the spec's phase plan.
"""
from __future__ import annotations

import secrets
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.routers.auth import get_current_club
from app.auth.capabilities import require_cap, MANAGE_FANTASY
from app.models.db import (
    get_db, Organisation, Player,
    FantasySeason, FantasyLeague, FantasyRound, FantasyPoolPlayer,
    FANTASY_ROLES,
)
from app.services import fantasy_engine
from app.services.fantasy_scoring import DEFAULT_SCORING, DEFAULT_RULES

router = APIRouter(prefix="/club-admin/fantasy", tags=["club-admin-fantasy"])

_require = Depends(require_cap(MANAGE_FANTASY))


# ── helpers ────────────────────────────────────────────────────────────────────

async def _load_season(db: AsyncSession, club, season_id: str) -> FantasySeason:
    fs = await db.get(FantasySeason, season_id)
    if fs is None or str(fs.organisation_id) != str(club.id):
        raise HTTPException(status_code=404, detail="Fantasy season not found")
    return fs


def _season_dict(fs: FantasySeason) -> dict:
    return {
        "id": str(fs.id),
        "season_year": fs.season_year,
        "name": fs.name,
        "status": fs.status,
        "included_grade_ids": fs.included_grade_ids,
        "scoring": fs.scoring or DEFAULT_SCORING,
        "rules": fs.rules or DEFAULT_RULES,
        "registration_open": fs.registration_open,
    }


# ── config + season ─────────────────────────────────────────────────────────────

@router.get("/config")
async def get_config(club=Depends(get_current_club), _=_require):
    """Module status + the default season config the setup screen seeds from."""
    return {
        "module": "fantasy",
        "club_id": str(club.id),
        "club_slug": club.slug,
        "roles": list(FANTASY_ROLES),
        "defaults": {"scoring": DEFAULT_SCORING, "rules": DEFAULT_RULES},
    }


@router.get("/season")
async def get_season(club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """The club's most recent fantasy season with its setup counts, or null."""
    fs = (await db.execute(
        select(FantasySeason)
        .where(FantasySeason.organisation_id == club.id)
        .order_by(FantasySeason.season_year.desc())
        .limit(1)
    )).scalar_one_or_none()
    if fs is None:
        return {"season": None, "link_token": club.fantasy_link_token}

    pool_n = (await db.execute(
        select(func.count()).select_from(FantasyPoolPlayer).where(FantasyPoolPlayer.fantasy_season_id == fs.id)
    )).scalar_one()
    rounds_total = (await db.execute(
        select(func.count()).select_from(FantasyRound).where(FantasyRound.fantasy_season_id == fs.id)
    )).scalar_one()
    rounds_scored = (await db.execute(
        select(func.count()).select_from(FantasyRound)
        .where(FantasyRound.fantasy_season_id == fs.id, FantasyRound.status == "scored")
    )).scalar_one()
    return {
        "season": _season_dict(fs),
        "link_token": club.fantasy_link_token,
        "counts": {"pool": pool_n, "rounds": rounds_total, "rounds_scored": rounds_scored},
    }


class SeasonCreate(BaseModel):
    season_year: int
    name: str | None = None


@router.post("/season")
async def create_season(body: SeasonCreate, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """Create the club's fantasy season for a year (idempotent on org+year). Seeds
    the scoring and rules from the defaults, creates the club-wide salary-cap
    league, and mints the public fantasy link if the club doesn't have one yet."""
    existing = (await db.execute(
        select(FantasySeason).where(
            FantasySeason.organisation_id == club.id,
            FantasySeason.season_year == body.season_year,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return {"season": _season_dict(existing), "created": False}

    name = body.name or f"{body.season_year}/{(body.season_year + 1) % 100:02d} Fantasy"
    fs = FantasySeason(
        organisation_id=club.id, season_year=body.season_year, name=name,
        status="setup", scoring=dict(DEFAULT_SCORING), rules=dict(DEFAULT_RULES),
        registration_open=True,
    )
    db.add(fs)
    await db.flush()
    db.add(FantasyLeague(
        fantasy_season_id=fs.id, organisation_id=club.id,
        kind="global_salary_cap", name="Club ladder", status="open",
    ))
    # Mint the public link token on the org if absent (mirrors BetterSelect).
    org = await db.get(Organisation, club.id)
    if org is not None and not org.fantasy_link_token:
        org.fantasy_link_token = secrets.token_urlsafe(24)
    await db.commit()
    return {"season": _season_dict(fs), "created": True}


# ── pool ─────────────────────────────────────────────────────────────────────

@router.post("/season/{season_id}/build-pool")
async def build_pool(season_id: str, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """Classify and price every eligible player into the season pool."""
    fs = await _load_season(db, club, season_id)
    n = await fantasy_engine.build_pool(db, fs)
    await db.commit()
    return {"pool": n}


@router.post("/season/{season_id}/generate-rounds")
async def generate_rounds(season_id: str, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """Group the season-year's games into weekly fantasy rounds."""
    fs = await _load_season(db, club, season_id)
    n = await fantasy_engine.generate_rounds(db, fs)
    await db.commit()
    return {"rounds": n}


@router.get("/season/{season_id}/pool")
async def list_pool(season_id: str, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """The priced pool with player names, roles and current points."""
    fs = await _load_season(db, club, season_id)
    rows = (await db.execute(
        select(FantasyPoolPlayer, Player.name)
        .join(Player, Player.id == FantasyPoolPlayer.player_id)
        .where(FantasyPoolPlayer.fantasy_season_id == fs.id)
        .order_by(FantasyPoolPlayer.current_price.desc())
    )).all()
    return {
        "players": [
            {
                "id": str(pp.id), "player_id": str(pp.player_id), "name": name,
                "role": pp.role, "role_source": pp.role_source,
                "base_price": float(pp.base_price), "current_price": float(pp.current_price),
                "total_points": float(pp.total_points), "last_round_points": float(pp.last_round_points),
                "owned_count": pp.owned_count, "is_available": pp.is_available,
            }
            for pp, name in rows
        ]
    }


class PoolPatch(BaseModel):
    role: str | None = None
    is_available: bool | None = None
    current_price: float | None = None


@router.patch("/pool/{pool_id}")
async def patch_pool_player(pool_id: str, body: PoolPatch, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """Admin override of a pool player — set the fantasy role (stamps role_source
    'admin' so a rebuild won't overwrite it), pull them from the pool, or nudge a
    price."""
    pp = await db.get(FantasyPoolPlayer, pool_id)
    if pp is None or str(pp.organisation_id) != str(club.id):
        raise HTTPException(status_code=404, detail="Pool player not found")
    if body.role is not None:
        if body.role not in FANTASY_ROLES:
            raise HTTPException(status_code=400, detail="Invalid role")
        pp.role = body.role
        pp.role_source = "admin"
    if body.is_available is not None:
        pp.is_available = body.is_available
    if body.current_price is not None:
        pp.current_price = round(float(body.current_price), 1)
    pp.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True}


# ── rounds + settlement ─────────────────────────────────────────────────────────

@router.get("/season/{season_id}/rounds")
async def list_rounds(season_id: str, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    fs = await _load_season(db, club, season_id)
    rows = (await db.execute(
        select(FantasyRound).where(FantasyRound.fantasy_season_id == fs.id).order_by(FantasyRound.round_number)
    )).scalars().all()
    return {
        "rounds": [
            {
                "id": str(r.id), "round_number": r.round_number, "name": r.name,
                "lock_at": r.lock_at.isoformat() if r.lock_at else None,
                "start_date": r.start_date.isoformat() if r.start_date else None,
                "end_date": r.end_date.isoformat() if r.end_date else None,
                "status": r.status,
                "scored_at": r.scored_at.isoformat() if r.scored_at else None,
            }
            for r in rows
        ]
    }


@router.post("/rounds/{round_id}/settle")
async def settle_round(round_id: str, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """Compute player fantasy points for one round from the scorecards. Idempotent."""
    rnd = await db.get(FantasyRound, round_id)
    if rnd is None or str(rnd.organisation_id) != str(club.id):
        raise HTTPException(status_code=404, detail="Round not found")
    fs = await _load_season(db, club, str(rnd.fantasy_season_id))
    n = await fantasy_engine.settle_round(db, fs, rnd)
    await db.commit()
    return {"players_scored": n}


@router.post("/season/{season_id}/settle-due")
async def settle_due(season_id: str, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """Settle every round whose window has finished and isn't scored yet — the
    after-the-weekend rollup. Safe to re-run."""
    fs = await _load_season(db, club, season_id)
    today = date.today()
    rounds = (await db.execute(
        select(FantasyRound).where(
            FantasyRound.fantasy_season_id == fs.id,
            FantasyRound.status != "scored",
            FantasyRound.end_date <= today,
        ).order_by(FantasyRound.round_number)
    )).scalars().all()
    settled = 0
    for rnd in rounds:
        await fantasy_engine.settle_round(db, fs, rnd)
        settled += 1
    await db.commit()
    return {"rounds_settled": settled}


@router.delete("/season/{season_id}")
async def delete_season(season_id: str, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """Delete a fantasy season and everything under it (pool, rounds, leagues,
    squads, scores) via the FK cascade. Refused once a round has scored, so a
    live competition can't be nuked by accident."""
    fs = await _load_season(db, club, season_id)
    scored = (await db.execute(
        select(func.count()).select_from(FantasyRound)
        .where(FantasyRound.fantasy_season_id == fs.id, FantasyRound.status == "scored")
    )).scalar_one()
    if scored:
        raise HTTPException(status_code=409, detail="This season has scored rounds, so it can't be deleted.")
    await db.delete(fs)
    await db.commit()
    return {"ok": True}
