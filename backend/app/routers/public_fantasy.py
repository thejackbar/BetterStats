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

import secrets
import string
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
    FantasyLeagueMember, FantasyPoolPlayer, FantasyRound, FantasyTransaction,
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


# ── transfers, captain, chips ────────────────────────────────────────────────

def _gen_code(n: int = 6) -> str:
    return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(n))


def _sell_value(purchase, current) -> float:
    """FPL-style sell-on: realise the buy price plus half of any profit."""
    profit = max(0.0, float(current) - float(purchase or 0))
    return round(float(purchase or 0) + profit / 2, 1)


async def _current_round(db: AsyncSession, season: FantasySeason) -> Optional[FantasyRound]:
    return (await db.execute(
        select(FantasyRound).where(
            FantasyRound.fantasy_season_id == season.id, FantasyRound.status != "scored",
        ).order_by(FantasyRound.round_number).limit(1)
    )).scalar_one_or_none()


async def _global_squad(db: AsyncSession, season: FantasySeason, mgr: FantasyManager) -> Optional[FantasySquad]:
    league = await _global_league(db, season)
    if league is None:
        return None
    return (await db.execute(
        select(FantasySquad).where(FantasySquad.league_id == league.id, FantasySquad.manager_id == mgr.id)
    )).scalar_one_or_none()


async def _record_round_transfer(db: AsyncSession, squad_id, rnd: Optional[FantasyRound], hit: int) -> None:
    """Tally a transfer (and any points hit) against the current round's score row,
    which settlement later reads when it computes points = raw - transfer_hit."""
    if rnd is None:
        return
    await db.execute(
        text("""
            INSERT INTO fantasy_squad_round_scores (squad_id, round_id, transfer_hit, transfers_made, lineup)
            VALUES (CAST(:sid AS UUID), CAST(:rid AS UUID), :hit, 1, '[]')
            ON CONFLICT (squad_id, round_id) DO UPDATE SET
                transfer_hit = fantasy_squad_round_scores.transfer_hit + :hit,
                transfers_made = fantasy_squad_round_scores.transfers_made + 1
        """),
        {"sid": str(squad_id), "rid": str(rnd.id), "hit": hit},
    )


class TransferBody(BaseModel):
    out_player_id: str
    in_player_id: str


@router.post("/{token}/transfer")
async def transfer(token: str, body: TransferBody, request: Request, db: AsyncSession = Depends(get_db)):
    """Swap one player for another of the same role. The first free transfer of the
    round is free; further transfers cost the points hit. Budget uses the sell-on
    value of the player leaving."""
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    if season is None or season.status == "completed":
        raise HTTPException(status_code=403, detail="Transfers are closed.")
    squad = await _global_squad(db, season, mgr)
    if squad is None:
        raise HTTPException(status_code=400, detail="Build your squad first.")
    rate_limit.enforce(f"fantasy-write:{mgr.id}", WRITE_LIMIT, WRITE_WINDOW)

    sps = (await db.execute(
        select(FantasySquadPlayer).where(FantasySquadPlayer.squad_id == squad.id)
    )).scalars().all()
    out_sp = next((s for s in sps if str(s.player_id) == body.out_player_id), None)
    if out_sp is None:
        raise HTTPException(status_code=400, detail="That player isn't in your squad.")
    if out_sp.is_captain or out_sp.is_vice_captain:
        raise HTTPException(status_code=400, detail="Change your captain or vice before transferring them out.")
    if any(str(s.player_id) == body.in_player_id for s in sps):
        raise HTTPException(status_code=400, detail="You already have that player.")

    in_pool = (await db.execute(
        select(FantasyPoolPlayer).where(
            FantasyPoolPlayer.fantasy_season_id == season.id,
            FantasyPoolPlayer.player_id == body.in_player_id,
        )
    )).scalar_one_or_none()
    if in_pool is None or not in_pool.is_available:
        raise HTTPException(status_code=400, detail="That player isn't available.")
    if in_pool.role != out_sp.role:
        raise HTTPException(status_code=400, detail=f"Transfers must be like-for-like by role ({out_sp.role}).")

    out_pool = (await db.execute(
        select(FantasyPoolPlayer).where(
            FantasyPoolPlayer.fantasy_season_id == season.id,
            FantasyPoolPlayer.player_id == body.out_player_id,
        )
    )).scalar_one_or_none()
    out_current = out_pool.current_price if out_pool else (out_sp.purchase_price or 0)
    sell = _sell_value(out_sp.purchase_price, out_current)
    budget = float(squad.budget_remaining or 0) + sell - float(in_pool.current_price)
    if budget < -1e-6:
        raise HTTPException(status_code=400, detail="Not enough budget for that transfer.")

    rnd = await _current_round(db, season)
    if squad.free_transfers and squad.free_transfers > 0:
        squad.free_transfers -= 1
        hit = 0
    else:
        hit = int((season.rules or DEFAULT_RULES).get("transfer_hit", DEFAULT_RULES["transfer_hit"]))

    await db.delete(out_sp)
    db.add(FantasySquadPlayer(
        squad_id=squad.id, player_id=body.in_player_id, role=in_pool.role,
        purchase_price=in_pool.current_price, added_round=rnd.round_number if rnd else None,
    ))
    squad.budget_remaining = round(budget, 1)
    db.add(FantasyTransaction(squad_id=squad.id, league_id=squad.league_id, round_id=rnd.id if rnd else None,
                              type="transfer_out", player_id=body.out_player_id, price=sell))
    db.add(FantasyTransaction(squad_id=squad.id, league_id=squad.league_id, round_id=rnd.id if rnd else None,
                              type="transfer_in", player_id=body.in_player_id, price=in_pool.current_price))
    await db.flush()
    await _record_round_transfer(db, squad.id, rnd, hit)
    await db.commit()
    await _recount_ownership(db, season.id)
    return {"ok": True, "hit": hit, "budget_remaining": squad.budget_remaining, "free_transfers": squad.free_transfers}


class CaptainBody(BaseModel):
    captain_player_id: str
    vice_player_id: Optional[str] = None


@router.post("/{token}/captain")
async def set_captain(token: str, body: CaptainBody, request: Request, db: AsyncSession = Depends(get_db)):
    """Set the captain (doubles) and optional vice-captain (the fallback)."""
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    if season is None:
        raise HTTPException(status_code=404, detail="No fantasy season")
    squad = await _global_squad(db, season, mgr)
    if squad is None:
        raise HTTPException(status_code=400, detail="Build your squad first.")
    sps = (await db.execute(
        select(FantasySquadPlayer).where(FantasySquadPlayer.squad_id == squad.id)
    )).scalars().all()
    ids = {str(s.player_id) for s in sps}
    if body.captain_player_id not in ids:
        raise HTTPException(status_code=400, detail="The captain must be in your squad.")
    if body.vice_player_id and body.vice_player_id not in ids:
        raise HTTPException(status_code=400, detail="The vice-captain must be in your squad.")
    if body.vice_player_id and body.vice_player_id == body.captain_player_id:
        raise HTTPException(status_code=400, detail="Captain and vice must be different players.")
    for s in sps:
        s.is_captain = str(s.player_id) == body.captain_player_id
        s.is_vice_captain = bool(body.vice_player_id) and str(s.player_id) == body.vice_player_id
    await db.commit()
    return {"ok": True}


class ChipBody(BaseModel):
    chip: str  # 'wildcard' | 'triple_captain'


@router.post("/{token}/chip")
async def play_chip(token: str, body: ChipBody, request: Request, db: AsyncSession = Depends(get_db)):
    """Play a chip for the current round. Wildcard makes this round's transfers
    free and unlimited; triple-captain triples the captain. One of each per half."""
    chip = body.chip
    if chip not in ("wildcard", "triple_captain"):
        raise HTTPException(status_code=400, detail="Unknown chip.")
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    if season is None:
        raise HTTPException(status_code=404, detail="No fantasy season")
    squad = await _global_squad(db, season, mgr)
    if squad is None:
        raise HTTPException(status_code=400, detail="Build your squad first.")
    rnd = await _current_round(db, season)
    if rnd is None:
        raise HTTPException(status_code=400, detail="No upcoming round to play a chip on.")

    total = (await db.execute(
        select(func.count()).select_from(FantasyRound).where(FantasyRound.fantasy_season_id == season.id)
    )).scalar_one() or 1
    half = 0 if (rnd.round_number - 1) < total / 2 else 1
    chips = dict(squad.chips_used or {})
    used = list(chips.get(chip, []))
    allow = int((season.rules or DEFAULT_RULES).get(
        "wildcards_per_half" if chip == "wildcard" else "triple_captains_per_half", 1))
    used_this_half = sum(1 for rn in used if (0 if (rn - 1) < total / 2 else 1) == half)
    if used_this_half >= allow:
        raise HTTPException(status_code=409, detail="You've already used that chip this half of the season.")

    if chip == "wildcard":
        squad.free_transfers = 9999  # unlimited for this round; rollover resets it
    else:  # triple_captain — flagged on the round score row, read at settlement
        await db.execute(
            text("""
                INSERT INTO fantasy_squad_round_scores (squad_id, round_id, chip_used, lineup)
                VALUES (CAST(:sid AS UUID), CAST(:rid AS UUID), 'triple_captain', '[]')
                ON CONFLICT (squad_id, round_id) DO UPDATE SET chip_used = 'triple_captain'
            """),
            {"sid": str(squad.id), "rid": str(rnd.id)},
        )
    chips[chip] = used + [rnd.round_number]
    squad.chips_used = chips  # reassign so the JSONB change is flagged
    db.add(FantasyTransaction(squad_id=squad.id, league_id=squad.league_id, round_id=rnd.id, type="chip",
                              detail={"chip": chip, "round": rnd.round_number}))
    await db.commit()
    return {"ok": True, "chip": chip, "round": rnd.round_number}


# ── mini-leagues ─────────────────────────────────────────────────────────────

class LeagueCreate(BaseModel):
    name: str


@router.post("/{token}/leagues")
async def create_league(token: str, body: LeagueCreate, request: Request, db: AsyncSession = Depends(get_db)):
    """Create a private mini-league and join it. Members are ranked on the same
    global salary-cap squads."""
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    if season is None:
        raise HTTPException(status_code=404, detail="No fantasy season")
    name = (body.name or "").strip() or f"{mgr.display_name}'s league"
    code = _gen_code()
    league = FantasyLeague(
        fantasy_season_id=season.id, organisation_id=club.id, kind="mini_salary_cap",
        name=name, join_code=code, status="open", created_by_manager_id=mgr.id,
    )
    db.add(league)
    await db.flush()
    squad = await _global_squad(db, season, mgr)
    db.add(FantasyLeagueMember(league_id=league.id, manager_id=mgr.id, squad_id=squad.id if squad else None))
    await db.commit()
    return {"ok": True, "league": {"id": str(league.id), "name": name, "join_code": code}}


class LeagueJoin(BaseModel):
    code: str


@router.post("/{token}/leagues/join")
async def join_league(token: str, body: LeagueJoin, request: Request, db: AsyncSession = Depends(get_db)):
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    if season is None:
        raise HTTPException(status_code=404, detail="No fantasy season")
    league = (await db.execute(
        select(FantasyLeague).where(
            FantasyLeague.fantasy_season_id == season.id,
            FantasyLeague.kind == "mini_salary_cap",
            func.upper(FantasyLeague.join_code) == (body.code or "").strip().upper(),
        )
    )).scalar_one_or_none()
    if league is None:
        raise HTTPException(status_code=404, detail="No league with that code.")
    member = (await db.execute(
        select(FantasyLeagueMember).where(
            FantasyLeagueMember.league_id == league.id, FantasyLeagueMember.manager_id == mgr.id)
    )).scalar_one_or_none()
    if member is None:
        squad = await _global_squad(db, season, mgr)
        db.add(FantasyLeagueMember(league_id=league.id, manager_id=mgr.id, squad_id=squad.id if squad else None))
        await db.commit()
    return {"ok": True, "league": {"id": str(league.id), "name": league.name}}


@router.get("/{token}/leagues")
async def my_leagues(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """The mini-leagues this manager is in, each with its ranked ladder."""
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    if season is None:
        return {"leagues": []}
    leagues = (await db.execute(
        select(FantasyLeague).join(FantasyLeagueMember, FantasyLeagueMember.league_id == FantasyLeague.id)
        .where(
            FantasyLeagueMember.manager_id == mgr.id,
            FantasyLeague.fantasy_season_id == season.id,
            FantasyLeague.kind == "mini_salary_cap",
        )
    )).scalars().all()
    out = []
    for lg in leagues:
        rows = (await db.execute(
            select(FantasySquad.team_name, FantasyManager.display_name, FantasySquad.total_points)
            .join(FantasyLeagueMember, FantasyLeagueMember.squad_id == FantasySquad.id)
            .join(FantasyManager, FantasyManager.id == FantasySquad.manager_id)
            .where(FantasyLeagueMember.league_id == lg.id)
            .order_by(FantasySquad.total_points.desc())
        )).all()
        out.append({
            "id": str(lg.id), "name": lg.name, "join_code": lg.join_code,
            "ladder": [
                {"rank": i, "team_name": tn, "manager": dn, "points": float(pts)}
                for i, (tn, dn, pts) in enumerate(rows, start=1)
            ],
        })
    return {"leagues": out}
