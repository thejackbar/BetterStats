"""Player Cards: the club's settings (BetterStats, no module needed).

A club decides whether cards are on, whether juniors are in the card pool (off by default), how many
weekly packs each player gets, the timezone the week resets in, and which players are taken out of
the pool. The player-facing side is `public_player_cards`.

Gated on MANAGE_SETTINGS, the club-wide settings capability. A PATCH reads `model_fields_set`, so a
key that is not sent leaves its setting alone and an explicit null clears the timezone.
"""
from __future__ import annotations

import json
import secrets
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_SETTINGS, require_cap
from app.models.db import Organisation, Player, User, get_db
from app.routers.auth import get_current_club
from app.routers.public_availability import _club_branding
from app.services import audit_log, player_card_admin as insight, player_card_challenges as challenges, player_card_designs as pack_designs, player_cards as cards

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
    alerts_enabled: Optional[bool] = None
    sets_enabled: Optional[bool] = None
    showcase_enabled: Optional[bool] = None
    board_enabled: Optional[bool] = None
    feed_enabled: Optional[bool] = None
    event_packs_enabled: Optional[bool] = None
    winner_packs: Optional[bool] = None
    starter_gifts: Optional[str] = None
    big_photos: Optional[str] = None


class EventBody(BaseModel):
    title: str
    starts_on: date
    ends_on: Optional[date] = None
    per_day: bool = True
    quality: str = "special"


class GiftBody(BaseModel):
    """Packs an admin creates by hand. `request_id` is the screen's id for this click, so a double click grants once."""
    title: str
    quality: str = "special"
    qty: int = 1
    audience: str = "all"
    player_ids: list[str] = []
    request_id: Optional[str] = None
    size: int = 5


class DesignBody(BaseModel):
    """Only the keys sent are changed; an explicit null clears a colour or the name."""
    title: Optional[str] = None
    color_a: Optional[str] = None
    color_b: Optional[str] = None
    color_on: Optional[str] = None
    overlay: Optional[float] = None
    show_name: Optional[bool] = None
    show_logo: Optional[bool] = None
    art_position: Optional[str] = None
    art_size: Optional[str] = None


class ChallengeBody(BaseModel):
    """A challenge as the admin screen sends it. `rules` is for an exchange, `selector` and `need` for a collection."""
    kind: str
    title: str
    blurb: Optional[str] = None
    rules: dict = {}
    selector: Optional[dict] = None
    need: Optional[int] = None
    reward: dict = {}
    max_completions: int = 1
    starts_on: Optional[str] = None
    ends_on: Optional[str] = None
    active: bool = True
    sort_order: int = 0


class TrimBody(BaseModel):
    apply: bool = False


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
        # The club's colours and fonts, so the screen can draw the cards as the players see them.
        "club": _club_branding(club),
        "settings": {
            "enabled": settings["enabled"],
            "include_juniors": settings["include_juniors"],
            "weekly_packs": settings["weekly_packs"],
            "timezone": settings["timezone"],
            "alerts_enabled": settings.get("alerts_enabled", True) is not False,
            **{k: settings.get(k, True) is not False for k in ("sets_enabled", "showcase_enabled", "board_enabled", "feed_enabled",
                                                         "event_packs_enabled", "winner_packs")},
            "starter_gifts": settings.get("starter_gifts") or "minimal",
            "big_photos": settings.get("big_photos") or "all",
            "effective_timezone": str(cards.club_zone(settings)),
        },
        "timezones": [{"id": i, "label": n} for i, n in TIMEZONES],
        "events": await cards.list_events(db, club.id),
        "gifts": await cards.list_gifts(db, club.id),
        "qualities": cards.quality_options(),
        "max_gift_qty": cards.MAX_GIFT_QTY,
        "pack_size": {"default": cards.PACK_SIZE, "min": cards.MIN_PACK_SIZE, "max": cards.MAX_PACK_SIZE},
        "designs": await pack_designs.load_all(db, club.id),
        "design_targets": await pack_designs.targets(db, club.id),
        "max_weekly_packs": cards.MAX_WEEKLY_PACKS,
        "link": {"path": f"/playerdash/{club.availability_link_token}" if club.availability_link_token else None},
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


@router.post("/events")
async def add_event(
    body: EventBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    """Schedule a pack for a day or a run of days (a Test match, a club day). Players get it the day they open their page."""
    await cards.ensure_launched(db, club.id)
    try:
        ev = await cards.add_event(db, club.id, body.title, body.starts_on, body.ends_on, body.per_day, body.quality)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    await audit_log.log_activity(db, org_id=club.id, user_id=user.id, action="player_card_event_added",
                                 target_type="card_event", target_id=ev["id"], details=ev)
    await db.commit()
    return await _payload(db, club)


@router.post("/gifts")
async def create_gift(
    body: GiftBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    """Create packs now and put them in players' hands: everyone with a card, or the players chosen. Players open them from their page."""
    snap = await cards.club_snapshot(db, club, fresh=True)
    await cards.ensure_launched(db, club.id)
    try:
        out = await cards.create_gift(db, club, snap, title=body.title, quality=body.quality, qty=body.qty, audience=body.audience,
                                      player_ids=body.player_ids, request_id=body.request_id, by=getattr(user, "email", None), size=body.size)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    if not out["repeat"]:
        await audit_log.log_activity(db, org_id=club.id, user_id=user.id, action="player_card_pack_gift", target_type="card_pack_gift",
                                     target_id=out["id"], details={k: out[k] for k in ("title", "quality", "qty", "players", "packs")})
    await db.commit()
    return {"gift": out, **await _payload(db, club)}


# ── Challenges: sets with a goal and a reward ─────────────────────────────────────────────────────────────────

def _challenge_http(exc: "challenges.ChallengeError") -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.message)


async def _challenge_payload(db: AsyncSession, club: Organisation) -> dict:
    snap = await cards.club_snapshot(db, club)
    drawable = [pid for pid, f in snap["figs"].items() if f["matches"] > 0 and pid in snap["people"]]
    return {
        "challenges": await challenges.admin_list(db, club),
        "premierships": await challenges.premiership_options(db, club, snap),
        "players": sorted(({"id": pid, "name": snap["people"][pid]["display_name"]} for pid in drawable), key=lambda p: p["name"].lower()),
        "tiers": [{"key": k, "label": challenges.TIER_NAME[k]} for k in challenges.TIER_KEYS],
        "special_kinds": [{"key": k, "label": v} for k, v in cards.SPECIAL_KINDS.items()],
        "qualities": cards.quality_options(),
        "limits": {"count": challenges.MAX_COUNT, "completions": challenges.MAX_COMPLETIONS, "reward_qty": challenges.MAX_REWARD_QTY,
                   "pack_size": {"min": cards.MIN_PACK_SIZE, "max": cards.MAX_PACK_SIZE, "default": cards.PACK_SIZE}},
    }


@router.get("/challenges")
async def list_challenges(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    return await _challenge_payload(db, club)


@router.post("/challenges")
async def create_challenge(
    body: ChallengeBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    """Publish a challenge to every player: a squad challenge (pick cards you hold that meet the rules) or a collection (hold a list of cards)."""
    snap = await cards.club_snapshot(db, club, fresh=True)
    try:
        made = await challenges.admin_save(db, club, snap, body.model_dump(), None, getattr(user, "email", None))
    except challenges.ChallengeError as exc:
        await db.rollback()
        raise _challenge_http(exc)
    await cards.ensure_launched(db, club.id)
    await audit_log.log_activity(db, org_id=club.id, user_id=user.id, action="player_card_challenge_made", target_type="card_challenge",
                                 target_id=made["id"], details={"title": made["title"], "kind": made["kind"]})
    await db.commit()
    return await _challenge_payload(db, club)


@router.put("/challenges/{challenge_id}")
async def update_challenge(
    challenge_id: str,
    body: ChallengeBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    snap = await cards.club_snapshot(db, club, fresh=True)
    try:
        uuid.UUID(challenge_id)
        made = await challenges.admin_save(db, club, snap, body.model_dump(), challenge_id, getattr(user, "email", None))
    except ValueError:
        raise HTTPException(status_code=404, detail="Challenge not found.")
    except challenges.ChallengeError as exc:
        await db.rollback()
        raise _challenge_http(exc)
    await audit_log.log_activity(db, org_id=club.id, user_id=user.id, action="player_card_challenge_changed", target_type="card_challenge",
                                 target_id=made["id"], details={"title": made["title"], "kind": made["kind"]})
    await db.commit()
    return await _challenge_payload(db, club)


@router.delete("/challenges/{challenge_id}")
async def delete_challenge(
    challenge_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    """Remove a challenge. What players completed stays on record, and the packs they earned stay theirs."""
    try:
        uuid.UUID(challenge_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Challenge not found.")
    if not await challenges.admin_delete(db, club, challenge_id):
        raise HTTPException(status_code=404, detail="Challenge not found.")
    await audit_log.log_activity(db, org_id=club.id, user_id=user.id, action="player_card_challenge_removed", target_type="card_challenge", target_id=challenge_id)
    await db.commit()
    return await _challenge_payload(db, club)


@router.post("/gifts/designed")
async def create_designed_gift(
    title: str = Form(...),
    quality: str = Form("special"),
    qty: int = Form(1),
    audience: str = Form("all"),
    player_ids: str = Form("[]"),
    request_id: Optional[str] = Form(None),
    size: int = Form(5),
    style: str = Form("{}"),
    bg: Optional[UploadFile] = File(None),
    art: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    """Create packs now AND give them a look of their own in the same step: a style (colours, darkness, layout) and a background and/or
    centre picture. Everything is checked before anything is made, so a bad picture or colour makes no packs and no half design."""
    try:
        ids = json.loads(player_ids or "[]")
        raw_style = json.loads(style or "{}")
        if not isinstance(ids, list) or not isinstance(raw_style, dict):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=422, detail="That request could not be read.")
    try:
        clean = pack_designs.clean_style({k: v for k, v in raw_style.items() if k != "title"})
        images = {}
        for kind, up in (("bg", bg), ("art", art)):
            if up is not None and up.filename:
                images[kind] = pack_designs.process_image(await up.read(pack_designs.MAX_UPLOAD_BYTES + 1), kind)
    except pack_designs.DesignError as exc:
        raise _design_error(exc)
    snap = await cards.club_snapshot(db, club, fresh=True)
    await cards.ensure_launched(db, club.id)
    try:
        out = await cards.create_gift(db, club, snap, title=title, quality=quality, qty=qty, audience=audience,
                                      player_ids=[str(i) for i in ids], request_id=request_id, by=getattr(user, "email", None), size=size)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    if not out["repeat"]:
        target = pack_designs.gift_target(out["id"])
        if clean:
            await pack_designs.save_style(db, club.id, target, clean)
        for kind, (data, mime) in images.items():
            await pack_designs.put_image(db, club.id, target, kind, data, mime)
        await audit_log.log_activity(db, org_id=club.id, user_id=user.id, action="player_card_pack_gift", target_type="card_pack_gift",
                                     target_id=out["id"], details={**{k: out[k] for k in ("title", "quality", "qty", "players", "packs", "size")},
                                                                   "designed": bool(clean or images)})
    await db.commit()
    return {"gift": out, **await _payload(db, club)}


@router.delete("/events/{event_id}")
async def delete_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    try:
        uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    if not await cards.delete_event(db, club.id, event_id):
        raise HTTPException(status_code=404, detail="Not found")
    await pack_designs.drop_event(db, club.id, event_id)
    await audit_log.log_activity(db, org_id=club.id, user_id=user.id, action="player_card_event_removed",
                                 target_type="card_event", target_id=event_id)
    await db.commit()
    return await _payload(db, club)


# ── Pack designs: a club's own look for its packs ────────────────────────────────────────────────────────────

def _design_error(exc: "pack_designs.DesignError") -> HTTPException:
    return HTTPException(status_code=exc.status, detail=str(exc))


@router.put("/designs/{target}")
async def save_design(
    target: str,
    body: DesignBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    """Change a design's colours, name and layout. Only what is sent changes."""
    patch = {k: getattr(body, k) for k in body.model_fields_set}
    try:
        await pack_designs.save_style(db, club.id, target, patch)
    except pack_designs.DesignError as exc:
        await db.rollback()
        raise _design_error(exc)
    await db.commit()
    return {"designs": await pack_designs.load_all(db, club.id)}


@router.post("/designs/{target}/{kind}")
async def upload_design_image(
    target: str,
    kind: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    """Set a design's background (`bg`) or centre image (`art`). The picture is checked, shrunk and re-encoded."""
    raw = await file.read(pack_designs.MAX_UPLOAD_BYTES + 1)
    try:
        await pack_designs.set_image(db, club.id, target, kind, raw)
    except pack_designs.DesignError as exc:
        await db.rollback()
        raise _design_error(exc)
    await audit_log.log_activity(db, org_id=club.id, user_id=user.id, action="player_card_design_image",
                                 target_type="card_pack_design", target_id=target, details={"kind": kind, "bytes": len(raw)})
    await db.commit()
    return {"designs": await pack_designs.load_all(db, club.id)}


@router.delete("/designs/{target}/{kind}")
async def remove_design_image(
    target: str,
    kind: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    try:
        await pack_designs.clear_image(db, club.id, target, kind)
    except pack_designs.DesignError as exc:
        await db.rollback()
        raise _design_error(exc)
    await db.commit()
    return {"designs": await pack_designs.load_all(db, club.id)}


@router.delete("/designs/{target}")
async def reset_design(
    target: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    """Back to the built-in look for this kind of pack."""
    try:
        await pack_designs.reset(db, club.id, target)
    except pack_designs.DesignError as exc:
        await db.rollback()
        raise _design_error(exc)
    await audit_log.log_activity(db, org_id=club.id, user_id=user.id, action="player_card_design_reset",
                                 target_type="card_pack_design", target_id=target)
    await db.commit()
    return {"designs": await pack_designs.load_all(db, club.id)}


@router.post("/trim-gifts")
async def trim_gifts(
    body: TrimBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    """Take the starting cards back to the minimal set (debut and latest landmark). `apply` false only counts what would go."""
    await cards.refresh_specials(db, club, force=True)
    out = await cards.trim_gifts(db, str(club.id), apply=body.apply)
    if out["applied"]:
        await audit_log.log_activity(db, org_id=club.id, user_id=user.id, action="player_card_gifts_trimmed",
                                     target_type="organisation", target_id=str(club.id), details=out)
    await db.commit()
    return out


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


# ── What the club can see: reads only ────────────────────────────────────────────────────────────────────────

@router.get("/overview")
async def overview(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    """Totals, and a row per player: cards collected, packs opened and waiting, when, and swaps."""
    snap = await cards.club_snapshot(db, club)
    return await insight.overview(db, club, snap)


@router.get("/activity")
async def activity(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    """What was added lately: special cards, the latest cards pulled or swapped in, the latest packs opened,
    and a fortnight of special cards added, packs opened and swaps made."""
    snap = await cards.club_snapshot(db, club)
    return await insight.activity(db, club, snap)


@router.get("/catalogue")
async def catalogue(
    kind: str = Query("all", pattern="^(all|player|special)$"),
    special_kind: Optional[str] = Query(None, pattern="^[a-z_]{1,30}$"),
    q: str = Query("", max_length=80),
    sort: str = Query("rarity", pattern="^(rarity|name|recent|held)$"),
    limit: int = Query(60, ge=1, le=insight.PAGE_MAX),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    """Every card that can come out of a pack, with copies held and owners."""
    snap = await cards.club_snapshot(db, club)
    return await insight.catalogue(db, club, snap, kind=kind, special_kind=special_kind, q=q, sort=sort, limit=limit, offset=offset)


@router.get("/wanted")
async def most_wanted(
    limit: int = Query(15, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    """The cards most often on a wish list. Demand only, never whose list."""
    snap = await cards.club_snapshot(db, club)
    return await insight.most_wanted(db, club, snap, limit=limit)


@router.get("/players/{player_id}")
async def player_detail(
    player_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    """One player's whole collection, their packs and what they have pulled or swapped lately. 404, not 403,
    for another club's player."""
    try:
        pid = uuid.UUID(player_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Player not found")
    player = await db.get(Player, pid)
    if not player or player.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Player not found")
    snap = await cards.club_snapshot(db, club)
    return await insight.player_view(db, club, snap, player)


@router.get("/swaps")
async def swap_audit(
    status: str = Query("all", pattern="^(all|pending|accepted|declined|cancelled|countered|expired)$"),
    q: str = Query("", max_length=80),
    limit: int = Query(50, ge=1, le=insight.PAGE_MAX),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SETTINGS)),
):
    """Every swap request the club's players have made, whoever asked and however it ended."""
    snap = await cards.club_snapshot(db, club)
    return await insight.swap_audit(db, club, snap, status=status, q=q, limit=limit, offset=offset)
