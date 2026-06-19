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
import uuid
from datetime import date, datetime, timezone
from typing import Optional

import bcrypt as _bcrypt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.routers.auth import get_current_club
from app.auth.capabilities import require_cap, MANAGE_FANTASY
from app.auth.modules import org_has_module, MODULE_FANTASY
from app.models.db import (
    get_db, Organisation, Player,
    FantasySeason, FantasyLeague, FantasyLeagueMember, FantasyRound, FantasyPoolPlayer,
    FantasyManager, FantasySquad, FantasySquadPlayer, FantasyDraft, FANTASY_ROLES,
)
from app.services import fantasy_engine, fantasy_draft
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
    # link_active is the club's REAL entitlement (super admins bypass the route
    # gate, so the admin pages work without it, but the public link won't).
    link_active = org_has_module(club, MODULE_FANTASY)
    if fs is None:
        return {"season": None, "link_token": club.fantasy_link_token, "link_active": link_active}

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
        "link_active": link_active,
        "counts": {"pool": pool_n, "rounds": rounds_total, "rounds_scored": rounds_scored},
    }


class RegistrationBody(BaseModel):
    registration_open: bool


@router.post("/season/{season_id}/registration")
async def set_registration(season_id: str, body: RegistrationBody, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """Open or close registration / squad changes for the season."""
    fs = await _load_season(db, club, season_id)
    fs.registration_open = body.registration_open
    await db.commit()
    return {"ok": True, "registration_open": fs.registration_open}


@router.post("/regenerate-link")
async def regenerate_link(club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """Mint a fresh public link token, retiring the old link."""
    org = await db.get(Organisation, club.id)
    org.fantasy_link_token = secrets.token_urlsafe(24)
    await db.commit()
    return {"link_token": org.fantasy_link_token}


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
async def build_pool(season_id: str, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require,
                     reset: Optional[bool] = None):
    """Classify and price every eligible player into the season pool. ``reset=true``
    forces prices back to the freshly-computed baseline (used when the admin
    changes the pricing window and wants prices recalculated, even mid-season)."""
    fs = await _load_season(db, club, season_id)
    n = await fantasy_engine.build_pool(db, fs, reset=reset)
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


# ── team make-up + budget (rules) ──────────────────────────────────────────────

class RulesUpdate(BaseModel):
    role_quota: dict | None = None
    budget: float | None = None
    count_best_n: int | None = None
    transfer_hit: int | None = None
    free_transfers_per_round: int | None = None
    max_banked_transfers: int | None = None
    wildcards_per_half: int | None = None
    triple_captains_per_half: int | None = None
    price_window_years: int | None = None


@router.patch("/season/{season_id}/rules")
async def update_rules(season_id: str, body: RulesUpdate, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """Edit the team make-up (how many of each role), the budget, the best-N count
    and the transfer/chip allowances. Squad size is derived from the role quota.
    Best done before the season starts — existing squads are validated against
    these on their next change."""
    fs = await _load_season(db, club, season_id)
    rules = dict(fs.rules or DEFAULT_RULES)
    if body.role_quota is not None:
        q = {r: int(body.role_quota.get(r, 0)) for r in FANTASY_ROLES}
        if any(v < 0 for v in q.values()):
            raise HTTPException(status_code=400, detail="Role counts can't be negative.")
        if q["keeper"] < 1:
            raise HTTPException(status_code=400, detail="A squad needs at least one keeper.")
        size = sum(q.values())
        if size < 2:
            raise HTTPException(status_code=400, detail="A squad needs at least two players.")
        rules["role_quota"] = q
        rules["squad_size"] = size
    if body.budget is not None:
        if float(body.budget) <= 0:
            raise HTTPException(status_code=400, detail="Budget must be greater than zero.")
        rules["budget"] = round(float(body.budget), 1)
    for fld in ("count_best_n", "transfer_hit", "free_transfers_per_round",
                "max_banked_transfers", "wildcards_per_half", "triple_captains_per_half"):
        val = getattr(body, fld)
        if val is not None:
            rules[fld] = max(0, int(val))
    if body.price_window_years is not None:
        rules["price_window_years"] = max(1, int(body.price_window_years))
    if rules.get("count_best_n", 11) > rules.get("squad_size", 12):
        raise HTTPException(status_code=400, detail="Best-N can't exceed the squad size.")
    fs.rules = rules  # reassign so the JSONB change is flagged
    await db.commit()
    return {"rules": rules}


# ── scoring (the points table) ─────────────────────────────────────────────────

# Point-value keys (any number; a duck is meant to be negative) and the
# multipliers (must be ≥ 1). Mirrors DEFAULT_SCORING in fantasy_scoring.
_SCORING_POINT_KEYS = (
    "run", "four", "six", "fifty", "hundred", "duck",
    "wicket", "three_wickets", "five_wickets", "maiden",
    "catch", "stumping", "run_out", "appearance",
)
_SCORING_MULTIPLIER_KEYS = ("off_role_multiplier", "captain_multiplier", "triple_captain_multiplier")


def _clean_number(v: float) -> float:
    """Round to 2dp and keep integer-valued points as ints, so the stored blob
    stays as tidy as the seeded defaults (16, not 16.0)."""
    f = round(float(v), 2)
    return int(f) if f == int(f) else f


class ScoringUpdate(BaseModel):
    run: float | None = None
    four: float | None = None
    six: float | None = None
    fifty: float | None = None
    hundred: float | None = None
    duck: float | None = None
    wicket: float | None = None
    three_wickets: float | None = None
    five_wickets: float | None = None
    maiden: float | None = None
    catch: float | None = None
    stumping: float | None = None
    run_out: float | None = None
    appearance: float | None = None
    off_role_multiplier: float | None = None
    captain_multiplier: float | None = None
    triple_captain_multiplier: float | None = None


@router.patch("/season/{season_id}/scoring")
async def update_scoring(season_id: str, body: ScoringUpdate, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """Edit the points table — what a run, wicket, catch, milestone etc. is worth,
    plus the off-role and captain multipliers. Stored in the season's JSONB scoring
    blob. New values apply to rounds settled from now on; re-settle an already-
    scored round (the per-round Settle button) to apply them to it as well."""
    fs = await _load_season(db, club, season_id)
    scoring = dict(fs.scoring or DEFAULT_SCORING)
    for key in _SCORING_POINT_KEYS:
        val = getattr(body, key)
        if val is not None:
            if not (-1000 <= float(val) <= 10000):
                raise HTTPException(status_code=400, detail=f"'{key}' points are out of range.")
            scoring[key] = _clean_number(val)
    for key in _SCORING_MULTIPLIER_KEYS:
        val = getattr(body, key)
        if val is not None:
            if not (1 <= float(val) <= 10):
                raise HTTPException(status_code=400, detail="Multipliers must be between 1 and 10.")
            scoring[key] = _clean_number(val)
    fs.scoring = scoring  # reassign so the JSONB change is flagged
    await db.commit()
    return {"scoring": scoring}


# ── managers (the people who signed up to play) ────────────────────────────────

async def _load_manager(db: AsyncSession, club, manager_id: str) -> FantasyManager:
    mgr = await db.get(FantasyManager, manager_id)
    if mgr is None or str(mgr.organisation_id) != str(club.id):
        raise HTTPException(status_code=404, detail="Manager not found")
    return mgr


@router.get("/managers")
async def list_managers(club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """Everyone who has registered to play this club's fantasy, with their team in
    the latest season's club ladder (so an admin can tidy up duplicates or testers)."""
    managers = (await db.execute(
        select(FantasyManager).where(FantasyManager.organisation_id == club.id)
        .order_by(FantasyManager.created_at.desc())
    )).scalars().all()
    season = (await db.execute(
        select(FantasySeason).where(FantasySeason.organisation_id == club.id)
        .order_by(FantasySeason.season_year.desc()).limit(1)
    )).scalar_one_or_none()
    squads: dict[str, tuple] = {}
    if season is not None:
        league = (await db.execute(
            select(FantasyLeague).where(
                FantasyLeague.fantasy_season_id == season.id,
                FantasyLeague.kind == "global_salary_cap",
            ).limit(1)
        )).scalar_one_or_none()
        if league is not None:
            for sq in (await db.execute(
                select(FantasySquad).where(FantasySquad.league_id == league.id)
            )).scalars().all():
                squads[str(sq.manager_id)] = (sq.team_name, float(sq.total_points))
    return {
        "managers": [
            {
                "id": str(m.id), "display_name": m.display_name, "email": m.email,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "last_seen_at": m.last_seen_at.isoformat() if m.last_seen_at else None,
                "team_name": squads.get(str(m.id), (None, None))[0],
                "total_points": squads.get(str(m.id), (None, None))[1],
                "has_squad": str(m.id) in squads,
            }
            for m in managers
        ]
    }


class ManagerUpdate(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    pin: Optional[str] = None


@router.patch("/managers/{manager_id}")
async def update_manager(manager_id: str, body: ManagerUpdate, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """Edit a registered player's display name or email, or reset their PIN (e.g.
    if they're locked out)."""
    mgr = await _load_manager(db, club, manager_id)
    if body.display_name is not None:
        name = body.display_name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Display name can't be empty.")
        mgr.display_name = name
    if body.email is not None:
        email = body.email.strip().lower()
        if email:
            clash = (await db.execute(
                select(FantasyManager).where(
                    FantasyManager.organisation_id == club.id,
                    func.lower(FantasyManager.email) == email,
                    FantasyManager.id != mgr.id,
                )
            )).scalar_one_or_none()
            if clash is not None:
                raise HTTPException(status_code=409, detail="Another player already uses that email.")
        mgr.email = email or None
    if body.pin is not None:
        pin = body.pin.strip()
        if len(pin) < 4:
            raise HTTPException(status_code=400, detail="PIN must be at least 4 digits.")
        mgr.credential_hash = _bcrypt.hashpw(pin.encode(), _bcrypt.gensalt()).decode()
    await db.commit()
    return {"ok": True}


@router.delete("/managers/{manager_id}")
async def delete_manager(manager_id: str, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """Remove a registered player and everything they own (squad, league
    memberships, draft picks) via the cascade. Use for testers and duplicates."""
    mgr = await _load_manager(db, club, manager_id)
    await db.delete(mgr)
    await db.commit()
    return {"ok": True}


@router.get("/managers/{manager_id}/teams")
async def manager_teams(manager_id: str, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """The squads a registered player has picked — their salary-cap team (the club
    ladder) and any draft teams — with the chosen players, captain/vice and each
    pick's season points. Lets an admin see who someone has selected."""
    mgr = await _load_manager(db, club, manager_id)
    rows = (await db.execute(
        select(FantasySquad, FantasyLeague, FantasySeason)
        .join(FantasyLeague, FantasyLeague.id == FantasySquad.league_id)
        .join(FantasySeason, FantasySeason.id == FantasySquad.fantasy_season_id)
        .where(FantasySquad.manager_id == mgr.id)
        .order_by(FantasySeason.season_year.desc())
    )).all()
    squads = []
    for sq, lg, ssn in rows:
        picks = (await db.execute(
            select(FantasySquadPlayer, Player.name, FantasyPoolPlayer.total_points)
            .join(Player, Player.id == FantasySquadPlayer.player_id)
            .join(FantasyPoolPlayer, and_(
                FantasyPoolPlayer.player_id == FantasySquadPlayer.player_id,
                FantasyPoolPlayer.fantasy_season_id == sq.fantasy_season_id,
            ), isouter=True)
            .where(FantasySquadPlayer.squad_id == sq.id)
        )).all()
        squads.append({
            "squad_id": str(sq.id), "league": lg.name, "kind": lg.kind,
            "season_year": ssn.season_year, "team_name": sq.team_name,
            "total_points": float(sq.total_points or 0),
            "budget_remaining": float(sq.budget_remaining) if sq.budget_remaining is not None else None,
            "players": [
                {
                    "player_id": str(sp.player_id), "name": name, "role": sp.role,
                    "is_captain": sp.is_captain, "is_vice_captain": sp.is_vice_captain,
                    "purchase_price": float(sp.purchase_price) if sp.purchase_price is not None else None,
                    "total_points": float(tp) if tp is not None else None,
                }
                for sp, name, tp in picks
            ],
        })
    return {"manager": {"id": str(mgr.id), "display_name": mgr.display_name}, "squads": squads}


# ── pool management (add returning / new players) ──────────────────────────────

@router.get("/season/{season_id}/available-players")
async def available_players(season_id: str, q: str = "", club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """Search the club's players who aren't in the pool yet — returning players
    who fell outside the recent window, or anyone added by hand."""
    fs = await _load_season(db, club, season_id)
    in_pool = select(FantasyPoolPlayer.player_id).where(FantasyPoolPlayer.fantasy_season_id == fs.id)
    stmt = (
        select(Player.id, Player.name).where(
            Player.organisation_id == club.id,
            Player.is_player.isnot(False),
            Player.id.notin_(in_pool),
        ).order_by(Player.name).limit(40)
    )
    if q.strip():
        stmt = stmt.where(Player.name.ilike(f"%{q.strip()}%"))
    rows = (await db.execute(stmt)).all()
    return {"players": [{"player_id": str(pid), "name": nm} for pid, nm in rows]}


class PoolAdd(BaseModel):
    player_id: str
    role: str | None = None
    price: float | None = None


@router.post("/season/{season_id}/pool")
async def add_pool_player(season_id: str, body: PoolAdd, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """Add an existing club player to the pool (a returning player). Role and price
    auto-fill from their history when not given."""
    fs = await _load_season(db, club, season_id)
    player = await db.get(Player, body.player_id)
    if player is None or str(player.organisation_id) != str(club.id):
        raise HTTPException(status_code=404, detail="Player not found")
    if body.role is not None and body.role not in FANTASY_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    role, price = body.role, body.price
    if role is None or price is None:
        auto_role, auto_price = await fantasy_engine.classify_and_price_one(db, fs, body.player_id)
        role = role or auto_role
        price = price if price is not None else auto_price
    price = round(float(price), 1)
    existing = (await db.execute(
        select(FantasyPoolPlayer).where(
            FantasyPoolPlayer.fantasy_season_id == fs.id, FantasyPoolPlayer.player_id == player.id)
    )).scalar_one_or_none()
    if existing is not None:
        existing.role, existing.role_source = role, "admin"
        existing.base_price = existing.current_price = price
        existing.is_available = True
    else:
        db.add(FantasyPoolPlayer(
            fantasy_season_id=fs.id, organisation_id=club.id, player_id=player.id,
            role=role, role_source="admin", base_price=price, current_price=price, is_available=True,
        ))
    await db.commit()
    return {"ok": True, "role": role, "price": price}


_FANTASY_TO_PROFILE = {"keeper": "Wicketkeeper", "batter": "Batter", "allrounder": "All Rounder", "bowler": "Bowler"}


class NewPlayer(BaseModel):
    name: str
    role: str = "batter"
    price: float = 5.0


@router.post("/season/{season_id}/pool/new-player")
async def add_new_player(season_id: str, body: NewPlayer, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """Create a brand-new club player and add them to the pool. They score 0 until
    their real games are synced to this record (or merged), so this is mainly for
    pre-season picks of someone not yet in the data."""
    fs = await _load_season(db, club, season_id)
    if body.role not in FANTASY_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Enter a name.")
    pid = uuid.uuid4()
    db.add(Player(id=pid, name=name, organisation_id=club.id, player_role=_FANTASY_TO_PROFILE.get(body.role)))
    price = round(float(body.price), 1)
    db.add(FantasyPoolPlayer(
        fantasy_season_id=fs.id, organisation_id=club.id, player_id=pid,
        role=body.role, role_source="admin", base_price=price, current_price=price, is_available=True,
    ))
    await db.commit()
    return {"ok": True, "player_id": str(pid)}


@router.delete("/pool/{pool_id}")
async def remove_pool_player(pool_id: str, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """Remove a player from the pool (e.g. one added by mistake)."""
    pp = await db.get(FantasyPoolPlayer, pool_id)
    if pp is None or str(pp.organisation_id) != str(club.id):
        raise HTTPException(status_code=404, detail="Pool player not found")
    await db.delete(pp)
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


# ── draft leagues (admin) ─────────────────────────────────────────────────────

class DraftLeagueCreate(BaseModel):
    name: str
    draft_type: str = "snake"
    scoring_type: str = "total"


@router.post("/season/{season_id}/draft-leagues")
async def create_draft_league(season_id: str, body: DraftLeagueCreate, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """Create a draft league. Members join it, then the admin starts the draft."""
    fs = await _load_season(db, club, season_id)
    if body.draft_type not in ("snake", "auction"):
        raise HTTPException(status_code=400, detail="Invalid draft type")
    if body.scoring_type not in ("total", "h2h"):
        raise HTTPException(status_code=400, detail="Invalid scoring type")
    lg = FantasyLeague(
        fantasy_season_id=fs.id, organisation_id=club.id, kind="draft",
        name=(body.name or "").strip() or "Draft league", join_code=secrets.token_hex(3).upper(),
        draft_type=body.draft_type, scoring_type=body.scoring_type, status="open",
    )
    db.add(lg)
    await db.commit()
    return {"ok": True, "league": {"id": str(lg.id), "name": lg.name, "join_code": lg.join_code,
                                   "draft_type": lg.draft_type, "scoring_type": lg.scoring_type}}


@router.get("/season/{season_id}/draft-leagues")
async def list_draft_leagues(season_id: str, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    fs = await _load_season(db, club, season_id)
    leagues = (await db.execute(
        select(FantasyLeague).where(FantasyLeague.fantasy_season_id == fs.id, FantasyLeague.kind == "draft")
        .order_by(FantasyLeague.created_at)
    )).scalars().all()
    out = []
    for lg in leagues:
        members = (await db.execute(
            select(func.count()).select_from(FantasyLeagueMember).where(FantasyLeagueMember.league_id == lg.id)
        )).scalar_one()
        draft = (await db.execute(select(FantasyDraft).where(FantasyDraft.league_id == lg.id))).scalar_one_or_none()
        out.append({
            "id": str(lg.id), "name": lg.name, "join_code": lg.join_code,
            "draft_type": lg.draft_type, "scoring_type": lg.scoring_type, "status": lg.status,
            "members": members, "draft_status": draft.status if draft else None,
        })
    return {"leagues": out}


async def _load_draft_league(db, club, league_id) -> FantasyLeague:
    lg = await db.get(FantasyLeague, league_id)
    if lg is None or str(lg.organisation_id) != str(club.id) or lg.kind != "draft":
        raise HTTPException(status_code=404, detail="Draft league not found")
    return lg


@router.post("/draft-leagues/{league_id}/start")
async def start_draft(league_id: str, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """Kick off the draft for a league. Snake starts the pick-one clock; auction
    opens the first nomination. Both run async with the clock auto-advancing."""
    lg = await _load_draft_league(db, club, league_id)
    fs = await db.get(FantasySeason, lg.fantasy_season_id)
    try:
        await fantasy_draft.start_draft(db, lg, fs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return {"ok": True}


@router.post("/draft-leagues/{league_id}/process-waivers")
async def process_waivers(league_id: str, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """Run the waiver wire for a draft league, granting claims in reverse-ladder order."""
    lg = await _load_draft_league(db, club, league_id)
    fs = await db.get(FantasySeason, lg.fantasy_season_id)
    granted = await fantasy_draft.process_waivers(db, lg, fs)
    await db.commit()
    return {"granted": granted}


@router.post("/draft-leagues/{league_id}/advance")
async def advance_draft(league_id: str, club=Depends(get_current_club), db: AsyncSession = Depends(get_db), _=_require):
    """Advance a running draft's clock now: snake auto-picks and auction lot awards
    / auto-nominations that are overdue settle immediately, rather than waiting for
    the scheduled tick. Handy for running a draft session or clearing a stall."""
    lg = await _load_draft_league(db, club, league_id)
    fs = await db.get(FantasySeason, lg.fantasy_season_id)
    draft = (await db.execute(select(FantasyDraft).where(FantasyDraft.league_id == lg.id))).scalar_one_or_none()
    if draft is None:
        raise HTTPException(status_code=400, detail="The draft hasn't started.")
    await fantasy_draft.resolve_overdue(db, draft, fs)
    await db.commit()
    return {"ok": True, "status": draft.status}
