"""An association workspace's crest library (table ``association_crests``).

A workspace's posts name every club in a grade, and Cricket Australia's crests
come in every shape: a crest on a white square, on a coloured block, already
cut out. Drawn as they are, a white square on a dark post reads as a sticker
and the crest itself ends up small inside it. So the first time a pull names a
club, its crest is fetched once, the plain background is taken off, the
picture is trimmed to the crest, its colours are read, and the result is kept
for the workspace. Every later post reuses it, so a round is one database read,
not a dozen fetches.

The rules:

* Background: only a PLAIN one is taken off. The picture's border must be one
  colour (most of the edge within a small distance of the median edge colour),
  and only the pixels of that colour joined to the edge are cleared, with a
  soft edge. A crest whose own artwork runs to the edge, or a photo, is left
  as it is. A picture that is already transparent is only trimmed.
* A person's choice wins: an upload (``uploaded_png``), "use the original"
  (``use_cleaned = false``) and a hand-set colour (``colour_by_hand``) are
  never replaced by code. A changed Cricket Australia address refreshes the
  automatic copy only.
* Outbound: one GET per new crest through ``club_teaser_theme.fetch_logo``
  (public host, image content, size cap, timeout), at most ``MAX_NEW`` new
  crests per pull and ``FETCH_CONCURRENCY`` at a time. Anything that fails
  falls back to the address the post used before, so a crest is never lost.

``clean_crest`` and ``crest_colours`` are pure (bytes in, bytes or colours out)
so the rules can be tested without a network.
"""
from __future__ import annotations

import asyncio
import colorsys
import hashlib
import io
import logging
from collections import deque
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.club_teaser_theme import fetch_logo
from app.services.session_safety import rollback_keeping

logger = logging.getLogger(__name__)

EDGE = 384                 # longest side we keep, in pixels
UPLOAD_EDGE = 512          # an upload keeps a little more
MAX_NEW = 24               # new crests fetched in one pull
FETCH_CONCURRENCY = 4
BG_TOLERANCE = 70          # sum of |dr|+|dg|+|db| still counted as the background
EDGE_AGREE = 45            # an edge pixel this close to the median edge colour agrees
EDGE_SHARE = 0.7           # share of the edge that must agree for a plain background
MIN_SAT = 0.28
EDGE_MATTE = 2 * BG_TOLERANCE  # an edge pixel this close to the background is part background
SPECK_MIN = 6                  # and at least this many pixels (smaller is resampling, not a hole)
SPECK_SHARE = 0.003            # an enclosed patch of background this small is cleared too
EDGE_BAND = 3                  # how many pixels in from the cleared area count as edge
DARK_EDGE_LUM = 0.08           # relative luminance below which an edge disappears on a dark post
DARK_EDGE_SHARE = 0.25         # this share of the outline band dark: give the crest a white edge
DARK_BAND = 4                  # how deep the outline band is, in pixels
CLEAN_VERSION = 2              # bump to re-clean every kept crest from its original
CUT_STYLES = ("auto", "plain", "edge")
URL_PREFIX = "/api/images/association-crests"


def _open(data: bytes):
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    im.load()
    return im.convert("RGBA")


def _png(im) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _trim(im):
    """Crop to the visible crest with a small margin, so it fills its box."""
    alpha = im.getchannel("A").point(lambda a: 255 if a > 16 else 0)
    box = alpha.getbbox()
    if not box:
        return im
    l, t, r, b = box
    pad = max(2, round(max(r - l, b - t) * 0.02))
    return im.crop((max(0, l - pad), max(0, t - pad), min(im.width, r + pad), min(im.height, b + pad)))


def _dist(a, b) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])


def clean_crest(data: bytes) -> Optional[tuple[bytes, Optional[bytes]]]:
    """``(original, cleaned)`` PNGs for a crest, or None when the bytes are not
    an image. ``original`` is the picture re-encoded and trimmed; ``cleaned`` is
    the same with its plain background cleared, or None when it has none."""
    try:
        im = _open(data)
    except Exception:  # noqa: BLE001 - not an image we can read
        return None
    im.thumbnail((EDGE, EDGE))
    original = _png(_trim(im))
    w, h = im.size
    if w < 8 or h < 8:
        return original, None
    px = im.load()
    border = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)] + \
             [(0, y) for y in range(1, h - 1)] + [(w - 1, y) for y in range(1, h - 1)]
    see_through = sum(1 for c in border if px[c][3] < 64)
    if see_through >= 0.5 * len(border):
        return original, None              # already cut out: trimmed is all it needs
    opaque = [px[c] for c in border if px[c][3] >= 64]
    if not opaque:
        return original, None
    med = tuple(sorted(p[i] for p in opaque)[len(opaque) // 2] for i in range(3))
    if sum(1 for p in opaque if _dist(p, med) <= EDGE_AGREE) < EDGE_SHARE * len(border):
        return original, None              # the artwork runs to the edge: leave it

    removed = bytearray(w * h)
    queue = deque()
    for x, y in border:
        p = px[x, y]
        if p[3] < 64 or _dist(p, med) <= BG_TOLERANCE:
            removed[y * w + x] = 1
            queue.append((x, y))
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not removed[ny * w + nx]:
                p = px[nx, ny]
                if p[3] < 64 or _dist(p, med) <= BG_TOLERANCE:
                    removed[ny * w + nx] = 1
                    queue.append((nx, ny))
    share = sum(removed) / (w * h)
    if share < 0.02 or share > 0.95:
        return original, None              # nothing to take off, or it would take everything

    # Background showing through small closed shapes (inside an O, an A, an R)
    # is not joined to the edge but is background all the same. A big enclosed
    # area of that colour (a white disc inside a ring) is the crest's own and stays.
    # Shrinking the picture leaves 1 to 3 pixel near-white flecks where two crest
    # colours meet (resampling overshoot); those are not holes and stay.
    small = SPECK_SHARE * w * h
    edge_removed = bytearray(removed)
    seen = bytearray(w * h)
    for y0 in range(h):
        for x0 in range(w):
            i0 = y0 * w + x0
            if removed[i0] or seen[i0] or _dist(px[x0, y0], med) > BG_TOLERANCE:
                continue
            blob, q = [], deque([(x0, y0)])
            seen[i0] = 1
            while q:
                x, y = q.popleft()
                blob.append(y * w + x)
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    j = ny * w + nx
                    if 0 <= nx < w and 0 <= ny < h and not seen[j] and not removed[j] \
                            and _dist(px[nx, ny], med) <= BG_TOLERANCE:
                        seen[j] = 1
                        q.append((nx, ny))
            if SPECK_MIN <= len(blob) <= small:
                for j in blob:
                    removed[j] = 1

    # The band of pixels the edge clean-up reaches: anti-aliasing runs two or
    # three pixels deep after the picture is shrunk, so matting only the first
    # ring left a pale outline round every letter. Three pixels in from the
    # background joined to the edge, one pixel round a cleared hole (a letter's
    # counter is small, and a wider band would eat the letter).
    def grown(mask, steps):
        m = bytearray(mask)
        for _ in range(steps):
            g = bytearray(m)
            for y in range(h):
                row = y * w
                for x in range(w):
                    if not m[row + x] and (
                            (x > 0 and m[row + x - 1]) or (x < w - 1 and m[row + x + 1])
                            or (y > 0 and m[row - w + x]) or (y < h - 1 and m[row + w + x])):
                        g[row + x] = 1
            m = g
        return m

    holes = bytearray(1 if (a and not b) else 0 for a, b in zip(removed, edge_removed))
    near = bytearray(1 if (a or b) else 0 for a, b in zip(grown(edge_removed, EDGE_BAND), grown(holes, 1)))

    out = im.copy()
    op = out.load()
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if removed[i]:
                op[x, y] = (0, 0, 0, 0)
                continue
            # The crest's edge pixels are part artwork, part background (anti-
            # aliasing). Work out how much of each is background and take that
            # share OUT of its colour, rather than fading the pixel: fading
            # thinned lettering and left a pale fringe round it.
            if near[i]:
                r, g, b, a = op[x, y]
                d = _dist((r, g, b), med)
                if d < EDGE_MATTE:
                    # A blend of the background and the crest colour beside it: the
                    # strongest colour within two pixels is that crest colour, and
                    # how far this pixel has moved toward it is how opaque it is.
                    best, best_d = None, 0
                    for yy in range(max(0, y - 2), min(h, y + 3)):
                        for xx in range(max(0, x - 2), min(w, x + 3)):
                            if removed[yy * w + xx]:
                                continue
                            q = px[xx, yy]
                            dq = _dist(q, med)
                            if dq > best_d:
                                best, best_d = q, dq
                    if best is None or best_d <= d:
                        continue
                    k = d / best_d
                    op[x, y] = (best[0], best[1], best[2], int(a * k))
    return original, _png(_trim(out))


def _edge_would_vanish(im) -> bool:
    """Would this cut-out crest lose its outline on a dark post? True when a
    good share of the crest within ``DARK_BAND`` pixels of its outline is dark:
    artwork drawn for a white page (dark lettering, a maroon or navy outline)
    that the white was carrying. A band, not the outermost ring, because thin
    lettering has no pure colour on its edge and would read as light."""
    a = im.getchannel("A")
    w, h = im.size
    ap, px = a.load(), im.load()
    # Distance in from the outside, by repeated rings (4-neighbour).
    inside = [[ap[x, y] >= 128 for x in range(w)] for y in range(h)]
    ring = [[False] * w for _ in range(h)]
    frontier = [(x, y) for y in range(h) for x in range(w) if inside[y][x] and any(
        not (0 <= nx < w and 0 <= ny < h) or not inside[ny][nx]
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))]
    for _ in range(DARK_BAND):
        nxt = []
        for x, y in frontier:
            if ring[y][x]:
                continue
            ring[y][x] = True
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < w and 0 <= ny < h and inside[ny][nx] and not ring[ny][nx]:
                    nxt.append((nx, ny))
        frontier = nxt
    band = dark = 0
    for y in range(h):
        for x in range(w):
            if ring[y][x]:
                band += 1
                if _lum(px[x, y][:3]) < DARK_EDGE_LUM:
                    dark += 1
    return band > 0 and dark / band >= DARK_EDGE_SHARE


def _lum(rgb) -> float:
    def ch(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def with_white_edge(png: bytes) -> bytes:
    """The cut-out crest on a white die-cut edge that follows its outline, like
    a sticker, so dark artwork still reads on a dark post. The gaps between
    letters close up, so a line of text sits on one white shape."""
    from PIL import Image, ImageFilter
    im = _open(png)
    w, h = im.size
    r = max(3, round(max(w, h) * 0.035))
    pad = r * 2
    canvas = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    canvas.paste(im, (pad, pad), im)
    alpha = canvas.getchannel("A")
    # Grow the outline by about `r`, rounded, with a soft rim.
    # A crisp rim, not a glow: grow, cut hard, then a hair of blur for a clean edge.
    grown = alpha.filter(ImageFilter.GaussianBlur(r)).point(lambda v: 255 if v > 20 else 0)
    grown = grown.filter(ImageFilter.GaussianBlur(0.8))
    white = Image.new("RGBA", canvas.size, (255, 255, 255, 0))
    white.putalpha(grown)
    white.alpha_composite(canvas)
    return _png(_trim(white))


def cut_styles(original_png: bytes) -> Optional[dict]:
    """Every cut-out of a kept crest: ``plain`` (background off), ``edge`` (on a
    white die-cut edge) and ``auto`` (whichever reads on a dark post). None when
    the picture has no plain background to take off."""
    made = clean_crest(original_png)
    if not made or not made[1]:
        return None
    plain = made[1]
    edge = with_white_edge(plain)
    return {"plain": plain, "edge": edge, "auto": edge if _edge_would_vanish(_open(plain)) else plain}


def original_png(data: bytes) -> Optional[bytes]:
    """The picture as we keep it (re-encoded, no bigger than ``EDGE``, trimmed),
    or None when the bytes are not an image. Every cut-out is made from this."""
    try:
        im = _open(data)
    except Exception:  # noqa: BLE001
        return None
    im.thumbnail((EDGE, EDGE))
    return _png(_trim(im))


def upload_png(data: bytes) -> Optional[bytes]:
    """A person's uploaded crest as a PNG no bigger than ``UPLOAD_EDGE``, trimmed.
    Re-encoded through Pillow, so only a raster we decoded ourselves is served."""
    try:
        im = _open(data)
    except Exception:  # noqa: BLE001
        return None
    im.thumbnail((UPLOAD_EDGE, UPLOAD_EDGE))
    return _png(_trim(im))


def crest_colours(png: bytes) -> tuple[Optional[str], Optional[str]]:
    """The crest's main colour and a second one at least 36 degrees round the
    wheel, as read: whites, greys, blacks and see-through pixels are skipped.
    ``(None, None)`` for a black and white crest."""
    try:
        im = _open(png)
    except Exception:  # noqa: BLE001
        return None, None
    im.thumbnail((64, 64))
    buckets: dict[int, list] = {}
    for r, g, b, a in im.getdata():
        if a < 160:
            continue
        hh, ss, vv = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if ss >= MIN_SAT and vv >= 0.18:
            buckets.setdefault(int(hh * 30) % 30, []).append((r, g, b, ss * vv))
    if sum(len(v) for v in buckets.values()) < 8:
        return None, None

    def weight(k):
        return sum(len(buckets.get((k + d) % 30, ())) for d in (-1, 0, 1))

    def average(k):
        members = [p for d in (-1, 0, 1) for p in buckets.get((k + d) % 30, ())]
        total = sum(m[3] for m in members) or 1.0
        return "#%02x%02x%02x" % tuple(int(round(sum(m[i] * m[3] for m in members) / total)) for i in range(3))

    best = max(buckets, key=weight)
    apart = [k for k in buckets if min((k - best) % 30, (best - k) % 30) >= 3]
    second = max(apart, key=weight) if apart else None
    c2 = average(second) if second is not None and weight(second) >= max(8, 0.12 * weight(best)) else None
    return average(best), c2


def _served(row) -> Optional[bytes]:
    if row["uploaded_png"]:
        return row["uploaded_png"]
    if row["use_cleaned"] and row["cleaned_png"]:
        return row["cleaned_png"]
    return row["original_png"]


def _version(row) -> str:
    data = _served(row) or b""
    return hashlib.sha1(data).hexdigest()[:10]


def crest_url(workspace_id, ca_org_id: str, version: Optional[str]) -> str:
    return f"{URL_PREFIX}/{workspace_id}/{ca_org_id}?v={version or '0'}"


_COLS = ("ca_org_id, name, src_url, original_png, cleaned_png, uploaded_png, use_cleaned, "
         "colour, colour2, colour_by_hand, version, uploaded_at, cut_style, clean_version")


async def _rows(db: AsyncSession, workspace_id, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    res = await db.execute(text(
        f"SELECT {_COLS} FROM association_crests "
        "WHERE workspace_id = CAST(:w AS uuid) AND ca_org_id = ANY(CAST(:ids AS text[]))"),
        {"w": str(workspace_id), "ids": ids})
    return {r["ca_org_id"]: dict(r) for r in res.mappings().all()}


async def _make(raw_url: str) -> Optional[dict]:
    data = await fetch_logo(raw_url)
    if not data:
        return None
    original = await asyncio.to_thread(original_png, data)
    if not original:
        return None
    styles = await asyncio.to_thread(cut_styles, original)
    cleaned = styles["auto"] if styles else None
    c1, c2 = await asyncio.to_thread(crest_colours, (styles or {}).get("plain") or original)
    return {"original_png": original, "cleaned_png": cleaned, "colour": c1, "colour2": c2}


async def _store(db: AsyncSession, workspace_id, ca_id: str, name: str, raw_url: str, made: dict) -> None:
    """Insert a new crest, or refresh the automatic copy of one whose Cricket
    Australia address changed. An upload, the original-or-cleaned choice and a
    hand-set colour are left as they are."""
    served = made["cleaned_png"] or made["original_png"]
    await db.execute(text("""
        INSERT INTO association_crests
            (workspace_id, ca_org_id, name, src_url, original_png, cleaned_png, colour, colour2, version, clean_version)
        VALUES (CAST(:w AS uuid), :ca, :name, :src, :o, :c, :c1, :c2, :v, :cv)
        ON CONFLICT (workspace_id, ca_org_id) DO UPDATE SET
            name = COALESCE(NULLIF(EXCLUDED.name, ''), association_crests.name),
            src_url = EXCLUDED.src_url,
            original_png = EXCLUDED.original_png,
            cleaned_png = EXCLUDED.cleaned_png,
            cut_style = 'auto',
            clean_version = EXCLUDED.clean_version,
            colour = CASE WHEN association_crests.colour_by_hand THEN association_crests.colour ELSE EXCLUDED.colour END,
            colour2 = CASE WHEN association_crests.colour_by_hand THEN association_crests.colour2 ELSE EXCLUDED.colour2 END,
            version = CASE WHEN association_crests.uploaded_png IS NOT NULL THEN association_crests.version
                           ELSE EXCLUDED.version END,
            updated_at = now()
    """), {"w": str(workspace_id), "ca": ca_id, "name": name or "", "src": raw_url,
           "o": made["original_png"], "c": made["cleaned_png"], "c1": made["colour"], "c2": made["colour2"],
           "v": hashlib.sha1(served).hexdigest()[:10], "cv": CLEAN_VERSION})


async def resolve_crests(
    db: AsyncSession, org, entries: list[tuple[Optional[str], Optional[str], Optional[str]]],
    fallback: Optional[list[Optional[str]]] = None,
) -> list[dict]:
    """One ``{logo, colour, colour2}`` per ``(ca_org_id, raw_url, name)``, in
    order. A club in the library prints its kept crest; a new one is fetched,
    cleaned and kept (bounded by ``MAX_NEW``); anything that cannot be made
    falls back to ``fallback[i]`` (the address the post used before) and then
    the raw Cricket Australia address. Never raises."""
    fallback = fallback or [None] * len(entries)
    out = [{"logo": fb or raw, "colour": None, "colour2": None}
           for (_, raw, _), fb in zip(entries, fallback)]
    workspace_id = getattr(org, "id", None)
    if workspace_id is None:
        return out
    ids = sorted({(ca or "").lower() for ca, _, _ in entries if ca})
    try:
        held = await _rows(db, workspace_id, ids)
        want: dict[str, tuple[str, str]] = {}
        for ca, raw, name in entries:
            key = (ca or "").lower()
            if not key or not raw or key in want:
                continue
            row = held.get(key)
            if row is None or (row["src_url"] != raw and not row["uploaded_png"]):
                want[key] = (raw, name or "")
        # Crests kept by an older clean-up are cleaned again from the original we
        # already hold (no fetch). The person's choice of style is kept.
        stale = [k for k, row in held.items()
                 if (row.get("clean_version") or 1) < CLEAN_VERSION and row["original_png"] and k not in want][:MAX_NEW]
        for key in stale:
            await _reclean(db, workspace_id, key, held[key])
        if stale:
            await db.commit()
            held = await _rows(db, workspace_id, ids)
        todo = list(want.items())[:MAX_NEW]
        if todo:
            gate = asyncio.Semaphore(FETCH_CONCURRENCY)

            async def one(item):
                async with gate:
                    return await _make(item[1][0])

            made = await asyncio.gather(*[one(it) for it in todo], return_exceptions=True)
            wrote = False
            for (key, (raw, name)), m in zip(todo, made):
                if isinstance(m, dict):
                    await _store(db, workspace_id, key, name, raw, m)
                    wrote = True
            if wrote:
                await db.commit()
                held = await _rows(db, workspace_id, ids)
    except Exception:  # noqa: BLE001 - a crest must never fail a pull
        logger.exception("crest library failed for workspace %s", workspace_id)
        try:
            await rollback_keeping(db, org)
        except Exception:  # noqa: BLE001
            pass
        return out
    for i, (ca, raw, _name) in enumerate(entries):
        row = held.get((ca or "").lower())
        if row and _served(row):
            out[i] = {"logo": crest_url(workspace_id, row["ca_org_id"], row["version"]),
                      "colour": row["colour"], "colour2": row["colour2"]}
    return out


async def _reclean(db: AsyncSession, workspace_id, ca_org_id: str, row: dict, style: Optional[str] = None) -> None:
    """Make the cut-out again from the kept original in ``style`` (the row's own
    when not given). Colours are read again unless set by hand; an upload is
    left as it is and still served."""
    style = style or row.get("cut_style") or "auto"
    styles = await asyncio.to_thread(cut_styles, row["original_png"])
    cleaned = styles.get(style if style in CUT_STYLES else "auto") if styles else None
    c1, c2 = await asyncio.to_thread(crest_colours, (styles or {}).get("plain") or row["original_png"])
    await db.execute(text("""
        UPDATE association_crests SET cleaned_png = :c, clean_version = :cv, cut_style = :st,
            colour = CASE WHEN colour_by_hand THEN colour ELSE :c1 END,
            colour2 = CASE WHEN colour_by_hand THEN colour2 ELSE :c2 END
        WHERE workspace_id = CAST(:w AS uuid) AND ca_org_id = :ca
    """), {"c": cleaned, "cv": CLEAN_VERSION, "st": style, "c1": c1, "c2": c2, "w": str(workspace_id), "ca": ca_org_id})
    await _refresh_version(db, workspace_id, ca_org_id)


async def crest_image(db: AsyncSession, workspace_id: str, ca_org_id: str, variant: str = "") -> Optional[bytes]:
    """The PNG a post draws for this crest, or one of its versions
    (``original``, ``cleaned``, ``uploaded``) for the library screen."""
    res = await db.execute(text(
        f"SELECT {_COLS} FROM association_crests WHERE workspace_id = CAST(:w AS uuid) AND ca_org_id = :ca"),
        {"w": workspace_id, "ca": (ca_org_id or "").lower()})
    row = res.mappings().first()
    if not row:
        return None
    if variant in ("original", "cleaned", "uploaded"):
        return row[f"{variant}_png"]
    return _served(row)


async def list_crests(db: AsyncSession, workspace_id) -> list[dict]:
    res = await db.execute(text(
        f"SELECT {_COLS} FROM association_crests WHERE workspace_id = CAST(:w AS uuid) ORDER BY lower(name), ca_org_id"),
        {"w": str(workspace_id)})
    out = []
    for r in res.mappings().all():
        base = f"{URL_PREFIX}/{workspace_id}/{r['ca_org_id']}"
        v = r["version"] or "0"
        out.append({
            "caOrgId": r["ca_org_id"],
            "name": r["name"] or "",
            "logo": f"{base}?v={v}",
            "original": f"{base}?variant=original&v={v}" if r["original_png"] else None,
            "cleaned": f"{base}?variant=cleaned&v={v}" if r["cleaned_png"] else None,
            "uploaded": f"{base}?variant=uploaded&v={v}" if r["uploaded_png"] else None,
            "useCleaned": bool(r["use_cleaned"]),
            "cutStyle": r["cut_style"] or "auto",
            "colour": r["colour"],
            "colour2": r["colour2"],
            "colourByHand": bool(r["colour_by_hand"]),
            "uploadedAt": r["uploaded_at"].isoformat() if r["uploaded_at"] else None,
        })
    return out


async def _refresh_version(db: AsyncSession, workspace_id, ca_org_id: str) -> None:
    res = await db.execute(text(
        f"SELECT {_COLS} FROM association_crests WHERE workspace_id = CAST(:w AS uuid) AND ca_org_id = :ca"),
        {"w": str(workspace_id), "ca": ca_org_id})
    row = res.mappings().first()
    if row:
        await db.execute(text(
            "UPDATE association_crests SET version = :v, updated_at = now() "
            "WHERE workspace_id = CAST(:w AS uuid) AND ca_org_id = :ca"),
            {"v": _version(row), "w": str(workspace_id), "ca": ca_org_id})


async def _exists(db: AsyncSession, workspace_id, ca_org_id: str) -> bool:
    res = await db.execute(text(
        "SELECT 1 FROM association_crests WHERE workspace_id = CAST(:w AS uuid) AND ca_org_id = :ca"),
        {"w": str(workspace_id), "ca": ca_org_id})
    return res.first() is not None


async def upload_crest(db: AsyncSession, workspace_id, ca_org_id: str, data: bytes, user_id=None) -> bool:
    """A person's own crest for this club. Its colours are read again unless
    the colour was set by hand. False when the club is not in the library or the
    bytes are not an image."""
    ca = (ca_org_id or "").lower()
    png = await asyncio.to_thread(upload_png, data)
    if not png or not await _exists(db, workspace_id, ca):
        return False
    c1, c2 = await asyncio.to_thread(crest_colours, png)
    await db.execute(text("""
        UPDATE association_crests SET uploaded_png = :p, uploaded_by = CAST(:u AS uuid), uploaded_at = now(),
            colour = CASE WHEN colour_by_hand THEN colour ELSE :c1 END,
            colour2 = CASE WHEN colour_by_hand THEN colour2 ELSE :c2 END
        WHERE workspace_id = CAST(:w AS uuid) AND ca_org_id = :ca
    """), {"p": png, "u": str(user_id) if user_id else None, "c1": c1, "c2": c2, "w": str(workspace_id), "ca": ca})
    await _refresh_version(db, workspace_id, ca)
    await db.commit()
    return True


async def update_crest(db: AsyncSession, workspace_id, ca_org_id: str, fields: dict) -> bool:
    """Apply the fields a person sent: ``use_cleaned`` (bool), ``colour``
    (a hex sets it by hand, null hands it back to the crest), ``drop_upload``
    (true goes back to the Cricket Australia crest). Absent keys are left alone."""
    ca = (ca_org_id or "").lower()
    if not await _exists(db, workspace_id, ca):
        return False
    w = str(workspace_id)
    if "use_cleaned" in fields and fields["use_cleaned"] is not None:
        await db.execute(text(
            "UPDATE association_crests SET use_cleaned = :v WHERE workspace_id = CAST(:w AS uuid) AND ca_org_id = :ca"),
            {"v": bool(fields["use_cleaned"]), "w": w, "ca": ca})
    if fields.get("cut_style") in CUT_STYLES:
        # Choosing a cut-out means using one.
        await db.execute(text(
            "UPDATE association_crests SET use_cleaned = TRUE WHERE workspace_id = CAST(:w AS uuid) AND ca_org_id = :ca"),
            {"w": w, "ca": ca})
        res = await db.execute(text(
            f"SELECT {_COLS} FROM association_crests WHERE workspace_id = CAST(:w AS uuid) AND ca_org_id = :ca"),
            {"w": w, "ca": ca})
        row = dict(res.mappings().first())
        if row["original_png"]:
            await _reclean(db, workspace_id, ca, row, fields["cut_style"])
    if fields.get("drop_upload"):
        await db.execute(text(
            "UPDATE association_crests SET uploaded_png = NULL, uploaded_by = NULL, uploaded_at = NULL "
            "WHERE workspace_id = CAST(:w AS uuid) AND ca_org_id = :ca"), {"w": w, "ca": ca})
    if "colour" in fields:
        colour = fields["colour"]
        if colour:
            await db.execute(text(
                "UPDATE association_crests SET colour = :c, colour_by_hand = TRUE "
                "WHERE workspace_id = CAST(:w AS uuid) AND ca_org_id = :ca"), {"c": colour, "w": w, "ca": ca})
        else:
            res = await db.execute(text(
                f"SELECT {_COLS} FROM association_crests WHERE workspace_id = CAST(:w AS uuid) AND ca_org_id = :ca"),
                {"w": w, "ca": ca})
            row = dict(res.mappings().first())
            row["colour_by_hand"] = False
            c1, c2 = await asyncio.to_thread(crest_colours, _served(row) or b"")
            await db.execute(text(
                "UPDATE association_crests SET colour = :c1, colour2 = :c2, colour_by_hand = FALSE "
                "WHERE workspace_id = CAST(:w AS uuid) AND ca_org_id = :ca"), {"c1": c1, "c2": c2, "w": w, "ca": ca})
    if fields.get("drop_upload") or "use_cleaned" in fields or "cut_style" in fields:
        # The picture shown changed: read its colours again unless set by hand.
        res = await db.execute(text(
            f"SELECT {_COLS} FROM association_crests WHERE workspace_id = CAST(:w AS uuid) AND ca_org_id = :ca"),
            {"w": w, "ca": ca})
        row = res.mappings().first()
        if row and not row["colour_by_hand"]:
            c1, c2 = await asyncio.to_thread(crest_colours, _served(row) or b"")
            await db.execute(text(
                "UPDATE association_crests SET colour = :c1, colour2 = :c2 "
                "WHERE workspace_id = CAST(:w AS uuid) AND ca_org_id = :ca"), {"c1": c1, "c2": c2, "w": w, "ca": ca})
    await _refresh_version(db, workspace_id, ca)
    await db.commit()
    return True
