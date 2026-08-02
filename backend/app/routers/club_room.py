"""Club Room Mode — an auto-rotating, full-screen slideshow a club leaves
running on a TV in the club room. Core capability (MANAGE_CLUB_ROOM), not a
paid module: every club gets it, but individual slide TYPES that pull from a
bolt-on module (fixtures/lineups needs BetterSelect, recent social posts
needs BetterSocials) are silently skipped for a club that isn't entitled —
the editor UI hides the option before it's ever saved, this is the defensive
backstop for a club that downgrades after saving a playlist that used it.

Two moving parts:
- A saved **playlist** (`club_room_slides`): an ordered list of slide-type
  entries an admin configures once. Each entry EXPANDS into one or more
  rendered slides on read — e.g. one "sponsors" entry becomes one slide per
  sponsor, exactly like "add sponsors as individual slides" was asked for.
- A shared **media pool** (`club_room_media`) for admin-uploaded custom
  images (source='upload') and social-post exports saved from the
  BetterSocials composer (source='social_export', see
  POST /media/social-export — gated on BetterSocials' own capability, not
  this module's, since it's the composer saving into this shared pool).

GET /settings and GET /play are open to any logged-in club member (viewing
the configured playlist / running the show needs no special permission,
matching how e.g. the sponsors list is read-only-open); every write endpoint
requires MANAGE_CLUB_ROOM.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_CLUB_ROOM, MANAGE_SOCIAL, require_cap
from app.auth.modules import org_has_module
from app.models.db import (
    ClubRoomMedia, ClubRoomSettings, ClubRoomSlide, Organisation, Sponsor, User, get_db,
)
from app.routers.auth import get_current_club, get_current_user

router = APIRouter(prefix="/club-admin/club-room", tags=["club-room"])

MEDIA_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MEDIA_MAX_BYTES = 8 * 1024 * 1024
MEDIA_MAX_PER_CLUB = 120
SLIDE_TYPES = {"sponsors", "fixtures", "social_posts", "custom_images"}
# Per-entry cap on how many individual slides one playlist row can expand
# into, so a misconfigured "show everything" entry can't produce a
# runaway-length loop.
EXPAND_CAP = 30

_IMAGE_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".gif": "image/gif",
}


async def _get_or_create_settings(db: AsyncSession, club: Organisation) -> ClubRoomSettings:
    row = await db.get(ClubRoomSettings, club.id)
    if row:
        return row
    row = ClubRoomSettings(organisation_id=club.id)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


def _settings_dict(s: ClubRoomSettings) -> dict:
    return {"enabled": s.enabled, "rotation_seconds": s.rotation_seconds}


def _slide_dict(s: ClubRoomSlide) -> dict:
    return {
        "id": str(s.id),
        "slide_type": s.slide_type,
        "title": s.title,
        "config": s.config or {},
        "duration_seconds": s.duration_seconds,
        "position": s.position,
        "enabled": s.enabled,
    }


async def _slide_or_404(db: AsyncSession, club: Organisation, slide_id: str) -> ClubRoomSlide:
    try:
        sid = uuid.UUID(slide_id)
    except (ValueError, AttributeError):
        raise HTTPException(404, "Not found")
    row = await db.get(ClubRoomSlide, sid)
    if not row or row.organisation_id != club.id:
        raise HTTPException(404, "Not found")
    return row


def _media_dict(m: ClubRoomMedia) -> dict:
    ts = int(m.created_at.timestamp()) if m.created_at else 0
    return {
        "id": str(m.id),
        "source": m.source,
        "caption": m.caption,
        "url": f"/api/images/club-room/{m.id}?v={ts}",
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


async def _save_media(db, club, current_user, data: bytes, mime: str, source: str, caption: str | None) -> ClubRoomMedia:
    media = ClubRoomMedia(
        organisation_id=club.id, source=source, caption=(caption or None),
        image_data=data, image_mime=mime, created_by=current_user.id,
    )
    db.add(media)
    await db.commit()
    await db.refresh(media)
    return media


# ─── Settings + playlist ──────────────────────────────────────────────────

@router.get("/settings")
async def get_settings(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    settings = await _get_or_create_settings(db, club)
    rows = await db.execute(
        select(ClubRoomSlide)
        .where(ClubRoomSlide.organisation_id == club.id)
        .order_by(ClubRoomSlide.position)
    )
    return {**_settings_dict(settings), "slides": [_slide_dict(s) for s in rows.scalars().all()]}


class SettingsPatch(BaseModel):
    enabled: Optional[bool] = None
    rotation_seconds: Optional[int] = None


@router.patch("/settings")
async def patch_settings(
    data: SettingsPatch,
    current_user: User = Depends(require_cap(MANAGE_CLUB_ROOM)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    settings = await _get_or_create_settings(db, club)
    if data.enabled is not None:
        settings.enabled = data.enabled
    if data.rotation_seconds is not None:
        settings.rotation_seconds = max(3, min(300, data.rotation_seconds))
    await db.commit()
    return _settings_dict(settings)


class SlideCreate(BaseModel):
    slide_type: str
    title: Optional[str] = None
    config: dict = {}
    duration_seconds: Optional[int] = None


@router.post("/slides", status_code=201)
async def create_slide(
    data: SlideCreate,
    current_user: User = Depends(require_cap(MANAGE_CLUB_ROOM)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    if data.slide_type not in SLIDE_TYPES:
        raise HTTPException(422, "Unknown slide type")
    from sqlalchemy import func
    max_pos = await db.scalar(
        select(func.max(ClubRoomSlide.position)).where(ClubRoomSlide.organisation_id == club.id)
    )
    slide = ClubRoomSlide(
        organisation_id=club.id, slide_type=data.slide_type, title=(data.title or None),
        config=data.config or {}, duration_seconds=data.duration_seconds,
        position=(max_pos + 1) if max_pos is not None else 0,
    )
    db.add(slide)
    await db.commit()
    await db.refresh(slide)
    return _slide_dict(slide)


class SlidePatch(BaseModel):
    title: Optional[str] = None
    config: Optional[dict] = None
    duration_seconds: Optional[int] = None
    enabled: Optional[bool] = None


@router.patch("/slides/{slide_id}")
async def patch_slide(
    slide_id: str,
    data: SlidePatch,
    current_user: User = Depends(require_cap(MANAGE_CLUB_ROOM)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    slide = await _slide_or_404(db, club, slide_id)
    if data.title is not None:
        slide.title = data.title or None
    if data.config is not None:
        slide.config = data.config
    if data.duration_seconds is not None:
        slide.duration_seconds = data.duration_seconds or None
    if data.enabled is not None:
        slide.enabled = data.enabled
    await db.commit()
    return _slide_dict(slide)


@router.delete("/slides/{slide_id}")
async def delete_slide(
    slide_id: str,
    current_user: User = Depends(require_cap(MANAGE_CLUB_ROOM)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    slide = await _slide_or_404(db, club, slide_id)
    await db.delete(slide)
    await db.commit()
    return {"ok": True}


class SlideReorderItem(BaseModel):
    id: str
    position: int


@router.put("/slides/reorder")
async def reorder_slides(
    items: list[SlideReorderItem],
    current_user: User = Depends(require_cap(MANAGE_CLUB_ROOM)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    for item in items:
        try:
            sid = uuid.UUID(item.id)
        except (ValueError, AttributeError):
            continue
        slide = await db.get(ClubRoomSlide, sid)
        if slide and slide.organisation_id == club.id:
            slide.position = item.position
    await db.commit()
    return {"ok": True}


# ─── Media pool (custom uploads + saved social exports) ───────────────────

@router.get("/media")
async def list_media(
    source: Optional[str] = None,
    current_user: User = Depends(require_cap(MANAGE_CLUB_ROOM)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ClubRoomMedia).where(ClubRoomMedia.organisation_id == club.id)
    if source in ("upload", "social_export"):
        stmt = stmt.where(ClubRoomMedia.source == source)
    stmt = stmt.order_by(ClubRoomMedia.created_at.desc())
    rows = await db.execute(stmt)
    return [_media_dict(m) for m in rows.scalars().all()]


async def _check_media_quota(db, club):
    from sqlalchemy import func
    count = await db.scalar(
        select(func.count()).select_from(ClubRoomMedia).where(ClubRoomMedia.organisation_id == club.id)
    )
    if (count or 0) >= MEDIA_MAX_PER_CLUB:
        raise HTTPException(400, f"Club Room media is full ({MEDIA_MAX_PER_CLUB} images). Delete some first.")


@router.post("/media")
async def upload_media(
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
    current_user: User = Depends(require_cap(MANAGE_CLUB_ROOM)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in MEDIA_ALLOWED_EXTS:
        raise HTTPException(400, "Image files only (jpg, png, webp, gif)")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > MEDIA_MAX_BYTES:
        raise HTTPException(400, "Image must be 8 MB or smaller")
    await _check_media_quota(db, club)
    media = await _save_media(db, club, current_user, data, _IMAGE_MIME.get(ext, "image/jpeg"), "upload", caption)
    return _media_dict(media)


@router.post("/media/social-export")
async def save_social_export(
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
    # Gated on BetterSocials' own capability, not Club Room's — this is the
    # composer saving into the shared Club Room pool, so a club admin who can
    # use the Post Designer but not Club Room Mode can still save one.
    current_user: User = Depends(require_cap(MANAGE_SOCIAL)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > MEDIA_MAX_BYTES:
        raise HTTPException(400, "Image must be 8 MB or smaller")
    await _check_media_quota(db, club)
    media = await _save_media(db, club, current_user, data, "image/png", "social_export", caption)
    return _media_dict(media)


@router.delete("/media/{media_id}")
async def delete_media(
    media_id: str,
    current_user: User = Depends(require_cap(MANAGE_CLUB_ROOM)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    try:
        mid = uuid.UUID(media_id)
    except (ValueError, AttributeError):
        raise HTTPException(404, "Not found")
    media = await db.get(ClubRoomMedia, mid)
    if not media or media.organisation_id != club.id:
        raise HTTPException(404, "Not found")
    await db.delete(media)
    await db.commit()
    return {"ok": True}


# ─── Play — resolves the saved playlist into a flat, ready-to-render list ──

async def _expand_sponsors(db, club, entry: ClubRoomSlide) -> list[dict]:
    stmt = select(Sponsor).where(Sponsor.organisation_id == club.id)
    ids = (entry.config or {}).get("sponsor_ids")
    if ids:
        try:
            stmt = stmt.where(Sponsor.id.in_([uuid.UUID(x) for x in ids]))
        except (ValueError, TypeError):
            return []
    stmt = stmt.order_by(Sponsor.display_order, Sponsor.created_at)
    rows = (await db.execute(stmt)).scalars().all()
    out = []
    for s in rows:
        if not (s.logo_url or s.logo_data):
            continue
        out.append({
            "type": "sponsor", "id": str(s.id), "title": s.name,
            "website_url": s.website_url,
            "logo_url": s.logo_url or f"/api/images/sponsors/{s.id}/logo",
        })
        if len(out) >= EXPAND_CAP:
            break
    return out


async def _expand_fixtures(db, club, entry: ClubRoomSlide) -> list[dict]:
    if not org_has_module(club, "select"):
        return []
    from app.routers.selection import selection_overview
    data = await selection_overview(db=db, club=club)
    count = min((entry.config or {}).get("count", 3) or 3, EXPAND_CAP)
    out = []
    for f in (data.get("fixtures") or [])[:count]:
        lineup = [
            {"display_name": p["display_name"], "batting_order": p["batting_order"],
             "is_captain": p["is_captain"], "is_wicket_keeper": p["is_wicket_keeper"]}
            for p in (f.get("lineup") or [])
        ]
        out.append({
            "type": "fixture", "id": f["id"],
            "title": f.get("label") or (f"vs {f['opponent_name']}" if f.get("opponent_name") else "Upcoming fixture"),
            "opponent_name": f.get("opponent_name"), "team_name": f.get("team_name"),
            "grade_name": f.get("grade_name"), "played_on": f.get("played_on"),
            "start_time": f.get("start_time"), "venue": f.get("venue"),
            "home_away": f.get("home_away"), "round": f.get("round"),
            "lineup": lineup,
        })
    return out


async def _expand_media(db, club, entry: ClubRoomSlide, source: str, slide_type: str, default_count: int) -> list[dict]:
    count = min((entry.config or {}).get("count", default_count) or default_count, EXPAND_CAP)
    rows = (await db.execute(
        select(ClubRoomMedia)
        .where(ClubRoomMedia.organisation_id == club.id, ClubRoomMedia.source == source)
        .order_by(ClubRoomMedia.created_at.desc())
        .limit(count)
    )).scalars().all()
    out = []
    for m in rows:
        ts = int(m.created_at.timestamp()) if m.created_at else 0
        out.append({
            "type": slide_type, "id": str(m.id), "title": m.caption,
            "image_url": f"/api/images/club-room/{m.id}?v={ts}",
        })
    return out


@router.get("/play")
async def play(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    settings = await _get_or_create_settings(db, club)
    rows = await db.execute(
        select(ClubRoomSlide)
        .where(ClubRoomSlide.organisation_id == club.id, ClubRoomSlide.enabled == True)  # noqa: E712
        .order_by(ClubRoomSlide.position)
    )
    entries = rows.scalars().all()

    slides: list[dict] = []
    for entry in entries:
        if entry.slide_type == "sponsors":
            expanded = await _expand_sponsors(db, club, entry)
        elif entry.slide_type == "fixtures":
            expanded = await _expand_fixtures(db, club, entry)
        elif entry.slide_type == "social_posts":
            if not org_has_module(club, "socials"):
                expanded = []
            else:
                expanded = await _expand_media(db, club, entry, "social_export", "social_post", 6)
        elif entry.slide_type == "custom_images":
            expanded = await _expand_media(db, club, entry, "upload", "custom_image", EXPAND_CAP)
        else:
            expanded = []
        duration = entry.duration_seconds or settings.rotation_seconds
        for item in expanded:
            item["duration_seconds"] = duration
            item["playlist_title"] = entry.title
            slides.append(item)

    return {
        "enabled": settings.enabled,
        "rotation_seconds": settings.rotation_seconds,
        "club_name": club.name,
        "club_short": club.short_name or (club.name or "")[:2].upper(),
        "logo_url": (f"/api/images/organisations/{club.id}/logo" if club.logo_data or club.logo_url else None),
        "slides": slides,
    }
