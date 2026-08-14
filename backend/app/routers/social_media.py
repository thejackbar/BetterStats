"""BetterSocials — club media library + brand kit.

Two per-club stores that back the BetterSocials editor:

- **Media library** (`social_media_asset`): a pool of uploaded images the
  editor can drop into a post. Bytes live in-table (like club/sponsor logos),
  served via GET /images/social-media/{id}. Capped at 200 assets per club.
- **Brand kit** (`organisations.social_brand_kit`): an opaque JSON blob holding
  the club's reusable palette / fonts / crest / sponsors set.

Gated on the BetterSocials module (`require_module("socials")`) + the
`MANAGE_SOCIAL` capability, org-scoped via `get_current_club` — same posture as
the other social admin routes in `admin.py`, mounted under the same
`/admin/social` prefix.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_SOCIAL, require_cap
from app.auth.modules import require_module
from app.models.db import Organisation, SocialMediaAsset, User, get_db
from app.routers.auth import get_current_club

router = APIRouter(prefix="/admin/social", tags=["social-media"])

MEDIA_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MEDIA_MAX_BYTES = 5 * 1024 * 1024
MEDIA_MAX_PER_CLUB = 200
BACKGROUND_MAX_PER_CLUB = 30
BRAND_KIT_MAX_BYTES = 256 * 1024
MEDIA_KINDS = {"background"}  # None/omitted = an ordinary Photos-tab upload

_IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _asset_dict(asset: SocialMediaAsset) -> dict:
    # The stored bytes never change, so a created_at-epoch cache-buster is stable
    # per asset yet still distinct across re-uploads (a new asset is a new id).
    ts = int(asset.created_at.timestamp()) if asset.created_at else 0
    return {
        "id": str(asset.id),
        "name": asset.filename,
        "url": f"/api/images/social-media/{asset.id}?v={ts}",
        "kind": asset.kind,
    }


@router.get("/media", dependencies=[Depends(require_module("socials"))])
async def list_media(
    kind: str | None = None,
    current_user: User = Depends(require_cap(MANAGE_SOCIAL)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    # kind=background lists only the club's background library; omitted (the
    # default) lists the ordinary Photos pool (kind IS NULL) — a background
    # never clutters the general photo picker and vice versa.
    q = select(SocialMediaAsset).where(SocialMediaAsset.organisation_id == club.id)
    q = q.where(SocialMediaAsset.kind == kind) if kind in MEDIA_KINDS else q.where(SocialMediaAsset.kind.is_(None))
    rows = await db.execute(q.order_by(SocialMediaAsset.created_at.desc()))
    return [_asset_dict(a) for a in rows.scalars().all()]


@router.post("/media", dependencies=[Depends(require_module("socials"))])
async def upload_media(
    file: UploadFile = File(...),
    kind: str | None = Form(None),
    current_user: User = Depends(require_cap(MANAGE_SOCIAL)),
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
        raise HTTPException(400, "Image must be 5 MB or smaller")

    kind = kind if kind in MEDIA_KINDS else None
    limit = BACKGROUND_MAX_PER_CLUB if kind == "background" else MEDIA_MAX_PER_CLUB
    count_q = select(func.count()).select_from(SocialMediaAsset).where(
        SocialMediaAsset.organisation_id == club.id
    )
    count_q = count_q.where(SocialMediaAsset.kind == kind) if kind else count_q.where(SocialMediaAsset.kind.is_(None))
    count = await db.scalar(count_q)
    if (count or 0) >= limit:
        label = "Background library" if kind == "background" else "Media library"
        raise HTTPException(400, f"{label} is full ({limit} images). Delete some first.")

    asset = SocialMediaAsset(
        organisation_id=club.id,
        filename=file.filename,
        mime=_IMAGE_MIME.get(ext, "image/jpeg"),
        image_data=data,
        created_by=current_user.id,
        kind=kind,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return _asset_dict(asset)


@router.delete("/media/{asset_id}", dependencies=[Depends(require_module("socials"))])
async def delete_media(
    asset_id: str,
    current_user: User = Depends(require_cap(MANAGE_SOCIAL)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    import uuid as _uuid
    try:
        aid = _uuid.UUID(asset_id)
    except (ValueError, AttributeError):
        raise HTTPException(404, "Not found")
    asset = await db.get(SocialMediaAsset, aid)
    if not asset or asset.organisation_id != club.id:
        raise HTTPException(404, "Not found")
    await db.delete(asset)
    await db.commit()
    return {"status": "deleted"}


# ─── Brand kit ───────────────────────────────────────────────────────────────

@router.get("/brand-kit", dependencies=[Depends(require_module("socials"))])
async def get_brand_kit(
    current_user: User = Depends(require_cap(MANAGE_SOCIAL)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    return club.social_brand_kit


@router.put("/brand-kit", dependencies=[Depends(require_module("socials"))])
async def save_brand_kit(
    request: Request,
    current_user: User = Depends(require_cap(MANAGE_SOCIAL)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    import json

    raw = await request.body()
    if len(raw) > BRAND_KIT_MAX_BYTES:
        raise HTTPException(400, "Brand kit is too large (256 KB max)")
    try:
        kit = json.loads(raw) if raw else None
    except (ValueError, TypeError):
        raise HTTPException(400, "Brand kit must be valid JSON")
    if not isinstance(kit, dict):
        raise HTTPException(400, "Brand kit must be a JSON object")

    club.social_brand_kit = kit
    await db.commit()
    return club.social_brand_kit
