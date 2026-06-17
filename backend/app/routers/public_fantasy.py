"""BetterFantasyCricket — public manager play (unauthenticated, link + credential).

Members and supporters play through a per-club magic link, with no BetterStats
account. They register once with a display name, email and a PIN they choose,
then a signed HttpOnly cookie (`bs_fantasy`) keeps them signed in — the same
shape as BetterSelect's public availability. Full design:
docs/betterfantasycricket.md.

Like the BetterSelect public router, these routes are NOT behind require_module:
each resolves the club from the link token and checks the club is entitled to
the fantasy module and has an open season itself, so a disabled or downgraded
club's link simply 404s.

This phase covers the salary-cap core: register/login, the pool, build the
squad, and the club ladder. Transfers, chips, mini-leagues and the draft room
are later phases.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt as _bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import MODULE_FANTASY, org_has_module
from app.config.settings import settings
from app.models.db import (
    Organisation, Player, get_db,
    FantasySeason, FantasyLeague, FantasyManager, FantasySquad, FantasySquadPlayer,
    FantasyLeagueMember, FantasyPoolPlayer,
)
from app.services import rate_limit
from app.services.fantasy_squad import validate_squad
from app.services.fantasy_scoring import DEFAULT_RULES

router = APIRouter(prefix="/public/fantasy", tags=["public-fantasy"])

COOKIE_NAME = "bs_fantasy"
SESSION_DAYS = 30

# Auth throttles, mirroring the BetterSelect public router.
LOGIN_MAX_FAILURES = 6
LOGIN_LOCKOUT_SECONDS = 15 * 60
AUTH_IP_LIMIT = 40
AUTH_IP_WINDOW = 60
WRITE_LIMIT = 60
WRITE_WINDOW = 60


def _hash_pin(pin: str) -> str:
    return _bcrypt.hashpw(pin.encode(), _bcrypt.gensalt()).decode()


def _verify_pin(pin: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(pin.encode(), hashed.encode())
    except (ValueError, TypeError):
        return False


def _client_ip(request: Request) -> str:
    for header in ("cf-connecting-ip", "x-real-ip"):
        v = request.headers.get(header)
        if v:
            return v.strip()
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _issue_cookie(response: Response, club_id, manager_id) -> None:
    exp = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    token = jwt.encode(
        {"club": str(club_id), "mgr": str(manager_id), "typ": "fantasy", "exp": exp},
        settings.secret_key, algorithm=settings.algorithm,
    )
    response.set_cookie(
        key=COOKIE_NAME, value=token, httponly=True, secure=settings.cookie_secure,
        samesite="lax", max_age=SESSION_DAYS * 24 * 60 * 60, path="/",
    )


def _read_session(request: Request, club_id) -> Optional[uuid.UUID]:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    try:
        payload = jwt.decode(raw, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None
    if payload.get("typ") != "fantasy" or payload.get("club") != str(club_id):
        return None
    try:
        return uuid.UUID(payload["mgr"])
    except (KeyError, ValueError, TypeError):
        return None


async def _club_for_token(db: AsyncSession, token: str) -> Organisation:
    """Resolve the club behind a fantasy link token, or 404. 404 (not 403) for
    every unusable case so a leaked or rotated link reveals nothing."""
    if not token:
        raise HTTPException(status_code=404, detail="Unknown link")
    club = (await db.execute(
        select(Organisation).where(Organisation.fantasy_link_token == token)
    )).scalar_one_or_none()
    if club is None or not org_has_module(club, MODULE_FANTASY):
        raise HTTPException(status_code=404, detail="This fantasy link isn't active")
    return club


async def _current_season(db: AsyncSession, club: Organisation) -> Optional[FantasySeason]:
    return (await db.execute(
        select(FantasySeason).where(FantasySeason.organisation_id == club.id)
        .order_by(FantasySeason.season_year.desc()).limit(1)
    )).scalar_one_or_none()


async def _global_league(db: AsyncSession, season: FantasySeason) -> Optional[FantasyLeague]:
    return (await db.execute(
        select(FantasyLeague).where(
            FantasyLeague.fantasy_season_id == season.id,
            FantasyLeague.kind == "global_salary_cap",
        ).limit(1)
    )).scalar_one_or_none()


def _club_branding(club: Organisation) -> dict:
    return {
        "name": club.name, "short_name": club.short_name, "slug": club.slug,
        "logo_url": club.logo_url, "primary_color": club.primary_color,
        "accent_color": club.accent_color,
    }


async def _manager_for_session(db: AsyncSession, request: Request, club: Organisation) -> FantasyManager:
    mid = _read_session(request, club.id)
    if not mid:
        raise HTTPException(status_code=401, detail="Not signed in")
    mgr = await db.get(FantasyManager, mid)
    if not mgr or mgr.organisation_id != club.id:
        raise HTTPException(status_code=401, detail="Not signed in")
    return mgr


# ── landing + auth ──────────────────────────────────────────────────────────

@router.get("/{token}")
async def landing(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Club branding, the current season, and whether the caller is already
    signed in. The squad-building screen reads this first."""
    club = await _club_for_token(db, token)
    season = await _current_season(db, club)
    me = None
    mid = _read_session(request, club.id)
    if mid:
        mgr = await db.get(FantasyManager, mid)
        if mgr and mgr.organisation_id == club.id:
            me = {"id": str(mgr.id), "display_name": mgr.display_name}
    season_out = None
    if season is not None:
        pool_n = (await db.execute(
            select(func.count()).select_from(FantasyPoolPlayer)
            .where(FantasyPoolPlayer.fantasy_season_id == season.id)
        )).scalar_one()
        season_out = {
            "id": str(season.id), "name": season.name, "year": season.season_year,
            "status": season.status, "registration_open": season.registration_open,
            "rules": season.rules or DEFAULT_RULES, "pool_size": pool_n,
        }
    return {"club": _club_branding(club), "season": season_out, "me": me}


class RegisterBody(BaseModel):
    display_name: str
    email: str
    pin: str


class LoginBody(BaseModel):
    email: str
    pin: str


@router.post("/{token}/register")
async def register(token: str, body: RegisterBody, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Create a manager for this club and sign them in. Email is the login id
    (unique per club); the PIN is theirs to choose."""
    club = await _club_for_token(db, token)
    season = await _current_season(db, club)
    if season is None or not season.registration_open:
        raise HTTPException(status_code=403, detail="Registration isn't open for this club.")
    rate_limit.enforce(f"fantasy-auth-ip:{token}:{_client_ip(request)}", AUTH_IP_LIMIT, AUTH_IP_WINDOW,
                       detail="Too many attempts — slow down and try again shortly.")

    name = (body.display_name or "").strip()
    email = (body.email or "").strip().lower()
    pin = (body.pin or "").strip()
    if not name or not email or len(pin) < 4:
        raise HTTPException(status_code=400, detail="Enter a name, an email and a PIN of at least 4 digits.")

    existing = (await db.execute(
        select(FantasyManager).where(
            FantasyManager.organisation_id == club.id, func.lower(FantasyManager.email) == email,
        )
    )).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="That email is already registered — sign in instead.")

    mgr = FantasyManager(
        organisation_id=club.id, display_name=name, email=email,
        credential_hash=_hash_pin(pin), last_seen_at=datetime.now(timezone.utc),
    )
    db.add(mgr)
    await db.commit()
    _issue_cookie(response, club.id, mgr.id)
    return {"status": "ok", "manager": {"id": str(mgr.id), "display_name": mgr.display_name}}


@router.post("/{token}/login")
async def login(token: str, body: LoginBody, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Sign in with email + PIN. Rate-limited per IP and locked out after repeated
    misses (the same identity-enumeration guard as BetterSelect)."""
    club = await _club_for_token(db, token)
    ip = _client_ip(request)
    rate_limit.enforce(f"fantasy-auth-ip:{token}:{ip}", AUTH_IP_LIMIT, AUTH_IP_WINDOW,
                       detail="Too many attempts — slow down and try again shortly.")
    email = (body.email or "").strip().lower()
    lock_key = f"fantasy-login:{token}:{email}:{ip}"
    rate_limit.assert_not_locked(lock_key, LOGIN_MAX_FAILURES, LOGIN_LOCKOUT_SECONDS,
                                 detail="Too many incorrect attempts. Please wait a few minutes and try again.")

    mgr = (await db.execute(
        select(FantasyManager).where(
            FantasyManager.organisation_id == club.id, func.lower(FantasyManager.email) == email,
        )
    )).scalar_one_or_none()
    if mgr is None or not mgr.credential_hash or not _verify_pin((body.pin or "").strip(), mgr.credential_hash):
        rate_limit.record_failure(lock_key, LOGIN_LOCKOUT_SECONDS)
        raise HTTPException(status_code=401, detail="That email and PIN didn't match.")

    rate_limit.clear_failures(lock_key)
    mgr.last_seen_at = datetime.now(timezone.utc)
    await db.commit()
    _issue_cookie(response, club.id, mgr.id)
    return {"status": "ok", "manager": {"id": str(mgr.id), "display_name": mgr.display_name}}


@router.post("/{token}/logout")
async def logout(token: str, response: Response):
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"status": "ok"}


# ── pool + squad ──────────────────────────────────────────────────────────────

@router.get("/{token}/pool")
async def pool(token: str, db: AsyncSession = Depends(get_db)):
    """The pickable players with role, price and points, for building a squad."""
    club = await _club_for_token(db, token)
    season = await _current_season(db, club)
    if season is None:
        raise HTTPException(status_code=404, detail="No fantasy season yet")
    rows = (await db.execute(
        select(FantasyPoolPlayer, Player.name)
        .join(Player, Player.id == FantasyPoolPlayer.player_id)
        .where(FantasyPoolPlayer.fantasy_season_id == season.id, FantasyPoolPlayer.is_available.is_(True))
        .order_by(FantasyPoolPlayer.current_price.desc())
    )).all()
    return {
        "rules": season.rules or DEFAULT_RULES,
        "players": [
            {
                "player_id": str(pp.player_id), "name": name, "role": pp.role,
                "price": float(pp.current_price), "total_points": float(pp.total_points),
                "owned_count": pp.owned_count,
            }
            for pp, name in rows
        ],
    }


def _squad_payload(squad: FantasySquad, picks_named: list) -> dict:
    return {
        "id": str(squad.id), "team_name": squad.team_name,
        "budget_remaining": float(squad.budget_remaining) if squad.budget_remaining is not None else None,
        "total_points": float(squad.total_points),
        "players": [
            {
                "player_id": str(sp.player_id), "name": name, "role": sp.role,
                "is_captain": sp.is_captain, "is_vice_captain": sp.is_vice_captain,
                "purchase_price": float(sp.purchase_price) if sp.purchase_price is not None else None,
            }
            for sp, name in picks_named
        ],
    }


@router.get("/{token}/me")
async def me(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """The signed-in manager's squad (if built) and its current standing."""
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    if season is None:
        return {"manager": {"id": str(mgr.id), "display_name": mgr.display_name}, "squad": None}
    league = await _global_league(db, season)
    squad = (await db.execute(
        select(FantasySquad).where(
            FantasySquad.league_id == league.id, FantasySquad.manager_id == mgr.id,
        )
    )).scalar_one_or_none() if league else None
    payload = None
    if squad is not None:
        picks = (await db.execute(
            select(FantasySquadPlayer, Player.name)
            .join(Player, Player.id == FantasySquadPlayer.player_id)
            .where(FantasySquadPlayer.squad_id == squad.id)
        )).all()
        payload = _squad_payload(squad, picks)
    return {"manager": {"id": str(mgr.id), "display_name": mgr.display_name}, "squad": payload}


class Pick(BaseModel):
    player_id: str
    is_captain: bool = False
    is_vice_captain: bool = False


class SquadBody(BaseModel):
    team_name: str
    picks: list[Pick]


@router.post("/{token}/squad")
async def build_squad(token: str, body: SquadBody, request: Request, db: AsyncSession = Depends(get_db)):
    """Create or replace the manager's squad in the club ladder. Allowed while the
    season is still open and before any round has scored; once the season is live,
    changes go through transfers (a later phase)."""
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    if season is None or not season.registration_open:
        raise HTTPException(status_code=403, detail="The squad window is closed for this club.")
    if season.status == "active":
        raise HTTPException(status_code=409, detail="The season has started — squad changes go through transfers.")
    league = await _global_league(db, season)
    if league is None:
        raise HTTPException(status_code=404, detail="No club ladder yet")
    rate_limit.enforce(f"fantasy-write:{mgr.id}", WRITE_LIMIT, WRITE_WINDOW)

    # Build the pool lookup the validator needs.
    pool_rows = (await db.execute(
        select(FantasyPoolPlayer).where(FantasyPoolPlayer.fantasy_season_id == season.id)
    )).scalars().all()
    pool = {
        str(pp.player_id): {"role": pp.role, "current_price": float(pp.current_price), "is_available": pp.is_available}
        for pp in pool_rows
    }
    picks = [p.model_dump() for p in body.picks]
    errors = validate_squad(picks, pool, season.rules or DEFAULT_RULES)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    team_name = (body.team_name or "").strip() or f"{mgr.display_name}'s XI"
    budget = (season.rules or DEFAULT_RULES).get("budget", DEFAULT_RULES["budget"])
    spend = sum(pool[str(p["player_id"])]["current_price"] for p in picks)

    squad = (await db.execute(
        select(FantasySquad).where(FantasySquad.league_id == league.id, FantasySquad.manager_id == mgr.id)
    )).scalar_one_or_none()
    if squad is None:
        squad = FantasySquad(
            fantasy_season_id=season.id, league_id=league.id, manager_id=mgr.id,
            organisation_id=club.id, team_name=team_name,
            budget_remaining=round(budget - spend, 1),
        )
        db.add(squad)
        await db.flush()
        db.add(FantasyLeagueMember(league_id=league.id, manager_id=mgr.id, squad_id=squad.id))
    else:
        squad.team_name = team_name
        squad.budget_remaining = round(budget - spend, 1)
        for old in (await db.execute(
            select(FantasySquadPlayer).where(FantasySquadPlayer.squad_id == squad.id)
        )).scalars().all():
            await db.delete(old)
        await db.flush()

    for p in picks:
        pid = str(p["player_id"])
        db.add(FantasySquadPlayer(
            squad_id=squad.id, player_id=pid, role=pool[pid]["role"],
            is_captain=bool(p["is_captain"]), is_vice_captain=bool(p["is_vice_captain"]),
            purchase_price=pool[pid]["current_price"],
        ))
    await db.commit()
    await _recount_ownership(db, season.id)
    return {"status": "ok", "squad_id": str(squad.id)}


async def _recount_ownership(db: AsyncSession, season_id) -> None:
    """Refresh each pool player's owned_count from the global-league squads (drives
    ownership-based pricing and the 'X% picked' display). Reset to zero, then set
    the owned counts, so a player nobody now holds drops back to zero."""
    await db.execute(
        text("UPDATE fantasy_pool_players SET owned_count = 0 WHERE fantasy_season_id = CAST(:fs AS UUID)"),
        {"fs": str(season_id)},
    )
    await db.execute(
        text("""
            UPDATE fantasy_pool_players pp SET owned_count = c.n
            FROM (
                SELECT sp.player_id, COUNT(*) AS n
                FROM fantasy_squad_players sp
                JOIN fantasy_squads sq ON sq.id = sp.squad_id
                JOIN fantasy_leagues l ON l.id = sq.league_id AND l.kind = 'global_salary_cap'
                WHERE sq.fantasy_season_id = CAST(:fs AS UUID)
                GROUP BY sp.player_id
            ) c
            WHERE pp.fantasy_season_id = CAST(:fs AS UUID) AND pp.player_id = c.player_id
        """),
        {"fs": str(season_id)},
    )
    await db.commit()


# ── ladder ─────────────────────────────────────────────────────────────────────

@router.get("/{token}/ladder")
async def ladder(token: str, db: AsyncSession = Depends(get_db)):
    """The club-wide salary-cap ladder, ranked by cumulative points."""
    club = await _club_for_token(db, token)
    season = await _current_season(db, club)
    if season is None:
        return {"ladder": []}
    league = await _global_league(db, season)
    if league is None:
        return {"ladder": []}
    rows = (await db.execute(
        select(FantasySquad.team_name, FantasyManager.display_name, FantasySquad.total_points)
        .join(FantasyManager, FantasyManager.id == FantasySquad.manager_id)
        .where(FantasySquad.league_id == league.id)
        .order_by(FantasySquad.total_points.desc())
    )).all()
    return {
        "ladder": [
            {"rank": i, "team_name": tn, "manager": dn, "points": float(pts)}
            for i, (tn, dn, pts) in enumerate(rows, start=1)
        ]
    }
