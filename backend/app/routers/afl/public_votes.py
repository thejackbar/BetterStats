"""BetterFootball — vote collection (public, unauthenticated).

Best-and-fairest votes via a per-medal magic link plus a last-4-of-phone PIN.
The same no-account posture the cricket page uses, and the same three controls:
a rotatable link token (identifies the medal only), the PIN (proves which
player you are), and a signed HttpOnly cookie (~30 days).

Who gets in:
  * Players verify with the PIN. Whether a verified player may vote on a game
    depends on the medal's config: 'players' mode = anyone named on the team
    sheet; 'captain' mode = only that game's captain.
  * Non-participants (coach, president, supporters) type a bare name — only
    when the medal's allow_non_participants toggle is on. Low-trust by design;
    the admin ballot list shows every name and can delete a spoof. A verified
    player who wasn't named also counts as a non-participant voter, which is a
    stronger identity than a typed name.

Votes only land on players named for the game, only while its window is open,
and the self-vote rule is enforced server-side. **No endpoint here ever returns
a tally** — the count stays admin-side, because a club keeps its B&F secret
until presentation night.

Not behind any module gate (there is no session to gate): each endpoint
resolves the club from the token and checks the medal's enabled flag itself.
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

from app.config.settings import settings
from app.models.afl import AflVoteBallot, AflVoteMedal
from app.models.db import Organisation, Player, get_db
from app.services import rate_limit
from app.services.afl import votes as vote_svc

router = APIRouter(prefix="/public/votes", tags=["afl-public-votes"])

COOKIE_NAME = "bs_vote"
SESSION_DAYS = 30

PIN_MAX_FAILURES = 5
PIN_LOCKOUT_SECONDS = 15 * 60
VERIFY_IP_LIMIT = 40
VERIFY_IP_WINDOW = 60
WRITE_LIMIT = 30
WRITE_WINDOW = 60
# Voting windows are days, not months, so a bounded scan keeps the landing
# cheap for a club with a decade of games.
LOOKBACK_DAYS = 120


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


def phone_last4(phone: Optional[str]) -> Optional[str]:
    digits = "".join(c for c in (phone or "") if c.isdigit())
    return digits[-4:] if len(digits) >= 4 else None


def _issue_cookie(response: Response, club_id, player_id) -> None:
    exp = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    token = jwt.encode(
        {"club": str(club_id), "pid": str(player_id), "typ": "vote", "exp": exp},
        settings.secret_key, algorithm=settings.algorithm)
    response.set_cookie(
        key=COOKIE_NAME, value=token, httponly=True, secure=settings.cookie_secure,
        samesite="lax", max_age=SESSION_DAYS * 24 * 60 * 60, path="/")


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


async def _club_for_token(db: AsyncSession, token: str) -> tuple[Organisation, AflVoteMedal]:
    """Resolve the club + MEDAL behind a vote link, or 404 telling nothing —
    the same posture the cricket link takes, so a guessed token can't be used
    to probe which clubs exist."""
    if not token:
        raise HTTPException(status_code=404, detail="Unknown link")
    medal = await vote_svc.medal_by_token(db, token)
    club = await db.get(Organisation, medal.organisation_id) if medal else None
    if medal is None or club is None or not medal.enabled:
        raise HTTPException(status_code=404, detail="This voting link isn't active")
    return club, medal


def _club_branding(club: Organisation) -> dict:
    return {
        "name": club.name, "short_name": club.short_name, "slug": club.slug,
        "logo_url": club.logo_url, "primary_color": club.primary_color,
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


async def _roster(db: AsyncSession, club: Organisation) -> list[Player]:
    """Who the "find your name" step offers: the club's active players."""
    res = await db.execute(
        select(Player)
        .where(Player.organisation_id == club.id, Player.status != "inactive")
        .order_by(Player.name)
    )
    return list(res.scalars().all())


async def _open_games(db: AsyncSession, club: Organisation, medal: AflVoteMedal, cfg: dict,
                      grade_id: Optional[str] = None) -> tuple[list[tuple[dict, str]], list[dict]]:
    """Recent games THIS MEDAL counts, with their voting state, newest first,
    plus the grade options for the filter.

    A medal restricted to its grades never lists a game outside them — someone
    following the Reserves link should not be offered the seniors' game.
    """
    today = date.today()
    rows = [
        r for r in await vote_svc.season_games(db, club.id, None)
        if r["played_at"] and r["played_at"] >= today - timedelta(days=LOOKBACK_DAYS)
    ]
    allowed = await vote_svc.medal_grade_ids(db, club.id, medal)
    rows = [r for r in rows if vote_svc.medal_covers(allowed, r.get("grade_id"))]

    grades = list({
        str(r["grade_id"]): {"id": str(r["grade_id"]), "name": r["grade_name"]}
        for r in rows if r["grade_id"]
    }.values())
    grades.sort(key=lambda g: g["name"])

    if grade_id:
        rows = [r for r in rows if str(r.get("grade_id")) == grade_id]
    if not rows:
        return [], grades

    from app.services.afl.lineups import lineup_counts
    expected = await lineup_counts(db, club.id, [r["id"] for r in rows])
    overrides = await vote_svc.overrides_by_game(db, medal.id, [r["id"] for r in rows])

    out = []
    for r in rows:
        ov = overrides.get(str(r["id"]))
        state = vote_svc.game_vote_state(
            r, cfg, ov.status if ov else None, expected.get(str(r["id"]), 0) > 0, today)
        out.append((r, state))
    return out, grades


@router.get("/{token}")
async def get_landing(token: str, request: Request, db: AsyncSession = Depends(get_db),
                      team: Optional[str] = None):
    """Club branding, the medal, the ballot shape, the open games and the name
    list for the verify step. Never returns tallies.

    ``team`` (one of the returned ``grades``' ids) narrows the list, so a club
    can hand out a link pre-scoped to one side rather than everyone wading
    through every grade's games to find their own.
    """
    club, medal = await _club_for_token(db, token)
    cfg = vote_svc.effective_config(medal)
    games, grades = await _open_games(db, club, medal, cfg, grade_id=team)
    me = await _verified_player(db, request, club)
    roster = await _roster(db, club)
    return {
        "club": _club_branding(club),
        # Named because a club can run several counts on separate links, and
        # the ballot shape alone doesn't say which award this one is.
        "medal": {"id": str(medal.id), "name": medal.name},
        "require_pin": bool(medal.require_pin),
        "voter_mode": cfg["voter_mode"],
        "allow_non_participants": cfg["allow_non_participants"],
        "allow_self_vote": cfg["allow_self_vote"],
        "ballot_values": cfg["ballot_values"],
        "me": {"id": str(me.id), "display_name": me.display_name} if me else None,
        "players": [
            {"id": str(p.id), "display_name": p.display_name,
             "has_phone": phone_last4(p.phone) is not None}
            for p in roster
        ],
        "grades": grades,
        "team": team,
        "games": [
            {
                "id": str(r["id"]),
                "opponent": vote_svc.game_label(r),
                "round": vote_svc.round_label_for(r),
                "grade": r["grade_name"],
                "date": r["played_at"].isoformat() if r["played_at"] else None,
                "state": state,
                "open": state == "open",
            }
            for r, state in games
        ],
    }


@router.post("/{token}/verify")
async def verify(token: str, body: VerifyBody, request: Request, response: Response,
                 db: AsyncSession = Depends(get_db)):
    """Prove which player you are with the last 4 digits of your phone.

    An unknown player and a wrong PIN both count as a failure and give the same
    message, so the link can't be used to enumerate the club's roster.
    """
    club, medal = await _club_for_token(db, token)
    ip = _client_ip(request)
    rate_limit.enforce(f"afl-vote-verify:{ip}", VERIFY_IP_LIMIT, VERIFY_IP_WINDOW)
    key = f"afl-vote:{token}:{body.player_id}:{ip}"
    rate_limit.assert_not_locked(key, PIN_MAX_FAILURES, PIN_LOCKOUT_SECONDS)

    try:
        pid = uuid.UUID(body.player_id)
    except ValueError:
        rate_limit.record_failure(key)
        raise HTTPException(status_code=400, detail="That didn't match. Check with your club.")

    player = await db.get(Player, pid)
    ok = bool(player and player.organisation_id == club.id)
    if ok and medal.require_pin:
        last4 = phone_last4(player.phone)
        ok = bool(last4) and (body.pin or "").strip() == last4
    if not ok:
        rate_limit.record_failure(key)
        raise HTTPException(status_code=400, detail="That didn't match. Check with your club.")

    rate_limit.clear_failures(key)
    _issue_cookie(response, club.id, player.id)
    return {"status": "ok", "me": {"id": str(player.id), "display_name": player.display_name}}


@router.post("/{token}/switch")
async def switch(token: str, response: Response, db: AsyncSession = Depends(get_db)):
    await _club_for_token(db, token)
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"status": "ok"}


def _voter_role(cfg: dict, me: Optional[Player], eligible: list[dict]) -> tuple[str, Optional[str]]:
    """('player' | 'non_player' | 'none', reason)."""
    eligible_ids = {p["id"] for p in eligible}
    captain_ids = {p["id"] for p in eligible if p.get("is_captain")}
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


@router.get("/{token}/games/{game_id}")
async def game_state(token: str, game_id: str, request: Request,
                     db: AsyncSession = Depends(get_db)):
    """One game's ballot page: who can be voted for, whether THIS caller can
    vote, and their own current ballot (players only — a typed-name voter just
    resubmits under the same name to change theirs)."""
    club, medal = await _club_for_token(db, token)
    cfg = vote_svc.effective_config(medal)
    try:
        gid = uuid.UUID(game_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid game")
    row = await vote_svc.get_game(db, club.id, gid)
    if not row:
        raise HTTPException(status_code=404, detail="Game not found")

    ov = await vote_svc.get_override(db, medal.id, row["id"])
    eligible, _ = await vote_svc.eligible_players(db, club.id, row["id"])
    state = vote_svc.game_vote_state(row, cfg, ov.status if ov else None, bool(eligible))
    me = await _verified_player(db, request, club)
    role, reason = _voter_role(cfg, me, eligible)

    my_ballot = None
    if me:
        res = await db.execute(select(AflVoteBallot).where(
            AflVoteBallot.medal_id == medal.id,
            AflVoteBallot.game_id == row["id"],
            AflVoteBallot.voter_player_id == me.id))
        b = res.scalar_one_or_none()
        if b:
            my_ballot = [str(p.player_id) for p in sorted(b.picks, key=lambda p: p.position)]

    return {
        "game": {
            "id": str(row["id"]),
            "opponent": vote_svc.game_label(row),
            "round": vote_svc.round_label_for(row),
            "grade": row["grade_name"],
            "date": row["played_at"].isoformat() if row["played_at"] else None,
            "state": state,
        },
        "medal": {"id": str(medal.id), "name": medal.name},
        "ballot_values": cfg["ballot_values"],
        "role": role,
        "reason": reason,
        "players": [{"id": p["id"], "name": p["name"]} for p in eligible],
        "my_ballot": my_ballot,
    }


@router.post("/{token}/games/{game_id}/ballot")
async def submit_ballot(token: str, game_id: str, body: BallotBody, request: Request,
                        db: AsyncSession = Depends(get_db)):
    """Cast (or update) a ballot. Verified players vote as themselves; a typed
    name is accepted only when the medal allows non-participant voting."""
    club, medal = await _club_for_token(db, token)
    cfg = vote_svc.effective_config(medal)
    rate_limit.enforce(f"afl-vote-write:{token}:{_client_ip(request)}", WRITE_LIMIT, WRITE_WINDOW)

    try:
        gid = uuid.UUID(game_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid game")
    row = await vote_svc.get_game(db, club.id, gid)
    if not row:
        raise HTTPException(status_code=404, detail="Game not found")

    ov = await vote_svc.get_override(db, medal.id, row["id"])
    eligible, _ = await vote_svc.eligible_players(db, club.id, row["id"])
    state = vote_svc.game_vote_state(row, cfg, ov.status if ov else None, bool(eligible))
    if state != "open":
        raise HTTPException(status_code=409, detail={
            "awaiting_team": "Voting opens once the team list for this game is in.",
            "upcoming": "This game hasn't been played yet.",
        }.get(state, "Voting has closed for this game."))

    me = await _verified_player(db, request, club)
    role, reason = _voter_role(cfg, me, eligible)
    if role == "none":
        raise HTTPException(status_code=403, detail={
            "captain_only": "Only the captain submits votes for this club.",
            "did_not_play": "Only players named for this game can vote.",
            "verify_required": "Find your name and verify with your PIN first.",
        }.get(reason, "You can't vote on this game."))

    voter_name = None
    if not me:
        voter_name = (body.voter_name or "").strip()[:120]
        if len(voter_name) < 2:
            raise HTTPException(status_code=400, detail="Enter your name so the club knows who voted")

    eligible_ids = {p["id"] for p in eligible}
    values = cfg["ballot_values"]
    if len(body.picks) != len(values):
        raise HTTPException(status_code=400, detail="Fill every voting position")
    if len(set(body.picks)) != len(body.picks):
        raise HTTPException(status_code=400, detail="Each position must be a different player")
    picks: list[uuid.UUID] = []
    for pid in body.picks:
        if pid not in eligible_ids:
            raise HTTPException(status_code=400, detail="Votes can only go to players named for this game")
        if me and pid == str(me.id) and not cfg["allow_self_vote"]:
            raise HTTPException(status_code=400, detail="Voting for yourself isn't allowed at this club")
        picks.append(uuid.UUID(pid))

    if me:
        res = await db.execute(select(AflVoteBallot).where(
            AflVoteBallot.medal_id == medal.id,
            AflVoteBallot.game_id == row["id"],
            AflVoteBallot.voter_player_id == me.id))
    else:
        res = await db.execute(select(AflVoteBallot).where(
            AflVoteBallot.medal_id == medal.id,
            AflVoteBallot.game_id == row["id"],
            AflVoteBallot.voter_player_id.is_(None),
            func.lower(AflVoteBallot.voter_name) == voter_name.lower()))
    ballot = res.scalar_one_or_none()
    if not ballot:
        ballot = AflVoteBallot(
            id=uuid.uuid4(), organisation_id=club.id, medal_id=medal.id,
            game_id=row["id"], voter_player_id=me.id if me else None,
            voter_name=voter_name,
            voter_kind="player" if role == "player" else "non_player",
            source="self")
        db.add(ballot)
        await db.flush()

    from app.routers.afl.votes import _replace_picks
    await _replace_picks(db, ballot, picks)
    await db.commit()
    return {"status": "ok"}
