"""BetterSelect — vote collection (public, unauthenticated).

Best-player votes via a per-club magic link + last-4-of-phone PIN — the same
no-account posture as the self-service availability page, and the same three
controls: a rotatable link token (identifies the club only), the PIN (proves
which player you are), and a signed HttpOnly cookie (~30 days).

Who gets in:
  * Players verify with the PIN. Whether a verified player may vote on a
    fixture depends on the club's config: 'players' mode = anyone who played
    in that game; 'captain' mode = only the game's captain.
  * Non-participants (coach / president / supporters) type a bare name — only
    when the club's allow_non_participants toggle is on. Low-trust by design;
    the admin ballot list shows every name and can delete spoof ballots. A
    verified player who DIDN'T play the game also counts as a non-participant
    voter (stronger identity than a typed name).

Votes only land on players who played (the synced scorecard), only while the
fixture's voting window is open, and the club's self-vote rule is enforced
server-side. Tallies are never returned by any endpoint here — the count
stays admin-side (many clubs keep it secret all season).

NOT behind require_module (no session): each endpoint resolves the club from
the token and checks entitlement + the enabled flag itself.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import MODULE_SELECT, org_has_module
from app.config.settings import settings
from app.models.db import Fixture, Organisation, Player, VoteBallot, VoteMedal, get_db
from app.routers.availability import active_self_service_players, phone_last4
from app.services import rate_limit
from app.services import votes as vote_svc

router = APIRouter(prefix="/public/votes", tags=["public-votes"])

COOKIE_NAME = "bs_vote"
SESSION_DAYS = 30

PIN_MAX_FAILURES = 5
PIN_LOCKOUT_SECONDS = 15 * 60
VERIFY_IP_LIMIT = 40
VERIFY_IP_WINDOW = 60
WRITE_LIMIT = 30
WRITE_WINDOW = 60
# How far back the public page lists fixtures — voting windows are days, not
# months, so a bounded scan keeps the landing cheap.
LOOKBACK_DAYS = 90


class VerifyBody(BaseModel):
    player_id: str
    pin: str = ""


class BallotBody(BaseModel):
    picks: list[str]  # player ids, position 1 (best) first
    voter_name: Optional[str] = None  # non-participant voters only


def _client_ip(request: Request) -> str:
    for header in ("cf-connecting-ip", "x-real-ip"):
        v = request.headers.get(header)
        if v:
            return v.strip()
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _issue_cookie(response: Response, club_id, player_id) -> None:
    exp = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    token = jwt.encode(
        {"club": str(club_id), "pid": str(player_id), "typ": "vote", "exp": exp},
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=SESSION_DAYS * 24 * 60 * 60,
        path="/",
    )


def _read_session(request: Request, club_id) -> Optional[uuid.UUID]:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    try:
        payload = jwt.decode(raw, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None
    if payload.get("typ") != "vote" or payload.get("club") != str(club_id):
        return None
    try:
        return uuid.UUID(payload["pid"])
    except (KeyError, ValueError, TypeError):
        return None


async def _club_for_token(db: AsyncSession, token: str) -> tuple[Organisation, VoteMedal]:
    """Resolve the club + MEDAL behind a vote-link token, or 404. Same
    tell-nothing 404 posture as the availability link.

    The token belongs to one medal, so a link decides which award the voter is
    voting for. A club's pre-medals club-wide token was carried onto its first
    medal by migration 267, so a link already in players' hands this season
    keeps working and lands on the count it always did."""
    if not token:
        raise HTTPException(status_code=404, detail="Unknown link")
    s = await vote_svc.medal_by_token(db, token)
    club = await db.get(Organisation, s.organisation_id) if s else None
    if s is None or club is None or not s.enabled or not org_has_module(club, MODULE_SELECT):
        raise HTTPException(status_code=404, detail="This voting link isn't active")
    return club, s


def _club_branding(club: Organisation) -> dict:
    return {
        "name": club.name,
        "short_name": club.short_name,
        "slug": club.slug,
        "logo_url": club.logo_url,
        "primary_color": club.primary_color,
        "accent_color": club.accent_color,
    }


async def _verified_player(db: AsyncSession, request: Request, club: Organisation) -> Optional[Player]:
    pid = _read_session(request, club.id)
    if not pid:
        return None
    player = await db.get(Player, pid)
    if not player or player.organisation_id != club.id:
        return None
    return player


async def _open_fixtures(
    db: AsyncSession, club: Organisation, cfg: dict, medal: VoteMedal,
    grade_id: Optional[str] = None, round_key: Optional[str] = None, q: Optional[str] = None,
) -> tuple[list[tuple[Fixture, str]], dict]:
    """Recent played fixtures THIS MEDAL counts, with their voting state,
    newest first, plus the filter option lists (``grades``/``rounds``).

    A medal restricted to a set of grades never lists a fixture outside them —
    a Colts voter following the Colts link should not be offered the senior
    game to vote on.

    ``grade_id``/``round_key``/``q`` narrow the list — the same filters the
    admin Fixtures tab has, so a club can share a link pre-scoped to one team
    (``?team=<grade_id>``) instead of everyone wading through every grade's
    fixtures to find their own. The option lists are always built from the
    WHOLE lookback window regardless of the other filters, so they don't
    collapse to the current selection.
    """
    today = date.today()
    res = await db.execute(
        select(Fixture)
        .where(
            Fixture.organisation_id == club.id,
            Fixture.played_on.is_not(None),
            Fixture.played_on <= today,
            Fixture.played_on >= today - timedelta(days=LOOKBACK_DAYS),
        )
        .order_by(Fixture.played_on.desc())
    )
    every_fixture = list(res.scalars().all())
    if not every_fixture:
        return [], {"grades": [], "rounds": []}

    from sqlalchemy import text

    # Resolve grades BEFORE narrowing to the medal's own set — a fixture that
    # carries its grade only on its synced game would otherwise drop out.
    grade_by_fixture = await vote_svc.effective_grade_ids(db, every_fixture)
    medal_grades = await vote_svc.medal_grade_ids(db, club.id, medal)
    all_fixtures = [
        f for f in every_fixture
        if vote_svc.medal_covers(medal_grades, grade_by_fixture.get(str(f.id)))
    ]
    if not all_fixtures:
        return [], {"grades": [], "rounds": []}
    grade_names: dict[str, str] = {}
    gids = {grade_by_fixture.get(str(f.id)) for f in all_fixtures}
    gids = {gid for gid in gids if gid}
    if gids:
        gn_res = await db.execute(text("SELECT id, name FROM grades WHERE id = ANY(:ids)"), {"ids": list(gids)})
        grade_names = {str(gid): name for gid, name in gn_res.fetchall()}
    grades_opt = sorted(
        ({"id": gid, "name": name} for gid, name in grade_names.items()), key=lambda g: g["name"],
    )

    rounds_seen: dict[str, tuple[str, Optional[date]]] = {}
    for f in all_fixtures:
        if grade_id and str(grade_by_fixture.get(str(f.id))) != grade_id:
            continue
        key = vote_svc.round_key_for(f)
        if key not in rounds_seen:
            rounds_seen[key] = (vote_svc.round_label_for(f), f.played_on)
    rounds_opt = [
        {"key": k, "label": lbl}
        for k, (lbl, d) in sorted(
            rounds_seen.items(), key=lambda kv: vote_svc.round_sort_key(kv[1][0], kv[1][1]), reverse=True,
        )
    ]

    fixtures = all_fixtures
    if grade_id:
        fixtures = [f for f in fixtures if str(grade_by_fixture.get(str(f.id))) == grade_id]
    if round_key:
        fixtures = [f for f in fixtures if vote_svc.round_key_for(f) == round_key.lower()]
    if q:
        ql = q.strip().lower()
        fixtures = [f for f in fixtures if ql in (f.opponent_name or f.label or "").lower()]
    if not fixtures:
        return [], {"grades": grades_opt, "rounds": rounds_opt}

    fids = [f.id for f in fixtures]
    match_ids = [vote_svc.match_ref_id(f) for f in fixtures]
    g_res = await db.execute(text("SELECT id FROM games WHERE id = ANY(:ids)"), {"ids": match_ids})
    synced_games = {str(r[0]) for r in g_res.fetchall()}
    synced = {str(f.id) for f in fixtures if str(vote_svc.match_ref_id(f)) in synced_games}
    l_res = await db.execute(
        text("SELECT DISTINCT fixture_id FROM fixture_lineups "
             "WHERE organisation_id = :org AND fixture_id = ANY(:ids)"),
        {"org": club.id, "ids": fids},
    )
    lineup_saved = {str(r[0]) for r in l_res.fetchall()}
    overrides = await vote_svc.overrides_by_fixture(db, medal.id, fids)
    out = []
    for f in fixtures:
        fid = str(f.id)
        ov = overrides.get(fid)
        source = vote_svc.effective_source(cfg, ov.eligibility_source if ov else None)
        # Cheap readiness (see the same note on the admin list): a per-fixture
        # live Play.Cricket check would be one upstream call per row, so the
        # ballot page does that check when a game is actually opened.
        ready = (
            fid in synced or fid in lineup_saved
            or (source == "playhq" and f.played_on is not None and f.played_on <= today)
        )
        state = vote_svc.fixture_vote_state(f, cfg, ov.status if ov else None, ready, today)
        out.append((f, state))
    return out, {"grades": grades_opt, "rounds": rounds_opt}


@router.get("/{token}")
async def get_landing(
    token: str, request: Request, db: AsyncSession = Depends(get_db),
    team: Optional[str] = None, round_key: Optional[str] = None, q: Optional[str] = None,
):
    """Club branding, the ballot shape, open fixtures, and the player name list
    for the verify step. Never returns tallies.

    ``team`` (one of the returned ``grades``' ids), ``round_key`` and ``q``
    (opponent search) narrow the fixture list — the same shape as the admin
    Fixtures tab filters, so a club can hand out a link pre-scoped to one
    team (``/vote/{token}?team=<grade_id>``) instead of a supporter hunting
    through every grade's games for their own.
    """
    club, s = await _club_for_token(db, token)
    cfg = vote_svc.effective_config(s)
    players = await active_self_service_players(db, club)
    me = await _verified_player(db, request, club)
    fixtures, filter_opts = await _open_fixtures(db, club, cfg, s, grade_id=team, round_key=round_key, q=q)
    return {
        "club": _club_branding(club),
        # Named so a player following one of several club links knows which
        # award they're voting for — the ballot shape alone doesn't say.
        "medal": {"id": str(s.id), "name": s.name},
        "require_pin": bool(s.require_pin),
        "voter_mode": cfg["voter_mode"],
        "allow_non_participants": cfg["allow_non_participants"],
        "allow_self_vote": cfg["allow_self_vote"],
        "ballot_values": cfg["ballot_values"],
        "me": {"id": str(me.id), "display_name": me.display_name} if me else None,
        "players": [
            {"id": str(p.id), "display_name": p.display_name,
             "has_phone": phone_last4(p.phone) is not None}
            for p in players
        ],
        "grades": filter_opts["grades"],
        "rounds": filter_opts["rounds"],
        "team": team,
        "round_key": round_key,
        "q": q,
        "fixtures": [
            {
                "id": str(f.id),
                "opponent": f.opponent_name or f.label,
                "round": vote_svc.round_label_for(f),
                "round_key": vote_svc.round_key_for(f),
                "date": f.played_on.isoformat() if f.played_on else None,
                "home_away": f.home_away,
                "state": state,
            }
            for f, state in fixtures
            if state in ("open", "awaiting_team", "closed", "locked")
        ],
    }


@router.post("/{token}/verify")
async def verify(token: str, body: VerifyBody, request: Request, response: Response,
                 db: AsyncSession = Depends(get_db)):
    """Prove identity with the last 4 of the player's mobile — identical
    mechanics (and lockout) to the availability link."""
    club, s = await _club_for_token(db, token)
    ip = _client_ip(request)
    rate_limit.enforce(
        f"vote-verify-ip:{token}:{ip}", VERIFY_IP_LIMIT, VERIFY_IP_WINDOW,
        detail="Too many attempts, slow down and try again shortly.",
    )

    try:
        pid = uuid.UUID(body.player_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid player")

    lock_key = f"vote-verify:{token}:{pid}:{ip}"
    rate_limit.assert_not_locked(
        lock_key, PIN_MAX_FAILURES, PIN_LOCKOUT_SECONDS,
        detail="Too many incorrect attempts. Please wait a few minutes and try again.",
    )

    player = await db.get(Player, pid)
    if not player or player.organisation_id != club.id or not player.is_player:
        rate_limit.record_failure(lock_key, PIN_LOCKOUT_SECONDS)
        raise HTTPException(status_code=401, detail="That didn't match. Check your details and try again.")

    if s.require_pin:
        want = phone_last4(player.phone)
        if want is None:
            raise HTTPException(
                status_code=409,
                detail="No mobile number is on file for you yet. Ask your club admin to add it, or to record your votes for you.",
            )
        given = phone_last4(body.pin)
        if given is None or given != want:
            rate_limit.record_failure(lock_key, PIN_LOCKOUT_SECONDS)
            raise HTTPException(status_code=401, detail="That PIN didn't match. Try the last 4 digits of your mobile.")

    rate_limit.clear_failures(lock_key)
    _issue_cookie(response, club.id, player.id)
    return {"status": "ok", "player": {"id": str(player.id), "display_name": player.display_name}}


@router.post("/{token}/switch")
async def switch_player(token: str, response: Response):
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"status": "ok"}


def _voter_role(cfg: dict, me: Optional[Player], eligible: list[dict]) -> tuple[str, Optional[str]]:
    """What this caller is allowed to do on a fixture.

    Returns (role, reason): role is 'player' (a counted participant ballot),
    'non_player' (allowed as a non-participant), or 'none' (can't vote —
    reason says why, for the UI)."""
    eligible_ids = {p["id"] for p in eligible}
    captain_ids = {p["id"] for p in eligible if p["is_captain"]}
    if me:
        mid = str(me.id)
        if mid in eligible_ids:
            if cfg["voter_mode"] == "captain" and mid not in captain_ids:
                return ("none", "captain_only")
            return ("player", None)
        if cfg["allow_non_participants"]:
            return ("non_player", None)
        return ("none", "did_not_play")
    if cfg["allow_non_participants"]:
        return ("non_player", None)
    return ("none", "verify_required")


@router.get("/{token}/fixtures/{fixture_id}")
async def fixture_state(token: str, fixture_id: str, request: Request,
                        db: AsyncSession = Depends(get_db)):
    """One fixture's ballot page: who can be voted for, whether THIS caller can
    vote, and their own current ballot (players only — a typed-name voter just
    resubmits under the same name to change theirs)."""
    club, s = await _club_for_token(db, token)
    cfg = vote_svc.effective_config(s)
    try:
        fid = uuid.UUID(fixture_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid fixture")
    fx = await db.get(Fixture, fid)
    if not fx or fx.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Fixture not found")

    ov = await vote_svc.get_override(db, s.id, fx.id)
    elig = await vote_svc.resolve_eligibility(
        db, club, fx, cfg, ov.eligibility_source if ov else None,
    )
    eligible = elig["players"]
    state = vote_svc.fixture_vote_state(fx, cfg, ov.status if ov else None, bool(eligible))
    me = await _verified_player(db, request, club)
    role, reason = _voter_role(cfg, me, eligible)

    my_ballot = None
    if me:
        res = await db.execute(select(VoteBallot).where(
            VoteBallot.medal_id == s.id,
            VoteBallot.fixture_id == fx.id,
            VoteBallot.voter_player_id == me.id,
        ))
        b = res.scalar_one_or_none()
        if b:
            my_ballot = [str(p.player_id) for p in sorted(b.picks, key=lambda p: p.position)]

    return {
        "club": _club_branding(club),
        "fixture": {
            "id": str(fx.id),
            "opponent": fx.opponent_name or fx.label,
            "round": vote_svc.round_label_for(fx),
            "date": fx.played_on.isoformat() if fx.played_on else None,
            "state": state,
        },
        "ballot_values": cfg["ballot_values"],
        "allow_self_vote": cfg["allow_self_vote"],
        "voter_mode": cfg["voter_mode"],
        "me": {"id": str(me.id), "display_name": me.display_name} if me else None,
        "role": role,
        "reason": reason,
        "players": [{"id": p["id"], "name": p["name"]} for p in eligible],
        "my_ballot": my_ballot,
    }


@router.post("/{token}/fixtures/{fixture_id}/ballot")
async def submit_ballot(token: str, fixture_id: str, body: BallotBody, request: Request,
                        db: AsyncSession = Depends(get_db)):
    """Cast (or update) a ballot. Verified players vote as themselves; a typed
    name is accepted only when the club allows non-participant voting."""
    club, s = await _club_for_token(db, token)
    cfg = vote_svc.effective_config(s)
    ip = _client_ip(request)
    rate_limit.enforce(f"vote-write:{token}:{ip}", WRITE_LIMIT, WRITE_WINDOW)

    try:
        fid = uuid.UUID(fixture_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid fixture")
    fx = await db.get(Fixture, fid)
    if not fx or fx.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Fixture not found")

    ov = await vote_svc.get_override(db, s.id, fx.id)
    elig = await vote_svc.resolve_eligibility(
        db, club, fx, cfg, ov.eligibility_source if ov else None,
    )
    eligible = elig["players"]
    state = vote_svc.fixture_vote_state(fx, cfg, ov.status if ov else None, bool(eligible))
    if state != "open":
        detail = {
            "awaiting_team": "Voting opens once the team list for this game is in.",
            "upcoming": "This game hasn't been played yet.",
        }.get(state, "Voting has closed for this game.")
        raise HTTPException(status_code=409, detail=detail)

    me = await _verified_player(db, request, club)
    role, reason = _voter_role(cfg, me, eligible)
    if role == "none":
        detail = {
            "captain_only": "Only the captain submits votes for this club.",
            "did_not_play": "Only players who played in this game can vote.",
            "verify_required": "Find your name and verify with your PIN first.",
        }.get(reason, "You can't vote on this game.")
        raise HTTPException(status_code=403, detail=detail)

    voter_name = None
    if not me:
        voter_name = (body.voter_name or "").strip()[:120]
        if len(voter_name) < 2:
            raise HTTPException(status_code=400, detail="Enter your name so the club knows who voted")

    eligible_ids = {p["id"] for p in eligible}
    picks: list[uuid.UUID] = []
    values = cfg["ballot_values"]
    if len(body.picks) != len(values):
        raise HTTPException(status_code=400, detail="Fill every voting position")
    if len(set(body.picks)) != len(body.picks):
        raise HTTPException(status_code=400, detail="Each position must be a different player")
    for pid in body.picks:
        if pid not in eligible_ids:
            raise HTTPException(status_code=400, detail="Votes can only go to players who played in this game")
        if me and pid == str(me.id) and not cfg["allow_self_vote"]:
            raise HTTPException(status_code=400, detail="Voting for yourself isn't allowed at this club")
        picks.append(uuid.UUID(pid))

    if me:
        res = await db.execute(select(VoteBallot).where(
            VoteBallot.medal_id == s.id,
            VoteBallot.fixture_id == fx.id,
            VoteBallot.voter_player_id == me.id,
        ))
    else:
        res = await db.execute(select(VoteBallot).where(
            VoteBallot.medal_id == s.id,
            VoteBallot.fixture_id == fx.id,
            VoteBallot.voter_player_id.is_(None),
            func.lower(VoteBallot.voter_name) == voter_name.lower(),
        ))
    ballot = res.scalar_one_or_none()
    if not ballot:
        ballot = VoteBallot(
            organisation_id=club.id,
            medal_id=s.id,
            fixture_id=fx.id,
            voter_player_id=me.id if me else None,
            voter_name=voter_name,
            voter_kind="player" if role == "player" else "non_player",
            source="self",
        )
        db.add(ballot)
        await db.flush()
    else:
        ballot.voter_kind = "player" if role == "player" else "non_player"
        ballot.source = "self"
        ballot.updated_at = datetime.now(timezone.utc)

    from sqlalchemy import delete
    from app.models.db import VoteBallotPick
    await db.execute(delete(VoteBallotPick).where(VoteBallotPick.ballot_id == ballot.id))
    for i, pid in enumerate(picks, start=1):
        db.add(VoteBallotPick(ballot_id=ballot.id, position=i, player_id=pid))
    await db.commit()
    return {"status": "ok"}
