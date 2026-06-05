"""Front-end Website — the public club website CMS (BetterStats Core).

Two routers in one module:

* ``public_router`` (prefix ``/clubs``) — unauthenticated reads that power the
  public site at ``/{slug}/website`` (homepage, news, pages, honours, committee,
  galleries). 404s when the club is inactive or hasn't enabled its website.
* ``admin_router`` (prefix ``/club-admin/website``) — CRUD for club admins,
  gated by the ``MANAGE_WEBSITE`` capability and scoped to the caller's club.

Rich-text bodies are sanitised on save (see ``services.sanitize_html``). Images
persist as DB blobs (served by ``routers.images``) so they survive container
recreation, matching club logos / yearbook images.
"""
from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_WEBSITE, require_cap
from app.models.db import (
    ClubCommitteeMember, ClubGalleryAlbum, ClubGalleryImage, ClubHonourBoard,
    ClubHonourEntry, ClubNews, ClubPage, Organisation, Player, get_db,
)
from app.routers.auth import get_current_club
from app.services.sanitize_html import html_to_text, sanitize_html

public_router = APIRouter(prefix="/clubs", tags=["website"])
admin_router = APIRouter(prefix="/club-admin/website", tags=["website-admin"])

# ─── shared helpers ──────────────────────────────────────────────────────────

_IMAGE_TYPES = {"image/png", "image/jpeg", "image/svg+xml", "image/webp", "image/gif"}
_MAX_IMAGE_BYTES = 6 * 1024 * 1024
_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Recognised social networks (anything else is ignored on save).
SOCIAL_KEYS = ("facebook", "instagram", "x", "twitter", "youtube", "tiktok", "linkedin", "website")


def _slugify(value: str) -> str:
    return _SLUG_RE.sub("-", (value or "").strip().lower()).strip("-")[:80]


async def _unique_slug(db: AsyncSession, model, org_id, base: str, exclude_id=None) -> str:
    base = _slugify(base) or "item"
    candidate, n = base, 2
    while True:
        q = select(model.id).where(model.organisation_id == org_id, model.slug == candidate)
        if exclude_id is not None:
            q = q.where(model.id != exclude_id)
        if (await db.execute(q)).first() is None:
            return candidate
        candidate, n = f"{base}-{n}", n + 1


async def _read_image(file: UploadFile) -> tuple[bytes, str]:
    if file.content_type not in _IMAGE_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported image type")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Empty file")
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image must be under 6 MB")
    return data, file.content_type


def _cache_bust() -> int:
    return int(time.time())


async def _public_org(slug: str, db: AsyncSession) -> Organisation:
    org = (await db.execute(
        select(Organisation).where(Organisation.slug == slug.lower())
    )).scalar_one_or_none()
    if not org or not org.is_active:
        raise HTTPException(status_code=404, detail="Club not found")
    return org


async def _website_org(slug: str, db: AsyncSession) -> Organisation:
    org = await _public_org(slug, db)
    if not org.website_enabled:
        raise HTTPException(status_code=404, detail="This club hasn't published a website yet.")
    return org


def _clean_social(raw: Optional[dict]) -> dict:
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key in SOCIAL_KEYS:
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()[:300]
    return out


def _season_year(year: Optional[int], name: Optional[str]) -> int:
    """Resolve a season's start year (from the column, else the name)."""
    if year is not None:
        return year
    m = re.search(r"(\d{4})", name or "")
    return int(m.group(1)) if m else -1


async def _latest_office_bearers(org_id, db: AsyncSession) -> Optional[dict]:
    """The most recent season's office bearers from the yearbook honour board.

    Clubs already maintain President/Secretary/Captain etc. per season on the
    yearbook honour board — surface the latest season's set on the website so
    it isn't entered twice. Linked players carry their id so we can deep-link.
    """
    rows = (await db.execute(text("""
        SELECT s.id::text AS season_id, s.name AS season_name, s.year AS season_year,
               h.position_title, h.sort_order, h.id AS hid,
               h.player_id::text AS player_id,
               COALESCE(p.display_name_override, p.name, h.name_override) AS name
        FROM yearbook_honour_board h
        JOIN yearbooks y ON y.id = h.yearbook_id
        JOIN seasons s ON s.id = y.season_id
        LEFT JOIN players p ON p.id = h.player_id
        WHERE y.org_id = :org
    """), {"org": str(org_id)})).mappings().all()
    if not rows:
        return None

    by_season: dict[str, dict] = {}
    for r in rows:
        slot = by_season.setdefault(r["season_id"], {
            "name": r["season_name"],
            "key": _season_year(r["season_year"], r["season_name"]),
            "rows": [],
        })
        slot["rows"].append(r)

    latest = max(by_season.values(), key=lambda s: s["key"])
    entries = [
        {"position_title": r["position_title"], "name": r["name"], "player_id": r["player_id"]}
        for r in sorted(latest["rows"], key=lambda r: (r["sort_order"], r["hid"]))
        if r["name"]
    ]
    if not entries:
        return None
    return {"season": latest["name"], "entries": entries}


async def _has_office_bearers(org_id, db: AsyncSession) -> bool:
    return (await db.execute(text(
        "SELECT 1 FROM yearbook_honour_board h JOIN yearbooks y ON y.id = h.yearbook_id "
        "WHERE y.org_id = :org LIMIT 1"
    ), {"org": str(org_id)})).first() is not None


# Resolve a UUID-or-text `season` column to the season's name (mirrors the
# achievements router) so we can read an induction year off it.
_ACH_SEASON_JOIN = """
    LEFT JOIN seasons s ON s.id = CASE
        WHEN pa.season ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN pa.season::uuid ELSE NULL END
"""


async def _auto_entries(org_id, category, subcategory, db: AsyncSession) -> list[dict]:
    """Entries auto-pulled from an achievements category (e.g. "Hall of Fame")."""
    if not category:
        return []
    rows = (await db.execute(text("""
        SELECT pa.player_id::text AS player_id,
               COALESCE(p.display_name_override, p.name, pa.player_name) AS name,
               COALESCE(s.name, pa.season) AS season_name,
               pa.detail, pa.achievement
        FROM player_achievements pa
        LEFT JOIN players p ON p.id = pa.player_id
    """ + _ACH_SEASON_JOIN + """
        WHERE pa.org_id = :org AND pa.category = :cat
          AND (:sub::text IS NULL OR pa.subcategory = :sub)
    """), {"org": str(org_id), "cat": category, "sub": subcategory})).mappings().all()

    cat_l = (category or "").strip().lower()
    out: list[dict] = []
    for r in rows:
        if not r["name"]:
            continue
        yr = _season_year(None, r["season_name"]) if r["season_name"] else -1
        ach = (r["achievement"] or "").strip()
        # Avoid echoing the board's own name ("Hall of Fame — Hall of Fame").
        detail = r["detail"] or (ach if ach and ach.lower() != cat_l else None)
        out.append({
            "name": r["name"],
            "player_id": r["player_id"],
            "year": yr if yr and yr > 0 else None,
            "detail": detail,
            "auto": True,
        })
    out.sort(key=lambda e: (-(e["year"] or 0), (e["name"] or "").lower()))
    return out


async def _auto_count(org_id, category, subcategory, db: AsyncSession) -> int:
    if not category:
        return 0
    return (await db.execute(text(
        "SELECT COUNT(*) FROM player_achievements WHERE org_id = :org AND category = :cat "
        "AND (:sub::text IS NULL OR subcategory = :sub)"
    ), {"org": str(org_id), "cat": category, "sub": subcategory})).scalar() or 0


# ─── serialisers ─────────────────────────────────────────────────────────────

def _news_card(n: ClubNews) -> dict:
    return {
        "id": str(n.id),
        "slug": n.slug,
        "title": n.title,
        "summary": n.summary,
        "cover_image_url": n.cover_image_url,
        "author": n.author,
        "is_pinned": n.is_pinned,
        "published_at": n.published_at.isoformat() if n.published_at else None,
    }


def _news_full(n: ClubNews, *, admin: bool = False) -> dict:
    out = _news_card(n)
    out["body"] = n.body
    if admin:
        out["is_published"] = n.is_published
        out["created_at"] = n.created_at.isoformat() if n.created_at else None
        out["updated_at"] = n.updated_at.isoformat() if n.updated_at else None
    return out


def _page_nav(p: ClubPage) -> dict:
    return {"slug": p.slug, "label": p.nav_label or p.title, "title": p.title}


def _page_full(p: ClubPage, *, admin: bool = False) -> dict:
    out = {
        "id": str(p.id),
        "slug": p.slug,
        "title": p.title,
        "nav_label": p.nav_label,
        "body": p.body,
        "show_in_nav": p.show_in_nav,
        "display_order": p.display_order,
    }
    if admin:
        out["is_published"] = p.is_published
    return out


def _entry(e: ClubHonourEntry) -> dict:
    return {
        "id": str(e.id),
        "year": e.year,
        "name": e.name,
        "detail": e.detail,
        "player_id": str(e.player_id) if e.player_id else None,
        "display_order": e.display_order,
    }


def _committee(m: ClubCommitteeMember) -> dict:
    return {
        "id": str(m.id),
        "role": m.role,
        "name": m.name,
        "email": m.email,
        "phone": m.phone,
        "bio": m.bio,
        "photo_url": m.photo_url,
        "display_order": m.display_order,
    }


def _image(img: ClubGalleryImage) -> dict:
    return {
        "id": str(img.id),
        "image_url": img.image_url,
        "caption": img.caption,
        "display_order": img.display_order,
    }


# ════════════════════════════════════════════════════════════════════════════
#  PUBLIC
# ════════════════════════════════════════════════════════════════════════════

@public_router.get("/{slug}/website")
async def get_website(slug: str, db: AsyncSession = Depends(get_db)):
    """Homepage payload: branding, nav, latest news + section availability."""
    org = await _website_org(slug, db)

    pages = (await db.execute(
        select(ClubPage)
        .where(ClubPage.organisation_id == org.id, ClubPage.is_published == True)  # noqa: E712
        .order_by(ClubPage.display_order, ClubPage.title)
    )).scalars().all()

    news = (await db.execute(
        select(ClubNews)
        .where(ClubNews.organisation_id == org.id, ClubNews.is_published == True)  # noqa: E712
        .order_by(ClubNews.is_pinned.desc(), ClubNews.published_at.desc().nullslast(), ClubNews.created_at.desc())
        .limit(6)
    )).scalars().all()

    async def _count(model, where) -> int:
        return (await db.execute(select(func.count()).select_from(model).where(where))).scalar() or 0

    boards = await _count(ClubHonourBoard, ClubHonourBoard.organisation_id == org.id)
    committee = await _count(ClubCommitteeMember, ClubCommitteeMember.organisation_id == org.id)
    albums = await _count(ClubGalleryAlbum, ClubGalleryAlbum.organisation_id == org.id)
    has_office_bearers = await _has_office_bearers(org.id, db)

    return {
        "slug": org.slug,
        "name": org.name,
        "short_name": org.short_name,
        "logo_url": org.logo_url,
        "hero_image_url": org.hero_image_url,
        "tagline": org.website_tagline,
        "intro": org.website_intro,
        "social": _clean_social(org.website_social),
        "contact_email": org.contact_email,
        "pages": [_page_nav(p) for p in pages if p.show_in_nav],
        "news": [_news_card(n) for n in news],
        "sections": {
            "news": len(news) > 0,
            "honours": boards > 0 or has_office_bearers,
            "committee": committee > 0,
            "gallery": albums > 0,
        },
    }


@public_router.get("/{slug}/website/news")
async def list_website_news(
    slug: str,
    limit: int = Query(24, ge=1, le=60),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    org = await _website_org(slug, db)
    base = select(ClubNews).where(
        ClubNews.organisation_id == org.id, ClubNews.is_published == True  # noqa: E712
    )
    total = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar() or 0
    rows = (await db.execute(
        base.order_by(
            ClubNews.is_pinned.desc(),
            ClubNews.published_at.desc().nullslast(),
            ClubNews.created_at.desc(),
        ).limit(limit).offset(offset)
    )).scalars().all()
    return {"total": total, "items": [_news_card(n) for n in rows]}


@public_router.get("/{slug}/website/news/{news_slug}")
async def get_website_article(slug: str, news_slug: str, db: AsyncSession = Depends(get_db)):
    org = await _website_org(slug, db)
    article = (await db.execute(
        select(ClubNews).where(
            ClubNews.organisation_id == org.id,
            ClubNews.slug == news_slug,
            ClubNews.is_published == True,  # noqa: E712
        )
    )).scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    more = (await db.execute(
        select(ClubNews).where(
            ClubNews.organisation_id == org.id,
            ClubNews.is_published == True,  # noqa: E712
            ClubNews.id != article.id,
        ).order_by(ClubNews.published_at.desc().nullslast(), ClubNews.created_at.desc()).limit(3)
    )).scalars().all()
    return {"article": _news_full(article), "more": [_news_card(n) for n in more]}


@public_router.get("/{slug}/website/pages/{page_slug}")
async def get_website_page(slug: str, page_slug: str, db: AsyncSession = Depends(get_db)):
    org = await _website_org(slug, db)
    page = (await db.execute(
        select(ClubPage).where(
            ClubPage.organisation_id == org.id,
            ClubPage.slug == page_slug,
            ClubPage.is_published == True,  # noqa: E712
        )
    )).scalar_one_or_none()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return _page_full(page)


@public_router.get("/{slug}/website/honours")
async def get_website_honours(slug: str, db: AsyncSession = Depends(get_db)):
    org = await _website_org(slug, db)
    boards = (await db.execute(
        select(ClubHonourBoard)
        .where(ClubHonourBoard.organisation_id == org.id)
        .order_by(ClubHonourBoard.display_order, ClubHonourBoard.title)
    )).scalars().all()
    # Eager-load entries (lazy relationship needs awaiting via selectinload, but
    # a simple per-board query keeps this dependency-free and counts are small).
    out = []
    for b in boards:
        entries = (await db.execute(
            select(ClubHonourEntry)
            .where(ClubHonourEntry.board_id == b.id)
            .order_by(ClubHonourEntry.display_order, ClubHonourEntry.year.desc().nullslast())
        )).scalars().all()
        merged = [_entry(e) for e in entries]
        if b.source_category:
            merged += await _auto_entries(org.id, b.source_category, b.source_subcategory, db)
        if not merged:
            continue  # hide an empty auto board (e.g. category with no winners yet)
        out.append({
            "id": str(b.id),
            "title": b.title,
            "description": b.description,
            "entries": merged,
        })
    office_bearers = await _latest_office_bearers(org.id, db)
    return {"office_bearers": office_bearers, "boards": out}


@public_router.get("/{slug}/website/committee")
async def get_website_committee(slug: str, db: AsyncSession = Depends(get_db)):
    org = await _website_org(slug, db)
    members = (await db.execute(
        select(ClubCommitteeMember)
        .where(ClubCommitteeMember.organisation_id == org.id)
        .order_by(ClubCommitteeMember.display_order, ClubCommitteeMember.role)
    )).scalars().all()
    return {"members": [_committee(m) for m in members]}


@public_router.get("/{slug}/website/gallery")
async def get_website_gallery(slug: str, db: AsyncSession = Depends(get_db)):
    org = await _website_org(slug, db)
    albums = (await db.execute(
        select(ClubGalleryAlbum)
        .where(ClubGalleryAlbum.organisation_id == org.id)
        .order_by(ClubGalleryAlbum.display_order, ClubGalleryAlbum.title)
    )).scalars().all()
    out = []
    for a in albums:
        imgs = (await db.execute(
            select(ClubGalleryImage)
            .where(ClubGalleryImage.album_id == a.id)
            .order_by(ClubGalleryImage.display_order)
        )).scalars().all()
        cover = imgs[0].image_url if imgs else None
        out.append({
            "id": str(a.id), "title": a.title, "description": a.description,
            "image_count": len(imgs), "cover_image_url": cover,
        })
    return {"albums": out}


@public_router.get("/{slug}/website/gallery/{album_id}")
async def get_website_album(slug: str, album_id: str, db: AsyncSession = Depends(get_db)):
    org = await _website_org(slug, db)
    album = (await db.execute(
        select(ClubGalleryAlbum).where(
            ClubGalleryAlbum.id == _uuid(album_id),
            ClubGalleryAlbum.organisation_id == org.id,
        )
    )).scalar_one_or_none()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    imgs = (await db.execute(
        select(ClubGalleryImage)
        .where(ClubGalleryImage.album_id == album.id)
        .order_by(ClubGalleryImage.display_order)
    )).scalars().all()
    return {
        "id": str(album.id), "title": album.title, "description": album.description,
        "images": [_image(i) for i in imgs],
    }


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=404, detail="Not found")


# ════════════════════════════════════════════════════════════════════════════
#  ADMIN — settings
# ════════════════════════════════════════════════════════════════════════════

@admin_router.get("/settings")
async def get_settings(
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
):
    return {
        "enabled": bool(club.website_enabled),
        "tagline": club.website_tagline,
        "intro": club.website_intro,
        "social": _clean_social(club.website_social),
        "hero_image_url": club.hero_image_url,
        "slug": club.slug,
    }


class SettingsPatch(BaseModel):
    enabled: Optional[bool] = None
    tagline: Optional[str] = None
    intro: Optional[str] = None
    social: Optional[dict] = None


@admin_router.put("/settings")
async def update_settings(
    data: SettingsPatch,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    if data.enabled is not None:
        club.website_enabled = bool(data.enabled)
    if data.tagline is not None:
        club.website_tagline = data.tagline.strip()[:200] or None
    if data.intro is not None:
        club.website_intro = sanitize_html(data.intro) or None
    if data.social is not None:
        club.website_social = _clean_social(data.social)
    await db.commit()
    return await get_settings(_=None, club=club)


@admin_router.post("/hero")
async def upload_hero(
    file: UploadFile = File(...),
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    data, mime = await _read_image(file)
    club.hero_image_data = data
    club.hero_image_mime = mime
    club.hero_image_url = f"/api/images/organisations/{club.id}/hero?v={_cache_bust()}"
    await db.commit()
    return {"hero_image_url": club.hero_image_url}


@admin_router.delete("/hero")
async def delete_hero(
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    club.hero_image_data = None
    club.hero_image_mime = None
    club.hero_image_url = None
    await db.commit()
    return {"ok": True}


# ════════════════════════════════════════════════════════════════════════════
#  ADMIN — news
# ════════════════════════════════════════════════════════════════════════════

@admin_router.get("/news")
async def admin_list_news(
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(ClubNews).where(ClubNews.organisation_id == club.id)
        .order_by(ClubNews.is_pinned.desc(), ClubNews.published_at.desc().nullslast(), ClubNews.created_at.desc())
    )).scalars().all()
    return [_news_full(n, admin=True) for n in rows]


class NewsBody(BaseModel):
    title: str
    summary: Optional[str] = None
    body: Optional[str] = None
    author: Optional[str] = None
    is_published: bool = True
    is_pinned: bool = False
    published_at: Optional[str] = None


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


@admin_router.post("/news")
async def admin_create_news(
    data: NewsBody,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    title = data.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Title is required")
    body = sanitize_html(data.body)
    summary = (data.summary or "").strip() or html_to_text(body)
    article = ClubNews(
        organisation_id=club.id,
        title=title[:200],
        slug=await _unique_slug(db, ClubNews, club.id, title),
        summary=summary or None,
        body=body or None,
        author=(data.author or "").strip() or None,
        is_published=data.is_published,
        is_pinned=data.is_pinned,
        published_at=_parse_dt(data.published_at) or (datetime.now(timezone.utc) if data.is_published else None),
    )
    db.add(article)
    await db.commit()
    return _news_full(article, admin=True)


@admin_router.get("/news/{news_id}")
async def admin_get_news(
    news_id: str,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    n = await db.get(ClubNews, _uuid(news_id))
    if not n or n.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Article not found")
    return _news_full(n, admin=True)


@admin_router.put("/news/{news_id}")
async def admin_update_news(
    news_id: str,
    data: NewsBody,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    n = await db.get(ClubNews, _uuid(news_id))
    if not n or n.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Article not found")
    title = data.title.strip()
    if title and title != n.title:
        n.title = title[:200]
        n.slug = await _unique_slug(db, ClubNews, club.id, title, exclude_id=n.id)
    n.body = sanitize_html(data.body) or None
    n.summary = (data.summary or "").strip() or html_to_text(n.body or "") or None
    n.author = (data.author or "").strip() or None
    # Stamp published_at the first time it goes live.
    if data.is_published and not n.is_published and not n.published_at:
        n.published_at = datetime.now(timezone.utc)
    explicit_dt = _parse_dt(data.published_at)
    if explicit_dt:
        n.published_at = explicit_dt
    n.is_published = data.is_published
    n.is_pinned = data.is_pinned
    n.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _news_full(n, admin=True)


@admin_router.delete("/news/{news_id}")
async def admin_delete_news(
    news_id: str,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    n = await db.get(ClubNews, _uuid(news_id))
    if not n or n.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Article not found")
    await db.delete(n)
    await db.commit()
    return {"ok": True}


@admin_router.post("/news/{news_id}/cover")
async def admin_news_cover(
    news_id: str,
    file: UploadFile = File(...),
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    n = await db.get(ClubNews, _uuid(news_id))
    if not n or n.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Article not found")
    n.cover_image_data, n.cover_image_mime = await _read_image(file)
    n.cover_image_url = f"/api/images/news/{n.id}/cover?v={_cache_bust()}"
    await db.commit()
    return {"cover_image_url": n.cover_image_url}


@admin_router.delete("/news/{news_id}/cover")
async def admin_news_cover_delete(
    news_id: str,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    n = await db.get(ClubNews, _uuid(news_id))
    if not n or n.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Article not found")
    n.cover_image_data = n.cover_image_mime = n.cover_image_url = None
    await db.commit()
    return {"ok": True}


# ════════════════════════════════════════════════════════════════════════════
#  ADMIN — pages
# ════════════════════════════════════════════════════════════════════════════

@admin_router.get("/pages")
async def admin_list_pages(
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(ClubPage).where(ClubPage.organisation_id == club.id)
        .order_by(ClubPage.display_order, ClubPage.title)
    )).scalars().all()
    return [_page_full(p, admin=True) for p in rows]


class PageBody(BaseModel):
    title: str
    nav_label: Optional[str] = None
    body: Optional[str] = None
    show_in_nav: bool = True
    is_published: bool = True


@admin_router.post("/pages")
async def admin_create_page(
    data: PageBody,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    title = data.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Title is required")
    max_order = (await db.execute(
        select(func.max(ClubPage.display_order)).where(ClubPage.organisation_id == club.id)
    )).scalar() or 0
    page = ClubPage(
        organisation_id=club.id,
        title=title[:120],
        slug=await _unique_slug(db, ClubPage, club.id, title),
        nav_label=(data.nav_label or "").strip()[:40] or None,
        body=sanitize_html(data.body) or None,
        show_in_nav=data.show_in_nav,
        is_published=data.is_published,
        display_order=max_order + 1,
    )
    db.add(page)
    await db.commit()
    return _page_full(page, admin=True)


@admin_router.put("/pages/{page_id}")
async def admin_update_page(
    page_id: str,
    data: PageBody,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    p = await db.get(ClubPage, _uuid(page_id))
    if not p or p.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Page not found")
    title = data.title.strip()
    if title and title != p.title:
        p.title = title[:120]
        p.slug = await _unique_slug(db, ClubPage, club.id, title, exclude_id=p.id)
    p.nav_label = (data.nav_label or "").strip()[:40] or None
    p.body = sanitize_html(data.body) or None
    p.show_in_nav = data.show_in_nav
    p.is_published = data.is_published
    p.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _page_full(p, admin=True)


@admin_router.delete("/pages/{page_id}")
async def admin_delete_page(
    page_id: str,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    p = await db.get(ClubPage, _uuid(page_id))
    if not p or p.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Page not found")
    await db.delete(p)
    await db.commit()
    return {"ok": True}


class ReorderBody(BaseModel):
    ids: list[str]


@admin_router.post("/pages/reorder")
async def admin_reorder_pages(
    data: ReorderBody,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    for idx, pid in enumerate(data.ids):
        p = await db.get(ClubPage, _uuid(pid))
        if p and p.organisation_id == club.id:
            p.display_order = idx
    await db.commit()
    return {"ok": True}


# ════════════════════════════════════════════════════════════════════════════
#  ADMIN — honours
# ════════════════════════════════════════════════════════════════════════════

@admin_router.get("/honours")
async def admin_list_honours(
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    boards = (await db.execute(
        select(ClubHonourBoard).where(ClubHonourBoard.organisation_id == club.id)
        .order_by(ClubHonourBoard.display_order, ClubHonourBoard.title)
    )).scalars().all()
    out = []
    for b in boards:
        entries = (await db.execute(
            select(ClubHonourEntry).where(ClubHonourEntry.board_id == b.id)
            .order_by(ClubHonourEntry.display_order, ClubHonourEntry.year.desc().nullslast())
        )).scalars().all()
        out.append({
            **_board_admin(b),
            "entries": [_entry(e) for e in entries],
            "auto_count": await _auto_count(club.id, b.source_category, b.source_subcategory, db),
        })
    return out


def _board_admin(b: ClubHonourBoard) -> dict:
    return {
        "id": str(b.id), "title": b.title, "description": b.description,
        "display_order": b.display_order,
        "source_category": b.source_category, "source_subcategory": b.source_subcategory,
    }


@admin_router.get("/honour-categories")
async def admin_honour_categories(
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Achievements categories (with counts) a board can auto-populate from."""
    rows = (await db.execute(text("""
        SELECT category, subcategory, COUNT(*) AS n
        FROM player_achievements
        WHERE org_id = :org AND category IS NOT NULL AND category <> ''
        GROUP BY category, subcategory
        ORDER BY category, subcategory NULLS FIRST
    """), {"org": str(club.id)})).mappings().all()
    return [
        {"category": r["category"], "subcategory": r["subcategory"], "count": r["n"]}
        for r in rows
    ]


class BoardBody(BaseModel):
    title: str
    description: Optional[str] = None
    source_category: Optional[str] = None
    source_subcategory: Optional[str] = None


@admin_router.post("/honours/boards")
async def admin_create_board(
    data: BoardBody,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    title = data.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Title is required")
    max_order = (await db.execute(
        select(func.max(ClubHonourBoard.display_order)).where(ClubHonourBoard.organisation_id == club.id)
    )).scalar() or 0
    board = ClubHonourBoard(
        organisation_id=club.id, title=title[:120],
        description=(data.description or "").strip() or None, display_order=max_order + 1,
        source_category=(data.source_category or "").strip() or None,
        source_subcategory=(data.source_subcategory or "").strip() or None,
    )
    db.add(board)
    await db.commit()
    return {**_board_admin(board), "entries": [],
            "auto_count": await _auto_count(club.id, board.source_category, board.source_subcategory, db)}


@admin_router.put("/honours/boards/{board_id}")
async def admin_update_board(
    board_id: str,
    data: BoardBody,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    b = await db.get(ClubHonourBoard, _uuid(board_id))
    if not b or b.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Board not found")
    if data.title.strip():
        b.title = data.title.strip()[:120]
    b.description = (data.description or "").strip() or None
    b.source_category = (data.source_category or "").strip() or None
    b.source_subcategory = (data.source_subcategory or "").strip() or None
    await db.commit()
    return {**_board_admin(b),
            "auto_count": await _auto_count(club.id, b.source_category, b.source_subcategory, db)}


@admin_router.delete("/honours/boards/{board_id}")
async def admin_delete_board(
    board_id: str,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    b = await db.get(ClubHonourBoard, _uuid(board_id))
    if not b or b.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Board not found")
    await db.delete(b)
    await db.commit()
    return {"ok": True}


class EntryBody(BaseModel):
    year: Optional[int] = None
    name: str
    detail: Optional[str] = None
    player_id: Optional[str] = None


async def _board_for_club(db, board_id, club) -> ClubHonourBoard:
    b = await db.get(ClubHonourBoard, _uuid(board_id))
    if not b or b.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Board not found")
    return b


@admin_router.post("/honours/boards/{board_id}/entries")
async def admin_create_entry(
    board_id: str,
    data: EntryBody,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    board = await _board_for_club(db, board_id, club)
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name is required")
    max_order = (await db.execute(
        select(func.max(ClubHonourEntry.display_order)).where(ClubHonourEntry.board_id == board.id)
    )).scalar() or 0
    pid = await _validate_player(db, data.player_id, club)
    entry = ClubHonourEntry(
        board_id=board.id, year=data.year, name=name[:160],
        detail=(data.detail or "").strip() or None, player_id=pid, display_order=max_order + 1,
    )
    db.add(entry)
    await db.commit()
    return _entry(entry)


async def _validate_player(db, player_id, club) -> Optional[uuid.UUID]:
    if not player_id:
        return None
    p = await db.get(Player, _uuid(player_id))
    if p and p.organisation_id == club.id:
        return p.id
    return None


@admin_router.put("/honours/entries/{entry_id}")
async def admin_update_entry(
    entry_id: str,
    data: EntryBody,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    e = await db.get(ClubHonourEntry, _uuid(entry_id))
    if not e:
        raise HTTPException(status_code=404, detail="Entry not found")
    board = await _board_for_club(db, str(e.board_id), club)  # ownership check
    if data.name.strip():
        e.name = data.name.strip()[:160]
    e.year = data.year
    e.detail = (data.detail or "").strip() or None
    e.player_id = await _validate_player(db, data.player_id, club)
    await db.commit()
    return _entry(e)


@admin_router.delete("/honours/entries/{entry_id}")
async def admin_delete_entry(
    entry_id: str,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    e = await db.get(ClubHonourEntry, _uuid(entry_id))
    if not e:
        raise HTTPException(status_code=404, detail="Entry not found")
    await _board_for_club(db, str(e.board_id), club)
    await db.delete(e)
    await db.commit()
    return {"ok": True}


# ════════════════════════════════════════════════════════════════════════════
#  ADMIN — committee
# ════════════════════════════════════════════════════════════════════════════

@admin_router.get("/committee")
async def admin_list_committee(
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(ClubCommitteeMember).where(ClubCommitteeMember.organisation_id == club.id)
        .order_by(ClubCommitteeMember.display_order, ClubCommitteeMember.role)
    )).scalars().all()
    return [_committee(m) for m in rows]


class CommitteeBody(BaseModel):
    role: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None


@admin_router.post("/committee")
async def admin_create_committee(
    data: CommitteeBody,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    if not data.role.strip() or not data.name.strip():
        raise HTTPException(status_code=422, detail="Role and name are required")
    max_order = (await db.execute(
        select(func.max(ClubCommitteeMember.display_order)).where(ClubCommitteeMember.organisation_id == club.id)
    )).scalar() or 0
    m = ClubCommitteeMember(
        organisation_id=club.id, role=data.role.strip()[:80], name=data.name.strip()[:120],
        email=(data.email or "").strip() or None, phone=(data.phone or "").strip() or None,
        bio=(data.bio or "").strip() or None, display_order=max_order + 1,
    )
    db.add(m)
    await db.commit()
    return _committee(m)


@admin_router.put("/committee/{member_id}")
async def admin_update_committee(
    member_id: str,
    data: CommitteeBody,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    m = await db.get(ClubCommitteeMember, _uuid(member_id))
    if not m or m.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Member not found")
    if data.role.strip():
        m.role = data.role.strip()[:80]
    if data.name.strip():
        m.name = data.name.strip()[:120]
    m.email = (data.email or "").strip() or None
    m.phone = (data.phone or "").strip() or None
    m.bio = (data.bio or "").strip() or None
    await db.commit()
    return _committee(m)


@admin_router.delete("/committee/{member_id}")
async def admin_delete_committee(
    member_id: str,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    m = await db.get(ClubCommitteeMember, _uuid(member_id))
    if not m or m.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Member not found")
    await db.delete(m)
    await db.commit()
    return {"ok": True}


@admin_router.post("/committee/{member_id}/photo")
async def admin_committee_photo(
    member_id: str,
    file: UploadFile = File(...),
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    m = await db.get(ClubCommitteeMember, _uuid(member_id))
    if not m or m.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Member not found")
    m.photo_data, m.photo_mime = await _read_image(file)
    m.photo_url = f"/api/images/committee/{m.id}/photo?v={_cache_bust()}"
    await db.commit()
    return {"photo_url": m.photo_url}


@admin_router.delete("/committee/{member_id}/photo")
async def admin_committee_photo_delete(
    member_id: str,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    m = await db.get(ClubCommitteeMember, _uuid(member_id))
    if not m or m.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Member not found")
    m.photo_data = m.photo_mime = m.photo_url = None
    await db.commit()
    return {"ok": True}


# ════════════════════════════════════════════════════════════════════════════
#  ADMIN — galleries
# ════════════════════════════════════════════════════════════════════════════

@admin_router.get("/gallery")
async def admin_list_gallery(
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    albums = (await db.execute(
        select(ClubGalleryAlbum).where(ClubGalleryAlbum.organisation_id == club.id)
        .order_by(ClubGalleryAlbum.display_order, ClubGalleryAlbum.title)
    )).scalars().all()
    out = []
    for a in albums:
        imgs = (await db.execute(
            select(ClubGalleryImage).where(ClubGalleryImage.album_id == a.id)
            .order_by(ClubGalleryImage.display_order)
        )).scalars().all()
        out.append({
            "id": str(a.id), "title": a.title, "description": a.description,
            "display_order": a.display_order,
            "images": [_image(i) for i in imgs],
        })
    return out


class AlbumBody(BaseModel):
    title: str
    description: Optional[str] = None


@admin_router.post("/gallery/albums")
async def admin_create_album(
    data: AlbumBody,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    if not data.title.strip():
        raise HTTPException(status_code=422, detail="Title is required")
    max_order = (await db.execute(
        select(func.max(ClubGalleryAlbum.display_order)).where(ClubGalleryAlbum.organisation_id == club.id)
    )).scalar() or 0
    a = ClubGalleryAlbum(
        organisation_id=club.id, title=data.title.strip()[:120],
        description=(data.description or "").strip() or None, display_order=max_order + 1,
    )
    db.add(a)
    await db.commit()
    return {"id": str(a.id), "title": a.title, "description": a.description, "images": []}


@admin_router.put("/gallery/albums/{album_id}")
async def admin_update_album(
    album_id: str,
    data: AlbumBody,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    a = await db.get(ClubGalleryAlbum, _uuid(album_id))
    if not a or a.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Album not found")
    if data.title.strip():
        a.title = data.title.strip()[:120]
    a.description = (data.description or "").strip() or None
    await db.commit()
    return {"id": str(a.id), "title": a.title, "description": a.description}


@admin_router.delete("/gallery/albums/{album_id}")
async def admin_delete_album(
    album_id: str,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    a = await db.get(ClubGalleryAlbum, _uuid(album_id))
    if not a or a.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Album not found")
    await db.delete(a)
    await db.commit()
    return {"ok": True}


async def _album_for_club(db, album_id, club) -> ClubGalleryAlbum:
    a = await db.get(ClubGalleryAlbum, _uuid(album_id))
    if not a or a.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Album not found")
    return a


@admin_router.post("/gallery/albums/{album_id}/images")
async def admin_add_gallery_image(
    album_id: str,
    file: UploadFile = File(...),
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    album = await _album_for_club(db, album_id, club)
    data, mime = await _read_image(file)
    max_order = (await db.execute(
        select(func.max(ClubGalleryImage.display_order)).where(ClubGalleryImage.album_id == album.id)
    )).scalar() or 0
    img = ClubGalleryImage(album_id=album.id, image_data=data, image_mime=mime, display_order=max_order + 1)
    db.add(img)
    await db.flush()
    img.image_url = f"/api/images/gallery/{img.id}?v={_cache_bust()}"
    await db.commit()
    return _image(img)


class CaptionBody(BaseModel):
    caption: Optional[str] = None


@admin_router.put("/gallery/images/{image_id}")
async def admin_update_gallery_image(
    image_id: str,
    data: CaptionBody,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    img = await db.get(ClubGalleryImage, _uuid(image_id))
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    await _album_for_club(db, str(img.album_id), club)
    img.caption = (data.caption or "").strip()[:300] or None
    await db.commit()
    return _image(img)


@admin_router.delete("/gallery/images/{image_id}")
async def admin_delete_gallery_image(
    image_id: str,
    _: object = Depends(require_cap(MANAGE_WEBSITE)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    img = await db.get(ClubGalleryImage, _uuid(image_id))
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    await _album_for_club(db, str(img.album_id), club)
    await db.delete(img)
    await db.commit()
    return {"ok": True}
