"""Serve uploaded images (club logos, player photos) stored in the database.

Images live in Postgres rather than on the container filesystem so they
survive container recreation — the upload volume is not guaranteed to be
persisted in every deployment.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    ClubCommitteeMember, ClubGalleryImage, ClubNews, ClubRoomMedia, Organisation,
    Player, SocialMediaAsset, Sponsor, get_db,
)
from app.models.scout import ScoutedPlayer
from app.services import fonts as font_service

router = APIRouter(prefix="/images", tags=["images"])

# Stored URLs carry a ?v= cache-buster that changes on every re-upload, so the
# bytes at any given URL never change — safe to cache hard.
_CACHE_HEADERS = {"Cache-Control": "public, max-age=604800"}


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(404, "Not found")


# Mail clients render PNG/JPEG/GIF reliably but WebP support is patchy (Outlook's
# Word engine renders nothing, some Gmail proxies show a broken image). A logo
# fetched for an email asks for ?format=png so we transcode WebP to PNG on the way
# out; already-safe formats pass through untouched.
_EMAIL_SAFE_MIME = {"image/png", "image/jpeg", "image/gif"}


def _to_png(data: bytes) -> bytes:
    from io import BytesIO

    from PIL import Image

    with Image.open(BytesIO(data)) as im:
        im = im.convert("RGBA")
        out = BytesIO()
        im.save(out, format="PNG")
        return out.getvalue()


@router.get("/organisations/{org_id}/logo")
async def get_org_logo(org_id: str, format: str | None = None, db: AsyncSession = Depends(get_db)):
    org = await db.get(Organisation, _parse_uuid(org_id))
    if not org or not org.logo_data:
        raise HTTPException(404, "No logo")
    data = org.logo_data
    mime = org.logo_mime or "image/png"
    # Transcode to an email-safe format when requested and the stored image isn't one.
    if (format or "").lower() == "png" and mime not in _EMAIL_SAFE_MIME:
        try:
            data = _to_png(data)
            mime = "image/png"
        except Exception:
            pass  # fall back to the stored bytes rather than 500 the image
    return Response(content=data, media_type=mime, headers=_CACHE_HEADERS)


@router.get("/organisations/{org_id}/font/{role}")
async def get_org_font(org_id: str, role: str, db: AsyncSession = Depends(get_db)):
    if role not in font_service.FONT_ROLES:
        raise HTTPException(404, "Unknown font role")
    org = await db.get(Organisation, _parse_uuid(org_id))
    data = getattr(org, f"font_{role}_data", None) if org else None
    if not data:
        raise HTTPException(404, "No font")
    mime = getattr(org, f"font_{role}_mime", None) or "font/woff2"
    return Response(content=data, media_type=mime, headers=_CACHE_HEADERS)


@router.get("/organisations/{org_id}/hero")
async def get_org_hero(org_id: str, db: AsyncSession = Depends(get_db)):
    org = await db.get(Organisation, _parse_uuid(org_id))
    if not org or not org.hero_image_data:
        raise HTTPException(404, "No hero image")
    return Response(
        content=org.hero_image_data,
        media_type=org.hero_image_mime or "image/jpeg",
        headers=_CACHE_HEADERS,
    )


@router.get("/news/{news_id}/cover")
async def get_news_cover(news_id: str, db: AsyncSession = Depends(get_db)):
    article = await db.get(ClubNews, _parse_uuid(news_id))
    if not article or not article.cover_image_data:
        raise HTTPException(404, "No cover image")
    return Response(
        content=article.cover_image_data,
        media_type=article.cover_image_mime or "image/jpeg",
        headers=_CACHE_HEADERS,
    )


@router.get("/committee/{member_id}/photo")
async def get_committee_photo(member_id: str, db: AsyncSession = Depends(get_db)):
    member = await db.get(ClubCommitteeMember, _parse_uuid(member_id))
    if not member or not member.photo_data:
        raise HTTPException(404, "No photo")
    return Response(
        content=member.photo_data,
        media_type=member.photo_mime or "image/png",
        headers=_CACHE_HEADERS,
    )


@router.get("/gallery/{image_id}")
async def get_gallery_image(image_id: str, db: AsyncSession = Depends(get_db)):
    img = await db.get(ClubGalleryImage, _parse_uuid(image_id))
    if not img or not img.image_data:
        raise HTTPException(404, "No image")
    return Response(
        content=img.image_data,
        media_type=img.image_mime or "image/jpeg",
        headers=_CACHE_HEADERS,
    )


@router.get("/players/{player_id}/photo")
async def get_player_photo(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, _parse_uuid(player_id))
    if not player or not player.photo_data:
        raise HTTPException(404, "No photo")
    return Response(
        content=player.photo_data,
        media_type=player.photo_mime or "image/png",
        headers=_CACHE_HEADERS,
    )


@router.get("/players/{player_id}/hero-photo")
async def get_player_hero_photo(player_id: str, db: AsyncSession = Depends(get_db)):
    """The player's action shot — see migration 272 for why it is a separate
    photograph from the headshot above. Same no-auth posture as that one: a
    low-sensitivity image behind an unguessable id."""
    player = await db.get(Player, _parse_uuid(player_id))
    if not player or not player.hero_photo_data:
        raise HTTPException(404, "No hero photo")
    return Response(
        content=player.hero_photo_data,
        media_type=player.hero_photo_mime or "image/png",
        headers=_CACHE_HEADERS,
    )


@router.get("/scouted-players/{scouted_player_id}/photo")
async def get_scouted_player_photo(scouted_player_id: str, db: AsyncSession = Depends(get_db)):
    """BetterScout's own scout-uploaded fallback photo — see
    services/scout_discovery.player_out for when this is used vs a real
    linked BetterCricket player's photo_url. No auth: same posture as the
    club player photo above, a low-sensitivity image behind an unguessable
    UUID."""
    player = await db.get(ScoutedPlayer, _parse_uuid(scouted_player_id))
    if not player or not player.photo_data:
        raise HTTPException(404, "No photo")
    return Response(
        content=player.photo_data,
        media_type=player.photo_mime or "image/png",
        headers=_CACHE_HEADERS,
    )


@router.get("/sponsors/{sponsor_id}/logo")
async def get_sponsor_logo(sponsor_id: str, db: AsyncSession = Depends(get_db)):
    sponsor = await db.get(Sponsor, _parse_uuid(sponsor_id))
    if not sponsor or not sponsor.logo_data:
        raise HTTPException(404, "No logo")
    return Response(
        content=sponsor.logo_data,
        media_type=sponsor.logo_mime or "image/png",
        headers=_CACHE_HEADERS,
    )


@router.get("/social-media/{asset_id}")
async def get_social_media_asset(asset_id: str, db: AsyncSession = Depends(get_db)):
    asset = await db.get(SocialMediaAsset, _parse_uuid(asset_id))
    if not asset or not asset.image_data:
        raise HTTPException(404, "No image")
    return Response(
        content=asset.image_data,
        media_type=asset.mime or "image/jpeg",
        headers=_CACHE_HEADERS,
    )


@router.get("/club-room/{media_id}")
async def get_club_room_media(media_id: str, db: AsyncSession = Depends(get_db)):
    media = await db.get(ClubRoomMedia, _parse_uuid(media_id))
    if not media or not media.image_data:
        raise HTTPException(404, "No image")
    return Response(
        content=media.image_data,
        media_type=media.image_mime or "image/jpeg",
        headers=_CACHE_HEADERS,
    )


@router.get("/yearbooks/{yearbook_id}/hero")
async def get_yearbook_hero(yearbook_id: str, db: AsyncSession = Depends(get_db)):
    _parse_uuid(yearbook_id)
    row = await db.execute(
        text("SELECT hero_image_data, hero_image_mime FROM yearbooks WHERE id = :id"),
        {"id": yearbook_id},
    )
    rec = row.mappings().first()
    if not rec or not rec["hero_image_data"]:
        raise HTTPException(404, "No hero image")
    return Response(
        content=rec["hero_image_data"],
        media_type=rec["hero_image_mime"] or "image/jpeg",
        headers=_CACHE_HEADERS,
    )


@router.get("/yearbooks/gallery/{image_id}")
async def get_yearbook_gallery_image(image_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.execute(
        text("SELECT image_data, image_mime FROM yearbook_images WHERE id = :id"),
        {"id": image_id},
    )
    rec = row.mappings().first()
    if not rec or not rec["image_data"]:
        raise HTTPException(404, "No image")
    return Response(
        content=rec["image_data"],
        media_type=rec["image_mime"] or "image/jpeg",
        headers=_CACHE_HEADERS,
    )
