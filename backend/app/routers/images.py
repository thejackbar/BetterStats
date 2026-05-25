"""Serve uploaded images (club logos, player photos) stored in the database.

Images live in Postgres rather than on the container filesystem so they
survive container recreation — the upload volume is not guaranteed to be
persisted in every deployment.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation, Player, Sponsor, get_db

router = APIRouter(prefix="/images", tags=["images"])

# Stored URLs carry a ?v= cache-buster that changes on every re-upload, so the
# bytes at any given URL never change — safe to cache hard.
_CACHE_HEADERS = {"Cache-Control": "public, max-age=604800"}


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(404, "Not found")


@router.get("/organisations/{org_id}/logo")
async def get_org_logo(org_id: str, db: AsyncSession = Depends(get_db)):
    org = await db.get(Organisation, _parse_uuid(org_id))
    if not org or not org.logo_data:
        raise HTTPException(404, "No logo")
    return Response(
        content=org.logo_data,
        media_type=org.logo_mime or "image/png",
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
