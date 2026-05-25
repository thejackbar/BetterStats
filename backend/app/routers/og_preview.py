"""
Server-side OG tag injection for social-media crawlers.

nginx detects crawler User-Agents and rewrites their requests to
GET /og-preview?path=<original-path>, which lands here. We query the
DB, build a minimal HTML page with correct Open Graph + Twitter Card
meta tags + JSON-LD structured data, and return it. Regular users never
hit this endpoint — search engines (Googlebot, bingbot) are excluded
from the nginx rewrite and get the real SPA instead.
"""
import json
import re
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.db import Player, Organisation, get_db

router = APIRouter(prefix="/og-preview", tags=["og-preview"])

SITE = "https://betterstats.cricket"

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)

CLUB_SECTIONS = {
    "dashboard", "players", "leaderboard", "records",
    "compare", "statlab", "yearbook", "yearbooks", "games",
}


def _parse_route(path: str):
    segments = [s for s in path.split("/") if s]
    if not segments:
        return None
    if segments[0] == "players" and len(segments) > 1 and UUID_RE.match(segments[1]):
        return {"type": "player", "player_id": segments[1]}
    if len(segments) >= 2 and segments[1] in CLUB_SECTIONS:
        return {"type": "club", "slug": segments[0]}
    return None


def _abs_url(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"{SITE}{url}"


def _esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _html(title: str, description: str, image: str | None, url: str, jsonld: dict | None = None) -> str:
    img_tags = ""
    if image:
        img_tags = f"""
    <meta property="og:image" content="{_esc(image)}" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:image" content="{_esc(image)}" />"""
    else:
        img_tags = '\n    <meta name="twitter:card" content="summary" />'

    jsonld_tag = ""
    if jsonld:
        # json.dumps is safe inside a <script> tag because we escape the
        # closing '</' sequence per the HTML5 spec.
        encoded = json.dumps(jsonld, separators=(",", ":")).replace("</", "<\\/")
        jsonld_tag = f'\n  <script type="application/ld+json">{encoded}</script>'

    return f"""<!DOCTYPE html>
<html lang="en-AU">
<head>
  <meta charset="UTF-8" />
  <title>{_esc(title)}</title>
  <meta name="description" content="{_esc(description)}" />
  <link rel="canonical" href="{_esc(url)}" />
  <meta property="og:site_name" content="BetterStats" />
  <meta property="og:type" content="website" />
  <meta property="og:locale" content="en_AU" />
  <meta property="og:title" content="{_esc(title)}" />
  <meta property="og:description" content="{_esc(description)}" />
  <meta property="og:url" content="{_esc(url)}" />{img_tags}
  <meta name="twitter:title" content="{_esc(title)}" />
  <meta name="twitter:description" content="{_esc(description)}" />{jsonld_tag}
</head>
<body>
  <h1>{_esc(title)}</h1>
  <p>{_esc(description)}</p>
</body>
</html>"""


async def _player_html(player_id: str, page_url: str, db: AsyncSession) -> str | None:
    try:
        player = await db.get(Player, uuid.UUID(player_id))
    except ValueError:
        return None
    if not player:
        return None

    org = await db.get(Organisation, player.organisation_id) if player.organisation_id else None

    name = player.display_name
    club_name = org.name if org else ""
    description = (
        f"Explore {name}'s full career batting, bowling and fielding records at {club_name} — "
        f"innings by innings, season by season, on BetterStats."
        if club_name
        else f"Explore {name}'s complete career cricket statistics — innings, wickets and more on BetterStats."
    )
    image = _abs_url(player.photo_url) or _abs_url(org.logo_url if org else None)

    jsonld: dict = {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": name,
        "url": page_url,
        "sport": "Cricket",
    }
    if image:
        jsonld["image"] = image
    if org and org.name:
        jsonld["memberOf"] = {
            "@type": "SportsTeam",
            "name": org.name,
            "sport": "Cricket",
        }
        if org.slug:
            jsonld["memberOf"]["url"] = f"{SITE}/{org.slug}/dashboard"

    return _html(
        f"{name} — Cricket Career Stats | BetterStats",
        description,
        image,
        page_url,
        jsonld=jsonld,
    )


async def _club_html(slug: str, page_url: str, db: AsyncSession) -> str | None:
    result = await db.execute(
        select(Organisation).where(Organisation.slug == slug.lower())
    )
    org = result.scalar_one_or_none()
    if not org:
        return None

    description = (
        f"Batting averages, bowling figures, fielding stats, season records and player profiles "
        f"for {org.name} — all in one place on BetterStats."
    )
    image = _abs_url(org.logo_url)
    jsonld = {
        "@context": "https://schema.org",
        "@type": "SportsTeam",
        "name": org.name,
        "sport": "Cricket",
        "url": page_url,
        **({"logo": image} if image else {}),
        "areaServed": {"@type": "Country", "name": "Australia"},
    }
    return _html(
        f"{org.name} Cricket Club Stats & Records | BetterStats",
        description,
        image,
        page_url,
        jsonld=jsonld,
    )


@router.get("", response_class=HTMLResponse)
async def og_preview(
    request: Request,
    path: str = "/",
    db: AsyncSession = Depends(get_db),
):
    route = _parse_route(path)
    page_url = f"{SITE}{path}"

    html = None
    if route and route["type"] == "player":
        html = await _player_html(route["player_id"], page_url, db)
    elif route and route["type"] == "club":
        html = await _club_html(route["slug"], page_url, db)

    if not html:
        # Unrecognised route — return generic fallback
        html = _html(
            "BetterStats — Cricket Analytics",
            "Player-facing cricket statistics platform.",
            None,
            page_url,
        )

    return HTMLResponse(content=html, headers={"cache-control": "public, max-age=300"})
