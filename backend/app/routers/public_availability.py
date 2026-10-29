"""BetterSelect — self-service player availability (public, unauthenticated).

Players set their own availability for upcoming fixtures via a per-club magic
link + a last-4-of-phone PIN, with **no account and no app**. Three controls,
each doing one job (see docs/betterselect-self-availability.md):

  * **link token** — scopes/distributes the page. Pinned publicly (group chat /
    QR), so it's low-trust by design and rotatable. Identifies the club only.
  * **PIN** (last 4 of `Player.phone`) — proves *which* player you are. Low
    entropy (10k combos), so the lockout below is mandatory, not optional. A
    club may turn the PIN off (`availability_require_pin = false`).
  * **session cookie** (`bs_avail`, signed, HttpOnly, ~30d) — keeps you verified
    after the PIN. "Switch player" clears it.

The write endpoint only ever touches the *verified* player's availability and
only for *valid upcoming club fixture dates*, and exposes no PII beyond the
player's own name and the (semi-public) fixture list.

These routes are intentionally NOT behind `require_module` (the caller has no
session); instead each resolves the club from the token and checks the club is
both entitled to BetterSelect and has self-service enabled — a disabled or
downgraded club's link simply 404s.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import MODULE_SELECT, org_has_module
from app.config.settings import settings
from app.models.db import (
    FeeMember, FantasyManager, FantasyPoolPlayer, FantasyRound, FantasySquad, Grade, Organisation, Player, PlayerAvailability,
    Sponsor, VoteBallot, VoteMedal, get_db,
)
from app.routers.ladders import _compute_team_ladders
from app.routers import public_fantasy as pf
from app.routers import public_votes as pv
from app.routers.availability import (
    MAYBE_OFF,
    active_self_service_players,
    allow_maybe,
    audit_availability,
    local_now,
    phone_last4,
    upcoming_fixtures_by_date,
)
from app.services import fines as fines_svc, player_cards as cards_svc, player_dashboard, rate_limit, section_names, selection_rules as rules_svc, squad_sides
from app.services import votes as vote_svc
from app.services.fonts import public_font_fields
from app.services.grade_labels import categories_for_name, org_grade_category_sets
from app.services.squad_next_game import fixtures_for_player
from app.services.session_safety import rollback_keeping

router = APIRouter(prefix="/public/availability", tags=["public-availability"])

logger = logging.getLogger(__name__)

COOKIE_NAME = "bs_avail"
SESSION_DAYS = 30

# PIN lockout: 5 wrong attempts inside 15 minutes (per player + IP) → cooldown.
PIN_MAX_FAILURES = 5
PIN_LOCKOUT_SECONDS = 15 * 60
# A coarser per-IP throttle so a single IP can't fan out across many player ids
# faster than a human ever would.
VERIFY_IP_LIMIT = 40
VERIFY_IP_WINDOW = 60
# Write throttle — generous (a real player taps a handful of dates).
WRITE_LIMIT = 60
WRITE_WINDOW = 60

# A player may only set a real answer for themselves (no NO_RESPONSE-as-default;
# NO_RESPONSE is allowed so a mis-tap can be retracted).
SELF_STATUSES = {"AVAILABLE", "UNAVAILABLE", "MAYBE", "NO_RESPONSE"}


class VerifyBody(BaseModel):
    player_id: str
    pin: str = ""


class SetBody(BaseModel):
    date: date
    status: str
    note: Optional[str] = None


def _client_ip(request: Request) -> str:
    """Best-effort real client IP for rate-limit keying (Cloudflare-aware)."""
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
        {"club": str(club_id), "pid": str(player_id), "typ": "avail", "exp": exp},
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
    """The verified player_id from the cookie, but only if it's for this club."""
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    try:
        payload = jwt.decode(raw, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None
    if payload.get("typ") != "avail" or payload.get("club") != str(club_id):
        return None
    try:
        return uuid.UUID(payload["pid"])
    except (KeyError, ValueError, TypeError):
        return None


async def _club_for_token(db: AsyncSession, token: str, need_select: bool = True, need_dashboard: bool = False) -> Organisation:
    """Resolve the club behind a self-service token, or 404.

    404 (not 403) for every "this link isn't usable" case: unknown token, switched
    off, or the club no longer entitled to BetterSelect. A leaked or rotated link
    reveals nothing about why it stopped working.

    The link has two sides with a switch each (`services/player_dashboard`): the
    availability side (answers, votes, the BetterSelect sections), switched in
    BetterSelect, and the dashboard side (Player Cards, season, fantasy, fees),
    switched in BetterStats. The link opens when either is on, and what a route may
    serve follows its own side:

    * `need_select` (the default): the availability side must be on. Every availability
      and vote write is this.
    * `need_dashboard`: the dashboard side must be on (Player Cards).
    * neither: the player's own page, which then draws only the sides that are on.
    """
    if not token:
        raise HTTPException(status_code=404, detail="Unknown link")
    res = await db.execute(
        select(Organisation).where(Organisation.availability_link_token == token)
    )
    club = res.scalar_one_or_none()
    if club is None:
        raise HTTPException(status_code=404, detail="This availability link isn't active")
    if (
        not player_dashboard.link_live(club)
        or (need_select and not player_dashboard.availability_live(club))
        or (need_dashboard and not player_dashboard.dashboard_live(club))
    ):
        raise HTTPException(status_code=404, detail="This availability link isn't active")
    return club


def _club_branding(club: Organisation) -> dict:
    return {
        # The club's chosen fonts (and the address of an uploaded one), so the player's cards can be
        # drawn in the club's own typeface, as its share card is.
        **public_font_fields(club),
        "name": club.name,
        "short_name": club.short_name,
        "slug": club.slug,
        "logo_url": club.logo_url,
        "primary_color": club.primary_color,
        "accent_color": club.accent_color,
    }


async def _player_for_session(db: AsyncSession, request: Request, club: Organisation) -> Player:
    pid = _read_session(request, club.id)
    if not pid:
        raise HTTPException(status_code=401, detail="Not verified")
    player = await db.get(Player, pid)
    if not player or player.organisation_id != club.id:
        raise HTTPException(status_code=401, detail="Not verified")
    return player


def _player_card(player: Player) -> dict:
    """Who the page is for: their name, photo and shirt number, and the way to their
    public profile. Their own details only."""
    return {
        "id": str(player.id),
        "display_name": player.display_name,
        "photo_url": player.photo_url,
        "shirt_number": player.shirt_number,
        # A profile the club has switched off (or the player asked to remove) is not linked.
        "profile_path": f"/players/{player.id}" if player.is_public is not False else None,
    }


@router.get("/{token}")
async def get_landing(token: str, db: AsyncSession = Depends(get_db)):
    """Club branding + the active-player name list (id + display name only) for
    the type-to-search step. 404 if the link is disabled / unknown."""
    club = await _club_for_token(db, token, need_select=False)
    players = await active_self_service_players(db, club)
    return {
        "club": _club_branding(club),
        "require_pin": bool(club.availability_require_pin),
        "has_availability": player_dashboard.availability_live(club),
        "allow_maybe": allow_maybe(club),
        "week_names": rules_svc.club_config(club)["week_names"],
        "players": [
            {"id": str(p.id), "display_name": p.display_name, "has_phone": phone_last4(p.phone) is not None}
            for p in players
        ],
    }


@router.post("/{token}/verify")
async def verify(token: str, body: VerifyBody, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Prove identity with the last 4 digits of the player's mobile, then issue
    the session cookie. Rate-limited per IP + locked out after repeated misses."""
    club = await _club_for_token(db, token, need_select=False)
    ip = _client_ip(request)
    rate_limit.enforce(
        f"avail-verify-ip:{token}:{ip}", VERIFY_IP_LIMIT, VERIFY_IP_WINDOW,
        detail="Too many attempts — slow down and try again shortly.",
    )

    try:
        pid = uuid.UUID(body.player_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid player")

    lock_key = f"avail-verify:{token}:{pid}:{ip}"
    rate_limit.assert_not_locked(
        lock_key, PIN_MAX_FAILURES, PIN_LOCKOUT_SECONDS,
        detail="Too many incorrect attempts. Please wait a few minutes and try again.",
    )

    player = await db.get(Player, pid)
    if not player or player.organisation_id != club.id or not player.is_player:
        # Don't distinguish "no such player" from "wrong PIN" — both count as a
        # failure so a leaked link can't be used to enumerate the roster.
        rate_limit.record_failure(lock_key, PIN_LOCKOUT_SECONDS)
        raise HTTPException(status_code=401, detail="That didn't match. Check your details and try again.")

    if club.availability_require_pin:
        want = phone_last4(player.phone)
        if want is None:
            raise HTTPException(
                status_code=409,
                detail="No mobile number is on file for you yet — ask your club admin to add it or set your availability for you.",
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
    """"Not you?" — clear the session cookie so a different player can verify."""
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"status": "ok"}


def _grouped_dates(by_date: dict[str, list[dict]]) -> list[dict]:
    return [{"date": d, "fixtures": by_date[d]} for d in sorted(by_date.keys())]


async def _player_squads(db: AsyncSession, club: Organisation, player: Player) -> list[tuple[str, Optional[frozenset]]]:
    """(squad id, the grade rows of every team it covers) for each squad the
    player is in; None where a squad has no grade to read games from."""
    rows = (await db.execute(
        text(
            "SELECT t.id FROM team_members tm JOIN teams t ON t.id = tm.team_id "
            "WHERE tm.player_id = :p AND t.organisation_id = :org"
        ),
        {"p": player.id, "org": club.id},
    )).fetchall()
    sides = await squad_sides.load(db, club.id)
    return [(str(tid), frozenset(sides.grade_ids(tid)) or None) for (tid,) in rows]


async def _in_junior_squad(db: AsyncSession, club: Organisation, player: Player) -> bool:
    """Is this player in a squad with a team Manage Grades calls junior? Read
    straight from team_members, whatever the club's show-squad switch says,
    because it only decides whether junior games stay on THEIR page."""
    rows = (await db.execute(
        text(
            "SELECT t.id, t.name FROM team_members tm JOIN teams t ON t.id = tm.team_id "
            "WHERE tm.player_id = :p AND t.organisation_id = :org"
        ),
        {"p": player.id, "org": club.id},
    )).fetchall()
    if not rows:
        return False
    categories = await org_grade_category_sets(db, club.id)
    sides = await squad_sides.load(db, club.id)
    for tid, tname in rows:
        # Every team the squad covers, else (no grade) the squad's own name.
        for name in (sides.grade_names(tid) or [tname]):
            if "junior" in categories_for_name(categories, name):
                return True
    return False


async def _squad_names(db: AsyncSession, club: Organisation, player: Player) -> list[str]:
    """The names of the squads this player is in, top squad first. Read only when
    the club has the show-squad switch on; with it off nothing about a squad is
    ever read for the page, so nothing can leak."""
    rows = (await db.execute(
        text(
            "SELECT COALESCE(NULLIF(t.short_name, ''), t.name) FROM team_members tm "
            "JOIN teams t ON t.id = tm.team_id "
            "WHERE tm.player_id = :p AND t.organisation_id = :org AND COALESCE(t.is_active, true) "
            "ORDER BY t.sequence NULLS LAST, t.name"
        ),
        {"p": player.id, "org": club.id},
    )).fetchall()
    return [r[0] for r in rows]


async def _fixtures_for_player(db: AsyncSession, club: Organisation, squads: list, tz: Optional[str] = None,
                               hide_juniors: bool = False) -> dict[str, list[dict]]:
    """Upcoming fixtures with time, venue, our team and which are this player's."""
    by_date = await upcoming_fixtures_by_date(
        db, club.id, with_scope=True, with_detail=True, now_local=local_now(tz), hide_juniors=hide_juniors,
    )
    team_rows = (await db.execute(
        text("SELECT id, name FROM teams WHERE organisation_id = :org"),
        {"org": club.id},
    )).fetchall()
    grade_ids = {uuid.UUID(f["grade_id"]) for fs in by_date.values() for f in fs if f.get("grade_id")}
    grade_rows = (await db.execute(
        select(Grade.id, Grade.name).where(Grade.id.in_(grade_ids)),
    )).fetchall() if grade_ids else []
    return fixtures_for_player(
        by_date,
        squads,
        {str(i): n for i, n in team_rows},
        {str(i): n for i, n in grade_rows},
    )


@router.get("/{token}/me")
async def get_me(token: str, request: Request, tz: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """This verified player's upcoming fixtures (grouped by date) + their current
    answers. Date-keyed: one answer covers every fixture that day."""
    club = await _club_for_token(db, token, need_select=False)
    player = await _player_for_session(db, request, club)
    if not player_dashboard.availability_live(club):
        # No BetterSelect or its link is off, so no fixtures to answer: the page leaves the Availability section out.
        return {
            "club": _club_branding(club), "player": _player_card(player), "allow_maybe": False,
            "week_names": [], "dates": [], "availability": {}, "has_squad": False, "squads": [],
            "has_availability": False,
        }
    # A club may not want players to know their squad: with the switch off the
    # squads are never read, so nothing about them can reach the page.
    squads = await _player_squads(db, club, player) if club.availability_show_squad else []
    # Junior games stay off a senior player's page (Manage Grades decides what
    # is junior); a player who is in a junior squad still sees theirs.
    by_date = await _fixtures_for_player(db, club, squads, tz, hide_juniors=not await _in_junior_squad(db, club, player))
    answers: dict[str, dict] = {}
    if by_date:
        av_res = await db.execute(
            select(PlayerAvailability).where(
                PlayerAvailability.player_id == player.id,
                PlayerAvailability.avail_date.in_([date.fromisoformat(d) for d in by_date.keys()]),
            )
        )
        for a in av_res.scalars().all():
            answers[a.avail_date.isoformat()] = {
                "status": a.status, "note": a.note, "source": a.source or "admin",
            }
    return {
        "club": _club_branding(club),
        "player": _player_card(player),
        "allow_maybe": allow_maybe(club),
        "week_names": rules_svc.club_config(club)["week_names"],
        "dates": _grouped_dates(by_date),
        "availability": answers,
        # False for a player in no squad: the page then emphasises no game.
        "has_squad": bool(squads),
        # Their squads by name, only where the club lets players see them.
        "squads": await _squad_names(db, club, player) if club.availability_show_squad else [],
        "has_availability": True,
    }


VOTES_LIVE_EXAMINED = 10   # games whose list comes from a live Play.Cricket fetch, per page load
VOTES_CAST_SHOWN = 6       # the player's own most recent ballots shown for reference


async def _votes_for_player(db: AsyncSession, club: Organisation, player: Player) -> tuple[list[dict], list[dict]]:
    """``(due, cast)``. ``due``: games this player can still vote on and has not: open for voting under an
    enabled medal, the player is on that game's votable list (the same list the
    ballot page uses, so a reminder never points at a game they cannot vote on),
    and no ballot from them yet. Nothing about anyone else, and nothing at all
    for a club with no enabled voting link.

    A club has a game open for every grade each round, so the player's own games
    are found first with two batched local lookups (their saved XIs and the
    scorecards they appear on) and only those get the full eligibility check.
    A game whose list can only come from a live Play.Cricket fetch cannot be
    found that way; those are checked directly, a few at a time.

    ``cast``: the player's OWN ballots on games this medal counts (open or closed),
    newest first, with who they gave 3, 2 and 1 to, for reference. Only their own
    ballot; nobody else's. An open game carries the link to change it.

    The link carries the medal's token, so it is only ever built here, for the
    verified player, and the vote page still asks for their PIN."""
    medals = (await db.execute(
        select(VoteMedal).where(
            VoteMedal.organisation_id == club.id, VoteMedal.enabled.is_(True),
            VoteMedal.link_token.is_not(None),
        ).order_by(VoteMedal.name)
    )).scalars().all()
    due: list[dict] = []
    cast: list[dict] = []
    live_left = VOTES_LIVE_EXAMINED
    for medal in medals:
        cfg = vote_svc.effective_config(medal)
        fixtures, _ = await pv._open_fixtures(db, club, cfg, medal)
        if not fixtures:
            continue
        fx_by = {f.id: f for f, _state in fixtures}
        state_by = {f.id: state for f, state in fixtures}
        open_fx = [f for f, state in fixtures if state == "open"]
        ballots = (await db.execute(
            select(VoteBallot).where(
                VoteBallot.medal_id == medal.id, VoteBallot.voter_player_id == player.id,
                VoteBallot.fixture_id.in_(list(fx_by)),
            )
        )).scalars().all()
        voted = {b.fixture_id for b in ballots}

        if ballots:
            pick_ids = {pk.player_id for b in ballots for pk in b.picks}
            names = {pid: nm for pid, nm in (await db.execute(
                text("SELECT id, COALESCE(display_name_override, name) FROM players WHERE organisation_id = :org AND id = ANY(CAST(:ids AS uuid[]))"),
                {"org": club.id, "ids": list(pick_ids)},
            )).fetchall()} if pick_ids else {}
            values = cfg["ballot_values"]
            for b in ballots:
                f = fx_by[b.fixture_id]
                is_open = state_by[b.fixture_id] == "open"
                closes = vote_svc.fixture_close_date(f, cfg)
                cast.append({
                    "medal": medal.name,
                    "fixture_id": str(f.id),
                    "opponent": f.opponent_name or f.label,
                    "round": vote_svc.round_label_for(f),
                    "date": f.played_on.isoformat() if f.played_on else None,
                    "open": is_open,
                    "closes_on": closes.isoformat() if is_open and closes else None,
                    # Points by position: who they gave 3, 2 and 1 to (or whatever the medal counts).
                    "picks": [
                        {"points": values[pk.position - 1] if 0 < pk.position <= len(values) else None,
                         "name": names.get(pk.player_id, "Unknown")}
                        for pk in sorted(b.picks, key=lambda x: x.position)
                    ],
                    "link": f"/vote/{medal.link_token}?fixture={f.id}&player={player.id}" if is_open else None,
                })

        todo = [f for f in open_fx if f.id not in voted]
        if not todo:
            continue
        overrides = await vote_svc.overrides_by_fixture(db, medal.id, [f.id for f in todo])

        own = await pv.own_local_fixture_ids(db, player, todo)
        # A person chosen to vote for a team is not necessarily in its side.
        own |= await vote_svc.chosen_fixture_ids(db, cfg, player.id, todo)

        for f in todo:
            ov = overrides.get(str(f.id))
            source = vote_svc.effective_source(cfg, ov.eligibility_source if ov else None)
            local = f.id in own
            if not local:
                # Only a live team-list fetch could still put them on this game's list.
                if source != "playhq" or live_left <= 0:
                    continue
                live_left -= 1
            elig = await vote_svc.resolve_eligibility(db, club, f, cfg, ov.eligibility_source if ov else None)
            role, _reason = pv._voter_role(
                await vote_svc.cfg_for_fixture(db, cfg, f), player, elig["players"])
            if role != "player":
                continue
            closes = vote_svc.fixture_close_date(f, cfg)
            due.append({
                "medal": medal.name,
                "fixture_id": str(f.id),
                "opponent": f.opponent_name or f.label,
                "round": vote_svc.round_label_for(f),
                "date": f.played_on.isoformat() if f.played_on else None,
                "closes_on": closes.isoformat() if closes else None,
                "link": f"/vote/{medal.link_token}?fixture={f.id}&player={player.id}",
            })
    due.sort(key=lambda d: (d["closes_on"] or "9999", d["date"] or ""))
    cast.sort(key=lambda c: c["date"] or "", reverse=True)
    return due, cast[:VOTES_CAST_SHOWN]


FANTASY_DEADLINES_SHOWN = 3


async def _fantasy_for_player(db: AsyncSession, club: Organisation, player: Player) -> Optional[dict]:
    """The Fantasy card: the next lock deadlines, the way in, and, when the player's
    own fantasy team can be found, where it sits. None when the club has nothing
    running (no season, or one still being set up), which drops the module.

    Read only, and deliberately light on the team. The fantasy login is the
    manager's own email and PIN; this page's PIN is the last four digits of a
    mobile, which teammates often know. So the card carries the same figures the
    club ladder already shows (name, rank, points) and never the picks, captain
    or transfers: before a round locks those are what a rival would want. The
    team is found by the player's email on file matching exactly ONE fantasy
    manager's email at this club; no email, no match or two matches means no
    team, and the card still has the deadlines and the link. With the PIN off,
    anyone holding the link could open anybody's page, so the team is left out
    (same rule as fees)."""
    season = await pf._current_season(db, club)
    if season is None or season.status == "setup":
        return None
    league = await pf._global_league(db, season)
    rounds = (await db.execute(
        select(FantasyRound).where(
            FantasyRound.fantasy_season_id == season.id, FantasyRound.status != "scored",
        ).order_by(FantasyRound.round_number).limit(FANTASY_DEADLINES_SHOWN)
    )).scalars().all()
    deadlines = [
        {"number": r.round_number, "name": r.name,
         "lock_at": r.lock_at.isoformat() if r.lock_at else None, "locked": pf._round_locked(r)}
        for r in rounds
    ]
    current = rounds[0] if rounds else None

    sponsors = (await db.execute(select(Sponsor).where(Sponsor.organisation_id == club.id))).scalars().all()
    named = section_names.resolve(club.section_names, sponsors).get("fantasy") or {}

    team = None
    email = (player.email or "").strip().lower()
    if club.availability_require_pin and email and league is not None:
        managers = (await db.execute(
            select(FantasyManager.id).where(
                FantasyManager.organisation_id == club.id,
                func.lower(func.trim(FantasyManager.email)) == email,
            ).limit(2)
        )).scalars().all()
        if len(managers) == 1:
            squad = (await db.execute(
                select(FantasySquad).where(FantasySquad.league_id == league.id, FantasySquad.manager_id == managers[0])
            )).scalar_one_or_none()
            if squad is None:
                team = {"built": False}
            else:
                last = (await db.execute(
                    text("""SELECT r.round_number, srs.points FROM fantasy_squad_round_scores srs
                            JOIN fantasy_rounds r ON r.id = srs.round_id
                            WHERE srs.squad_id = CAST(:sid AS UUID) AND r.status = 'scored'
                            ORDER BY r.round_number DESC LIMIT 1"""),
                    {"sid": str(squad.id)},
                )).first()
                # Points the running round has banked so far (the stored provisional
                # row), only while it is locked. Shown beside the total, never added to it.
                live = None
                if current is not None and deadlines and deadlines[0]["locked"]:
                    live = (await db.execute(
                        text("""SELECT points FROM fantasy_squad_round_scores
                                WHERE squad_id = CAST(:sid AS UUID) AND round_id = CAST(:rid AS UUID)"""),
                        {"sid": str(squad.id), "rid": str(current.id)},
                    )).scalar_one_or_none()
                total = (await db.execute(
                    select(func.count()).select_from(FantasySquad).where(FantasySquad.league_id == league.id)
                )).scalar_one()
                team = {
                    "built": True,
                    "team_name": squad.team_name,
                    "points": float(squad.total_points or 0),
                    "rank": await pf._overall_rank(db, league.id, squad.id),
                    "of": int(total or 0),
                    "last_round": {"number": last[0], "points": float(last[1])} if last else None,
                    "this_round_points": float(live) if live is not None else None,
                    "free_transfers": squad.free_transfers,
                }

    # How the player themselves is doing as a pick: public on the club's pool list.
    pool = (await db.execute(
        select(FantasyPoolPlayer).where(
            FantasyPoolPlayer.fantasy_season_id == season.id, FantasyPoolPlayer.player_id == player.id,
        )
    )).scalar_one_or_none()
    as_player = None
    if pool is not None:
        as_player = {
            "points": float(pool.total_points or 0),
            "last_round_points": float(pool.last_round_points or 0),
            "price": float(pool.current_price or 0),
            "price_change": float(pool.price_change or 0),
            "owned_count": int(pool.owned_count or 0),
        }
    return {
        "link": f"/fantasy/{club.fantasy_link_token}",
        "name": named.get("name"),
        "season": {"name": season.name, "status": season.status, "registration_open": bool(season.registration_open)},
        "deadlines": deadlines,
        "team": team,
        "as_player": as_player,
    }


@router.get("/{token}/me/profile")
async def get_my_profile(token: str, request: Request, tz: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """The verified player's own page ("My page"): the modules the club has turned
    on, in the club's order, with the data behind each. Their own data only,
    behind the same PIN cookie as the availability answers; nobody else's name
    appears.

    `modules` is the list the page draws, already cut down to what this club may
    show (see services/player_dashboard) and to what has something to say for
    this player. A module the club has not turned on is never queried.

    A side shows only once it is LOCKED (confirmed). A draft or an unlocked side
    can still change, and telling a player they are in before the selector has
    finished is worse than telling them nothing."""
    club = await _club_for_token(db, token, need_select=False)
    player = await _player_for_session(db, request, club)
    now = local_now(tz)
    today = now.date() if now else date.today()

    modules = player_dashboard.served_modules(club)
    squads_visible = bool(club.availability_show_squad)
    squad_names = await _squad_names(db, club, player) if squads_visible and "squad" in modules else []

    # Keys an older page bundle reads stay present (empty) when their module is
    # off, so a stale tab left open across a deploy still renders.
    selected = await _selected_sides(db, club, player, today, squads_visible) if "selected" in modules else []
    training = (
        await _training(db, club, player, today) if "training" in modules
        else {"upcoming": [], "attended_8_weeks": 0, "last_attended": None}
    )

    # The newer modules fail on their own: one that cannot be built is dropped
    # from this response and the rest of the page still loads.
    season = fees = fines = fantasy = cards = None
    votes: list[dict] = []
    votes_cast: list[dict] = []
    if "cards" in modules:
        try:
            cards = await cards_svc.dashboard_summary(db, club, player)
            await db.commit()
        except Exception:
            logger.exception("player page: cards failed for %s", player.id)
            await rollback_keeping(db, club, player)
        if cards is None:
            modules = [m for m in modules if m != "cards"]
    if "votes" in modules:
        try:
            votes, votes_cast = await _votes_for_player(db, club, player)
        except Exception:
            logger.exception("player page: votes failed for %s", player.id)
            await rollback_keeping(db, club, player)
        if not votes and not votes_cast:
            modules = [m for m in modules if m != "votes"]
    if "season" in modules:
        try:
            season = await player_dashboard.season_overview(db, club, player)
        except Exception:
            logger.exception("player page: season overview failed for %s", player.id)
            await rollback_keeping(db, club, player)
            modules = [m for m in modules if m != "season"]
        if season is not None:
            # The recent-form strip fails on its own: the season still draws without it.
            try:
                season["form"] = await player_dashboard.recent_form(db, club, player)
            except Exception:
                logger.exception("player page: recent form failed for %s", player.id)
                await rollback_keeping(db, club, player)
                season["form"] = {"batting": [], "bowling": []}
    if "fantasy" in modules:
        try:
            fantasy = await _fantasy_for_player(db, club, player)
        except Exception:
            logger.exception("player page: fantasy failed for %s", player.id)
            await rollback_keeping(db, club, player)
        if fantasy is None:
            modules = [m for m in modules if m != "fantasy"]
    if "fees" in modules:
        try:
            fees = await player_dashboard.fees_owing(db, club, player)
        except Exception:
            logger.exception("player page: fees failed for %s", player.id)
            await rollback_keeping(db, club, player)
            modules = [m for m in modules if m != "fees"]
    if "fines" in modules:
        try:
            fines = await fines_svc.player_fines(db, club.id, player.id)
        except Exception:
            logger.exception("player page: fines failed for %s", player.id)
            await rollback_keeping(db, club, player)
            fines = []
        if not fines:
            modules = [m for m in modules if m != "fines"]

    return {
        "club": _club_branding(club),
        "player": _player_card(player),
        # The Update details button: only offered where the PIN guards the page.
        "can_update_details": bool(club.availability_require_pin),
        "modules": modules,
        "squads": squad_names,
        "squads_visible": squads_visible,
        "selected": selected,
        "training": training,
        "season": season,
        "fees": fees,
        "fines": fines,
        "fantasy": fantasy,
        "votes": votes,
        "votes_cast": votes_cast,
        "cards": cards,
        "has_availability": player_dashboard.availability_live(club),
    }


@router.get("/{token}/me/ranks")
async def get_my_ranks(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Where the player ranks in the club this season for runs, wickets and catches.
    Read on its own when the Stats section opens, because it reads the club's
    leaderboards, which the rest of the page does not. 404 unless the club has the
    season module on. A failure answers with no ranks and the section still draws."""
    club = await _club_for_token(db, token, need_select=False)
    player = await _player_for_session(db, request, club)
    if "season" not in player_dashboard.served_modules(club):
        raise HTTPException(status_code=404, detail="Not available")
    try:
        out = await player_dashboard.season_ranks(db, club, player)
    except Exception:
        logger.exception("player page: season ranks failed for %s", player.id)
        await rollback_keeping(db, club, player)
        out = None
    return {"ranks": out}


@router.get("/{token}/me/ladder")
async def get_my_ladder(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """The competition ladder for each squad the player is in. Read on its own
    (the ladder module calls it when it opens) because it asks Cricket Australia,
    which the rest of the page does not. 404 unless the club has the module on
    and Show squad on, since the ladder names the player's squad."""
    club = await _club_for_token(db, token, need_select=False)
    player = await _player_for_session(db, request, club)
    if "ladder" not in player_dashboard.served_modules(club):
        raise HTTPException(status_code=404, detail="Not available")
    team_ids = [r[0] for r in (await db.execute(
        text("SELECT team_id FROM team_members WHERE player_id = :p AND organisation_id = :org"),
        {"p": player.id, "org": club.id},
    )).fetchall()]
    if not team_ids:
        return {"ladders": []}
    data = await _compute_team_ladders(db, club, auto_link=False, only_team_ids=team_ids)
    show = {"played", "won", "lost", "competitionPoints"}
    ladders = []
    for t in data["teams"]:
        if not t.get("available") or not t.get("views"):
            continue
        view = t["views"][0]
        ladders.append({
            "team": t["team_name"],
            "grade": t.get("grade_name"),
            "view": view["name"],
            "columns": [c for c in view["columns"] if c["id"] in show],
            "rows": [
                {"rank": r["rank"], "team_name": r["team_name"], "is_club": bool(r["is_club"]),
                 "stats": {k: v for k, v in r["stats"].items() if k in show}}
                for r in view["rows"][:20]
            ],
        })
    return {"ladders": ladders[:3]}


async def _selected_sides(db: AsyncSession, club: Organisation, player: Player, today: date, squads_visible: bool) -> list[dict]:
    my_sides = await squad_sides.load(db, club.id)
    sel_rows = (await db.execute(
        text(
            "SELECT f.id, f.played_on, f.start_time, f.venue, f.opponent_name, f.home_away, f.label, f.round, "
            "COALESCE(NULLIF(t.short_name, ''), t.name), fl.is_captain, fl.is_wicket_keeper, f.team_id, f.grade_id, f.side_key "
            "FROM fixture_lineups fl JOIN fixtures f ON f.id = fl.fixture_id "
            "LEFT JOIN teams t ON t.id = f.team_id "
            "WHERE fl.player_id = :p AND fl.organisation_id = :org AND f.locked_at IS NOT NULL "
            "AND f.played_on >= :today AND COALESCE(f.status, '') <> 'CANCELLED' "
            "ORDER BY f.played_on, f.start_time NULLS LAST LIMIT 10"
        ),
        {"p": player.id, "org": club.id, "today": today},
    )).fetchall()
    return [
        {
            # The fixture's id (already on this player's own date cards), so the
            # page can show "selected" on the date the game is on, and on both
            # dates of a two-day game.
            "fixture_id": str(r[0]),
            "date": r[1].isoformat() if r[1] else None, "start_time": r[2], "venue": r[3],
            "opponent_name": r[4], "home_away": r[5], "label": r[6], "round": r[7],
            # The side's name is the squad's, so it follows the same switch.
            # (A squad covering several teams names this one by its team.)
            "team_name": (my_sides.name(r[11], r[12], r[13]) or r[8]) if squads_visible else None,
            "is_captain": bool(r[9]), "is_wicket_keeper": bool(r[10]),
        }
        for r in sel_rows
    ]


async def _training(db: AsyncSession, club: Organisation, player: Player, today: date) -> dict:
    """The sessions still to come that are for everyone or for a squad this player
    is in, and how often they have turned up lately."""
    my_team_ids = {r[0] for r in (await db.execute(
        text("SELECT team_id FROM team_members WHERE player_id = :p AND organisation_id = :org"),
        {"p": player.id, "org": club.id},
    )).fetchall()}
    sessions = (await db.execute(
        text(
            "SELECT session_date, label, squad_team_ids FROM net_sessions "
            "WHERE organisation_id = :org AND status = 'active' AND session_date >= :today "
            "ORDER BY session_date, created_at LIMIT 12"
        ),
        {"org": club.id, "today": today},
    )).fetchall()
    upcoming = [
        {"date": d.isoformat(), "label": label}
        for d, label, squad_ids in sessions
        if not squad_ids or my_team_ids.intersection(squad_ids)
    ][:5]
    since = today - timedelta(days=56)
    att = (await db.execute(
        text(
            "SELECT count(*), max(ns.session_date) FROM net_attendance na "
            "JOIN net_sessions ns ON ns.id = na.session_id "
            "WHERE na.player_id = :p AND ns.organisation_id = :org AND ns.session_date >= :since"
        ),
        {"p": player.id, "org": club.id, "since": since},
    )).first()
    return {
        "upcoming": upcoming,
        "attended_8_weeks": int(att[0] or 0) if att else 0,
        "last_attended": att[1].isoformat() if att and att[1] else None,
    }


@router.post("/{token}/me")
async def set_me(token: str, body: SetBody, request: Request, db: AsyncSession = Depends(get_db)):
    """Upsert this player's own answer for a date. Validates the date is a real
    upcoming club fixture date and stamps source='self' (recorded_by stays NULL)."""
    club = await _club_for_token(db, token)
    player = await _player_for_session(db, request, club)
    rate_limit.enforce(f"avail-write:{player.id}", WRITE_LIMIT, WRITE_WINDOW)

    status = (body.status or "").upper()
    if status not in SELF_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {body.status}")
    if status == "MAYBE" and not allow_maybe(club):
        raise HTTPException(status_code=400, detail=MAYBE_OFF)

    by_date = await upcoming_fixtures_by_date(db, club.id)
    if body.date.isoformat() not in by_date:
        raise HTTPException(status_code=400, detail="No upcoming fixture on that date")

    note = (body.note or "").strip() or None
    res = await db.execute(
        select(PlayerAvailability).where(
            PlayerAvailability.player_id == player.id,
            PlayerAvailability.avail_date == body.date,
        )
    )
    row = res.scalar_one_or_none()
    # The player's own answer: the trail names the player, not a user.
    await audit_availability(db, club.id, player.id, body.date, row.status if row else None, status, note,
                             self_service=True)
    if row:
        row.status = status
        row.note = note
        row.source = "self"
        row.recorded_by = None
        row.recorded_at = datetime.now(timezone.utc)
    else:
        db.add(PlayerAvailability(
            organisation_id=club.id,
            player_id=player.id,
            avail_date=body.date,
            status=status,
            note=note,
            source="self",
            recorded_by=None,
        ))
    await db.commit()
    return {"status": "ok"}


# ─── Update my details ───────────────────────────────────────────────────────
# A player corrects their own email, mobile, address and emergency contact from
# their page. The page's only proof of who is typing is the last four digits of a
# mobile, which teammates often know, so the write is held to a higher bar than an
# availability tap: the PIN must be on (with it off anyone holding the link could
# edit anybody), the current PIN is asked for again on every save and counts
# against the same lockout as signing in, the writes are throttled, and every
# change leaves an audit entry that keeps the old values so the club can put them
# back.

DETAIL_FIELDS = (
    "email", "phone", "address_line1", "suburb", "state", "postcode",
    "emergency_contact_name", "emergency_contact_phone",
)
DETAIL_MAX = {
    "email": 254, "phone": 30, "address_line1": 120, "suburb": 60, "state": 40, "postcode": 10,
    "emergency_contact_name": 100, "emergency_contact_phone": 30,
}
DETAILS_WRITE_LIMIT = 10
DETAILS_WRITE_WINDOW = 10 * 60
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[0-9 ()\-]+$")
DETAILS_NEED_PIN = "Updating your details needs the PIN switched on for this link. Ask your club."


class DetailsBody(BaseModel):
    """Only the fields sent are touched; "" clears one (an absent key is not a clear)."""
    pin: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address_line1: Optional[str] = None
    suburb: Optional[str] = None
    state: Optional[str] = None
    postcode: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None


def _details_of(player: Player) -> dict:
    return {f: getattr(player, f) or "" for f in DETAIL_FIELDS}


def _clean_detail(field: str, raw: Optional[str]) -> Optional[str]:
    """The value to store (None clears), or a 422 saying what is wrong."""
    v = (raw or "").strip()
    if not v:
        return None
    if len(v) > DETAIL_MAX[field]:
        raise HTTPException(status_code=422, detail=f"That is too long ({DETAIL_MAX[field]} characters at most).")
    if field == "email" and not _EMAIL_RE.match(v):
        raise HTTPException(status_code=422, detail="That email address does not look right.")
    if field in ("phone", "emergency_contact_phone"):
        digits = re.sub(r"\D", "", v)
        if not _PHONE_RE.match(v) or not 8 <= len(digits) <= 15:
            raise HTTPException(status_code=422, detail="That phone number does not look right. Use digits, spaces, + and brackets only.")
    if field == "postcode" and not re.match(r"^[A-Za-z0-9 \-]+$", v):
        raise HTTPException(status_code=422, detail="That postcode does not look right.")
    return v


def _same_contact(a: Optional[str], b: Optional[str], digits: bool) -> bool:
    norm = (lambda x: re.sub(r"\D", "", x or "")) if digits else (lambda x: (x or "").strip().lower())
    return norm(a) == norm(b)


@router.get("/{token}/me/details")
async def get_my_details(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """The verified player's own contact details, for the Update details form. Their
    own record only. Refused with the PIN off, like fees."""
    club = await _club_for_token(db, token, need_select=False)
    player = await _player_for_session(db, request, club)
    if not club.availability_require_pin:
        raise HTTPException(status_code=403, detail=DETAILS_NEED_PIN)
    return {"details": _details_of(player), "pin_required": True}


@router.patch("/{token}/me/details")
async def update_my_details(token: str, body: DetailsBody, request: Request, db: AsyncSession = Depends(get_db)):
    club = await _club_for_token(db, token, need_select=False)
    player = await _player_for_session(db, request, club)
    if not club.availability_require_pin:
        raise HTTPException(status_code=403, detail=DETAILS_NEED_PIN)
    rate_limit.enforce(f"avail-details:{player.id}", DETAILS_WRITE_LIMIT, DETAILS_WRITE_WINDOW,
                       detail="Too many changes just now. Try again in a few minutes.")

    # Prove it again, against their CURRENT mobile (read before this write changes it).
    lock_key = f"avail-verify:{token}:{player.id}:{_client_ip(request)}"
    rate_limit.assert_not_locked(
        lock_key, PIN_MAX_FAILURES, PIN_LOCKOUT_SECONDS,
        detail="Too many incorrect attempts. Please wait a few minutes and try again.",
    )
    want = phone_last4(player.phone)
    if want is None:
        raise HTTPException(status_code=409, detail="There is no mobile number on file for you, so your details cannot be changed here. Ask your club.")
    if phone_last4(body.pin) != want:
        rate_limit.record_failure(lock_key, PIN_LOCKOUT_SECONDS)
        raise HTTPException(status_code=401, detail="That PIN did not match. Use the last 4 digits of your current mobile.")
    rate_limit.clear_failures(lock_key)

    sent = [f for f in DETAIL_FIELDS if f in body.model_fields_set]
    new: dict[str, Optional[str]] = {f: _clean_detail(f, getattr(body, f)) for f in sent}
    # The mobile is the PIN: clearing it would lock them out of this page.
    if "phone" in new and new["phone"] is None:
        raise HTTPException(status_code=422, detail="Your mobile is your PIN, so it cannot be cleared. Replace it with the new number instead.")
    if "phone" in new and phone_last4(new["phone"]) is None:
        raise HTTPException(status_code=422, detail="That phone number does not look right.")

    old = _details_of(player)
    changed = {f: (old[f] or None, new[f]) for f in sent if (old[f] or None) != new[f]}
    if not changed:
        return {"status": "ok", "changed": [], "details": old}

    for f, (_was, now) in changed.items():
        setattr(player, f, now)

    # The club's fee/membership record keeps its own email and mobile and is read
    # first by billing and comms. Move it with the player only where it was just
    # mirroring their old value (or was empty): a different address there (a
    # parent's, for a junior) is the club's own entry and is left alone.
    mirrored: list[str] = []
    member = (await db.execute(
        select(FeeMember).where(FeeMember.organisation_id == club.id, FeeMember.player_id == player.id)
    )).scalars().first()
    if member is not None:
        for f, col, digits in (("email", "email", False), ("phone", "mobile", True)):
            if f in changed:
                cur = getattr(member, col)
                if not (cur or "").strip() or _same_contact(cur, changed[f][0], digits):
                    setattr(member, col, changed[f][1])
                    mirrored.append(col)

    from app.services import player_audit
    pname = await player_audit.player_name(db, player.id)
    labels = {"email": "email", "phone": "mobile", "address_line1": "address", "suburb": "address", "state": "address",
              "postcode": "address", "emergency_contact_name": "emergency contact", "emergency_contact_phone": "emergency contact"}
    said = sorted({labels[f] for f in changed})
    await player_audit.record(
        db, club_id=club.id, area="details", action="details_updated",
        summary=f"{pname} updated their own details: {', '.join(said)}",
        player_id=player.id, player_name_=pname,
        # The old values are kept so the club can put a change back.
        detail={"fields": {f: {"from": was, "to": now} for f, (was, now) in changed.items()}, "fee_record_also_updated": mirrored},
        user=None, via="player link", by=pname,
    )
    await db.commit()
    await db.refresh(player)
    return {"status": "ok", "changed": sorted(changed), "details": _details_of(player)}
