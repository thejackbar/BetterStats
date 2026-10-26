"""Player Cards: the club's settings (BetterStats, no module needed).

A club decides whether cards are on, whether juniors are in the card pool (off by default), how many
weekly packs each player gets, the timezone the week resets in, and which players are taken out of
the pool. The player-facing side is `public_player_cards`.

Gated on MANAGE_SETTINGS, the club-wide settings capability. A PATCH reads `model_fields_set`, so a
key that is not sent leaves its setting alone and an explicit null clears the timezone.
"""
from __future__ import annotations

import secrets
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_SETTINGS, require_cap
from app.models.db import Organisation, Player, User, get_db
from app.routers.auth import get_current_club
from app.services import audit_log, player_cards as cards

router = APIRouter(prefix="/player-cards", tags=["player-cards"])

# The zones an Australian club picks from. The server accepts any IANA name; this is the list the
# screen offers.
TIMEZONES = [
    ("Australia/Perth", "Western Australia"),
    ("Australia/Adelaide", "South Australia"),
    ("Australia/Darwin", "Northern Territory"),
    ("Australia/Brisbane", "Queensland"),
    ("Australia/Sydney", "New South Wales, ACT"),
    ("Australia/Melbourne", "Victoria"),
    ("Australia/Hobart", "Tasmania"),
    ("Pacific/Auckland", "New Zealand"),
]


class SettingsBody(BaseModel):
    enabled: Optional[bool] = None
    include_juniors: Optional[bool] = None
    weekly_packs: Optional[int] = None
    timezone: Optional[str] = None


class HiddenBody(BaseModel):
    hidden: bool


async def _payload(db: AsyncSession, club: Organisation) -> dict:
    snap = await cards.club_snapshot(db, club, fresh=True)
    settings = snap["settings"]
    hidden = await cards.hidden_ids(db, club.id)
    players = (await db.execute(
        select(Player).where(Player.organisation_id == club.id, Player.is_player.is_(True))
    )).scalars().all()
    rows = []
    for p in players:
        pid = str(p.id)
        fig = snap["figs"].get(pid)
        rating = snap["rating"].get(pid)
        rows.append({
            "id": pid,
            "display_name": p.display_name,
            "hidden": pid in hidden,
            "in_pool": bool(fig and fig["matches"] > 0 and pid in snap["people"]),
            "matches": fig["matches"] if fig else 0,
            "rarity": rating["score"] if rating else None,
            "tier": rating["tier"] if rating else None,
            # Not in the card pool for a reason the club did not choose here.
            "excluded": "private" if p.is_public is False else (None if pid in snap["people"] or pid in hidden else "junior"),
        })
    rows.sort(key=lambda r: (r["display_name"] or "").lower())
    return {
        "settings": {
            "enabled": settings["enabled"],
            "include_juniors": settings["include_juniors"],
            "weekly_packs": settings["weekly_packs"],
            "timezone": settings["timezone"],
            "effective_timezone": str(cards.club_zone(settings)),
        },
        "timezones": [{"id": i, "label": n} for i, n in TIMEZONES],
        "max_weekly_packs": cards.MAX_WEEKLY_PACKS,
        "link": {"path": f"/avail/{club.availability_link_token}" if club.availability_link_token else None},
        "pool": {"size": sum(1 for r in rows if r["in_pool"]), "players": len(rows)},
        "players": rows,
    }


@router.get("/settings")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    # Players reach their cards through the club's player page link. A club that never had one gets
    # it now, so the link on this screen works the first time it is opened.
    if not club.availability_link_token:
        club.availability_link_token = secrets.token_urlsafe(24)
        await db.commit()
    return await _payload(db, club)


@router.patch("/settings")
async def update_settings(
    body: SettingsBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    patch = {k: getattr(body, k) for k in body.model_fields_set}
    try:
        await cards.save_settings(db, club.id, patch)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return await _payload(db, club)


@router.post("/players/{player_id}/hidden")
async def hide_player(
    player_id: str,
    body: HiddenBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    """Take a player out of (or put them back into) the card pool. 404, not 403, for another club's
    player: a capability says the caller administers SOME club, nothing about this player."""
    try:
        pid = uuid.UUID(player_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Player not found")
    player = await db.get(Player, pid)
    if not player or player.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Player not found")
    await cards.ensure_launched(db, club.id)
    await cards.set_hidden(db, club.id, pid, body.hidden, getattr(user, "email", None))
    await audit_log.log_activity(
        db, org_id=club.id, user_id=user.id,
        action="player_card_hidden" if body.hidden else "player_card_shown",
        target_type="player", target_id=str(pid),
        details={"player": player.display_name},
    )
    await db.commit()
    return await _payload(db, club)


@router.post("/refresh-specials")
async def refresh_specials(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    """Look through the club's history for events that have no special card yet. Add-only."""
    made = await cards.refresh_specials(db, club, force=True)
    await db.commit()
    return {"made": made}
