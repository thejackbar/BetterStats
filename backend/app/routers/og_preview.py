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
    "Turn your cricket club's match history into an automatic website with "
    "player profiles, leaderboards and records. For Australian cricket clubs."
)

# Marketing routes -> (title, description). Keyed by the clean single-segment
# path. Copy mirrors the in-app usePageMeta meta so the card matches the page.
# Descriptions are kept in the 50-160 char window (AEO meta-description check).
MARKETING_PAGES: dict[str, tuple[str, str]] = {
    "/": (HOME_TITLE, HOME_DESC),
    "/features": (
        "Features — Automated cricket club stats | BetterCricket",
        "Automatic stats sync, player profiles, leaderboards, all-time records "
        "and season yearbooks. The BetterStats Core that every BetterCricket "
        "club starts with.",
    ),
    "/pricing": (
        "Pricing — modular plans for cricket clubs | BetterCricket",
        "Flat-rate annual pricing for Australian cricket clubs. BetterStats is "
        "$399 a year, add modules from $149, and bundle for a discount. One "
        "price per club.",
    ),
    "/trial": (
        "Start your club's free trial | BetterCricket",
        "Register your cricket club yourself and start a free trial of every "
        "BetterCricket module. No credit card and no sales call. Pick your club "
        "from the Cricket Australia register and you're in.",
    ),
    "/overview": (
        "Overview — Everything BetterCricket does",
        "A one-page tour of BetterCricket: automatic stats and a public club "
        "website, plus selection, social posts, club admin and opposition "
        "analytics.",
    ),
    "/modules": (
        "Modules — BetterSelect, BetterSocials, BetterClubhouse & BetterIQ | BetterCricket",
        "The four BetterCricket add-ons: BetterSelect for selection, "
        "BetterSocials for your website, BetterClubhouse for the club back "
        "office, and BetterIQ for analytics.",
    ),
    "/modules/betterstats": (
        "BetterStats — your club's stats and public website | BetterCricket",
        "BetterStats turns your club's full history into a public website with "
        "player profiles, leaderboards, all-time records, partnerships and "
        "season yearbooks.",
    ),
    "/modules/betterselect": (
        "BetterSelect — availability & smart team selection | BetterCricket",
        "BetterSelect collects player availability with no app, then suggests a "
        "balanced XI from form, grade and role for captains and selectors.",
    ),
    "/modules/bettersocials": (
        "BetterSocials — your club website & match-day posts | BetterCricket",
        "BetterSocials runs your club's public website and turns match data "
        "into share-ready graphics: lineups, results, player of the match and "
        "scorecards.",
    ),
    # betteradmin was this module's public name until Aug 2026. Both paths are
    # kept so an older shared link still renders a card; the frontend redirects
    # the old URL to the new one.
    "/modules/betterclubhouse": (
        "BetterClubhouse — the club back office | BetterCricket",
        "BetterClubhouse runs the club back office off one member directory: "
        "match fees that allocate themselves, bulk member email, stock, the "
        "volunteer roster and committee meetings with minutes and motions.",
    ),
    "/modules/betteradmin": (
        "BetterClubhouse — the club back office | BetterCricket",
        "BetterClubhouse runs the club back office off one member directory: "
        "match fees that allocate themselves, bulk member email, stock, the "
        "volunteer roster and committee meetings with minutes and motions.",
    ),
    "/modules/betteriq": (
        "BetterIQ — opposition scouting & analytics | BetterCricket",
        "BetterIQ turns your own scorecards into an opposition dossier, a "
        "best-available XI, player trends and deep team analysis for captains "
        "and coaches.",
    ),
    "/modules/betterfantasy": (
        "BetterFantasyCricket — a club fantasy game | BetterCricket",
        "BetterFantasyCricket runs your club's own fantasy comp, scored off your "
        "real games, with salary-cap and draft formats. A fun way to engage the "
        "club all season and an easy pre-season fundraiser.",
    ),
    "/compare": (
        "Compare — BetterCricket vs the tools clubs already use",
        "An honest side-by-side of how BetterCricket compares with the "
        "spreadsheets, website builders, design apps and email tools your club "
        "already pays for.",
    ),
    "/about": (
        "About — BetterCricket",
        "The story behind BetterCricket and BetterSports: stats and history, "
        "weekend availability and selection, social posts, the back office and "
        "match prep.",
    ),
    "/contact": (
        "Contact — Request access for your cricket club | BetterCricket",
        "Request access for your Australian cricket club, ask a question, or "
        "email the BetterCricket team directly.",
    ),
    "/faq": (
        "FAQ — BetterCricket",
        "Common questions about BetterCricket: pricing, onboarding, how far the "
        "historical data goes, player profiles, season yearbooks and how it "
        "works.",
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


# Shared answerable body for the marketing server-render. Mirrors the
# pre-render block in frontend/index.html and /llms.txt so an AI crawler that
# does not run JavaScript gets real content: a descriptive heading, 300+ words,
# question headings, in-body internal links and external citations. Keep the
# copy in step with index.html and the FAQ.jsx source.
MARKETING_FAQ: list[tuple[str, str]] = [
    ("What is BetterCricket?",
     "BetterCricket is a modular platform for Australian club cricket, made by "
     "BetterSports. Every club starts with BetterStats, which brings in every "
     "batting, bowling and fielding stat and turns it into a public club "
     "website with player profiles, leaderboards, all-time records, "
     "partnerships, awards, season yearbooks and shareable stat cards. From "
     "there you can add BetterSelect, BetterSocials, BetterClubhouse and BetterIQ."),
    ("How much does BetterCricket cost?",
     "BetterStats is $399 a year and includes your public stats site. You add "
     "only the modules you want: BetterSelect, BetterSocials and BetterClubhouse are "
     "$149 a year each, and BetterIQ is $249. Bundle two or more and a set "
     "discount applies, which brings BetterStats plus every module to $949 a "
     "year. Every price is a flat rate per club, the same for one team or fifty."),
    ("How far back does the historical data go?",
     "As far back as Australian cricket records go. There is no limit: "
     "BetterCricket brings across everything Cricket Australia holds on first "
     "sync, and if your club has old spreadsheets, those can be imported on "
     "top."),
    ("Who is BetterCricket for?",
     "Australian cricket clubs of any size, from premier grade to country and "
     "association clubs, plus the stats volunteers, captains, coaches, "
     "committees, players, parents and sponsors who care about the club."),
    ("Does each player get their own profile?",
     "Yes. Every player gets a public profile with career stats, a "
     "season-by-season breakdown, career progression charts, dismissal and "
     "batting-position analysis, partnership history, milestone badges and a "
     "one-tap shareable stat card."),
    ("How do I get BetterCricket for my club?",
     "Fill in the request-access form on the homepage or email "
     "support@bettersports.com.au. The BetterCricket team handles the setup, "
     "including the first full historical sync."),
    ("Do we own our club's data?",
     "Always. The data belongs to your club, and you can export all of it to "
     "CSV at any time."),
    ("How long does setup take?",
     "A simple setup is live in under an hour. The BetterCricket team runs the "
     "first sync to bring your history in, then helps you tidy it before the "
     "site goes public."),
    ("Can we customise how the club site looks?",
     "Yes. You control your club's colours, crest, sponsor placement and hero "
     "imagery, so the site looks like your club."),
    ("Do we have to change how our club scores?",
     "No. BetterCricket sits on top of how you already run match day. Keep "
     "scoring as you do now, and the stats turn up on your site automatically."),
]


def _faq_jsonld() -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in MARKETING_FAQ
        ],
    }


def _marketing_body() -> str:
    intro = (
        "<p>BetterCricket is the platform Australian cricket clubs run on. It "
        "imports your club's full match history, going back decades, and turns "
        "it into an automatic public website with player profiles, leaderboards, "
        "all-time records and season yearbooks. It adds modules for team "
        "selection, social posts, club admin and opposition analytics.</p>"
        "<p>BetterCricket keeps your club's match history online and updates it "
        "automatically after every match, so the figures match your official "
        'competition results. See the full <a href="/features">feature list</a> '
        'and <a href="/pricing">pricing</a>, or <a href="/contact">request access '
        'for your club</a>.</p>'
    )
    faq = "".join(f"<h2>{_esc(q)}</h2><p>{_esc(a)}</p>" for q, a in MARKETING_FAQ)
    return intro + faq


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
    body_extra: str = "",
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
  <p>{_esc(description)}</p>{body_extra}
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
        jsonld=_faq_jsonld(),
        image_w=COVER_W,
        image_h=COVER_H,
        image_alt=COVER_ALT,
        body_extra=_marketing_body(),
    )


def _blocks_to_html(blocks: list[dict]) -> str:
    """Render the blog content blocks (mirrored from frontend blog.js) into the
    crawler HTML so an AI engine that doesn't run JS gets the full article body,
    not just the card. Block types match BlogPost.jsx: p / h2 / ul / callout /
    links."""
    out: list[str] = []
    for b in blocks or []:
        t = b.get("type")
        if t == "h2":
            out.append(f"<h2>{_esc(b.get('text',''))}</h2>")
        elif t == "p":
            out.append(f"<p>{_esc(b.get('text',''))}</p>")
        elif t == "ul":
            lis = "".join(f"<li>{_esc(i)}</li>" for i in b.get("items", []))
            out.append(f"<ul>{lis}</ul>")
        elif t == "callout":
            out.append(f'<p>{_esc(b.get("text",""))} <a href="/contact">Learn more</a></p>')
        elif t == "table":
            head = "".join(f"<th>{_esc(h)}</th>" for h in b.get("headers", []))
            rows = "".join(
                "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in r) + "</tr>"
                for r in b.get("rows", [])
            )
            out.append(f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>")
        elif t == "links":
            parts = []
            for it in b.get("items", []):
                rel = ' rel="noopener"' if it.get("external") else ""
                parts.append(f'<a href="{_esc(it.get("href",""))}"{rel}>{_esc(it.get("label",""))}</a>')
            out.append("<p>" + " · ".join(parts) + "</p>")
    return "".join(out)


def _faq_section_html(faq: list[dict]) -> str:
    if not faq:
        return ""
    items = "".join(
        f"<h3>{_esc(f.get('q',''))}</h3><p>{_esc(f.get('a',''))}</p>" for f in faq
    )
    return f"<h2>Frequently asked questions</h2>{items}"


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

    # Posts that carry a body/faq (the JTBD/comparison posts) get the full
    # article rendered into the crawler HTML plus FAQ schema; the older
    # card-only posts fall back to the title + description card unchanged.
    faq = post.get("faq") or []
    body_extra = _blocks_to_html(post.get("body") or []) + _faq_section_html(faq)
    if faq:
        jsonld.append({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": f["q"],
                 "acceptedAnswer": {"@type": "Answer", "text": f["a"]}}
                for f in faq
            ],
        })

    howto = post.get("howto") or []
    if howto:
        jsonld.append({
            "@context": "https://schema.org",
            "@type": "HowTo",
            "name": post["title"],
            "description": post["description"],
            "step": [
                {"@type": "HowToStep", "position": i + 1, "name": s["name"], "text": s["text"]}
                for i, s in enumerate(howto)
            ],
        })

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
        body_extra=body_extra,
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
