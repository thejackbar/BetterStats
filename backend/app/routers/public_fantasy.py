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
    Organisation, Player, Team, get_db,
    FantasySeason, FantasyLeague, FantasyManager, FantasySquad, FantasySquadPlayer,
    FantasyLeagueMember, FantasyPoolPlayer, FantasyRound, FantasyTransaction,
    FantasySquadRoundScore, FantasyPlayerRoundScore,
    FantasyDraft, FantasyDraftPick, FantasyDraftWishlist, FantasyWaiverClaim, FantasyTrade,
)
from app.services import rate_limit, fantasy_draft, fantasy_engine
from app.services.fantasy_squad import validate_squad, score_squad_round
from app.services.fantasy_scoring import DEFAULT_RULES, DEFAULT_SCORING

# The four salary-cap chips. Wildcard + triple-captain were in the first cut;
# bench boost + free hit are the redesign additions. Each is allowed a set number
# of plays per half-season (see rules).
FANTASY_CHIPS = ("wildcard", "triple_captain", "bench_boost", "free_hit")

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


# ── shared read helpers (photos, form, ownership, deltas) ─────────────────────

def _initials(name: str) -> str:
    parts = [w for w in (name or "").split() if w]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


async def _manager_count(db: AsyncSession, league_id) -> int:
    if league_id is None:
        return 0
    return (await db.execute(
        select(func.count()).select_from(FantasySquad).where(FantasySquad.league_id == league_id)
    )).scalar_one() or 0


async def _form_by_player(db: AsyncSession, season_id) -> dict[str, float]:
    """Each pool player's recent-form score: the average of their last up-to-5
    scored-round totals. Drives the pool/profile 'Form' chip."""
    rows = (await db.execute(
        text("""
            SELECT player_id, ROUND(AVG(total_points)::numeric, 1) AS form FROM (
                SELECT prs.player_id, prs.total_points,
                       ROW_NUMBER() OVER (PARTITION BY prs.player_id ORDER BY r.round_number DESC) AS rn
                FROM fantasy_player_round_scores prs
                JOIN fantasy_rounds r ON r.id = prs.round_id AND r.status = 'scored'
                WHERE prs.fantasy_season_id = CAST(:fs AS UUID)
            ) x WHERE rn <= 5 GROUP BY player_id
        """),
        {"fs": str(season_id)},
    )).all()
    return {str(pid): float(form) for pid, form in rows}


async def _team_by_player(db: AsyncSession, player_ids: list) -> dict[str, str]:
    """Map each player to their BetterSelect squad team name (the pool 'Team' column)."""
    if not player_ids:
        return {}
    rows = (await db.execute(
        select(Player.id, Team.name).join(Team, Team.id == Player.squad_team_id, isouter=True)
        .where(Player.id.in_(player_ids))
    )).all()
    return {str(pid): tn for pid, tn in rows if tn}


def _player_card(p: Player) -> dict:
    """The shared per-player visual fields the redesign needs everywhere: a photo
    (with the club crest as the UI fallback) and initials."""
    return {"photo_url": p.photo_url, "initials": _initials(p.name)}


async def _enrich_lineup(db: AsyncSession, lineup: list, sort: bool = True) -> list[dict]:
    """Add the player name + photo + initials onto a stored round lineup snapshot,
    so Points and Live can render the photo-led rows. Counted players first."""
    ids = [uuid.UUID(str(e["player_id"])) for e in lineup if e.get("player_id")]
    info: dict[str, tuple] = {}
    if ids:
        for pid, nm, photo in (await db.execute(
            select(Player.id, Player.name, Player.photo_url).where(Player.id.in_(ids))
        )).all():
            info[str(pid)] = (nm, photo)
    rows = sorted(lineup, key=lambda e: (not e.get("counted"), e.get("role", ""))) if sort else lineup
    out = []
    for e in rows:
        nm, photo = info.get(str(e.get("player_id")), ("?", None))
        out.append({**e, "name": nm, "photo_url": photo, "initials": _initials(nm)})
    return out


def _chip_states(season: FantasySeason, squad: Optional[FantasySquad], rnd: Optional[FantasyRound], current_chip: Optional[str]) -> list[dict]:
    """Per-chip state for the Chips screen: available / armed (active this round) /
    used (played a prior round). The play limits are still enforced server-side in
    play_chip; this is the display model."""
    defs = [
        ("wildcard", "Wildcard", "Unlimited free transfers for one round."),
        ("triple_captain", "Triple Captain", "Your captain scores 3× instead of 2×."),
        ("bench_boost", "Bench Boost", "All 12 players score, bench included."),
        ("free_hit", "Free Hit", "A one-week team that reverts next round."),
    ]
    chips = (squad.chips_used if squad else None) or {}
    cur_n = rnd.round_number if rnd else None
    out = []
    for key, name, desc in defs:
        used_rounds = list(chips.get(key, []))
        armed = False
        if cur_n is not None:
            if key == "wildcard":
                armed = bool(squad and squad.free_transfers and squad.free_transfers > 100) and cur_n in used_rounds
            else:
                armed = current_chip == key and cur_n in used_rounds
        prior = [r for r in used_rounds if r != cur_n]
        if armed:
            state, status = "armed", f"Armed · round {cur_n}"
        elif prior:
            state, status = "used", f"Used · round {max(prior)}"
        else:
            state, status = "available", "Available"
        out.append({"key": key, "name": name, "desc": desc, "state": state, "status": status})
    return out


async def _league_standings(db: AsyncSession, *, league_id=None, squad_ids: Optional[list] = None) -> list[dict]:
    """Ranked standings with a per-round movement delta. Select the squads either by
    the league they sit in (``league_id``, used for the global ladder) or by an
    explicit squad-id set (``squad_ids``, used for mini-leagues, whose members
    point at their global squad). The delta is rank now (by season total) vs rank
    before the last scored round (total minus that squad's most-recent round
    points) — a real ▲/▼ without snapshot tables."""
    q = (
        select(
            FantasySquad.id, FantasySquad.team_name, FantasyManager.display_name,
            FantasySquad.total_points,
        )
        .join(FantasyManager, FantasyManager.id == FantasySquad.manager_id)
    )
    if squad_ids is not None:
        if not squad_ids:
            return []
        q = q.where(FantasySquad.id.in_(squad_ids))
    else:
        q = q.where(FantasySquad.league_id == league_id)
    rows = (await db.execute(q)).all()
    if not rows:
        return []
    ids = [r[0] for r in rows]
    # Each squad's most-recent scored-round points (for the "before last round" rank).
    last_rows = (await db.execute(
        text("""
            SELECT DISTINCT ON (srs.squad_id) srs.squad_id, srs.points, r.round_number
            FROM fantasy_squad_round_scores srs
            JOIN fantasy_rounds r ON r.id = srs.round_id AND r.status = 'scored'
            WHERE srs.squad_id = ANY(:ids)
            ORDER BY srs.squad_id, r.round_number DESC
        """),
        {"ids": ids},
    )).all()
    last_pts = {str(sid): float(pts or 0) for sid, pts, _rn in last_rows}
    last_gw = {str(sid): float(pts or 0) for sid, pts, _rn in last_rows}

    now_order = sorted(rows, key=lambda r: float(r[3]), reverse=True)
    prev_order = sorted(rows, key=lambda r: float(r[3]) - last_pts.get(str(r[0]), 0.0), reverse=True)
    prev_rank = {str(r[0]): i for i, r in enumerate(prev_order, start=1)}

    out = []
    for i, r in enumerate(now_order, start=1):
        sid = str(r[0])
        delta = prev_rank.get(sid, i) - i  # +ve = climbed
        out.append({
            "rank": i, "squad_id": sid, "team_name": r[1], "manager": r[2],
            "points": float(r[3]), "gw": last_gw.get(sid, 0.0), "rank_delta": delta,
        })
    return out


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
            "rules": season.rules or DEFAULT_RULES, "scoring": season.scoring or DEFAULT_SCORING,
            "pool_size": pool_n,
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
        select(FantasyPoolPlayer, Player)
        .join(Player, Player.id == FantasyPoolPlayer.player_id)
        .where(FantasyPoolPlayer.fantasy_season_id == season.id, FantasyPoolPlayer.is_available.is_(True))
        .order_by(FantasyPoolPlayer.current_price.desc())
    )).all()
    league = await _global_league(db, season)
    managers = await _manager_count(db, league.id) if league else 0
    form = await _form_by_player(db, season.id)
    teams = await _team_by_player(db, [pp.player_id for pp, _p in rows])
    return {
        "rules": season.rules or DEFAULT_RULES,
        "managers": managers,
        "players": [
            {
                "player_id": str(pp.player_id), "name": p.name, "role": pp.role,
                "price": float(pp.current_price), "total_points": float(pp.total_points),
                "last_round_points": float(pp.last_round_points),
                "price_change": float(pp.price_change),
                "owned_count": pp.owned_count,
                "selected_pct": round(100.0 * pp.owned_count / managers, 1) if managers else 0.0,
                "form": form.get(str(pp.player_id), 0.0),
                "team": teams.get(str(pp.player_id)),
                **_player_card(p),
            }
            for pp, p in rows
        ],
    }


def _squad_payload(squad: FantasySquad, picks_named: list) -> dict:
    return {
        "id": str(squad.id), "team_name": squad.team_name,
        "budget_remaining": float(squad.budget_remaining) if squad.budget_remaining is not None else None,
        "total_points": float(squad.total_points),
        "players": [
            {
                "player_id": str(sp.player_id), "name": p.name, "role": sp.role,
                "is_captain": sp.is_captain, "is_vice_captain": sp.is_vice_captain,
                "purchase_price": float(sp.purchase_price) if sp.purchase_price is not None else None,
                **_player_card(p),
            }
            for sp, p in picks_named
        ],
    }


async def _overall_rank(db: AsyncSession, league_id, squad_id) -> Optional[int]:
    """The squad's position on the club-wide ladder (1 = top)."""
    if league_id is None or squad_id is None:
        return None
    row = (await db.execute(
        text("""
            SELECT rnk FROM (
                SELECT id, RANK() OVER (ORDER BY total_points DESC) AS rnk
                FROM fantasy_squads WHERE league_id = CAST(:lid AS UUID)
            ) r WHERE id = CAST(:sid AS UUID)
        """),
        {"lid": str(league_id), "sid": str(squad_id)},
    )).first()
    return int(row[0]) if row else None


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
    rnd = await _current_round(db, season)
    cur_chip = None
    if rnd is not None and squad is not None:
        cur_chip = (await db.execute(
            text("SELECT chip_used FROM fantasy_squad_round_scores WHERE squad_id = CAST(:sid AS UUID) AND round_id = CAST(:rid AS UUID)"),
            {"sid": str(squad.id), "rid": str(rnd.id)},
        )).scalar_one_or_none()

    payload = None
    if squad is not None:
        picks = (await db.execute(
            select(FantasySquadPlayer, Player)
            .join(Player, Player.id == FantasySquadPlayer.player_id)
            .where(FantasySquadPlayer.squad_id == squad.id)
        )).all()
        payload = _squad_payload(squad, picks)
        payload["free_transfers"] = squad.free_transfers
        # Team value = what the squad is worth now (current prices) plus the bank.
        val = (await db.execute(
            text("""SELECT COALESCE(SUM(pp.current_price), 0) FROM fantasy_squad_players sp
                    JOIN fantasy_pool_players pp ON pp.player_id = sp.player_id
                       AND pp.fantasy_season_id = CAST(:fs AS UUID)
                    WHERE sp.squad_id = CAST(:sid AS UUID)"""),
            {"fs": str(season.id), "sid": str(squad.id)},
        )).scalar_one()
        payload["value"] = round(float(val) + float(squad.budget_remaining or 0), 1)
        lr = (await db.execute(
            text("""SELECT r.round_number, srs.points FROM fantasy_squad_round_scores srs
                    JOIN fantasy_rounds r ON r.id = srs.round_id
                    WHERE srs.squad_id = CAST(:sid AS UUID) AND r.status = 'scored'
                    ORDER BY r.round_number DESC LIMIT 1"""),
            {"sid": str(squad.id)},
        )).first()
        if lr:
            payload["last_round"] = {"number": lr[0], "points": float(lr[1])}
        payload["overall_rank"] = await _overall_rank(db, league.id if league else None, squad.id)
        payload["chips"] = _chip_states(season, squad, rnd, cur_chip)

    round_info = None
    if rnd:
        round_info = {
            "number": rnd.round_number, "name": rnd.name,
            "lock_at": rnd.lock_at.isoformat() if rnd.lock_at else None,
            "locked": _round_locked(rnd), "status": rnd.status,
        }
    return {"manager": {"id": str(mgr.id), "display_name": mgr.display_name}, "squad": payload, "round": round_info}


@router.get("/{token}/round")
async def round_view(token: str, request: Request, db: AsyncSession = Depends(get_db), n: Optional[int] = None):
    """The manager's per-player points for a round (defaults to the latest scored
    round), plus the round average and high score. The FPL 'Points' screen."""
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    if season is None:
        return {"round": None, "rounds": []}
    rounds = (await db.execute(
        select(FantasyRound).where(FantasyRound.fantasy_season_id == season.id).order_by(FantasyRound.round_number)
    )).scalars().all()
    if not rounds:
        return {"round": None, "rounds": []}
    scored = [r for r in rounds if r.status == "scored"]
    target = None
    if n is not None:
        target = next((r for r in rounds if r.round_number == n), None)
    if target is None:
        target = scored[-1] if scored else rounds[0]

    squad = await _global_squad(db, season, mgr)
    srs = None
    if squad is not None:
        srs = (await db.execute(
            select(FantasySquadRoundScore).where(
                FantasySquadRoundScore.squad_id == squad.id, FantasySquadRoundScore.round_id == target.id)
        )).scalar_one_or_none()

    mine = None
    if srs is not None:
        mine = {
            "points": float(srs.points), "raw_points": float(srs.raw_points),
            "transfer_hit": srs.transfer_hit, "chip_used": srs.chip_used,
            "lineup": await _enrich_lineup(db, srs.lineup or []),
        }
    stats = (await db.execute(
        text("""SELECT AVG(points)::float AS avg, MAX(points)::float AS high, COUNT(*) AS teams
                FROM fantasy_squad_round_scores WHERE round_id = CAST(:rid AS UUID)"""),
        {"rid": str(target.id)},
    )).mappings().first()
    return {
        "round": {"number": target.round_number, "name": target.name, "status": target.status},
        "mine": mine,
        "stats": {"avg": round(stats["avg"], 1) if stats and stats["avg"] is not None else None,
                  "high": stats["high"] if stats else None, "teams": stats["teams"] if stats else 0},
        "rounds": [{"number": r.round_number, "status": r.status} for r in rounds],
    }


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
    await _assert_unlocked(db, season)
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
async def ladder(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """The club-wide salary-cap ladder, ranked by cumulative points, each row with
    its round-on-round movement (▲/▼) and last-round GW points. The signed-in
    manager's own squad is flagged so the UI can highlight it."""
    club = await _club_for_token(db, token)
    season = await _current_season(db, club)
    if season is None:
        return {"ladder": []}
    league = await _global_league(db, season)
    if league is None:
        return {"ladder": []}
    my_squad_id = None
    mid = _read_session(request, club.id)
    if mid:
        mine = (await db.execute(
            select(FantasySquad.id).where(FantasySquad.league_id == league.id, FantasySquad.manager_id == mid)
        )).scalar_one_or_none()
        my_squad_id = str(mine) if mine else None
    rows = await _league_standings(db, league_id=league.id)
    for r in rows:
        r["you"] = r["squad_id"] == my_squad_id
    return {"ladder": rows, "my_squad_id": my_squad_id}


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


def _round_locked(rnd: Optional[FantasyRound]) -> bool:
    """A round is locked once its first game has started and before it's scored —
    teams are frozen for the weekend, the FPL deadline behaviour."""
    return bool(rnd and rnd.lock_at and datetime.now(timezone.utc) >= rnd.lock_at and rnd.status != "scored")


async def _assert_unlocked(db: AsyncSession, season: FantasySeason) -> None:
    if _round_locked(await _current_round(db, season)):
        raise HTTPException(status_code=403, detail="This round has locked. You can change your team again once it's scored.")


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
    await _assert_unlocked(db, season)

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
    await _assert_unlocked(db, season)
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
    chip: str  # one of FANTASY_CHIPS


# How many of each chip a manager gets per half-season. Wildcard / triple-captain
# come from the rules (defaults 1); bench-boost / free-hit default to one a half.
_CHIP_ALLOW_KEY = {
    "wildcard": "wildcards_per_half",
    "triple_captain": "triple_captains_per_half",
    "bench_boost": "bench_boosts_per_half",
    "free_hit": "free_hits_per_half",
}

# Chips that mark the round-score row (only one such chip per round). Wildcard is
# separate — it lifts the free-transfer cap rather than tagging the round.
_ROUND_TAG_CHIPS = ("triple_captain", "bench_boost", "free_hit")


@router.post("/{token}/chip")
async def play_chip(token: str, body: ChipBody, request: Request, db: AsyncSession = Depends(get_db)):
    """Play a chip for the current round. Wildcard and Free Hit make this round's
    transfers free and unlimited; Triple Captain triples the captain; Bench Boost
    counts all 12. One of each per half. A round can carry only one round-tag chip
    (triple captain / bench boost / free hit)."""
    chip = body.chip
    if chip not in FANTASY_CHIPS:
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
    if _round_locked(rnd):
        raise HTTPException(status_code=403, detail="This round has locked.")

    total = (await db.execute(
        select(func.count()).select_from(FantasyRound).where(FantasyRound.fantasy_season_id == season.id)
    )).scalar_one() or 1
    half = 0 if (rnd.round_number - 1) < total / 2 else 1
    chips = dict(squad.chips_used or {})
    used = list(chips.get(chip, []))
    allow = int((season.rules or DEFAULT_RULES).get(_CHIP_ALLOW_KEY[chip], 1))
    used_this_half = sum(1 for rn in used if (0 if (rn - 1) < total / 2 else 1) == half)
    if used_this_half >= allow:
        raise HTTPException(status_code=409, detail="You've already used that chip this half of the season.")

    if chip in _ROUND_TAG_CHIPS:
        # Only one round-tag chip per round.
        existing = (await db.execute(
            text("SELECT chip_used FROM fantasy_squad_round_scores WHERE squad_id = CAST(:sid AS UUID) AND round_id = CAST(:rid AS UUID)"),
            {"sid": str(squad.id), "rid": str(rnd.id)},
        )).scalar_one_or_none()
        if existing and existing != chip:
            raise HTTPException(status_code=409, detail="You've already played a chip on this round.")
        await db.execute(
            text("""
                INSERT INTO fantasy_squad_round_scores (squad_id, round_id, chip_used, lineup)
                VALUES (CAST(:sid AS UUID), CAST(:rid AS UUID), :chip, '[]')
                ON CONFLICT (squad_id, round_id) DO UPDATE SET chip_used = :chip
            """),
            {"sid": str(squad.id), "rid": str(rnd.id), "chip": chip},
        )
    if chip in ("wildcard", "free_hit"):
        # Free, unlimited transfers for this round; rollover resets it at settle.
        squad.free_transfers = 9999

    chips[chip] = used + [rnd.round_number]
    squad.chips_used = chips  # reassign so the JSONB change is flagged
    db.add(FantasyTransaction(squad_id=squad.id, league_id=squad.league_id, round_id=rnd.id, type="chip",
                              detail={"chip": chip, "round": rnd.round_number}))
    await db.commit()
    return {"ok": True, "chip": chip, "round": rnd.round_number}


@router.post("/{token}/chip/cancel")
async def cancel_chip(token: str, body: ChipBody, request: Request, db: AsyncSession = Depends(get_db)):
    """Un-arm a chip while the round is still open (the Chips screen 'Cancel for
    this round'). Frees the play back up so it can be used another round."""
    chip = body.chip
    if chip not in FANTASY_CHIPS:
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
    if rnd is None or _round_locked(rnd):
        raise HTTPException(status_code=403, detail="This round has locked.")

    chips = dict(squad.chips_used or {})
    used = [rn for rn in list(chips.get(chip, [])) if rn != rnd.round_number]
    chips[chip] = used
    squad.chips_used = chips
    if chip in _ROUND_TAG_CHIPS:
        await db.execute(
            text("UPDATE fantasy_squad_round_scores SET chip_used = NULL "
                 "WHERE squad_id = CAST(:sid AS UUID) AND round_id = CAST(:rid AS UUID) AND chip_used = :chip"),
            {"sid": str(squad.id), "rid": str(rnd.id), "chip": chip},
        )
    if chip in ("wildcard", "free_hit"):
        squad.free_transfers = int((season.rules or DEFAULT_RULES).get("free_transfers_per_round", 1))
    await db.commit()
    return {"ok": True, "chip": chip}


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


async def _mini_member_squads(db: AsyncSession, league_id) -> list:
    """The squad ids backing a mini-league's members (each points at their global
    salary-cap squad)."""
    return [
        sid for (sid,) in (await db.execute(
            select(FantasyLeagueMember.squad_id).where(
                FantasyLeagueMember.league_id == league_id, FantasyLeagueMember.squad_id.isnot(None))
        )).all()
    ]


@router.get("/{token}/leagues")
async def my_leagues(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """The mini-leagues this manager is in, each with its ranked ladder (movement
    deltas and the manager's own row flagged)."""
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    if season is None:
        return {"leagues": []}
    my_squad = await _global_squad(db, season, mgr)
    my_squad_id = str(my_squad.id) if my_squad else None
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
        sids = await _mini_member_squads(db, lg.id)
        rows = await _league_standings(db, squad_ids=sids)
        for r in rows:
            r["you"] = r["squad_id"] == my_squad_id
        out.append({
            "id": str(lg.id), "name": lg.name, "join_code": lg.join_code,
            "members": len(sids), "ladder": rows,
        })
    return {"leagues": out}


@router.get("/{token}/leagues/{league_id}")
async def league_detail(token: str, league_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """A single mini-league: full standings with movement, the manager's own
    matchup snapshot for the latest scored round, and the meta the About tab shows."""
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    if season is None:
        raise HTTPException(status_code=404, detail="No fantasy season")
    lg = await db.get(FantasyLeague, league_id)
    if lg is None or str(lg.fantasy_season_id) != str(season.id) or lg.kind != "mini_salary_cap":
        raise HTTPException(status_code=404, detail="League not found")
    member = (await db.execute(
        select(FantasyLeagueMember).where(
            FantasyLeagueMember.league_id == lg.id, FantasyLeagueMember.manager_id == mgr.id)
    )).scalar_one_or_none()
    sids = await _mini_member_squads(db, lg.id)
    my_squad = await _global_squad(db, season, mgr)
    my_squad_id = str(my_squad.id) if my_squad else None
    rows = await _league_standings(db, squad_ids=sids)
    for r in rows:
        r["you"] = r["squad_id"] == my_squad_id
    creator = await db.get(FantasyManager, lg.created_by_manager_id) if lg.created_by_manager_id else None
    return {
        "id": str(lg.id), "name": lg.name, "join_code": lg.join_code,
        "members": len(sids), "scoring": "classic",
        "is_member": member is not None,
        "created_by": creator.display_name if creator else None,
        "my_squad_id": my_squad_id,
        "ladder": rows,
    }


@router.post("/{token}/leagues/{league_id}/leave")
async def leave_league(token: str, league_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Leave a mini-league (the global club ladder can't be left)."""
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    if season is None:
        raise HTTPException(status_code=404, detail="No fantasy season")
    lg = await db.get(FantasyLeague, league_id)
    if lg is None or str(lg.fantasy_season_id) != str(season.id) or lg.kind != "mini_salary_cap":
        raise HTTPException(status_code=404, detail="League not found")
    member = (await db.execute(
        select(FantasyLeagueMember).where(
            FantasyLeagueMember.league_id == lg.id, FantasyLeagueMember.manager_id == mgr.id)
    )).scalar_one_or_none()
    if member is not None:
        await db.delete(member)
        await db.commit()
    return {"ok": True}


@router.get("/{token}/h2h/{league_id}")
async def head_to_head(token: str, league_id: str, request: Request, db: AsyncSession = Depends(get_db),
                       round: Optional[int] = None, opponent_squad_id: Optional[str] = None):
    """A round head-to-head between the manager's squad and an opponent in a
    mini-league: each side's score and a per-line comparison (captain, top batter,
    top bowler, bench). Opponent defaults to the nearest-ranked rival."""
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    if season is None:
        raise HTTPException(status_code=404, detail="No fantasy season")
    lg = await db.get(FantasyLeague, league_id)
    if lg is None or str(lg.fantasy_season_id) != str(season.id):
        raise HTTPException(status_code=404, detail="League not found")
    sids = await _mini_member_squads(db, lg.id)
    standings = await _league_standings(db, squad_ids=sids)
    my_squad = await _global_squad(db, season, mgr)
    my_squad_id = str(my_squad.id) if my_squad else None
    if my_squad_id is None or my_squad_id not in {r["squad_id"] for r in standings}:
        raise HTTPException(status_code=400, detail="Build a squad and join this league first.")
    # Pick the opponent: explicit, else the squad next to me on the table.
    opp_id = opponent_squad_id
    if opp_id is None:
        order = [r["squad_id"] for r in standings]
        idx = order.index(my_squad_id)
        opp_id = order[idx + 1] if idx + 1 < len(order) else (order[idx - 1] if idx > 0 else None)
    if opp_id is None:
        return {"round": None, "me": None, "opp": None, "rows": []}

    rounds = (await db.execute(
        select(FantasyRound).where(FantasyRound.fantasy_season_id == season.id, FantasyRound.status == "scored")
        .order_by(FantasyRound.round_number.desc())
    )).scalars().all()
    target = next((r for r in rounds if r.round_number == round), rounds[0] if rounds else None)
    if target is None:
        return {"round": None, "me": None, "opp": None, "rows": []}

    names = {str(s): (tn, dn) for s, tn, dn in (await db.execute(
        select(FantasySquad.id, FantasySquad.team_name, FantasyManager.display_name)
        .join(FantasyManager, FantasyManager.id == FantasySquad.manager_id)
        .where(FantasySquad.id.in_([uuid.UUID(my_squad_id), uuid.UUID(opp_id)]))
    )).all()}

    async def _side(sid):
        srs = (await db.execute(
            select(FantasySquadRoundScore).where(
                FantasySquadRoundScore.squad_id == uuid.UUID(sid), FantasySquadRoundScore.round_id == target.id)
        )).scalar_one_or_none()
        lineup = (srs.lineup if srs else []) or []
        return srs, await _enrich_lineup(db, lineup, sort=False)

    my_srs, my_line = await _side(my_squad_id)
    op_srs, op_line = await _side(opp_id)

    def _cap(line):
        e = next((x for x in line if x.get("captained")), None)
        return f'{e["name"]} · {round_num(e)}' if e else "—", (e["eff_points"] if e else 0)

    def round_num(e):
        return int(round(float(e.get("eff_points", e.get("points", 0)) or 0)))

    def _top(line, role, counted_only=True):
        cand = [x for x in line if x.get("role") == role and (x.get("counted") if counted_only else True)]
        e = max(cand, key=lambda x: float(x.get("points", 0) or 0)) if cand else None
        return (f'{e["name"]} · {round_num(e)}', float(e.get("points", 0) or 0)) if e else ("—", 0)

    def _bench(line):
        pts = sum(float(x.get("points", 0) or 0) for x in line if not x.get("counted"))
        return (f"{int(round(pts))}", pts)

    rows = []
    for label, fn in [("Captain", _cap), ("Top batter", lambda l: _top(l, "batter")),
                      ("Top bowler", lambda l: _top(l, "bowler")), ("Bench pts", _bench)]:
        m_txt, m_val = fn(my_line)
        o_txt, o_val = fn(op_line)
        rows.append({"role": label, "mine": m_txt, "theirs": o_txt,
                     "me_lead": m_val > o_val, "opp_lead": o_val > m_val})

    return {
        "round": {"number": target.round_number, "name": target.name},
        "me": {"squad_id": my_squad_id, "team": names.get(my_squad_id, ("?", "?"))[0],
               "manager": names.get(my_squad_id, ("?", "?"))[1],
               "score": float(my_srs.points) if my_srs else 0.0},
        "opp": {"squad_id": opp_id, "team": names.get(opp_id, ("?", "?"))[0],
                "manager": names.get(opp_id, ("?", "?"))[1],
                "score": float(op_srs.points) if op_srs else 0.0},
        "rows": rows,
    }


# ── rounds / fixtures + live ─────────────────────────────────────────────────

@router.get("/{token}/rounds")
async def rounds_list(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Every round with its lock time, status and the manager's points (Fixtures
    screen). The current unscored round is flagged live once it has locked."""
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    if season is None:
        return {"rounds": []}
    rounds = (await db.execute(
        select(FantasyRound).where(FantasyRound.fantasy_season_id == season.id).order_by(FantasyRound.round_number)
    )).scalars().all()
    squad = await _global_squad(db, season, mgr)
    my_pts: dict[int, float] = {}
    if squad is not None:
        for rn, pts in (await db.execute(
            text("""SELECT r.round_number, srs.points FROM fantasy_squad_round_scores srs
                    JOIN fantasy_rounds r ON r.id = srs.round_id
                    WHERE srs.squad_id = CAST(:sid AS UUID)"""),
            {"sid": str(squad.id)},
        )).all():
            my_pts[rn] = float(pts)
    out = []
    for r in rounds:
        if r.status == "scored":
            state = "scored"
        elif _round_locked(r):
            state = "live"
        else:
            state = "upcoming"
        out.append({
            "number": r.round_number, "name": r.name, "status": state,
            "lock_at": r.lock_at.isoformat() if r.lock_at else None,
            "start_date": r.start_date.isoformat() if r.start_date else None,
            "my_points": my_pts.get(r.round_number),
        })
    return {"rounds": out}


@router.get("/{token}/live")
async def live(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Provisional points for the round in progress, computed live from whatever
    scorecards have synced so far (no writes). Returns the latest scored round if
    nothing is in progress, so the screen always has something to show."""
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    if season is None:
        return {"live": False, "round": None}
    squad = await _global_squad(db, season, mgr)
    if squad is None:
        return {"live": False, "round": None}
    rnd = await _current_round(db, season)
    is_live = bool(rnd and _round_locked(rnd))
    if not is_live:
        # Fall back to the most recent scored round breakdown.
        data = await round_view(token, request, db, n=None)
        return {"live": False, "round": data.get("round"), "mine": data.get("mine"),
                "overall_rank": await _overall_rank(db, squad.league_id, squad.id)}

    # Provisional: score the in-progress round read-only and roll the best-11.
    by_player = await fantasy_engine._round_player_scores(db, season, rnd)
    score_by_player = {pid: (sc["total"], sc["games"]) for pid, sc in by_player.items()}
    picks = (await db.execute(
        select(FantasySquadPlayer).where(FantasySquadPlayer.squad_id == squad.id)
    )).scalars().all()
    cur_chip = (await db.execute(
        text("SELECT chip_used FROM fantasy_squad_round_scores WHERE squad_id = CAST(:sid AS UUID) AND round_id = CAST(:rid AS UUID)"),
        {"sid": str(squad.id), "rid": str(rnd.id)},
    )).scalar_one_or_none()
    rules = season.rules or DEFAULT_RULES
    best_n = rules.get("squad_size", 12) if cur_chip == "bench_boost" else rules.get("count_best_n", 11)
    res = score_squad_round(picks, score_by_player, best_n, season.scoring or DEFAULT_SCORING,
                            is_triple=(cur_chip == "triple_captain"))
    # Provisional rank: where this live total would sit among current totals.
    others = (await db.execute(
        text("""SELECT total_points FROM fantasy_squads
                WHERE league_id = CAST(:lid AS UUID) AND id <> CAST(:sid AS UUID)"""),
        {"lid": str(squad.league_id), "sid": str(squad.id)},
    )).scalars().all()
    live_total = float(squad.total_points) + res["points"]
    prov_rank = 1 + sum(1 for t in others if float(t) > live_total)
    playing = sum(1 for e in res["lineup"] if (e.get("games") or score_by_player.get(e["player_id"], (0, 0))[1]))
    return {
        "live": True,
        "round": {"number": rnd.round_number, "name": rnd.name, "status": "live"},
        "mine": {
            "points": res["points"], "raw_points": res["raw_points"],
            "transfer_hit": 0, "chip_used": cur_chip,
            "lineup": await _enrich_lineup(db, res["lineup"]),
        },
        "playing_now": playing,
        "provisional_rank": prov_rank,
        "overall_rank": await _overall_rank(db, squad.league_id, squad.id),
    }


# ── player detail ────────────────────────────────────────────────────────────

@router.get("/{token}/player/{player_id}")
async def player_detail(token: str, player_id: str, db: AsyncSession = Depends(get_db)):
    """Per-player detail for the Player profile screen: price, form, ownership,
    season stat tiles, last-5 round points (for the bar chart) and the upcoming
    rounds. Stats come from the held season aggregates; difficulty isn't modelled
    so upcoming rounds are returned without a hard/easy rating."""
    club = await _club_for_token(db, token)
    season = await _current_season(db, club)
    if season is None:
        raise HTTPException(status_code=404, detail="No fantasy season")
    pp = (await db.execute(
        select(FantasyPoolPlayer, Player).join(Player, Player.id == FantasyPoolPlayer.player_id)
        .where(FantasyPoolPlayer.fantasy_season_id == season.id, FantasyPoolPlayer.player_id == player_id)
    )).first()
    if pp is None:
        raise HTTPException(status_code=404, detail="Player not in the pool")
    pool, p = pp
    league = await _global_league(db, season)
    managers = await _manager_count(db, league.id) if league else 0
    teams = await _team_by_player(db, [pool.player_id])
    form = await _form_by_player(db, season.id)

    # Last-5 scored rounds for the form chart.
    last5 = (await db.execute(
        text("""
            SELECT r.round_number, prs.total_points
            FROM fantasy_player_round_scores prs
            JOIN fantasy_rounds r ON r.id = prs.round_id AND r.status = 'scored'
            WHERE prs.fantasy_season_id = CAST(:fs AS UUID) AND prs.player_id = CAST(:pid AS UUID)
            ORDER BY r.round_number DESC LIMIT 5
        """),
        {"fs": str(season.id), "pid": str(pool.player_id)},
    )).all()
    last5 = [{"round": rn, "points": float(pts)} for rn, pts in reversed(last5)]

    # Season aggregate stat tiles from the held BetterStats record.
    agg = (await db.execute(
        text("""
            SELECT COALESCE(SUM(pss.runs),0) runs, COALESCE(SUM(pss.wickets),0) wickets,
                   COALESCE(SUM(pss.fifties),0) fifties, COALESCE(SUM(pss.hundreds),0) hundreds,
                   COALESCE(SUM(pss.matches),0) matches, COALESCE(SUM(pss.catches),0) catches
            FROM v_effective_player_season_stats pss
            JOIN seasons s ON s.id = pss.season_id AND s.organisation_id = CAST(:org AS UUID) AND s.year = :yr
            WHERE pss.player_id = CAST(:pid AS UUID)
        """),
        {"org": str(club.id), "yr": season.season_year, "pid": str(pool.player_id)},
    )).mappings().first() or {}

    # Career aggregate across every held season for this club (all years).
    career = (await db.execute(
        text("""
            SELECT COALESCE(SUM(pss.runs),0) runs, COALESCE(SUM(pss.wickets),0) wickets,
                   COALESCE(SUM(pss.fifties),0) fifties, COALESCE(SUM(pss.hundreds),0) hundreds,
                   COALESCE(SUM(pss.matches),0) matches, COALESCE(SUM(pss.catches),0) catches,
                   COUNT(DISTINCT s.year) seasons
            FROM v_effective_player_season_stats pss
            JOIN seasons s ON s.id = pss.season_id AND s.organisation_id = CAST(:org AS UUID)
            WHERE pss.player_id = CAST(:pid AS UUID)
        """),
        {"org": str(club.id), "pid": str(pool.player_id)},
    )).mappings().first() or {}

    # Fantasy scoring breakdown: rounds played and the average points per scored round.
    scoring = (await db.execute(
        text("""
            SELECT COUNT(*) rounds, COALESCE(ROUND(AVG(prs.total_points)::numeric, 1), 0) avg
            FROM fantasy_player_round_scores prs
            JOIN fantasy_rounds r ON r.id = prs.round_id AND r.status = 'scored'
            WHERE prs.fantasy_season_id = CAST(:fs AS UUID) AND prs.player_id = CAST(:pid AS UUID)
        """),
        {"fs": str(season.id), "pid": str(pool.player_id)},
    )).mappings().first() or {}

    upcoming = (await db.execute(
        select(FantasyRound).where(
            FantasyRound.fantasy_season_id == season.id, FantasyRound.status != "scored")
        .order_by(FantasyRound.round_number).limit(3)
    )).scalars().all()

    sel = round(100.0 * pool.owned_count / managers, 1) if managers else 0.0
    return {
        "player_id": str(pool.player_id), "name": p.name, "role": pool.role,
        "price": float(pool.current_price), "price_change": float(pool.price_change),
        "team": teams.get(str(pool.player_id)),
        "selected_pct": sel, "form": form.get(str(pool.player_id), 0.0),
        "total_points": float(pool.total_points),
        "last_round_points": float(pool.last_round_points),
        "weekly_avg": float(scoring.get("avg", 0) or 0),
        "rounds_played": int(scoring.get("rounds", 0) or 0),
        **_player_card(p),
        "season_stats": {
            "runs": int(agg.get("runs", 0)), "wickets": int(agg.get("wickets", 0)),
            "fifties": int(agg.get("fifties", 0)), "hundreds": int(agg.get("hundreds", 0)),
            "matches": int(agg.get("matches", 0)), "catches": int(agg.get("catches", 0)),
        },
        "career_stats": {
            "runs": int(career.get("runs", 0)), "wickets": int(career.get("wickets", 0)),
            "fifties": int(career.get("fifties", 0)), "hundreds": int(career.get("hundreds", 0)),
            "matches": int(career.get("matches", 0)), "catches": int(career.get("catches", 0)),
            "seasons": int(career.get("seasons", 0)),
        },
        "last5": last5,
        "fixtures": [{"round": r.round_number, "name": r.name, "difficulty": "even"} for r in upcoming],
    }


# ── notifications + profile ──────────────────────────────────────────────────

@router.get("/{token}/notifications")
async def notifications(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """A synthesised activity feed for the signed-in manager from current state:
    the deadline reminder, price moves on owned players, league rank moves and the
    season top scorer. Each item has a stable id so the client can track read
    state locally."""
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    feed: list[dict] = []
    if season is None:
        return {"notifications": feed}
    squad = await _global_squad(db, season, mgr)
    rnd = await _current_round(db, season)
    if rnd is not None and rnd.lock_at and not _round_locked(rnd):
        feed.append({
            "id": f"lock-{rnd.round_number}", "tone": "accent", "badge": "!",
            "title": f"Round {rnd.round_number} locks soon",
            "body": "Set your captain and make transfers before the deadline.",
        })
    if squad is not None:
        # Price moves on owned players (last settled round).
        moves = (await db.execute(
            text("""
                SELECT p.name, pp.price_change, pp.player_id
                FROM fantasy_squad_players sp
                JOIN fantasy_pool_players pp ON pp.player_id = sp.player_id AND pp.fantasy_season_id = CAST(:fs AS UUID)
                JOIN players p ON p.id = sp.player_id
                WHERE sp.squad_id = CAST(:sid AS UUID) AND pp.price_change <> 0
                ORDER BY ABS(pp.price_change) DESC LIMIT 4
            """),
            {"fs": str(season.id), "sid": str(squad.id)},
        )).all()
        for name, chg, pid in moves:
            up = float(chg) > 0
            feed.append({
                "id": f"price-{pid}", "tone": "green" if up else "amber",
                "badge": "▲" if up else "▼",
                "title": f"{name} {'rose' if up else 'fell'} {abs(float(chg)):.1f}",
                "body": "A player you own moved in price.",
            })
        rank = await _overall_rank(db, squad.league_id, squad.id)
        if rank:
            feed.append({
                "id": f"rank-{rank}", "tone": "accent", "badge": "▲",
                "title": f"You're {rank}{_ord(rank)} on the club ladder",
                "body": "Your standing after the latest round.",
            })
    top = (await db.execute(
        text("""SELECT p.name, pp.total_points FROM fantasy_pool_players pp
                JOIN players p ON p.id = pp.player_id
                WHERE pp.fantasy_season_id = CAST(:fs AS UUID)
                ORDER BY pp.total_points DESC LIMIT 1"""),
        {"fs": str(season.id)},
    )).first()
    if top and float(top[1]) > 0:
        feed.append({
            "id": "top-scorer", "tone": "amber", "badge": "★",
            "title": f"{top[0]} is the top scorer",
            "body": f"{int(float(top[1]))} points across the season so far.",
        })

    # Draft activity: your turn / the live auction lot, trade offers, waiver results.
    draft_rows = (await db.execute(
        select(FantasyLeague, FantasyDraft)
        .join(FantasyLeagueMember, FantasyLeagueMember.league_id == FantasyLeague.id)
        .outerjoin(FantasyDraft, FantasyDraft.league_id == FantasyLeague.id)
        .where(FantasyLeagueMember.manager_id == mgr.id,
               FantasyLeague.kind == "draft", FantasyLeague.fantasy_season_id == season.id)
    )).all()
    for lg, draft in draft_rows:
        if draft is None or draft.status != "in_progress":
            continue
        if draft.type == "auction":
            order = draft.draft_order or []
            if draft.lot_player_id is None:
                if order and str(order[draft.nomination_index % len(order)]) == str(mgr.id):
                    feed.append({"id": f"draft-nom-{lg.id}", "tone": "accent", "badge": "!",
                                 "title": "You're on the clock to nominate",
                                 "body": f"Put a player up for auction in {lg.name}."})
            else:
                lp = await db.get(Player, draft.lot_player_id)
                nm = lp.name if lp else "a player"
                top_bid = float(draft.lot_high_bid or 0)
                if str(draft.lot_high_bidder_id) == str(mgr.id):
                    feed.append({"id": f"draft-lot-{lg.id}-{draft.lot_player_id}", "tone": "green", "badge": "▲",
                                 "title": f"You lead the bidding on {nm}",
                                 "body": f"Top bid ${top_bid:.0f} in {lg.name}."})
                else:
                    feed.append({"id": f"draft-lot-{lg.id}-{draft.lot_player_id}", "tone": "accent", "badge": "!",
                                 "title": f"Bidding open on {nm}",
                                 "body": f"Top bid ${top_bid:.0f} in {lg.name}. Get a bid in."})
        else:
            cur = (await db.execute(
                select(FantasyDraftPick).where(
                    FantasyDraftPick.draft_id == draft.id, FantasyDraftPick.pick_index == draft.current_pick)
            )).scalar_one_or_none()
            if cur and str(cur.manager_id) == str(mgr.id):
                feed.append({"id": f"draft-clock-{lg.id}", "tone": "accent", "badge": "!",
                             "title": "You're on the clock",
                             "body": f"Make your pick in {lg.name}."})

    incoming = (await db.execute(
        select(FantasyTrade).join(FantasySquad, FantasySquad.id == FantasyTrade.receiver_squad_id)
        .where(FantasySquad.manager_id == mgr.id, FantasyTrade.status == "proposed",
               FantasyTrade.organisation_id == club.id)
    )).scalars().all()
    for t in incoming:
        prop = await db.get(FantasySquad, t.proposer_squad_id)
        feed.append({"id": f"trade-{t.id}", "tone": "accent", "badge": "+",
                     "title": "New trade offer",
                     "body": f"{prop.team_name if prop else 'A manager'} wants to trade. Open Manage team to respond."})

    claims = (await db.execute(
        select(FantasyWaiverClaim).where(
            FantasyWaiverClaim.manager_id == mgr.id, FantasyWaiverClaim.organisation_id == club.id,
            FantasyWaiverClaim.status.in_(["approved", "rejected"]))
        .order_by(FantasyWaiverClaim.processed_at.desc()).limit(5)
    )).scalars().all()
    for c in claims:
        addp = await db.get(Player, c.add_player_id)
        ok = c.status == "approved"
        feed.append({"id": f"waiver-{c.id}", "tone": "green" if ok else "amber", "badge": "▲" if ok else "▼",
                     "title": f"Waiver {'granted' if ok else 'missed'}",
                     "body": f"Your claim for {addp.name if addp else 'a player'} was {c.status}."})

    return {"notifications": feed}


def _ord(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


class ProfileBody(BaseModel):
    team_name: Optional[str] = None
    pin: Optional[str] = None


@router.post("/{token}/profile")
async def update_profile(token: str, body: ProfileBody, request: Request, db: AsyncSession = Depends(get_db)):
    """Rename the team and / or change the PIN. Theme and notification prefs are a
    local-only setting in the client, so they don't post here."""
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    rate_limit.enforce(f"fantasy-write:{mgr.id}", WRITE_LIMIT, WRITE_WINDOW)
    if body.team_name is not None and season is not None:
        name = body.team_name.strip()
        if name:
            squad = await _global_squad(db, season, mgr)
            if squad is not None:
                squad.team_name = name
    if body.pin is not None:
        pin = body.pin.strip()
        if len(pin) < 4:
            raise HTTPException(status_code=400, detail="PIN must be at least 4 digits.")
        mgr.credential_hash = _hash_pin(pin)
    await db.commit()
    return {"ok": True}


# ── draft mode (public) ──────────────────────────────────────────────────────

async def _draft_for(db: AsyncSession, league_id) -> Optional[FantasyDraft]:
    return (await db.execute(select(FantasyDraft).where(FantasyDraft.league_id == league_id))).scalar_one_or_none()


async def _draft_league(db: AsyncSession, club, season, league_id) -> FantasyLeague:
    lg = await db.get(FantasyLeague, league_id)
    if lg is None or str(lg.organisation_id) != str(club.id) or lg.kind != "draft" or str(lg.fantasy_season_id) != str(season.id):
        raise HTTPException(status_code=404, detail="Draft league not found")
    return lg


@router.get("/{token}/draft-leagues")
async def list_draft_leagues(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """The club's draft leagues, with whether this manager has joined and the size cap."""
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    if season is None:
        return {"leagues": []}
    rules = season.rules or DEFAULT_RULES
    size = int(rules.get("squad_size", 12))
    pool_n = (await db.execute(
        select(func.count()).select_from(FantasyPoolPlayer).where(FantasyPoolPlayer.fantasy_season_id == season.id)
    )).scalar_one()
    leagues = (await db.execute(
        select(FantasyLeague).where(FantasyLeague.fantasy_season_id == season.id, FantasyLeague.kind == "draft")
    )).scalars().all()
    mine = set((await db.execute(
        select(FantasyLeagueMember.league_id).where(FantasyLeagueMember.manager_id == mgr.id)
    )).scalars().all())
    out = []
    for lg in leagues:
        members = (await db.execute(
            select(func.count()).select_from(FantasyLeagueMember).where(FantasyLeagueMember.league_id == lg.id)
        )).scalar_one()
        draft = await _draft_for(db, lg.id)
        out.append({
            "id": str(lg.id), "name": lg.name, "draft_type": lg.draft_type, "scoring_type": lg.scoring_type,
            "status": lg.status, "members": members, "capacity": max(2, pool_n // size),
            "joined": lg.id in mine, "draft_status": draft.status if draft else None,
        })
    return {"leagues": out}


@router.post("/{token}/draft-leagues/{league_id}/join")
async def join_draft_league(token: str, league_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    if season is None:
        raise HTTPException(status_code=404, detail="No fantasy season")
    lg = await _draft_league(db, club, season, league_id)
    draft = await _draft_for(db, lg.id)
    if draft and draft.status != "scheduled":
        raise HTTPException(status_code=409, detail="The draft has already started.")
    member = (await db.execute(
        select(FantasyLeagueMember).where(FantasyLeagueMember.league_id == lg.id, FantasyLeagueMember.manager_id == mgr.id)
    )).scalar_one_or_none()
    if member is not None:
        return {"ok": True}
    rules = season.rules or DEFAULT_RULES
    size = int(rules.get("squad_size", 12))
    pool_n = (await db.execute(
        select(func.count()).select_from(FantasyPoolPlayer).where(FantasyPoolPlayer.fantasy_season_id == season.id)
    )).scalar_one()
    members = (await db.execute(
        select(func.count()).select_from(FantasyLeagueMember).where(FantasyLeagueMember.league_id == lg.id)
    )).scalar_one()
    if members >= max(2, pool_n // size):
        raise HTTPException(status_code=409, detail="That draft league is full.")
    db.add(FantasyLeagueMember(league_id=lg.id, manager_id=mgr.id))
    await db.commit()
    return {"ok": True}


@router.get("/{token}/draft/{league_id}")
async def draft_state(token: str, league_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """The live draft board: order, picks made, who's on the clock, and the players
    still available. Resolves any lapsed pick clocks on the way in."""
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    lg = await _draft_league(db, club, season, league_id)
    draft = await _draft_for(db, lg.id)
    if draft is None:
        return {"status": "not_started", "scoring_type": lg.scoring_type, "draft_type": lg.draft_type}
    await fantasy_draft.resolve_overdue(db, draft, season)
    await db.commit()
    draft = await _draft_for(db, lg.id)

    if draft.type == "auction":
        view = await fantasy_draft.auction_view(db, draft, season, str(mgr.id))
        view["scoring_type"] = lg.scoring_type
        return view

    rules = season.rules or DEFAULT_RULES
    quota = rules.get("role_quota", DEFAULT_RULES["role_quota"])
    picks = (await db.execute(
        select(FantasyDraftPick).where(FantasyDraftPick.draft_id == draft.id).order_by(FantasyDraftPick.pick_index)
    )).scalars().all()
    mgr_names = {str(m.id): m.display_name for m in (await db.execute(
        select(FantasyManager).where(FantasyManager.organisation_id == club.id))).scalars().all()}
    pool_rows = (await db.execute(
        select(FantasyPoolPlayer, Player.name).join(Player, Player.id == FantasyPoolPlayer.player_id)
        .where(FantasyPoolPlayer.fantasy_season_id == season.id, FantasyPoolPlayer.is_available.is_(True))
    )).all()
    pool = {str(pp.player_id): {"name": nm, "role": pp.role, "price": float(pp.current_price)} for pp, nm in pool_rows}
    taken = {str(p.player_id) for p in picks if p.player_id}

    my_counts: dict[str, int] = {}
    for p in picks:
        if p.player_id and str(p.manager_id) == str(mgr.id):
            r = pool.get(str(p.player_id), {}).get("role", "")
            my_counts[r] = my_counts.get(r, 0) + 1

    cur = picks[draft.current_pick] if draft.current_pick < len(picks) else None
    wl_ids = (await db.execute(
        select(FantasyDraftWishlist.player_ids).where(
            FantasyDraftWishlist.draft_id == draft.id, FantasyDraftWishlist.manager_id == mgr.id)
    )).scalar_one_or_none() or []
    return {
        "status": draft.status, "scoring_type": lg.scoring_type, "draft_type": draft.type,
        "order": [mgr_names.get(m, "?") for m in (draft.draft_order or [])],
        "current_pick": draft.current_pick,
        "on_clock": None if not cur else {
            "manager": mgr_names.get(str(cur.manager_id), "?"),
            "deadline": cur.deadline.isoformat() if cur.deadline else None,
            "round": cur.round_no + 1,
        },
        "my_turn": bool(cur and str(cur.manager_id) == str(mgr.id) and draft.status == "in_progress"),
        "picks": [
            {"pick": p.pick_index + 1, "round": p.round_no + 1, "manager": mgr_names.get(str(p.manager_id), "?"),
             "player": pool.get(str(p.player_id), {}).get("name") if p.player_id else None,
             "auto": p.auto_picked}
            for p in picks if p.player_id
        ],
        "my_role_counts": my_counts, "quota": quota,
        "my_wishlist": [{"player_id": str(pid), "name": pool.get(str(pid), {}).get("name", "?"),
                         "role": pool.get(str(pid), {}).get("role", "")} for pid in wl_ids],
        "available": sorted(
            [{"player_id": pid, "name": v["name"], "role": v["role"], "price": v["price"]}
             for pid, v in pool.items() if pid not in taken],
            key=lambda x: x["price"], reverse=True,
        ),
    }


class DraftPick(BaseModel):
    player_id: str


@router.post("/{token}/draft/{league_id}/pick")
async def draft_pick(token: str, league_id: str, body: DraftPick, request: Request, db: AsyncSession = Depends(get_db)):
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    lg = await _draft_league(db, club, season, league_id)
    draft = await _draft_for(db, lg.id)
    if draft is None:
        raise HTTPException(status_code=400, detail="The draft hasn't started.")
    rate_limit.enforce(f"fantasy-write:{mgr.id}", WRITE_LIMIT, WRITE_WINDOW)
    try:
        await fantasy_draft.make_pick(db, draft, season, str(mgr.id), body.player_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return {"ok": True}


class Nomination(BaseModel):
    player_id: str
    opening_bid: Optional[float] = None


@router.post("/{token}/draft/{league_id}/nominate")
async def auction_nominate(token: str, league_id: str, body: Nomination, request: Request, db: AsyncSession = Depends(get_db)):
    """Auction: put a player up for bidding (you become the opening high bidder)."""
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    lg = await _draft_league(db, club, season, league_id)
    draft = await _draft_for(db, lg.id)
    if draft is None:
        raise HTTPException(status_code=400, detail="The draft hasn't started.")
    rate_limit.enforce(f"fantasy-write:{mgr.id}", WRITE_LIMIT, WRITE_WINDOW)
    try:
        await fantasy_draft.nominate(db, draft, season, str(mgr.id), body.player_id, body.opening_bid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return {"ok": True}


class Bid(BaseModel):
    amount: float


@router.post("/{token}/draft/{league_id}/bid")
async def auction_bid(token: str, league_id: str, body: Bid, request: Request, db: AsyncSession = Depends(get_db)):
    """Auction: bid on the player currently up for auction."""
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    lg = await _draft_league(db, club, season, league_id)
    draft = await _draft_for(db, lg.id)
    if draft is None:
        raise HTTPException(status_code=400, detail="The draft hasn't started.")
    rate_limit.enforce(f"fantasy-write:{mgr.id}", WRITE_LIMIT, WRITE_WINDOW)
    try:
        await fantasy_draft.place_bid(db, draft, season, str(mgr.id), body.amount)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return {"ok": True}


class Wishlist(BaseModel):
    player_ids: list[str]


@router.put("/{token}/draft/{league_id}/wishlist")
async def set_wishlist(token: str, league_id: str, body: Wishlist, request: Request, db: AsyncSession = Depends(get_db)):
    """The ranked auto-pick list used if the manager's clock runs out."""
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    lg = await _draft_league(db, club, season, league_id)
    draft = await _draft_for(db, lg.id)
    if draft is None:
        raise HTTPException(status_code=400, detail="The draft hasn't started.")
    row = (await db.execute(
        select(FantasyDraftWishlist).where(
            FantasyDraftWishlist.draft_id == draft.id, FantasyDraftWishlist.manager_id == mgr.id)
    )).scalar_one_or_none()
    if row is None:
        db.add(FantasyDraftWishlist(draft_id=draft.id, manager_id=mgr.id, player_ids=body.player_ids))
    else:
        row.player_ids = body.player_ids
    await db.commit()
    return {"ok": True}


@router.get("/{token}/draft/{league_id}/ladder")
async def draft_ladder(token: str, league_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    club = await _club_for_token(db, token)
    await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    lg = await _draft_league(db, club, season, league_id)
    if lg.scoring_type == "h2h":
        return {"type": "h2h", "ladder": await fantasy_draft.h2h_ladder(db, lg.id)}
    rows = (await db.execute(
        select(FantasySquad.team_name, FantasyManager.display_name, FantasySquad.total_points)
        .join(FantasyManager, FantasyManager.id == FantasySquad.manager_id)
        .where(FantasySquad.league_id == lg.id).order_by(FantasySquad.total_points.desc())
    )).all()
    return {"type": "total", "ladder": [
        {"rank": i, "team_name": tn, "manager": dn, "points": float(pts)}
        for i, (tn, dn, pts) in enumerate(rows, start=1)
    ]}


@router.get("/{token}/draft/{league_id}/manage")
async def draft_manage(token: str, league_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """In-season management for a completed draft league: my squad, the other
    squads' rosters (for trades), the unowned pool (for waivers), my pending
    waiver claims and any trade offers in or out."""
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    lg = await _draft_league(db, club, season, league_id)

    pool_rows = (await db.execute(
        select(FantasyPoolPlayer.player_id, Player.name, FantasyPoolPlayer.role, FantasyPoolPlayer.current_price)
        .join(Player, Player.id == FantasyPoolPlayer.player_id)
        .where(FantasyPoolPlayer.fantasy_season_id == season.id, FantasyPoolPlayer.is_available.is_(True))
    )).all()
    pool = {str(pid): {"name": nm, "role": role, "price": float(pr)} for pid, nm, role, pr in pool_rows}

    squads = (await db.execute(select(FantasySquad).where(FantasySquad.league_id == lg.id))).scalars().all()
    mgr_names = {str(m.id): m.display_name for m in (await db.execute(
        select(FantasyManager).where(FantasyManager.organisation_id == club.id))).scalars().all()}
    sp_rows = (await db.execute(
        select(FantasySquadPlayer).where(FantasySquadPlayer.squad_id.in_([s.id for s in squads]))
    )).scalars().all() if squads else []
    by_squad: dict[str, list] = {}
    owned: set[str] = set()
    for sp in sp_rows:
        by_squad.setdefault(str(sp.squad_id), []).append(sp)
        owned.add(str(sp.player_id))

    def player_obj(sp):
        info = pool.get(str(sp.player_id), {})
        return {"player_id": str(sp.player_id), "name": info.get("name", "?"), "role": sp.role,
                "is_captain": sp.is_captain, "is_vice_captain": sp.is_vice_captain}

    my_squad, squads_out = None, []
    for s in squads:
        obj = {"squad_id": str(s.id), "team_name": s.team_name,
               "manager": mgr_names.get(str(s.manager_id), "?"), "is_me": str(s.manager_id) == str(mgr.id),
               "players": [player_obj(sp) for sp in by_squad.get(str(s.id), [])]}
        squads_out.append(obj)
        if obj["is_me"]:
            my_squad = obj
    my_squad_id = my_squad["squad_id"] if my_squad else None

    unowned = sorted(
        [{"player_id": pid, "name": v["name"], "role": v["role"], "price": v["price"]}
         for pid, v in pool.items() if pid not in owned],
        key=lambda x: x["price"], reverse=True,
    )

    wv = (await db.execute(
        select(FantasyWaiverClaim).where(
            FantasyWaiverClaim.league_id == lg.id, FantasyWaiverClaim.manager_id == mgr.id)
        .order_by(FantasyWaiverClaim.created_at.desc())
    )).scalars().all()
    my_waivers = [{
        "id": str(w.id), "status": w.status,
        "add": pool.get(str(w.add_player_id), {}).get("name", "?"),
        "drop": pool.get(str(w.drop_player_id), {}).get("name", "?") if w.drop_player_id else None,
    } for w in wv]

    squad_team = {str(s.id): s.team_name for s in squads}
    trade_rows = (await db.execute(
        select(FantasyTrade).where(FantasyTrade.league_id == lg.id, FantasyTrade.status == "proposed")
    )).scalars().all()

    def trade_obj(t):
        give = (t.offer or {}).get("give", [])
        get = (t.offer or {}).get("get", [])
        return {"id": str(t.id),
                "from": squad_team.get(str(t.proposer_squad_id), "?"),
                "to": squad_team.get(str(t.receiver_squad_id), "?"),
                "give": [pool.get(str(p), {}).get("name", "?") for p in give],
                "get": [pool.get(str(p), {}).get("name", "?") for p in get]}

    return {
        "scoring_type": lg.scoring_type,
        "my_squad": my_squad,
        "squads": squads_out,
        "unowned": unowned,
        "my_waivers": my_waivers,
        "trades": {
            "incoming": [trade_obj(t) for t in trade_rows if str(t.receiver_squad_id) == my_squad_id],
            "outgoing": [trade_obj(t) for t in trade_rows if str(t.proposer_squad_id) == my_squad_id],
        },
    }


class WaiverBody(BaseModel):
    add_player_id: str
    drop_player_id: str


@router.post("/{token}/draft/{league_id}/waiver")
async def submit_waiver(token: str, league_id: str, body: WaiverBody, request: Request, db: AsyncSession = Depends(get_db)):
    """Claim an unowned player, dropping one of yours. Processed by the admin in
    reverse-ladder order."""
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    lg = await _draft_league(db, club, season, league_id)
    db.add(FantasyWaiverClaim(
        league_id=lg.id, organisation_id=club.id, manager_id=mgr.id,
        add_player_id=body.add_player_id, drop_player_id=body.drop_player_id, status="pending",
    ))
    await db.commit()
    return {"ok": True}


class TradeBody(BaseModel):
    receiver_squad_id: str
    give: list[str]
    get: list[str]


@router.post("/{token}/draft/{league_id}/trade")
async def propose_trade(token: str, league_id: str, body: TradeBody, request: Request, db: AsyncSession = Depends(get_db)):
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    season = await _current_season(db, club)
    lg = await _draft_league(db, club, season, league_id)
    mine = (await db.execute(
        select(FantasySquad).where(FantasySquad.league_id == lg.id, FantasySquad.manager_id == mgr.id)
    )).scalar_one_or_none()
    if mine is None:
        raise HTTPException(status_code=400, detail="You're not in this league.")
    db.add(FantasyTrade(
        league_id=lg.id, organisation_id=club.id, proposer_squad_id=mine.id,
        receiver_squad_id=body.receiver_squad_id, offer={"give": body.give, "get": body.get}, status="proposed",
    ))
    await db.commit()
    return {"ok": True}


class TradeRespond(BaseModel):
    accept: bool


@router.post("/{token}/trades/{trade_id}/respond")
async def respond_trade(token: str, trade_id: str, body: TradeRespond, request: Request, db: AsyncSession = Depends(get_db)):
    club = await _club_for_token(db, token)
    mgr = await _manager_for_session(db, request, club)
    trade = await db.get(FantasyTrade, trade_id)
    if trade is None or str(trade.organisation_id) != str(club.id) or trade.status != "proposed":
        raise HTTPException(status_code=404, detail="Trade not found")
    receiver = await db.get(FantasySquad, trade.receiver_squad_id)
    if receiver is None or str(receiver.manager_id) != str(mgr.id):
        raise HTTPException(status_code=403, detail="That trade isn't yours to answer.")
    if not body.accept:
        trade.status = "rejected"
        await db.commit()
        return {"ok": True, "status": "rejected"}
    try:
        await fantasy_draft.apply_trade(db, trade)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return {"ok": True, "status": "accepted"}
