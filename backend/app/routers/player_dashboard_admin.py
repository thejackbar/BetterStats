"""Player Dashboard: the club's settings (BetterStats, no module needed).

The player's own page (`/playerdash/:token`) holds their cards and season, so it belongs to
BetterStats. These routes are where a club switches the DASHBOARD on, hides the button on its public
site, sets the PIN, picks the modules and shares the link. They are NOT behind `require_module("select")`
like `/availability/self-service`.

The dashboard switch is its own (`organisations.player_dashboard_enabled`) and never touches the
BetterSelect availability switch, which keeps owning availability, votes and the BetterSelect sections
of the same link (`services/player_dashboard.availability_live` / `dashboard_live`). Gated on
MANAGE_SETTINGS, the club-wide settings capability. A key that is not sent leaves its setting alone.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_PLAYERS, MANAGE_SETTINGS, require_cap
from app.auth.modules import MODULE_SELECT, org_has_module
from app.models.db import Organisation, Player, User, get_db
from app.routers.auth import get_current_club
from app.routers.availability import active_self_service_players, phone_last4
from app.services import player_dashboard, player_registration as reg_svc
from app.services.player_audit import user_label

router = APIRouter(prefix="/player-dashboard", tags=["player-dashboard"])


class SettingsBody(BaseModel):
    enabled: Optional[bool] = None
    require_pin: Optional[bool] = None
    show_on_site: Optional[bool] = None
    # An empty list is a real choice (everything off); only None means "not sent".
    dashboard_modules: Optional[list[str]] = None
    # "Let people add themselves" (Can't find your name? on the player page).
    registration_enabled: Optional[bool] = None


async def _payload(db: AsyncSession, club: Organisation) -> dict:
    players = await active_self_service_players(db, club)
    with_phone = sum(1 for p in players if phone_last4(p.phone))
    return {
        "enabled": player_dashboard.dashboard_live(club),
        # With BetterSelect the same link also carries availability and votes, on their own switch.
        "has_select": org_has_module(club, MODULE_SELECT),
        "availability_enabled": player_dashboard.availability_live(club),
        "require_pin": bool(club.availability_require_pin),
        "show_on_site": club.availability_show_on_site is not False,
        "dashboard_modules": player_dashboard.catalogue_for(club),
        "token": club.availability_link_token,
        "path": f"/playerdash/{club.availability_link_token}" if club.availability_link_token else None,
        "phone_coverage": {"with_phone": with_phone, "total": len(players)},
        "registration_enabled": reg_svc.registration_open(club),
        "registrations_pending": (await db.execute(text(
            "SELECT count(*) FROM player_registrations WHERE organisation_id = :o AND status = 'pending'"
        ), {"o": str(club.id)})).scalar() or 0,
    }


@router.get("/settings")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    """The page's switches plus a phone-coverage count (a player signs in with the last four
    digits of their mobile, so a player with none cannot open their page)."""
    return await _payload(db, club)


@router.post("/settings")
async def update_settings(
    body: SettingsBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    if body.require_pin is not None:
        club.availability_require_pin = bool(body.require_pin)
    if body.show_on_site is not None:
        club.availability_show_on_site = bool(body.show_on_site)
    if body.dashboard_modules is not None:
        club.player_dashboard_modules = player_dashboard.store(body.dashboard_modules)
    if body.enabled is not None:
        player_dashboard.set_dashboard_live(club, body.enabled)
    if body.registration_enabled is not None:
        club.player_registration_enabled = bool(body.registration_enabled)
    await db.commit()
    await db.refresh(club)
    return await _payload(db, club)


@router.post("/regenerate")
async def regenerate_link(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    """Rotate the token: the old link and QR stop working at once."""
    club.availability_link_token = secrets.token_urlsafe(24)
    await db.commit()
    await db.refresh(club)
    return await _payload(db, club)


# ── People who added themselves ─────────────────────────────────────────────────
# The list of everyone who used "Can't find your name?", so the club can welcome them,
# approve them onto the name list, and follow up (play, volunteer, help out). Gated on
# MANAGE_PLAYERS: approving one changes a player record. Rows are archived, never deleted.

_LIST_SQL = """
SELECT r.*, COALESCE(p.display_name_override, p.name) AS player_name, p.is_player,
       (SELECT MAX(g.played_at) FROM game_appearances ga JOIN games g ON g.id = ga.game_id
         WHERE ga.player_id = r.player_id) AS last_played
  FROM player_registrations r
  LEFT JOIN players p ON p.id = r.player_id
 WHERE r.organisation_id = :o {extra}
 ORDER BY r.created_at DESC
"""


async def _rows(db: AsyncSession, club: Organisation, rid: Optional[uuid.UUID] = None) -> list[dict]:
    extra, params = "", {"o": str(club.id)}
    if rid is not None:
        extra, params["id"] = "AND r.id = :id", str(rid)
    rows = (await db.execute(text(_LIST_SQL.format(extra=extra)), params)).mappings().all()
    return [reg_svc.serialise(r) for r in rows]


async def _one(db: AsyncSession, club: Organisation, registration_id: str) -> dict:
    try:
        rid = uuid.UUID(registration_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Registration not found")
    found = await _rows(db, club, rid)
    if not found:
        raise HTTPException(status_code=404, detail="Registration not found")
    return found[0]


@router.get("/registrations")
async def list_registrations(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_PLAYERS)),
):
    """Everyone who added themselves or claimed an old record, newest first, with the form's
    roles and interests so the screen can label them."""
    rows = await _rows(db, club)
    return {
        "registrations": rows,
        "roles": reg_svc.ROLES,
        "interests": reg_svc.INTERESTS,
        "counts": {s: sum(1 for r in rows if r["status"] == s) for s in reg_svc.STATUSES},
        "registration_enabled": reg_svc.registration_open(club),
    }


async def _set_status(db: AsyncSession, club: Organisation, rid: str, status: str, by: str, reviewed: bool) -> None:
    await db.execute(text(
        "UPDATE player_registrations SET status = :s, updated_at = now()"
        + (", reviewed_at = now(), reviewed_by = :by" if reviewed else "")
        + " WHERE id = :id AND organisation_id = :o"
    ), {"s": status, "by": by, "id": rid, "o": str(club.id)})


@router.post("/registrations/{registration_id}/approve")
async def approve_registration(
    registration_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_PLAYERS)),
):
    """Confirm them. A new person joins the public name list; one who said they are a current
    player becomes a player (selection, votes, public profile). A claimed record gets the mobile,
    email (with their consent) and date of birth they gave where the club had none, and a current
    player is marked no longer dormant so they show for selection before their first game."""
    from app.services import player_audit
    reg = await _one(db, club, registration_id)
    if reg["status"] == "approved":
        return reg
    player = await db.get(Player, uuid.UUID(reg["player_id"])) if reg["player_id"] else None
    if player is None or player.organisation_id != club.id:
        raise HTTPException(status_code=409, detail="The player record behind this registration is gone, so there is nothing to approve.")
    changes: list[str] = []
    current = reg["role"] == "current_player"
    if reg["kind"] == "new":
        if player.status == "inactive":
            player.status = "active"
        if current and player.is_player is not True:
            player.is_player = True
            player.is_public = True
            changes.append("now a player")
    else:
        if not (player.phone or "").strip() and reg["phone"]:
            player.phone = reg["phone"]; changes.append("mobile added")
        if not (player.email or "").strip() and reg["email"] and reg["contact_consent"]:
            player.email = reg["email"]; changes.append("email added")
        if player.date_of_birth is None and reg["date_of_birth"]:
            player.date_of_birth = date.fromisoformat(reg["date_of_birth"]); changes.append("date of birth added")
        if current:
            player.dormancy_cleared_on = date.today(); changes.append("marked no longer dormant")
    name = player.display_name
    by = user_label(user)
    await _set_status(db, club, reg["id"], "approved", by, reviewed=True)
    await player_audit.record(
        db, club_id=club.id, area="details", action="registration_approved",
        summary=f"Approved {name}'s Player Dashboard registration" + (f" ({', '.join(changes)})" if changes else ""),
        player_id=player.id, player_name_=name, user=user,
        detail={"registration_id": reg["id"], "changes": changes},
    )
    await db.commit()
    return await _one(db, club, registration_id)


@router.post("/registrations/{registration_id}/archive")
async def archive_registration(
    registration_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_PLAYERS)),
):
    """Take it off the list. A self-added record also loses the Player Dashboard and is marked
    inactive (so off the name list and selection). The row and the record stay: Restore undoes it."""
    from app.services import player_audit
    reg = await _one(db, club, registration_id)
    if reg["status"] == "archived":
        return reg
    player = await db.get(Player, uuid.UUID(reg["player_id"])) if reg["player_id"] else None
    if reg["kind"] == "new" and player is not None and player.organisation_id == club.id:
        player.status = "inactive"
    await _set_status(db, club, reg["id"], "archived", user_label(user), reviewed=False)
    name = player.display_name if player is not None else f"{reg['first_name']} {reg['last_name']}".strip()
    await player_audit.record(
        db, club_id=club.id, area="details", action="registration_archived",
        summary=f"Archived {name}'s Player Dashboard registration",
        player_id=player.id if player is not None else None, player_name_=name, user=user,
        detail={"registration_id": reg["id"], "was": reg["status"]},
    )
    await db.commit()
    return await _one(db, club, registration_id)


@router.post("/registrations/{registration_id}/restore")
async def restore_registration(
    registration_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_PLAYERS)),
):
    """Undo Archive: back to approved if it had been approved, otherwise waiting for review."""
    from app.services import player_audit
    reg = await _one(db, club, registration_id)
    if reg["status"] != "archived":
        return reg
    player = await db.get(Player, uuid.UUID(reg["player_id"])) if reg["player_id"] else None
    if reg["kind"] == "new" and player is not None and player.organisation_id == club.id:
        player.status = "active"
    await _set_status(db, club, reg["id"], "approved" if reg["reviewed_at"] else "pending", user_label(user), reviewed=False)
    name = player.display_name if player is not None else f"{reg['first_name']} {reg['last_name']}".strip()
    await player_audit.record(
        db, club_id=club.id, area="details", action="registration_restored",
        summary=f"Restored {name}'s Player Dashboard registration",
        player_id=player.id if player is not None else None, player_name_=name, user=user,
        detail={"registration_id": reg["id"]},
    )
    await db.commit()
    return await _one(db, club, registration_id)


class FollowUpBody(BaseModel):
    """Only what is sent changes. `contacted` true stamps now, false clears it."""
    admin_note: Optional[str] = None
    contacted: Optional[bool] = None


@router.patch("/registrations/{registration_id}")
async def update_registration(
    registration_id: str,
    body: FollowUpBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_PLAYERS)),
):
    """The club's follow-up: a note and whether someone has been in touch."""
    reg = await _one(db, club, registration_id)
    sent = body.model_fields_set
    sets, params = [], {"id": reg["id"], "o": str(club.id)}
    if "admin_note" in sent:
        note = (body.admin_note or "").strip()
        if len(note) > 2000:
            raise HTTPException(status_code=422, detail="That note is too long (2000 characters at most).")
        sets.append("admin_note = :note"); params["note"] = note or None
    if "contacted" in sent and body.contacted is not None:
        sets.append("contacted_at = " + ("COALESCE(contacted_at, now())" if body.contacted else "NULL"))
    if sets:
        await db.execute(text(
            f"UPDATE player_registrations SET {', '.join(sets)}, updated_at = now() WHERE id = :id AND organisation_id = :o"
        ), params)
        await db.commit()
    return await _one(db, club, registration_id)
