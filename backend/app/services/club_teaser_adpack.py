"""The Meta ad pack: a zip a person uploads into Ads Manager by hand.

For each chosen club it holds the two ad pictures (feed and story), the ad
words, the landing link with its tracking, and the club's location for geo
targeting. It is an EXPORT. Nothing here talks to Meta, creates an ad, or
spends money; the person who uploads it decides all of that.

Which clubs: the ones that match the Club Directory filters the operator has
on screen, that are not customers, not excluded, not marked not-interested, and
have a good snapshot whose pictures have been drawn (and are on disk). A club
without a picture cannot be in a pack. A club without a location can be, and
is flagged ``geo_ready = no``: it can still be used for a generic audience.

Rules this module keeps:

* Ad pictures never print a player's name (see ``club_teaser_images.FORMATS``),
  and neither does the copy. The words talk about "your top run-scorer", not
  about whoever that is.
* Every figure in the words comes from the same snapshot the picture was drawn
  from, through ``club_teaser.presentation``.
* Words never address the person who sees them or assume they belong to the
  club (Meta's personal attributes rule). They speak about "the club" in the
  third person.
* The tracking on each link is the same attribution the emails use (``utm_id``
  is the club's UTM code), so a visit from an ad is tied back to the club.
"""
from __future__ import annotations

import csv
import io
import re
import tempfile
import unicodedata
import zipfile
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import club_directory as cd
from app.services import club_teaser, club_teaser_images as ti

PACK_FORMATS = ("feed", "story")
DEFAULT_LIMIT = 50
MAX_LIMIT = 100
DEFAULT_RADIUS_KM = 15
MIN_RADIUS_KM, MAX_RADIUS_KM = 2, 80
DEFAULT_CAMPAIGN = "club-season"

# Meta's recommended lengths. Text over these is cut off in the feed, so the
# copy builder stays inside them rather than hoping.
HEADLINE_MAX = 40
PRIMARY_MAX = 125
DESCRIPTION_MAX = 30

MANIFEST_COLUMNS = [
    "club", "state", "suburb", "postcode", "latitude", "longitude", "radius_km", "geo_ready",
    "association", "season", "lead_figure", "headline", "primary_text", "description", "call_to_action",
    "landing_url_feed", "landing_url_story", "feed_image", "story_image", "utm_code", "club_id",
]


def clean_campaign(value: Optional[str]) -> str:
    """A campaign name that is safe in a link: lowercase letters, digits and
    hyphens. Anything else becomes a hyphen; an empty result is the default."""
    s = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")[:60]
    return s or DEFAULT_CAMPAIGN


def clamp_radius(value) -> int:
    try:
        r = int(value)
    except (TypeError, ValueError):
        return DEFAULT_RADIUS_KM
    return max(MIN_RADIUS_KM, min(MAX_RADIUS_KM, r))


def slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "club"


def file_name(name: str, token: str) -> str:
    """``<club>-<first 8 of the token>.png``: readable in Ads Manager, and two
    clubs with the same name never collide."""
    return f"{slug(name)}-{token[:8]}.png"


def landing_url(token: str, fmt: str, *, campaign: str, utm_code: str) -> str:
    base = ti.public_page_url(token)
    q = (f"utm_source=meta&utm_medium=paid_social&utm_campaign={quote(campaign, safe='')}"
         f"&utm_content={fmt}&utm_id={quote(utm_code, safe='')}")
    return f"{base}?{q}"


def lead_figure(view: dict) -> str:
    hero = view.get("hero")
    return f"{int(hero['value']):,} {hero['unit']}" if hero else ""


def ad_copy(club_name: str, view: dict) -> dict:
    """Headline, primary text and description for one club. Plain words, no
    player names, inside Meta's recommended lengths."""
    name = (club_name or "").strip()
    headline = f"{name} season, ready to claim"
    if len(headline) > HEADLINE_MAX:
        headline = "Club season, ready to claim"
    hero = view.get("hero")
    season = (view.get("season") or {}).get("name") or ""
    tail = "Claim the club to see every player and record."

    def sentence(with_season: bool) -> str:
        if not hero:
            return "The club's season is already on BetterCricket."
        where = f" in {season}" if (with_season and season) else ""
        if hero["kind"] == "runs":
            return f"The club's top run-scorer made {int(hero['value']):,} runs{where}."
        return f"The club's leading wicket-taker took {int(hero['value']):,} wickets{where}."

    primary = f"{sentence(True)} {tail}"
    if len(primary) > PRIMARY_MAX:
        primary = f"{sentence(False)} {tail}"
    return {"headline": headline, "primary_text": primary, "description": "Free trial. No card."}


_SQL = """
    SELECT mc.id, mc.name, mc.state, mc.suburb, mc.postcode, mc.latitude, mc.longitude,
           mc.association_name, mc.utm_code, t.token, t.snapshot, t.image_version
    FROM marketing_clubs mc
    JOIN club_teaser_snapshots t ON t.marketing_club_id = mc.id
    WHERE t.status = 'ok' AND t.snapshot IS NOT NULL AND t.image_version IS NOT NULL
      AND mc.existing_org_id IS NULL AND mc.excluded IS NOT TRUE AND mc.not_interested IS NOT TRUE
      AND mc.kind = 'club' AND mc.id = ANY(CAST(:ids AS uuid[]))
    ORDER BY mc.name, mc.id
"""


async def matching_ids(session: AsyncSession, filters: dict) -> list[str]:
    """Ids of the clubs the directory filters match (any kind of club row, the
    same conditions the list and the CSV use)."""
    from sqlalchemy import select
    from app.models.db import MarketingClub
    q = select(MarketingClub.id).where(MarketingClub.kind == "club")
    for cond in cd.club_filters(**(filters or {})):
        q = q.where(cond)
    return [str(i) for i in (await session.execute(q)).scalars().all()]


def _pictures_on_disk(token: str) -> bool:
    return all(ti.image_path(token, f).is_file() for f in PACK_FORMATS)


async def select_clubs(session: AsyncSession, filters: dict, *, limit: int = DEFAULT_LIMIT,
                       offset: int = 0) -> dict:
    """``{matching, eligible, without_location, clubs}``: how many clubs the
    filters match, how many of those can go in a pack, and the slice
    (``offset`` .. ``offset + limit``) that this pack would hold."""
    limit = max(1, min(int(limit), MAX_LIMIT))
    offset = max(0, int(offset))
    ids = await matching_ids(session, filters)
    if not ids:
        return {"matching": 0, "eligible": 0, "without_location": 0, "clubs": [], "limit": limit, "offset": offset}
    rows = (await session.execute(text(_SQL), {"ids": ids})).mappings().all()
    eligible = [dict(r) for r in rows if _pictures_on_disk(r["token"])]
    have_geo = lambda r: r["latitude"] is not None and r["longitude"] is not None  # noqa: E731
    return {
        "matching": len(ids), "eligible": len(eligible),
        "without_location": sum(1 for r in eligible if not have_geo(r)),
        "clubs": eligible[offset:offset + limit], "limit": limit, "offset": offset,
    }


def manifest_rows(clubs: list[dict], *, campaign: str, radius_km: int) -> list[dict]:
    out = []
    for c in clubs:
        view = club_teaser.presentation(c["snapshot"])
        copy = ad_copy(c["name"], view)
        utm = c["utm_code"] or cd._default_utm(c["name"])
        lat, lng = c["latitude"], c["longitude"]
        geo = lat is not None and lng is not None
        out.append({
            "club": c["name"], "state": c["state"] or "", "suburb": c["suburb"] or "",
            "postcode": c["postcode"] or "",
            "latitude": f"{float(lat):.6f}" if geo else "", "longitude": f"{float(lng):.6f}" if geo else "",
            "radius_km": radius_km if geo else "", "geo_ready": "yes" if geo else "no",
            "association": c["association_name"] or "", "season": (view.get("season") or {}).get("name") or "",
            "lead_figure": lead_figure(view), **copy, "call_to_action": "LEARN_MORE",
            "landing_url_feed": landing_url(c["token"], "feed", campaign=campaign, utm_code=utm),
            "landing_url_story": landing_url(c["token"], "story", campaign=campaign, utm_code=utm),
            "feed_image": f"feed/{file_name(c['name'], c['token'])}",
            "story_image": f"story/{file_name(c['name'], c['token'])}",
            "utm_code": utm, "club_id": str(c["id"]),
        })
    return out


README = """BetterCricket club season ad pack
=================================

What is in this zip
  manifest.csv      one row per club: location, the ad words, the landing links
  feed/             the feed picture for each club (1080 x 1350)
  story/            the story and reel picture for each club (1080 x 1920)

How to use it
  1. In Ads Manager, make one campaign for the pack, or one per state.
  2. For a club, make an ad set that targets a pin at the club's latitude and
     longitude with the radius in the manifest (radius_km). Clubs where
     geo_ready is "no" have no location on file: use them with a custom
     audience or a broader area instead.
  3. Make an ad with the club's feed and story pictures. Use headline,
     primary_text, description and call_to_action from the same row, and the
     matching landing_url_feed and landing_url_story.
  4. Review the ad in Meta's preview before you publish.

Things to know
  * Nothing here has been sent to Meta. No ad exists until you create it, and
    nothing is spent until you publish.
  * The pictures and words never name a player. Only the email picture does.
  * The words speak about the club, not about the person who sees the ad.
  * The links carry utm_source=meta and the club's own utm_id, so a visit from
    an ad is tied back to the club in the Club Directory.
  * The figures come from Cricket Australia's public match data and are only
    as current as the club's last pull.
"""


def build_zip(clubs: list[dict], *, campaign: str, radius_km: int) -> Path:
    """Write the pack to a temporary file and return its path. The caller
    deletes it once it has been sent. PNGs are already compressed, so they are
    stored as they are."""
    rows = manifest_rows(clubs, campaign=campaign, radius_km=radius_km)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=MANIFEST_COLUMNS)
    w.writeheader()
    w.writerows(rows)
    tmp = tempfile.NamedTemporaryFile(prefix="ad-pack-", suffix=".zip", delete=False)
    tmp.close()
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_STORED) as z:
        z.writestr("README.txt", README)
        z.writestr("manifest.csv", buf.getvalue())
        for c in clubs:
            for fmt in PACK_FORMATS:
                z.write(ti.image_path(c["token"], fmt), f"{fmt}/{file_name(c['name'], c['token'])}")
    return Path(tmp.name)
