"""Player Cards: a club's own designs for its packs.

A design belongs to a TARGET: `default` (any pack without a design of its own), a pack source (`weekly`, `century`, ...) or one
scheduled event (`event:<id>`, so a Test match can have its own look). A pack takes the most specific design that exists:
its event, then its source, then `default`, then the built-in look. Nothing here touches what is in a pack.

What a club can set: a background image and a centre image, three colours (the foil, its shade and the text), how dark the
background is laid down, whether the pack's name and the club logo are drawn, where the centre image sits and how big, and a
name of its own for that kind of pack. Colours are checked to be `#rrggbb` and the rest to be one of a few words, so nothing a
club types can reach the page as style.

Images are decoded, shrunk and re-encoded here (PNG when they have transparency, JPEG when they do not). That bounds the size,
drops anything hidden in the file and strips location data from phone photos. SVG is refused: served from this domain it
could run script. They live in Postgres, like every other club image, and are served by `routers/images.py`.
"""
from __future__ import annotations

import re
import time
import uuid
from io import BytesIO
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import player_card_pack_kinds as kinds

DEFAULT_TARGET = "default"
KINDS_OF_IMAGE = ("bg", "art")
MAX_UPLOAD_BYTES = 6 * 1024 * 1024
MAX_SIDE = {"bg": 1200, "art": 900}       # the longest side an image is kept at
ALLOWED_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp", "GIF": "image/png"}
POSITIONS = ("top", "center", "bottom")
SIZES = ("s", "m", "l")
MAX_TITLE = 40
MAX_LINE = 36
MAX_PIXELS = 40_000_000                    # refuse a decompression bomb before decoding it
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_STYLE_KEYS = ("title", "line", "color_a", "color_b", "color_on", "overlay", "show_name", "show_logo", "art_position", "art_size")

COLUMNS = ("id, target, title, line, color_a, color_b, color_on, overlay, show_name, show_logo, art_position, art_size, "
           "bg_rev, art_rev, bg_mime IS NOT NULL AS has_bg, art_mime IS NOT NULL AS has_art")


class DesignError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def event_target(event_id) -> str:
    return f"event:{event_id}"


def gift_target(gift_id) -> str:
    """A pack an admin made by hand can have a look of its own, made while creating it."""
    return f"gift:{gift_id}"


def image_url(design_id, kind: str, rev) -> str:
    return f"/api/images/card-packs/{design_id}/{kind}?v={int(rev or 0)}"


def row_dict(r) -> dict:
    """A design as the page uses it. Image URLs only when there is an image."""
    return {
        "id": str(r["id"]), "target": r["target"], "title": r["title"], "line": r["line"],
        "a": r["color_a"], "b": r["color_b"], "on": r["color_on"],
        "overlay": float(r["overlay"] if r["overlay"] is not None else 0.25),
        "show_name": r["show_name"] is not False, "show_logo": r["show_logo"] is not False,
        "art_position": r["art_position"] or "center", "art_size": r["art_size"] or "m",
        "background_url": image_url(r["id"], "bg", r["bg_rev"]) if r["has_bg"] else None,
        "art_url": image_url(r["id"], "art", r["art_rev"]) if r["has_art"] else None,
    }


async def load_all(db: AsyncSession, org_id) -> dict[str, dict]:
    """Every design the club has, by target. The image bytes are not read."""
    rows = (await db.execute(text(
        f"SELECT {COLUMNS} FROM club_card_pack_designs WHERE organisation_id = CAST(:o AS UUID)"
    ), {"o": str(org_id)})).mappings().all()
    return {r["target"]: row_dict(r) for r in rows}


def resolve(designs: dict[str, dict], source: str, event_id: Optional[str] = None, gift_id: Optional[str] = None) -> Optional[dict]:
    """The design a pack uses: its own event's or gift's, then its source's, then the club's default."""
    if event_id and event_target(event_id) in designs:
        return designs[event_target(event_id)]
    if gift_id and gift_target(gift_id) in designs:
        return designs[gift_target(gift_id)]
    return designs.get(source) or designs.get(DEFAULT_TARGET)


def gift_id_of(source: str, ref_key: str) -> Optional[str]:
    """The id of the gift an admin-made pack came from (its ref is `<gift id>:<n>`)."""
    if source != "custom" or not ref_key:
        return None
    try:
        return str(uuid.UUID(str(ref_key).split(":", 1)[0]))
    except ValueError:
        return None


def event_id_of(source: str, ref_key: str) -> Optional[str]:
    """A scheduled event's id from the ref its pack was granted under (`<id>:<date>` one a day, `<id>` for the run)."""
    if source != "event" or not ref_key:
        return None
    head = str(ref_key).split(":", 1)[0]
    try:
        return str(uuid.UUID(head))
    except ValueError:
        return None


async def targets(db: AsyncSession, org_id) -> list[dict]:
    """What a club can design: all packs, each kind of pack, and each scheduled event."""
    out = [{"key": DEFAULT_TARGET, "label": "Every pack", "group": "All"}]
    groups = (("Everyday", ("starter", "weekly", "runs", "wickets", "dismissals", "duck")),
              ("For what you do", ("century", "five_for", "hat_trick", "fifty", "milestone")),
              ("On the day", tuple(kinds.DAY_SOURCES)),
              ("From the club", ("custom", "reward")))
    for group, sources in groups:
        for s in sources:
            out.append({"key": s, "label": kinds.KINDS[s].label, "group": group})
    events = (await db.execute(text(
        "SELECT id::text, title FROM club_card_event_packs WHERE organisation_id = CAST(:o AS UUID) AND ends_on >= CURRENT_DATE - 30 "
        "ORDER BY starts_on, created_at"), {"o": str(org_id)})).fetchall()
    out += [{"key": event_target(i), "label": t, "group": "Scheduled"} for i, t in events]
    gifts = (await db.execute(text(
        "SELECT id::text, title FROM club_card_pack_gifts WHERE organisation_id = CAST(:o AS UUID) ORDER BY created_at DESC LIMIT 12"),
        {"o": str(org_id)})).fetchall()
    out += [{"key": gift_target(i), "label": t, "group": "From the club"} for i, t in gifts]
    return out


async def check_target(db: AsyncSession, org_id, target: str) -> str:
    """The target if this club can design it, else a 404."""
    if target == DEFAULT_TARGET or target in kinds.KINDS:
        return target
    if target.startswith("event:"):
        try:
            ev = str(uuid.UUID(target.split(":", 1)[1]))
        except ValueError:
            raise DesignError("Not found", 404)
        found = (await db.execute(text(
            "SELECT 1 FROM club_card_event_packs WHERE id = CAST(:i AS UUID) AND organisation_id = CAST(:o AS UUID)"),
            {"i": ev, "o": str(org_id)})).first()
        if found:
            return event_target(ev)
    if target.startswith("gift:"):
        try:
            gid = str(uuid.UUID(target.split(":", 1)[1]))
        except ValueError:
            raise DesignError("Not found", 404)
        found = (await db.execute(text(
            "SELECT 1 FROM club_card_pack_gifts WHERE id = CAST(:i AS UUID) AND organisation_id = CAST(:o AS UUID)"),
            {"i": gid, "o": str(org_id)})).first()
        if found:
            return gift_target(gid)
    raise DesignError("Not found", 404)


def clean_style(patch: dict) -> dict:
    """The keys that were sent, checked. An explicit null clears a colour or the title; an absent key is not here."""
    out: dict[str, Any] = {}
    for k in _STYLE_KEYS:
        if k not in patch:
            continue
        v = patch[k]
        if k in ("color_a", "color_b", "color_on"):
            if v is not None and not (isinstance(v, str) and _HEX.match(v)):
                raise DesignError("Colours are six digit hex codes, like #b91c1c.")
            out[k] = v.lower() if v else None
        elif k == "title":
            t = " ".join(str(v or "").split())[:MAX_TITLE]
            out[k] = t or None
        elif k == "line":
            t = " ".join(str(v or "").split())[:MAX_LINE]
            out[k] = t or None
        elif k == "overlay":
            try:
                f = float(v)
            except (TypeError, ValueError):
                raise DesignError("How dark the background is must be a number from 0 to 0.8.")
            if not 0 <= f <= 0.8:
                raise DesignError("How dark the background is must be a number from 0 to 0.8.")
            out[k] = round(f, 2)
        elif k in ("show_name", "show_logo"):
            if v is None:
                continue
            out[k] = bool(v)
        elif k == "art_position":
            if v not in POSITIONS:
                raise DesignError("The centre image sits at the top, centre or bottom.")
            out[k] = v
        elif k == "art_size":
            if v not in SIZES:
                raise DesignError("The centre image is small, medium or large.")
            out[k] = v
    return out


def process_image(raw: bytes, kind: str) -> tuple[bytes, str]:
    """Decode, shrink and re-encode an upload. Raises DesignError for anything that is not a picture we accept."""
    from PIL import Image, ImageOps

    if not raw:
        raise DesignError("That file is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise DesignError("Pick an image under 6 MB.", 413)
    try:
        with Image.open(BytesIO(raw)) as probe:
            fmt = probe.format
            if fmt not in ALLOWED_FORMATS:
                raise DesignError("Use a PNG, JPEG, WebP or GIF picture.")
            if probe.width * probe.height > MAX_PIXELS:
                raise DesignError("That picture is too large. Shrink it and try again.")
            im = ImageOps.exif_transpose(probe)
            im.load()
    except DesignError:
        raise
    except Exception:
        raise DesignError("That file could not be read as a picture.")
    side = MAX_SIDE[kind]
    if max(im.size) > side:
        im.thumbnail((side, side), Image.LANCZOS)
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    out = BytesIO()
    if has_alpha:
        im.convert("RGBA").save(out, format="PNG", optimize=True)
        return out.getvalue(), "image/png"
    im.convert("RGB").save(out, format="JPEG", quality=86, optimize=True, progressive=True)
    return out.getvalue(), "image/jpeg"


async def _ensure_row(db: AsyncSession, org_id, target: str) -> None:
    await db.execute(text(
        "INSERT INTO club_card_pack_designs (organisation_id, target) VALUES (CAST(:o AS UUID), :t) "
        "ON CONFLICT (organisation_id, target) DO NOTHING"), {"o": str(org_id), "t": target})


async def get_one(db: AsyncSession, org_id, target: str) -> Optional[dict]:
    r = (await db.execute(text(
        f"SELECT {COLUMNS} FROM club_card_pack_designs WHERE organisation_id = CAST(:o AS UUID) AND target = :t"),
        {"o": str(org_id), "t": target})).mappings().first()
    return row_dict(r) if r else None


async def save_style(db: AsyncSession, org_id, target: str, patch: dict) -> dict:
    """Apply only the style keys that were sent."""
    target = await check_target(db, org_id, target)
    style = clean_style(patch)
    await _ensure_row(db, org_id, target)
    if style:
        sets = ", ".join(f"{k} = :{k}" for k in style) + ", updated_at = NOW()"
        await db.execute(text(
            f"UPDATE club_card_pack_designs SET {sets} WHERE organisation_id = CAST(:o AS UUID) AND target = :t"),
            {**style, "o": str(org_id), "t": target})
    return await get_one(db, org_id, target)


async def set_image(db: AsyncSession, org_id, target: str, kind: str, raw: bytes) -> dict:
    if kind not in KINDS_OF_IMAGE:
        raise DesignError("Not found", 404)
    target = await check_target(db, org_id, target)
    data, mime = process_image(raw, kind)
    return await put_image(db, org_id, target, kind, data, mime)


async def put_image(db: AsyncSession, org_id, target: str, kind: str, data: bytes, mime: str) -> dict:
    """Store a picture that `process_image` has already checked. The target has been checked by the caller."""
    await _ensure_row(db, org_id, target)
    await db.execute(text(
        f"UPDATE club_card_pack_designs SET {kind}_data = :d, {kind}_mime = :m, {kind}_rev = :v, updated_at = NOW() "
        "WHERE organisation_id = CAST(:o AS UUID) AND target = :t"),
        {"d": data, "m": mime, "v": int(time.time() * 1000), "o": str(org_id), "t": target})
    return await get_one(db, org_id, target)


async def clear_image(db: AsyncSession, org_id, target: str, kind: str) -> Optional[dict]:
    if kind not in KINDS_OF_IMAGE:
        raise DesignError("Not found", 404)
    target = await check_target(db, org_id, target)
    await db.execute(text(
        f"UPDATE club_card_pack_designs SET {kind}_data = NULL, {kind}_mime = NULL, {kind}_rev = NULL, updated_at = NOW() "
        "WHERE organisation_id = CAST(:o AS UUID) AND target = :t"), {"o": str(org_id), "t": target})
    return await get_one(db, org_id, target)


async def reset(db: AsyncSession, org_id, target: str) -> bool:
    """Back to the built-in look for this target. A design is a club's own artwork, not something a pack depends on."""
    target = await check_target(db, org_id, target)
    res = await db.execute(text(
        "DELETE FROM club_card_pack_designs WHERE organisation_id = CAST(:o AS UUID) AND target = :t"),
        {"o": str(org_id), "t": target})
    return bool(res.rowcount)


async def drop_event(db: AsyncSession, org_id, event_id) -> None:
    """A removed scheduled event takes its design with it (nothing else could ever use it)."""
    await db.execute(text(
        "DELETE FROM club_card_pack_designs WHERE organisation_id = CAST(:o AS UUID) AND target = :t"),
        {"o": str(org_id), "t": event_target(event_id)})


async def image_bytes(db: AsyncSession, design_id: str, kind: str) -> Optional[tuple[bytes, str]]:
    if kind not in KINDS_OF_IMAGE:
        return None
    r = (await db.execute(text(
        f"SELECT {kind}_data, {kind}_mime FROM club_card_pack_designs WHERE id = CAST(:i AS UUID)"), {"i": design_id})).first()
    return (bytes(r[0]), r[1]) if r and r[0] else None
