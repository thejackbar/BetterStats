"""Player Dashboard: "Can't find your name?" (public, unauthenticated).

The routes behind the Register / Played here before? step of ``/playerdash/:token``.
The rules (who is signed in when, what is written to a player, what waits for an
admin) live in ``services/player_registration``; this module is the HTTP side.

Same trust model as the rest of the link (``routers/public_availability``): the
token names the club only, the mobile's last four digits prove a claimed record,
and the signed cookie keeps a person in. Every write is rate limited per IP, the
past-player search needs three letters and returns a handful of names (never the
whole register), and a club that switched registration off gets a 404 here.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation, Player, get_db
from app.routers.availability import active_self_service_players, club_player_roster, phone_last4
from app.routers.public_availability import (
    PIN_LOCKOUT_SECONDS, PIN_MAX_FAILURES, _client_ip, _club_for_token, _issue_cookie,
)
from app.services import player_registration as reg_svc, rate_limit

router = APIRouter(prefix="/public/availability", tags=["public-availability"])

SEARCH_MIN = 3
SEARCH_LIMIT = 15
SEARCH_IP_LIMIT = 60
SEARCH_IP_WINDOW = 60
REGISTER_IP_LIMIT = 15
REGISTER_IP_WINDOW = 60 * 60

CLOSED = "This club isn't taking new names on its Player Dashboard. Ask your club to add you."


class RegisterBody(BaseModel):
    # Set when they picked an older record of theirs from the past-player search.
    claim_player_id: Optional[str] = None
    pin: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    date_of_birth: Optional[date] = None
    years_played: Optional[str] = None
    grades_played: Optional[str] = None
    notes: Optional[str] = None
    interests: list[str] = []
    contact_consent: bool = False
    # What they play (role, batting hand, bowling, opener, overseas). Unknown values are dropped.
    playing: dict = {}
    # Sent after "None of these are me" on the possible-matches step.
    confirmed_new: bool = False


async def _open_club(db: AsyncSession, token: str) -> Organisation:
    club = await _club_for_token(db, token, need_select=False)
    if not reg_svc.registration_open(club):
        raise HTTPException(status_code=404, detail=CLOSED)
    return club


@router.get("/{token}/register")
async def registration_form(token: str, db: AsyncSession = Depends(get_db)):
    """What the form offers: the roles, the interests, and whether a claimed record is
    proven with the mobile's last four digits."""
    club = await _open_club(db, token)
    return {
        "open": True,
        "require_pin": bool(club.availability_require_pin),
        "roles": reg_svc.ROLES,
        "interests": reg_svc.INTERESTS,
    }


@router.get("/{token}/past-players")
async def search_past_players(token: str, request: Request, q: str = "", db: AsyncSession = Depends(get_db)):
    """Older records the name list hides (dormant or marked inactive) whose name matches.

    Three letters at least and fifteen matches at most, with the year they last played
    so a person can tell two of the same name apart. Name, year and whether a mobile is
    on file: nothing else."""
    club = await _open_club(db, token)
    rate_limit.enforce(f"reg-search:{token}:{_client_ip(request)}", SEARCH_IP_LIMIT, SEARCH_IP_WINDOW,
                       detail="Too many searches just now. Try again in a minute.")
    query = (q or "").strip()
    if len(query.replace(" ", "")) < SEARCH_MIN:
        return {"players": [], "min_chars": SEARCH_MIN}
    active_ids = {p.id for p in await active_self_service_players(db, club)}
    # A player hidden from the public site (`is_public` false, which includes anyone removed at
    # their own request) is never named here: this route is public.
    hits = [p for p in await club_player_roster(db, club)
            if p.id not in active_ids and p.is_public is not False
            and reg_svc.name_matches(p.display_name, query)][:SEARCH_LIMIT]
    last = await _last_played(db, [p.id for p in hits])
    return {
        "min_chars": SEARCH_MIN,
        "players": [
            {"id": str(p.id), "display_name": p.display_name,
             "last_played_year": last[p.id].year if last.get(p.id) else None,
             "has_phone": phone_last4(p.phone) is not None}
            for p in hits
        ],
    }


async def _last_played(db: AsyncSession, ids: list) -> dict:
    if not ids:
        return {}
    rows = (await db.execute(text(
        "SELECT ga.player_id, MAX(g.played_at) AS lp FROM game_appearances ga "
        "JOIN games g ON g.id = ga.game_id WHERE ga.player_id = ANY(CAST(:ids AS uuid[])) "
        "GROUP BY ga.player_id"
    ), {"ids": [str(i) for i in ids]})).fetchall()
    return {pid: lp for pid, lp in rows}


async def _insert(db: AsyncSession, club: Organisation, player_id, kind: str, f: dict, *,
                  status: str = "pending", matched_by: Optional[str] = None, applied: Optional[list] = None) -> uuid.UUID:
    """A proven match goes in `approved` (nothing for the club to decide, only to know about);
    a new person or an unproven claim goes in `pending` for the club to review."""
    rid = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO player_registrations (id, organisation_id, player_id, kind, role, first_name, last_name, email, "
        "phone, date_of_birth, years_played, grades_played, notes, interests, contact_consent, status, matched_by, "
        "playing, applied, reviewed_at, reviewed_by) "
        "VALUES (:id, :org, :pid, :kind, :role, :first, :last, :email, :phone, :dob, :years, :grades, "
        ":notes, CAST(:interests AS jsonb), :consent, CAST(:status AS text), CAST(:matched AS text), CAST(:playing AS jsonb), "
        "CAST(:applied AS jsonb), CASE WHEN CAST(:status AS text) = 'approved' THEN now() END, "
        "CASE WHEN CAST(:status AS text) = 'approved' THEN 'Matched automatically' END)"
    ), {
        "id": rid, "org": club.id, "pid": player_id, "kind": kind, "role": f["role"], "first": f["first_name"],
        "last": f["last_name"], "email": f["email"], "phone": f["phone"], "dob": f["date_of_birth"],
        "years": f["years_played"], "grades": f["grades_played"], "notes": f["notes"],
        "interests": json.dumps(f["interests"]), "consent": f["contact_consent"], "status": status,
        "matched": matched_by, "playing": json.dumps(f["playing"]), "applied": json.dumps(applied or []),
    })
    return rid


_BACKGROUND: set = set()


def _tell_the_club(club_id) -> None:
    """The bell (and the next email digest) for the club's player admins, after the commit, on
    its own session. Never raises; the daily scan catches up anything this misses."""
    from app.services import notification_scan
    task = asyncio.create_task(notification_scan.raise_now(club_id, "player_registered"))
    _BACKGROUND.add(task)
    task.add_done_callback(_BACKGROUND.discard)


async def _matched(db: AsyncSession, club: Organisation, player: Player, f: dict, how: str,
                   response: Response, who: str) -> dict:
    """It is them: link the registration to their record, fill what the record lacks, sign them
    in, and tell the club. Nothing waits for review."""
    from app.services import player_audit
    # Matched by the old PIN means the number they typed is NEW: keep it on the registration for
    # the club to see, and leave the record's own mobile alone.
    applied = reg_svc.fill_empty(player, f, phone=(how == "mobile"))
    if f["role"] == "current_player":
        # Back in the weeks before their first game, the same as an admin's "no longer dormant".
        player.dormancy_cleared_on = date.today()
        applied.append("back for selection")
    pname = player.display_name
    pid = player.id
    await _insert(db, club, pid, "claim", f, status="approved", matched_by=how, applied=applied)
    await player_audit.record(
        db, club_id=club.id, area="details", action="registration_matched",
        summary=f"{who} signed up on the Player Dashboard and was matched to {pname} by their "
                + ("mobile" if how == "mobile" else "PIN")
                + (f"; added {', '.join(applied)}" if applied else ""),
        player_id=pid, player_name_=pname, user=None, via="player link", by=who,
        detail={"matched_by": how, "applied": applied},
    )
    await db.commit()
    _issue_cookie(response, club.id, pid)
    _tell_the_club(club.id)
    return {"status": "signed_in", "matched": True, "player_name": pname}


@router.post("/{token}/register")
async def register(token: str, body: RegisterBody, request: Request, response: Response,
                   db: AsyncSession = Depends(get_db)):
    """Add yourself, or claim an older record of yours. The answer's ``status``:

    * ``signed_in``: the session cookie is set. ``matched`` is true when they were linked to
      their existing record (the mobile they typed is the one on it, or the PIN matched).
    * ``need_pin``: the claimed record has a different mobile on it. Ask for the last four
      digits of that one and send again.
    * ``possible_matches``: a new sign-up whose name matches records already on the books.
      Ask "Is one of these you?"; send again as a claim, or with ``confirmed_new``.
    * ``pending``: the claimed record has no mobile on it, so the club confirms it first."""
    club = await _open_club(db, token)
    ip = _client_ip(request)
    rate_limit.enforce(f"reg-write:{token}:{ip}", REGISTER_IP_LIMIT, REGISTER_IP_WINDOW,
                       detail="Too many registrations from here just now. Try again later or ask your club.")

    role = reg_svc.clean_role(body.role)
    f = {
        "role": role,
        "first_name": reg_svc.clean_text("first_name", body.first_name, required=True),
        "last_name": reg_svc.clean_text("last_name", body.last_name, required=True),
        "phone": reg_svc.clean_phone(body.phone),
        "email": reg_svc.clean_email(body.email),
        "date_of_birth": reg_svc.clean_dob(body.date_of_birth),
        "years_played": reg_svc.clean_text("years_played", body.years_played),
        "grades_played": reg_svc.clean_text("grades_played", body.grades_played),
        "notes": reg_svc.clean_text("notes", body.notes),
        "interests": reg_svc.clean_interests(body.interests),
        "contact_consent": bool(body.contact_consent),
        # Only someone who plays (or played) has a batting hand worth recording.
        "playing": reg_svc.clean_playing(body.playing) if role in reg_svc.PLAYING_ROLES else {},
    }
    from app.services import player_audit
    who = f"{f['first_name']} {f['last_name']}"

    if body.claim_player_id:
        try:
            pid = uuid.UUID(body.claim_player_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="That record wasn't found.")
        player = await db.get(Player, pid)
        if not player or player.organisation_id != club.id or not player.is_player:
            raise HTTPException(status_code=404, detail="That record wasn't found.")
        if not await reg_svc.may_sign_in(db, club, player):
            raise HTTPException(status_code=409, detail="That record can't be used on the Player Dashboard. Ask your club.")
        pname = player.display_name
        on_file = phone_last4(player.phone)

        # The strongest proof there is: the whole mobile they typed is the one on their record.
        if reg_svc.same_mobile(player.phone, f["phone"]):
            return await _matched(db, club, player, f, "mobile", response, who)

        if on_file is not None and club.availability_require_pin:
            if not (body.pin or "").strip():
                return {"status": "need_pin", "player_name": pname}
            lock_key = f"avail-verify:{token}:{pid}:{ip}"
            rate_limit.assert_not_locked(lock_key, PIN_MAX_FAILURES, PIN_LOCKOUT_SECONDS,
                                         detail="Too many incorrect attempts. Please wait a few minutes and try again.")
            if phone_last4(body.pin) != on_file:
                rate_limit.record_failure(lock_key, PIN_LOCKOUT_SECONDS)
                raise HTTPException(status_code=401, detail=f"Those digits don't match the mobile the club has for {pname}.")
            rate_limit.clear_failures(lock_key)
            return await _matched(db, club, player, f, "pin", response, who)

        # Nothing proves it is them: a record with no mobile (the one they typed would become its
        # PIN), or a club that runs the link on names alone. The club confirms it.
        signed_in = on_file is not None  # PIN off: the page lets anyone in by name anyway
        await _insert(db, club, pid, "claim", f)
        await player_audit.record(
            db, club_id=club.id, area="details", action="registration_claim_pending",
            summary=f"{who} says they are {pname} and asked the club to confirm it",
            player_id=pid, player_name_=pname, user=None, via="player link", by=who,
        )
        await db.commit()
        _tell_the_club(club.id)
        if signed_in:
            _issue_cookie(response, club.id, pid)
            return {"status": "signed_in", "matched": False, "player_name": pname}
        return {"status": "pending", "player_name": pname}

    # Not picked from the past-player list. Smart matching, strongest first.
    # 1. Their mobile is already on a record: the same name means it is them.
    rows = (await db.execute(select(Player).where(
        Player.organisation_id == club.id, Player.phone.isnot(None)))).scalars().all()
    clash = [p for p in rows if reg_svc.same_mobile(p.phone, f["phone"])]
    if clash:
        regs = await reg_svc.latest_by_player(db, club.id, [p.id for p in clash])
        for p in clash:
            if not reg_svc.same_person_name(p, f["first_name"], f["last_name"]):
                continue
            r = regs.get(p.id)
            if p.is_player:
                if r and r["kind"] == "new" and r["status"] == "archived":
                    break
                if await reg_svc.may_sign_in(db, club, p):
                    return await _matched(db, club, p, f, "mobile", response, who)
            elif r and r["kind"] == "new" and r["status"] in reg_svc.LIVE:
                # They added themselves before and lost the cookie: back in, nothing new made.
                _issue_cookie(response, club.id, p.id)
                return {"status": "signed_in", "matched": False, "player_name": p.display_name, "existing": True}
        raise HTTPException(
            status_code=409,
            detail="That mobile is already on file for someone else at the club. Check the number, or ask your club.",
        )

    # 2. Their name is already on the books: ask before making a second record of them.
    if not body.confirmed_new:
        likely = [p for p in await club_player_roster(db, club)
                  if p.is_public is not False and reg_svc.same_person_name(p, f["first_name"], f["last_name"])][:5]
        if likely:
            last = await _last_played(db, [p.id for p in likely])
            return {"status": "possible_matches", "players": [
                {"id": str(p.id), "display_name": p.display_name,
                 "last_played_year": last[p.id].year if last.get(p.id) else None,
                 "has_phone": phone_last4(p.phone) is not None}
                for p in likely]}

    # 3. Someone new.
    pl = f["playing"]
    player = Player(
        id=uuid.uuid4(),
        name=reg_svc.stored_name(f["first_name"], f["last_name"]),
        organisation_id=club.id,
        # "Not a player" until the club approves a current player: keeps a self-added name off
        # selection boards, player voting and fantasy pools.
        is_player=False,
        # No public profile for someone who has not been approved.
        is_public=False,
        status="active",
        claimed=False,
        skill_positions=[],
    )
    db.add(player)
    reg_svc.fill_empty(player, f)
    await db.flush()
    await _insert(db, club, player.id, "new", f)
    await player_audit.record(
        db, club_id=club.id, area="details", action="registration_new",
        summary=f"{who} added themselves on the Player Dashboard as {reg_svc.ROLE_LABELS[f['role']].lower()}",
        player_id=player.id, player_name_=who, user=None, via="player link", by=who,
    )
    await db.commit()
    _issue_cookie(response, club.id, player.id)
    _tell_the_club(club.id)
    return {"status": "signed_in", "matched": False, "player_name": who}
