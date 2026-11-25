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
REGISTER_IP_LIMIT = 8
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
    last: dict = {}
    if hits:
        rows = (await db.execute(text(
            "SELECT ga.player_id, MAX(g.played_at) AS lp FROM game_appearances ga "
            "JOIN games g ON g.id = ga.game_id WHERE ga.player_id = ANY(CAST(:ids AS uuid[])) "
            "GROUP BY ga.player_id"
        ), {"ids": [str(p.id) for p in hits]})).fetchall()
        last = {pid: lp for pid, lp in rows}
    return {
        "min_chars": SEARCH_MIN,
        "players": [
            {"id": str(p.id), "display_name": p.display_name,
             "last_played_year": last[p.id].year if last.get(p.id) else None,
             "has_phone": phone_last4(p.phone) is not None}
            for p in hits
        ],
    }


async def _insert(db: AsyncSession, club: Organisation, player_id, kind: str, f: dict) -> uuid.UUID:
    """Every registration starts `pending`: waiting for the club to look at it (a claim proven
    with the mobile is already signed in; review is the club's follow-up, not the gate)."""
    rid = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO player_registrations (id, organisation_id, player_id, kind, role, first_name, last_name, email, "
        "phone, date_of_birth, years_played, grades_played, notes, interests, contact_consent, status) "
        "VALUES (:id, :org, :pid, :kind, :role, :first, :last, :email, :phone, :dob, :years, :grades, "
        ":notes, CAST(:interests AS jsonb), :consent, 'pending')"
    ), {
        "id": rid, "org": club.id, "pid": player_id, "kind": kind, "role": f["role"], "first": f["first_name"],
        "last": f["last_name"], "email": f["email"], "phone": f["phone"], "dob": f["date_of_birth"],
        "years": f["years_played"], "grades": f["grades_played"], "notes": f["notes"],
        "interests": json.dumps(f["interests"]), "consent": f["contact_consent"],
    })
    return rid


def _fill_empty(player: Player, f: dict) -> list[str]:
    """Copy what they told us onto the player where the club has nothing (rule 1: never
    overwrite). The email goes across only with their consent to be contacted."""
    filled = []
    if not (player.phone or "").strip() and f["phone"]:
        player.phone = f["phone"]; filled.append("mobile")
    if not (player.email or "").strip() and f["email"] and f["contact_consent"]:
        player.email = f["email"]; filled.append("email")
    if player.date_of_birth is None and f["date_of_birth"]:
        player.date_of_birth = f["date_of_birth"]; filled.append("date of birth")
    return filled


@router.post("/{token}/register")
async def register(token: str, body: RegisterBody, request: Request, response: Response,
                   db: AsyncSession = Depends(get_db)):
    """Add yourself, or claim an older record of yours.

    Returns ``{"status": "signed_in"}`` with the session cookie when they can use the
    Player Dashboard now, or ``{"status": "pending"}`` when a claimed record has no mobile
    on file and the club has to confirm it is them first."""
    club = await _open_club(db, token)
    ip = _client_ip(request)
    rate_limit.enforce(f"reg-write:{token}:{ip}", REGISTER_IP_LIMIT, REGISTER_IP_WINDOW,
                       detail="Too many registrations from here just now. Try again later or ask your club.")

    f = {
        "role": reg_svc.clean_role(body.role),
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

        if on_file is None:
            # Nothing to prove it against, and the mobile they typed would become the PIN.
            await _insert(db, club, pid, "claim", f)
            await player_audit.record(
                db, club_id=club.id, area="details", action="registration_claim_pending",
                summary=f"{who} says they are {pname} and asked the club to confirm it",
                player_id=pid, player_name_=pname, user=None, via="player link", by=who,
            )
            await db.commit()
            return {"status": "pending", "player_name": pname}

        if club.availability_require_pin:
            lock_key = f"avail-verify:{token}:{pid}:{ip}"
            rate_limit.assert_not_locked(lock_key, PIN_MAX_FAILURES, PIN_LOCKOUT_SECONDS,
                                         detail="Too many incorrect attempts. Please wait a few minutes and try again.")
            if phone_last4(body.pin) != on_file:
                rate_limit.record_failure(lock_key, PIN_LOCKOUT_SECONDS)
                raise HTTPException(status_code=401, detail=f"That PIN didn't match the mobile on file for {pname}. Use its last 4 digits.")
            rate_limit.clear_failures(lock_key)
            filled = _fill_empty(player, f)
        else:
            # The club runs the link on names alone, so nothing here proves who they are:
            # sign them in as the page would, and leave the record for an admin to update.
            filled = []
        await _insert(db, club, pid, "claim", f)
        await player_audit.record(
            db, club_id=club.id, area="details", action="registration_claimed",
            summary=f"{who} found their old record ({pname}) on the Player Dashboard"
                    + (f" and added their {', '.join(filled)}" if filled else ""),
            player_id=pid, player_name_=pname, user=None, via="player link", by=who,
        )
        await db.commit()
        _issue_cookie(response, club.id, pid)
        return {"status": "signed_in", "player_name": pname}

    # New to the club's books. One mobile, one person: send someone already on file to find
    # their name instead of making a second record of them.
    rows = (await db.execute(select(Player.id, Player.phone).where(
        Player.organisation_id == club.id, Player.phone.isnot(None)))).all()
    clash = [pid for pid, ph in rows if reg_svc.same_mobile(ph, f["phone"])]
    if clash:
        regs = await reg_svc.latest_by_player(db, club.id, clash)
        for pid in clash:
            r = regs.get(pid)
            p = await db.get(Player, pid)
            if r and r["kind"] == "new" and r["status"] in reg_svc.LIVE and p is not None \
                    and p.name.lower() == reg_svc.stored_name(f["first_name"], f["last_name"]).lower():
                # They registered before (and lost the cookie): back in, nothing new made.
                _issue_cookie(response, club.id, pid)
                return {"status": "signed_in", "player_name": p.display_name, "existing": True}
        raise HTTPException(
            status_code=409,
            detail="That mobile is already on file for someone at the club. Use “Played here before?” to find your name, or ask your club.",
        )

    player = Player(
        id=uuid.uuid4(),
        name=reg_svc.stored_name(f["first_name"], f["last_name"]),
        organisation_id=club.id,
        # "Not a player" until the club approves a current player: keeps a self-added name off
        # selection boards, player voting and fantasy pools.
        is_player=False,
        # No public profile for someone who has not been approved.
        is_public=False,
        phone=f["phone"],
        email=f["email"] if f["contact_consent"] else None,
        date_of_birth=f["date_of_birth"],
        status="active",
        claimed=False,
        skill_positions=[],
    )
    db.add(player)
    await db.flush()
    await _insert(db, club, player.id, "new", f)
    await player_audit.record(
        db, club_id=club.id, area="details", action="registration_new",
        summary=f"{who} added themselves on the Player Dashboard as {reg_svc.ROLE_LABELS[f['role']].lower()}",
        player_id=player.id, player_name_=who, user=None, via="player link", by=who,
    )
    await db.commit()
    _issue_cookie(response, club.id, player.id)
    return {"status": "signed_in", "player_name": who}
