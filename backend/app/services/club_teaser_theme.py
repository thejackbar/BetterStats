"""A club's look on its season page: an accent colour and light or dark, from its logo.

A prospect's season page is shown in the club's own colours, so it reads as that
club's site rather than ours. The colour is read once from the club's logo and
stored (``club_teaser_snapshots.theme``), not worked out in the browser, so the
page never flashes the wrong colour and a logo host that blocks cross-origin
reads does not matter. It lives in its own column, not in the snapshot: a theme
change must not move the snapshot's content hash, or every picture would be
marked out of date and drawn again.

``theme_from_image`` is pure (bytes in, dict out) so the rules can be tested
without a network. ``fetch_logo`` is the only outbound call, one GET per club
and only when a club has no theme yet or its logo address changed. It never
raises: a club with no readable logo simply has no theme and the page uses the
BetterCricket look.

The rules:

* Accent: the most common clearly coloured pixel group in the logo (not white,
  black or grey, and not the logo's own background). A logo with no colour at
  all (a black and white crest) has no accent and the page keeps the default.
* Light or dark page: a logo on a white background, or dark artwork on a
  transparent one, sits on a LIGHT page. A logo on a dark background, or light
  artwork on a transparent one, sits on a DARK page. Colourful artwork with no
  clear answer goes dark, like the club dashboard.
* The accent is nudged until it can be read on the chosen page (about 3:1) and
  carries the text colour that sits on it.
"""
from __future__ import annotations

import colorsys
import io
import ipaddress
import logging
import socket
from typing import Optional
from urllib.parse import urlparse

import json

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

THEME_VERSION = 1
MAX_LOGO_BYTES = 3_000_000
FETCH_TIMEOUT = 8.0
SAMPLE = 64                      # logos are shrunk to this many pixels a side
MIN_SATURATION = 0.28            # below this a pixel is grey, white or black
MIN_COLOURED_SHARE = 0.015       # fewer coloured pixels than this: no accent
PAGE_BG = {"dark": (11, 14, 19), "light": (246, 247, 249)}
MIN_CONTRAST = 3.0
DARK_ARTWORK = 0.12              # mean relative luminance of the artwork at or below this


def _lum(rgb) -> float:
    def ch(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _contrast(a, b) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(int(round(v)) for v in rgb)


def _mix(rgb, towards, t: float):
    return tuple(c + (w - c) * t for c, w in zip(rgb, towards))


def _readable(rgb, mode: str):
    """The accent, moved toward white (dark page) or black (light page) just far
    enough to be read on that page."""
    bg = PAGE_BG[mode]
    towards = (255, 255, 255) if mode == "dark" else (0, 0, 0)
    out = tuple(float(c) for c in rgb)
    for _ in range(40):
        if _contrast(out, bg) >= MIN_CONTRAST:
            break
        out = _mix(out, towards, 0.06)
    return out


def _on(rgb) -> str:
    return "#000000" if _contrast(rgb, (0, 0, 0)) >= _contrast(rgb, (255, 255, 255)) else "#ffffff"


def theme_from_image(data: bytes) -> Optional[dict]:
    """The theme for a logo, or None when the bytes are not an image."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        im.load()
        im = im.convert("RGBA")
    except Exception:  # noqa: BLE001 - not an image we can read
        return None
    im.thumbnail((SAMPLE, SAMPLE))
    w, h = im.size
    px = list(im.getdata())
    if not px:
        return None

    opaque = [p for p in px if p[3] >= 128]
    if len(opaque) < max(10, 0.02 * len(px)):
        return None                       # an empty or near empty picture
    transparent_share = 1 - len(opaque) / len(px)

    # The logo's own background, if it has one: the corners, when they are opaque
    # and agree with each other.
    corners = [im.getpixel(c) for c in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    bg_rgb = None
    if all(c[3] >= 128 for c in corners):
        spread = max(max(c[i] for c in corners) - min(c[i] for c in corners) for i in range(3))
        if spread <= 24:
            bg_rgb = tuple(sum(c[i] for c in corners) // 4 for i in range(3))

    def is_bg(p) -> bool:
        return bg_rgb is not None and sum(abs(p[i] - bg_rgb[i]) for i in range(3)) <= 60

    fg = [p for p in opaque if not is_bg(p)]
    if not fg:
        return None

    # Accent: group the coloured foreground pixels into 12-degree hue buckets and
    # take the biggest, averaging its pixels.
    buckets: dict[int, list] = {}
    for r, g, b, _a in fg:
        hh, ss, vv = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if ss >= MIN_SATURATION and vv >= 0.18:
            buckets.setdefault(int(hh * 30) % 30, []).append((r, g, b, ss * vv))
    coloured = sum(len(v) for v in buckets.values())
    accent_rgb = None
    if coloured >= MIN_COLOURED_SHARE * len(fg) and coloured >= 8:
        # A hue and its neighbours are one colour (red straddles the wrap).
        def weight(k):
            return sum(len(buckets.get((k + d) % 30, ())) for d in (-1, 0, 1))
        best = max(buckets, key=weight)
        members = [p for d in (-1, 0, 1) for p in buckets.get((best + d) % 30, ())]
        total = sum(m[3] for m in members) or 1.0
        accent_rgb = tuple(sum(m[i] * m[3] for m in members) / total for i in range(3))

    # Light or dark page.
    if bg_rgb is not None:
        mode = "light" if _lum(bg_rgb) >= 0.55 else "dark"
    else:
        mean_fg = sum(_lum(p[:3]) for p in fg) / len(fg)
        # Dark artwork on a transparent logo disappears on a dark page.
        mode = "light" if transparent_share >= 0.10 and mean_fg <= DARK_ARTWORK else "dark"

    out = {"v": THEME_VERSION, "mode": mode, "accent": None, "on_accent": None}
    if accent_rgb is not None:
        usable = _readable(accent_rgb, mode)
        out["accent"] = _hex(usable)
        out["on_accent"] = _on(usable)
    return out


def _public_host(host: str) -> bool:
    """Refuse a logo address that points inside our network."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return bool(infos)


async def fetch_logo(url: str, *, client: Optional[httpx.AsyncClient] = None) -> Optional[bytes]:
    """The logo's bytes, or None. One GET, https or http only, a public host,
    image content, at most ``MAX_LOGO_BYTES``. Never raises."""
    try:
        u = urlparse(url or "")
        if u.scheme not in ("http", "https") or not u.hostname or not _public_host(u.hostname):
            return None
        own = client is None
        c = client or httpx.AsyncClient(follow_redirects=False, timeout=FETCH_TIMEOUT)
        try:
            r = await c.get(url)
        finally:
            if own:
                await c.aclose()
        if r.status_code != 200 or len(r.content) > MAX_LOGO_BYTES:
            return None
        if "image" not in (r.headers.get("content-type") or "").lower():
            return None
        return r.content
    except Exception as exc:  # noqa: BLE001 - a missing logo is not an error
        logger.info("Logo fetch failed for %s: %s", url, exc)
        return None


async def theme_for_url(url: Optional[str], *, fetch=fetch_logo) -> Optional[dict]:
    """The theme for a logo address, with the address it was read from (so a
    changed logo is noticed), or None."""
    if not url:
        return None
    data = await fetch(url)
    if not data:
        return None
    theme = theme_from_image(data)
    if theme is None:
        return None
    return {**theme, "src": url}


async def store_theme(session: AsyncSession, club_id, logo_url: Optional[str], *,
                      fetch=fetch_logo, force: bool = False) -> Optional[dict]:
    """Read the club's logo and store its theme, when the club has none yet or its
    logo address changed (``force`` always reads). A logo that cannot be fetched
    leaves a theme already stored as it is; a club with no logo address at all
    loses it. Commits. Never raises: a swallowed database error is rolled back."""
    try:
        row = (await session.execute(text(
            "SELECT theme FROM club_teaser_snapshots WHERE marketing_club_id = CAST(:c AS uuid)"),
            {"c": str(club_id)})).first()
        if row is None:
            return None
        current = row[0]
        if not logo_url:
            if current is not None:
                await session.execute(text(
                    "UPDATE club_teaser_snapshots SET theme = NULL WHERE marketing_club_id = CAST(:c AS uuid)"),
                    {"c": str(club_id)})
                await session.commit()
            return None
        if current and current.get("src") == logo_url and current.get("v") == THEME_VERSION and not force:
            return current
        theme = await theme_for_url(logo_url, fetch=fetch)
        if theme is None:
            return current
        await session.execute(text(
            "UPDATE club_teaser_snapshots SET theme = CAST(:t AS jsonb) WHERE marketing_club_id = CAST(:c AS uuid)"),
            {"t": json.dumps(theme), "c": str(club_id)})
        await session.commit()
        return theme
    except Exception:  # noqa: BLE001 - a missing theme must never fail a pull
        logger.exception("Storing the teaser theme failed for %s", club_id)
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None
