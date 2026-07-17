"""
SEO/AEO endpoints.

- /sitemap.xml  — dynamic XML sitemap covering marketing pages, every active
                   club's section pages, and every player profile. Search
                   engines fetch this directly (nginx proxies the request to
                   the backend; see frontend/nginx.conf).
- /robots.txt   — also served from frontend/public/robots.txt as a static file,
                   but exposed here for parity / curl debugging.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.content.blog import BLOG_SLUGS
from app.models.db import Organisation, Player, get_db

router = APIRouter(tags=["seo"])

SITE = "https://betterat.cricket"

# Public marketing routes. Keep in sync with App.jsx.
STATIC_PAGES: list[tuple[str, str, str]] = [
    ("/",         "1.0", "weekly"),
    ("/overview", "0.9", "monthly"),
    ("/features", "0.9", "monthly"),
    ("/modules",  "0.9", "monthly"),
    ("/pricing",  "0.9", "monthly"),
    ("/trial",    "0.9", "monthly"),
    ("/compare",  "0.8", "monthly"),
    ("/faq",      "0.8", "monthly"),
    ("/blog",     "0.8", "weekly"),
    ("/about",    "0.7", "monthly"),
    ("/contact",  "0.6", "yearly"),
    ("/terms",    "0.2", "yearly"),
    ("/privacy",  "0.2", "yearly"),
]

# Module detail pages at /modules/{slug}. Keep in sync with
# frontend/src/data/modules-marketing.js.
MODULE_PAGES: list[str] = [
    "betterstats", "betterselect", "bettersocials", "betteradmin", "betteriq",
]

# Marketing blog posts at /blog/{slug} come from app.content.blog (BLOG_SLUGS),
# the shared source the OG-preview cards also read.

# Section pages a connected club exposes publicly.
CLUB_SECTIONS = ["dashboard", "players", "leaderboard", "records", "games", "yearbook", "statlab", "compare"]


def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&apos;"))


def _url_entry(loc: str, lastmod: str | None = None, changefreq: str = "weekly", priority: str = "0.5") -> str:
    parts = [f"<loc>{_xml_escape(loc)}</loc>"]
    if lastmod:
        parts.append(f"<lastmod>{lastmod}</lastmod>")
    parts.append(f"<changefreq>{changefreq}</changefreq>")
    parts.append(f"<priority>{priority}</priority>")
    return "<url>" + "".join(parts) + "</url>"


@router.get("/sitemap.xml", response_class=Response)
async def sitemap(db: AsyncSession = Depends(get_db)):
    today = datetime.now(timezone.utc).date().isoformat()
    entries: list[str] = []

    for path, prio, cf in STATIC_PAGES:
        entries.append(_url_entry(f"{SITE}{path}", lastmod=today, changefreq=cf, priority=prio))

    for slug in MODULE_PAGES:
        entries.append(_url_entry(f"{SITE}/modules/{slug}", lastmod=today, changefreq="monthly", priority="0.8"))

    for slug in BLOG_SLUGS:
        entries.append(_url_entry(f"{SITE}/blog/{slug}", lastmod=today, changefreq="monthly", priority="0.7"))

    # Every active club's public section pages.
    club_rows = (await db.execute(
        select(Organisation.slug, Organisation.updated_at)
        .where(Organisation.is_active == True, Organisation.slug.isnot(None))  # noqa: E712
    )).all()

    for slug, updated_at in club_rows:
        if not slug:
            continue
        lastmod = (updated_at.date().isoformat() if updated_at else today)
        for section in CLUB_SECTIONS:
            # Canonical club home lives at /{slug}, not /{slug}/dashboard.
            loc = f"{SITE}/{slug}" if section == "dashboard" else f"{SITE}/{slug}/{section}"
            entries.append(_url_entry(
                loc,
                lastmod=lastmod,
                changefreq="weekly",
                priority="0.7" if section == "dashboard" else "0.5",
            ))

    # Every player at an active club gets a profile URL.
    player_rows = (await db.execute(
        select(Player.id)
        .join(Organisation, Player.organisation_id == Organisation.id)
        .where(Organisation.is_active == True)  # noqa: E712
    )).all()

    for (pid,) in player_rows:
        entries.append(_url_entry(
            f"{SITE}/players/{pid}",
            changefreq="weekly",
            priority="0.6",
        ))

    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries) +
        "\n</urlset>\n"
    )
    return Response(
        content=body,
        media_type="application/xml",
        headers={"cache-control": "public, max-age=3600"},
    )


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /admin/\n"
        "Disallow: /login\n"
        "Disallow: /onboard\n"
        "Disallow: /api/\n"
        "Disallow: /og-preview\n"
        "Disallow: /players/*/share\n"
        "\n"
        f"Sitemap: {SITE}/sitemap.xml\n"
    )
    return PlainTextResponse(body, headers={"cache-control": "public, max-age=86400"})
