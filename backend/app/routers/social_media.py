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
import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import func, select, text
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
TEMPLATE_MAX_BYTES = 256 * 1024
TEMPLATE_MAX_PER_CLUB = 100
TEMPLATE_NAME_MAX = 80
_TEMPLATE_KEY = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
# What a saved template may carry. The editor is the only consumer, so this is
# an allowlist and a type check rather than a schema that chases its shape.
_TEMPLATE_FIELDS = {"templateId", "custom", "style", "blank", "layers", "event", "created_at"}
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


# ─── Saved templates ─────────────────────────────────────────────────────────
#
# One row per template (migration 313), so saving, updating and deleting one
# never rewrites the others. They used to live inside the socials_style blob on
# the organisation, which every save replaced whole: a second admin or a second
# tab overwrote the first one's templates, and saving needed the Settings
# permission that these screens do not.

def _clean_template(raw, key: str | None = None) -> tuple[str, str, dict]:
    """(key, name, data) for a template the editor sent, or a 422 saying why.

    ``key`` is the URL's when there is one; a body that names a different key is
    refused rather than quietly saved under the wrong one."""
    if not isinstance(raw, dict):
        raise HTTPException(422, "A template must be a JSON object")
    body_key = raw.get("key")
    key = key or body_key
    if not isinstance(key, str) or not _TEMPLATE_KEY.match(key):
        raise HTTPException(422, "Template key is missing or not valid")
    if body_key is not None and body_key != key:
        raise HTTPException(422, "Template key does not match the address")
    name = raw.get("name")
    name = " ".join(name.split()) if isinstance(name, str) else ""
    if not name:
        raise HTTPException(422, "Give the template a name")
    name = name[:TEMPLATE_NAME_MAX]
    data = {k: v for k, v in raw.items() if k in _TEMPLATE_FIELDS}
    if not isinstance(data.get("templateId"), str) or not data["templateId"]:
        raise HTTPException(422, "Template has no base layout")
    if data.get("style") is not None and not isinstance(data["style"], dict):
        raise HTTPException(422, "Template style must be an object")
    for field in ("blank",):
        if data.get(field) is not None and not isinstance(data[field], list):
            raise HTTPException(422, "Template blocks must be a list")
    if data.get("event") is not None and not isinstance(data["event"], dict):
        raise HTTPException(422, "Template event content must be an object")
    if data.get("layers") is not None and not isinstance(data["layers"], dict):
        raise HTTPException(422, "Template layers must be an object")
    try:
        if len(json.dumps(data)) > TEMPLATE_MAX_BYTES:
            raise HTTPException(413, "That template is too large to save (256 KB max)")
    except (TypeError, ValueError):
        raise HTTPException(422, "Template could not be read")
    return key, name, data


def _template_out(row) -> dict:
    return {
        **(row["data"] or {}),
        "key": row["key"],
        "name": row["name"],
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


async def _template_count(db: AsyncSession, org_id) -> int:
    return (await db.execute(
        text("SELECT COUNT(*) FROM social_templates WHERE organisation_id = :o"),
        {"o": org_id},
    )).scalar_one()


_UPSERT_TEMPLATE = text("""
    INSERT INTO social_templates (organisation_id, key, name, data, created_by)
    VALUES (:o, :k, :n, CAST(:d AS jsonb), :u)
    ON CONFLICT (organisation_id, key) DO UPDATE
        SET name = EXCLUDED.name, data = EXCLUDED.data, updated_at = NOW()
    RETURNING key, name, data, updated_at
""")


@router.get("/templates", dependencies=[Depends(require_module("socials"))])
async def list_templates(
    current_user: User = Depends(require_cap(MANAGE_SOCIAL)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        text("""SELECT key, name, data, updated_at FROM social_templates
                WHERE organisation_id = :o ORDER BY updated_at DESC, created_at DESC"""),
        {"o": club.id},
    )).mappings().all()
    return [_template_out(r) for r in rows]


@router.put("/templates/{key}", dependencies=[Depends(require_module("socials"))])
async def save_template(
    key: str,
    request: Request,
    current_user: User = Depends(require_cap(MANAGE_SOCIAL)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Create the template, or update it in place when the key already exists —
    which is what lets a saved template be improved rather than saved again
    beside its old self."""
    raw = await request.body()
    if len(raw) > TEMPLATE_MAX_BYTES + 4096:
        raise HTTPException(413, "That template is too large to save (256 KB max)")
    try:
        body = json.loads(raw) if raw else None
    except (ValueError, TypeError):
        raise HTTPException(422, "Template must be valid JSON")
    key, name, data = _clean_template(body, key)

    org_id, user_id = club.id, current_user.id  # before any commit expires them
    exists = (await db.execute(
        text("SELECT 1 FROM social_templates WHERE organisation_id = :o AND key = :k"),
        {"o": org_id, "k": key},
    )).first()
    if not exists and await _template_count(db, org_id) >= TEMPLATE_MAX_PER_CLUB:
        raise HTTPException(409, f"A club can keep {TEMPLATE_MAX_PER_CLUB} saved templates. Delete one you no longer use first.")
    row = (await db.execute(
        _UPSERT_TEMPLATE, {"o": org_id, "k": key, "n": name, "d": json.dumps(data), "u": user_id},
    )).mappings().one()
    await db.commit()
    return _template_out(row)


@router.delete("/templates/{key}", dependencies=[Depends(require_module("socials"))])
async def delete_template(
    key: str,
    current_user: User = Depends(require_cap(MANAGE_SOCIAL)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        text("DELETE FROM social_templates WHERE organisation_id = :o AND key = :k"),
        {"o": club.id, "k": key},
    )
    await db.commit()
    # Deleting one that is already gone is the answer the caller wanted.
    return {"status": "deleted", "removed": res.rowcount}


@router.post("/templates/import", dependencies=[Depends(require_module("socials"))])
async def import_templates(
    request: Request,
    current_user: User = Depends(require_cap(MANAGE_SOCIAL)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Bring templates saved before this table existed (this browser's copy, and
    the ones that rode in the style blob) across. Only keys the club does not
    already hold are added, so an import can never overwrite a template that
    has since been edited, and it is safe to send twice."""
    raw = await request.body()
    if len(raw) > 8 * TEMPLATE_MAX_BYTES:
        raise HTTPException(413, "Too much to import in one go")
    try:
        body = json.loads(raw) if raw else None
    except (ValueError, TypeError):
        raise HTTPException(422, "Import must be valid JSON")
    items = body.get("templates") if isinstance(body, dict) else None
    if not isinstance(items, list):
        raise HTTPException(422, "Send {\"templates\": [...]}")

    org_id, user_id = club.id, current_user.id
    room = TEMPLATE_MAX_PER_CLUB - await _template_count(db, org_id)
    added, skipped = [], []
    for item in items[:TEMPLATE_MAX_PER_CLUB * 2]:
        try:
            key, name, data = _clean_template(item)
        except HTTPException as e:
            skipped.append({"key": item.get("key") if isinstance(item, dict) else None, "reason": e.detail})
            continue
        if room <= 0:
            skipped.append({"key": key, "reason": "The club is at its saved template limit"})
            continue
        res = await db.execute(text("""
            INSERT INTO social_templates (organisation_id, key, name, data, created_by)
            VALUES (:o, :k, :n, CAST(:d AS jsonb), :u)
            ON CONFLICT (organisation_id, key) DO NOTHING
        """), {"o": org_id, "k": key, "n": name, "d": json.dumps(data), "u": user_id})
        if res.rowcount:
            added.append(key)
            room -= 1
        else:
            skipped.append({"key": key, "reason": "Already saved"})
    await db.commit()
    return {"added": added, "skipped": skipped}
