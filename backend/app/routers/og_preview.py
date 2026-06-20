"""
Server-side OG tag injection for social-media crawlers.

nginx detects crawler User-Agents and rewrites their requests to
GET /og-preview?path=<original-path>, which lands here. We build a minimal
HTML page with correct Open Graph + Twitter Card meta tags (and JSON-LD for
players/clubs), then return it. Regular users never hit this endpoint, and
search engines (Googlebot, bingbot) are excluded from the nginx rewrite and
get the real SPA instead.

The homepage and the marketing pages get a branded card with the wide
og-cover.png social image; club and player pages get their own photo/logo,
falling back to the same cover.
"""
import json
import re
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.content import blog as blog_content
from app.models.db import Player, Organisation, get_db

router = APIRouter(prefix="/og-preview", tags=["og-preview"])

# Default/fallback origin. The live origin is taken from the request host
# (see _base_url) so the card's URLs and image sit on whatever domain was
# actually shared.
SITE = "https://betterat.cricket"
SITE_NAME = "BetterCricket"
TWITTER_HANDLE = "@betterstatsau"

# Only echo a request host back into the card if it is one of ours, so a
# spoofed Host header can't point the preview somewhere else.
ALLOWED_HOSTS = {
    "betterat.cricket", "www.betterat.cricket",
    "betterstats.cricket", "www.betterstats.cricket",
}

# The wide 1200x630 social card. Square og-image.png stays the favicon/app icon.
OG_COVER = "/og-cover.png"
COVER_W, COVER_H = 1200, 630
COVER_ALT = "BetterCricket, making your cricket club better"

HOME_TITLE = "Making your cricket club better"
HOME_DESC = (
    "Your club's match history becomes a proper website: player profiles, "
    "leaderboards, records and season yearbooks, updated automatically after "
    "every game. Plus selection, socials, admin and analytics."
)

# Marketing routes -> (title, description). Keyed by the clean single-segment
# path. Copy mirrors the in-app usePageMeta meta so the card matches the page.
MARKETING_PAGES: dict[str, tuple[str, str]] = {
    "/": (HOME_TITLE, HOME_DESC),
    "/features": (
        "Features — Automated cricket club stats | BetterCricket",
        "Automatic stats sync, player profiles, leaderboards, all-time records "
        "and season yearbooks, the foundation of every BetterCricket plan. "
        "Plus partnership records, StatLab custom queries, awards and admin tools.",
    ),
    "/pricing": (
        "Pricing — modular plans for cricket clubs | BetterCricket",
        "Flat-rate annual pricing for Australian cricket clubs. BetterStats is "
        "$399 a year; add BetterSelect, BetterSocials and BetterAdmin for $149 "
        "each and BetterIQ for $249, with a discount when you bundle. One price "
        "per club, whatever the size.",
    ),
    "/overview": (
        "Overview — Everything BetterCricket does",
        "A one-page tour of BetterCricket: automated stats and a public club "
        "site (BetterStats), plus BetterSelect, BetterSocials, BetterAdmin and "
        "BetterIQ. The whole platform Australian cricket clubs run on.",
    ),
    "/modules": (
        "Modules — BetterSelect, BetterSocials, BetterAdmin & BetterIQ | BetterCricket",
        "BetterCricket in parts: the BetterStats Core plus four bolt-on "
        "modules. BetterSelect for selection, BetterSocials for your website and "
        "social posts, BetterAdmin for fees and comms, and BetterIQ for "
        "analytics and opposition scouting.",
    ),
    "/modules/betterstats": (
        "BetterStats — your club's stats and public website | BetterCricket",
        "The Core every plan starts with: your club's full reconciled history "
        "turned into a public website with player profiles, leaderboards, "
        "all-time records, partnerships, season yearbooks and shareable stat "
        "cards. No manual data entry.",
    ),
    "/modules/betterselect": (
        "BetterSelect — availability & smart team selection | BetterCricket",
        "Players set their own availability with no account and no app. "
        "Captains and selectors get a whole-squad grid, drag-and-drop squad "
        "boards, live fixtures and ladders, and a form and role aware autofill "
        "that suggests a balanced XI.",
    ),
    "/modules/bettersocials": (
        "BetterSocials — your club website & match-day posts | BetterCricket",
        "Run your club's public website and turn match data into share-ready "
        "graphics: lineups, toss, player of the match, results and full "
        "scorecards, all in your crest, colours and fonts with one-tap export.",
    ),
    "/modules/betteradmin": (
        "BetterAdmin — fees, comms & merch | BetterCricket",
        "The back office in one place: BetterFees auto-allocates match-fee "
        "payments and keeps a live Paid, Part-paid and Unpaid picture, "
        "BetterComms sends bulk member email, and BetterMerch (stock and sales) "
        "is coming soon.",
    ),
    "/modules/betteriq": (
        "BetterIQ — opposition scouting & analytics | BetterCricket",
        "Turn your own scorecards into an opposition dossier with danger "
        "players, head-to-head history and a printable captain's cheat sheet, "
        "plus player trends, a best-available XI and deep team analysis.",
    ),
    "/compare": (
        "Compare — BetterCricket vs the tools clubs already use",
        "An honest, side-by-side look at how BetterCricket stacks up against "
        "the spreadsheets, website builders, design apps and bulk email tools "
        "your club already pays for.",
    ),
    "/about": (
        "About — BetterCricket",
        "BetterCricket puts everything an Australian cricket club runs on in "
        "one place: stats and history, weekend availability and selection, "
        "social posts, the back office and match prep.",
    ),
    "/contact": (
        "Contact — Request access for your cricket club | BetterCricket",
        "Request access for your Australian cricket club, ask a question, or "
        "email the BetterCricket team directly.",
    ),
    "/faq": (
        "FAQ — BetterCricket",
        "Common questions about BetterCricket: pricing, onboarding, how deep "
        "the historical data goes, player profiles, season yearbooks, and how "
        "it works for Australian cricket clubs.",
    ),
    "/blog": (
        "Blog — Cricket stats guides & club tips | BetterCricket",
        "Cricket statistics guides and club management tips from the Better "
        "Cricket team: batting averages, bowling economy, historical data and "
        "more.",
    ),
    "/terms": (
        "Terms of Service — BetterCricket",
        "Terms of service for BetterCricket, the cricket platform for "
        "Australian clubs, provided by BetterSports.",
    ),
    "/privacy": (
        "Privacy Policy — BetterCricket",
        "How BetterCricket, provided by BetterSports, collects, stores and "
        "handles club, player and account information under the Australian "
        "Privacy Act.",
    ),
}

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)

CLUB_SECTIONS = {
    "dashboard", "players", "leaderboard", "records",
    "compare", "statlab", "yearbook", "yearbooks", "games",
}
# Single-segment paths that are NOT club slugs (must stay in sync with App.jsx routes).
RESERVED_ROOT_SEGMENTS = {
    "login", "admin", "onboard", "club-inactive",
    "games", "match", "scorecards", "players",
    "features", "pricing", "compare", "about", "contact", "faq",
    "terms", "privacy", "blog", "overview", "modules",
}


def _base_url(request: Request) -> str:
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or ""
    ).split(",")[0].strip().lower()
    if host in ALLOWED_HOSTS:
        return f"https://{host}"
    return SITE


def _parse_route(path: str):
    segments = [s for s in path.split("/") if s]
    if not segments:
        return None
    if segments[0] == "players" and len(segments) > 1 and UUID_RE.match(segments[1]):
        return {"type": "player", "player_id": segments[1]}
    if segments[0] == "blog" and len(segments) == 2:
        return {"type": "blog", "slug": segments[1]}
    if len(segments) >= 2 and segments[1] in CLUB_SECTIONS:
        return {"type": "club", "slug": segments[0]}
    if len(segments) == 1 and segments[0] not in RESERVED_ROOT_SEGMENTS:
        return {"type": "club", "slug": segments[0]}
    return None


def _abs_url(url: str | None, base: str) -> str | None:
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"{base}{url}"


def _esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _html(
    title: str,
    description: str,
    image: str | None,
    url: str,
    jsonld: dict | list | None = None,
    image_w: int | None = None,
    image_h: int | None = None,
    image_alt: str | None = None,
    og_type: str = "website",
) -> str:
    if image:
        img_tags = f"""
    <meta property="og:image" content="{_esc(image)}" />
    <meta property="og:image:secure_url" content="{_esc(image)}" />"""
        if image_w and image_h:
            img_tags += f"""
    <meta property="og:image:width" content="{image_w}" />
    <meta property="og:image:height" content="{image_h}" />"""
        if image_alt:
            img_tags += f"""
    <meta property="og:image:alt" content="{_esc(image_alt)}" />"""
        img_tags += f"""
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:image" content="{_esc(image)}" />"""
        if image_alt:
            img_tags += f"""
    <meta name="twitter:image:alt" content="{_esc(image_alt)}" />"""
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
  <meta property="og:site_name" content="{SITE_NAME}" />
  <meta property="og:type" content="{_esc(og_type)}" />
  <meta property="og:locale" content="en_AU" />
  <meta property="og:title" content="{_esc(title)}" />
  <meta property="og:description" content="{_esc(description)}" />
  <meta property="og:url" content="{_esc(url)}" />{img_tags}
  <meta name="twitter:site" content="{TWITTER_HANDLE}" />
  <meta name="twitter:title" content="{_esc(title)}" />
  <meta name="twitter:description" content="{_esc(description)}" />{jsonld_tag}
</head>
<body>
  <h1>{_esc(title)}</h1>
  <p>{_esc(description)}</p>
</body>
</html>"""


def _marketing_html(path: str, base: str) -> str:
    key = "/" + path.strip("/").lower()
    title, description = MARKETING_PAGES.get(key, (HOME_TITLE, HOME_DESC))
    return _html(
        title,
        description,
        _abs_url(OG_COVER, base),
        f"{base}{path}",
        image_w=COVER_W,
        image_h=COVER_H,
        image_alt=COVER_ALT,
    )


def _blog_html(slug: str, page_url: str, base: str) -> str | None:
    post = blog_content.get_post(slug)
    if not post:
        return None

    image = _abs_url(post.get("image"), base) or _abs_url(OG_COVER, base)
    # Title mirrors the in-app BlogPost meta so a JS-running crawler and a
    # plain one see the same card.
    title = f"{post['title']} | {SITE_NAME}"

    # BlogPosting + breadcrumb, mirroring frontend BlogPost.jsx so search and
    # AI engines read the article cleanly.
    jsonld = [
        {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": post["title"],
            "description": post["description"],
            "image": image,
            "datePublished": post["date"],
            "dateModified": post["date"],
            "inLanguage": "en-AU",
            "author": {"@type": "Organization", "name": SITE_NAME, "url": f"{base}/"},
            "publisher": {
                "@type": "Organization",
                "name": "BetterSports",
                "logo": {"@type": "ImageObject", "url": f"{base}/og-image.png"},
            },
            "mainEntityOfPage": {"@type": "WebPage", "@id": page_url},
            "url": page_url,
        },
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{base}/"},
                {"@type": "ListItem", "position": 2, "name": "Blog", "item": f"{base}/blog"},
                {"@type": "ListItem", "position": 3, "name": post["title"], "item": page_url},
            ],
        },
    ]

    return _html(
        title,
        post["description"],
        image,
        page_url,
        jsonld=jsonld,
        image_w=blog_content.IMAGE_WIDTH,
        image_h=blog_content.IMAGE_HEIGHT,
        image_alt=post["title"],
        og_type="article",
    )


async def _player_html(player_id: str, page_url: str, base: str, db: AsyncSession) -> str | None:
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
        f"innings by innings, season by season, on BetterCricket."
        if club_name
        else f"Explore {name}'s complete career cricket statistics — innings, wickets and more on BetterCricket."
    )
    image = (
        _abs_url(player.photo_url, base)
        or _abs_url(org.logo_url if org else None, base)
        or _abs_url(OG_COVER, base)
    )

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
            jsonld["memberOf"]["url"] = f"{base}/{org.slug}"

    return _html(
        f"{name} — Cricket Career Stats | BetterCricket",
        description,
        image,
        page_url,
        jsonld=jsonld,
    )


async def _club_html(slug: str, page_url: str, base: str, db: AsyncSession) -> str | None:
    result = await db.execute(
        select(Organisation).where(Organisation.slug == slug.lower())
    )
    org = result.scalar_one_or_none()
    if not org:
        return None

    description = (
        f"Batting averages, bowling figures, fielding stats, season records and player profiles "
        f"for {org.name} — all in one place on BetterCricket."
    )
    image = _abs_url(org.logo_url, base) or _abs_url(OG_COVER, base)
    jsonld = {
        "@context": "https://schema.org",
        "@type": "SportsTeam",
        "name": org.name,
        "sport": "Cricket",
        "url": page_url,
        **({"logo": _abs_url(org.logo_url, base)} if org.logo_url else {}),
        "areaServed": {"@type": "Country", "name": "Australia"},
    }
    return _html(
        f"{org.name} Cricket Club Stats & Records | BetterCricket",
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
    base = _base_url(request)
    route = _parse_route(path)
    page_url = f"{base}{path}"

    html = None
    if route and route["type"] == "player":
        html = await _player_html(route["player_id"], page_url, base, db)
    elif route and route["type"] == "blog":
        html = _blog_html(route["slug"], page_url, base)
    elif route and route["type"] == "club":
        html = await _club_html(route["slug"], page_url, base, db)

    # Homepage, marketing pages and any unrecognised route fall back to a
    # branded card with the wide cover image.
    if not html:
        html = _marketing_html(path, base)

    return HTMLResponse(content=html, headers={"cache-control": "public, max-age=300"})
