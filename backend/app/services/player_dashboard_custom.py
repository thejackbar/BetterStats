"""A club's own Player Dashboard modules, and the order of the dashboard's cards.

A club can add cards of its own to the Player Dashboard, like a link page: a button to
the ticketing site for presentation night, the merch store, a registration form, a
notice, an event with a countdown, or an image banner (a poster) that may link
somewhere. Each one is its own card on the dashboard grid, and the club sets the order
of every card, its own and the built-in sections, in BetterStats > Player Dashboard.

Rules kept here:

* A link only ever opens ``http`` or ``https``. Anything else (``javascript:``, ``data:``)
  is refused when it is saved, and a bare ``club.com.au`` gets ``https://`` in front.
* What a player sees is decided on read (``is_live``): switched on, inside its dates,
  an event not yet past, an image banner with an image. Nothing is stored about it.
* The custom cards belong to the dashboard side of the link, so they follow
  ``player_dashboard.dashboard_live``.
* ``click_count`` is a tally of taps and nothing else: no player id is recorded.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, time
from typing import Any, Optional
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import MODULE_SELECT, org_has_module
from app.models.db import Organisation
from app.services import player_dashboard

KINDS = ("link", "text", "event", "image")
KIND_LABELS = {"link": "Link button", "text": "Announcement", "event": "Event", "image": "Image banner"}

TITLE_MAX = 80
BODY_MAX = 1000
BUTTON_MAX = 30
EMOJI_MAX = 8
LOCATION_MAX = 120
URL_MAX = 2000
MAX_PER_CLUB = 30

IMAGE_EXTS = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}
IMAGE_MAX_BYTES = 5 * 1024 * 1024

CUSTOM_PREFIX = "custom:"

# The built-in cards of the dashboard grid, in their standard order, and the modules each one holds.
# It mirrors GROUPS and ORDER in frontend/src/pages/PublicAvailability.jsx; keep the two in step.
SECTIONS: list[dict] = [
    {"id": "availability", "label": "Availability", "keys": []},
    {"id": "selection", "label": "Selection", "keys": ["squad", "selected", "training", "ladder"]},
    {"id": "cards", "label": "Player Cards", "keys": ["cards"]},
    {"id": "fantasy", "label": "Fantasy", "keys": ["fantasy"]},
    {"id": "stats", "label": "Stats", "keys": ["season"]},
    {"id": "voting", "label": "Voting", "keys": ["votes"]},
    {"id": "admin", "label": "Club admin", "keys": ["fees", "fines"]},
]
SECTION_IDS = [s["id"] for s in SECTIONS]


class Invalid(ValueError):
    """A value the club typed that cannot be saved; the message is shown to them as it is."""


# ── Cleaning what the club typed ────────────────────────────────────────────────

def _text(value: Any, limit: int, what: str) -> Optional[str]:
    if value is None:
        return None
    s = re.sub(r"[ \t]+", " ", str(value)).strip()
    if len(s) > limit:
        raise Invalid(f"{what} is too long ({limit} characters at most).")
    return s or None


def clean_url(value: Any) -> Optional[str]:
    """An ``http(s)`` address, or None for blank. A bare domain gets ``https://``; any
    other scheme is refused, so a card can never run script in the player's page."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if len(s) > URL_MAX:
        raise Invalid("That link is too long.")
    if re.search(r"\s", s):
        raise Invalid("A link cannot have spaces in it.")
    if "://" not in s and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", s):
        s = "https://" + s
    parsed = urlparse(s)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc or "." not in parsed.netloc:
        raise Invalid("Links must be a web address starting with https:// (for example https://tickets.club.com.au).")
    return s


def _date(value: Any, what: str) -> Optional[date]:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise Invalid(f"{what} is not a date.")


def _time(value: Any) -> Optional[time]:
    if value in (None, ""):
        return None
    if isinstance(value, time):
        return value
    try:
        return time.fromisoformat(str(value)[:8])
    except ValueError:
        raise Invalid("The start time is not a time.")


# Field name -> cleaner. Only the fields that are sent are cleaned and saved.
def clean_fields(sent: dict) -> dict:
    out: dict = {}
    for key, value in sent.items():
        if key == "kind":
            if value not in KINDS:
                raise Invalid("Pick what kind of module this is.")
            out[key] = value
        elif key == "title":
            out[key] = _text(value, TITLE_MAX, "The title")
        elif key == "body":
            body = None if value is None else str(value).strip()
            if body and len(body) > BODY_MAX:
                raise Invalid(f"The text is too long ({BODY_MAX} characters at most).")
            out[key] = body or None
        elif key == "url":
            out[key] = clean_url(value)
        elif key == "button_label":
            out[key] = _text(value, BUTTON_MAX, "The button label")
        elif key == "emoji":
            out[key] = _text(value, EMOJI_MAX, "The icon")
        elif key == "location":
            out[key] = _text(value, LOCATION_MAX, "The location")
        elif key == "event_date":
            out[key] = _date(value, "The event date")
        elif key == "event_time":
            out[key] = _time(value)
        elif key == "show_from":
            out[key] = _date(value, "Show from")
        elif key == "show_until":
            out[key] = _date(value, "Show until")
        elif key == "enabled":
            out[key] = bool(value)
    return out


def check_complete(row: dict) -> None:
    """Refuse a module that could never be shown for want of what its kind needs. An image
    banner is allowed without its image, because the image is uploaded after it is made."""
    if not row.get("title"):
        raise Invalid("Give it a title.")
    kind = row.get("kind")
    if kind == "link" and not row.get("url"):
        raise Invalid("A link button needs the address it opens.")
    if kind == "text" and not row.get("body"):
        raise Invalid("An announcement needs some text.")
    if kind == "event" and not row.get("event_date"):
        raise Invalid("An event needs its date.")
    if row.get("show_from") and row.get("show_until") and row["show_until"] < row["show_from"]:
        raise Invalid("Show until is before Show from.")


# ── What a player sees ──────────────────────────────────────────────────────────

def ends_on(row: dict) -> Optional[date]:
    """The last day the module shows: Show until, or for an event with none, its own date."""
    if row.get("show_until"):
        return row["show_until"]
    if row.get("kind") == "event":
        return row.get("event_date")
    return None


def hidden_reason(row: dict, today: date) -> Optional[str]:
    """Why players cannot see this module today, or None when they can."""
    if not row.get("enabled"):
        return "Switched off."
    if row.get("kind") == "image" and not row.get("image_version"):
        return "Add an image first."
    if row.get("show_from") and today < row["show_from"]:
        return f"Shows from {row['show_from'].strftime('%-d %b %Y')}."
    last = ends_on(row)
    if last and today > last:
        return "The event has been." if (row.get("kind") == "event" and not row.get("show_until")) else "Its dates have passed."
    return None


def is_live(row: dict, today: date) -> bool:
    return hidden_reason(row, today) is None


def image_url(row: dict) -> Optional[str]:
    if not row.get("image_version"):
        return None
    return f"/api/images/player-dashboard-modules/{row['id']}?v={row['image_version']}"


def _iso(v) -> Optional[str]:
    return v.isoformat() if v is not None else None


def serialise_public(row: dict) -> dict:
    """What the player's page gets: the card's content and nothing about counts or dates."""
    return {
        "id": str(row["id"]),
        "kind": row["kind"],
        "title": row["title"],
        "body": row.get("body"),
        "url": row.get("url"),
        "button_label": row.get("button_label"),
        "emoji": row.get("emoji"),
        "location": row.get("location"),
        "event_date": _iso(row.get("event_date")),
        "event_time": row["event_time"].strftime("%H:%M") if row.get("event_time") else None,
        "image_url": image_url(row),
    }


def serialise_admin(row: dict, today: date) -> dict:
    return {
        **serialise_public(row),
        "kind_label": KIND_LABELS.get(row["kind"], row["kind"]),
        "enabled": bool(row.get("enabled")),
        "show_from": _iso(row.get("show_from")),
        "show_until": _iso(row.get("show_until")),
        "click_count": int(row.get("click_count") or 0),
        "last_clicked_at": _iso(row.get("last_clicked_at")),
        "live": is_live(row, today),
        "hidden_reason": hidden_reason(row, today),
        "created_at": _iso(row.get("created_at")),
    }


# ── Storage ─────────────────────────────────────────────────────────────────────

_COLS = ("id, organisation_id, kind, title, body, url, button_label, emoji, event_date, event_time, location, "
         "show_from, show_until, enabled, image_mime, image_version, click_count, last_clicked_at, created_at")


async def list_rows(db: AsyncSession, club_id) -> list[dict]:
    rows = (await db.execute(text(
        f"SELECT {_COLS} FROM player_dashboard_custom_modules WHERE organisation_id = CAST(:o AS uuid) ORDER BY created_at, id"
    ), {"o": str(club_id)})).mappings().all()
    return [dict(r) for r in rows]


async def get_row(db: AsyncSession, club_id, module_id: str) -> Optional[dict]:
    try:
        mid = uuid.UUID(str(module_id))
    except ValueError:
        return None
    row = (await db.execute(text(
        f"SELECT {_COLS} FROM player_dashboard_custom_modules WHERE id = CAST(:id AS uuid) AND organisation_id = CAST(:o AS uuid)"
    ), {"id": str(mid), "o": str(club_id)})).mappings().first()
    return dict(row) if row else None


_WRITABLE = ("kind", "title", "body", "url", "button_label", "emoji", "event_date", "event_time", "location",
             "show_from", "show_until", "enabled")


async def create(db: AsyncSession, club: Organisation, fields: dict, by: Optional[str]) -> dict:
    count = (await db.execute(text(
        "SELECT count(*) FROM player_dashboard_custom_modules WHERE organisation_id = CAST(:o AS uuid)"
    ), {"o": str(club.id)})).scalar() or 0
    if count >= MAX_PER_CLUB:
        raise Invalid(f"A club can have {MAX_PER_CLUB} of its own modules. Remove one you no longer use first.")
    row = {k: None for k in _WRITABLE}
    row.update({"enabled": True, "kind": "link"})
    row.update(clean_fields(fields))
    check_complete(row)
    new_id = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO player_dashboard_custom_modules (id, organisation_id, created_by, "
        + ", ".join(_WRITABLE) + ") VALUES (CAST(:id AS uuid), CAST(:o AS uuid), :by, "
        + ", ".join(f":{k}" for k in _WRITABLE) + ")"
    ), {**row, "id": str(new_id), "o": str(club.id), "by": by})
    # A new card goes at the end of a layout the club has already arranged.
    if isinstance(club.player_dashboard_layout, list):
        club.player_dashboard_layout = [*club.player_dashboard_layout, f"{CUSTOM_PREFIX}{new_id}"]
    return await get_row(db, club.id, str(new_id))


async def update(db: AsyncSession, club: Organisation, module_id: str, sent: dict) -> Optional[dict]:
    """Change only the fields that were sent (an absent key leaves its field alone)."""
    current = await get_row(db, club.id, module_id)
    if current is None:
        return None
    changes = clean_fields({k: v for k, v in sent.items() if k in _WRITABLE})
    merged = {**current, **changes}
    check_complete(merged)
    if changes:
        sets = ", ".join(f"{k} = :{k}" for k in changes)
        await db.execute(text(
            f"UPDATE player_dashboard_custom_modules SET {sets}, updated_at = now() "
            "WHERE id = CAST(:id AS uuid) AND organisation_id = CAST(:o AS uuid)"
        ), {**changes, "id": str(current["id"]), "o": str(club.id)})
    return await get_row(db, club.id, module_id)


async def delete(db: AsyncSession, club: Organisation, module_id: str) -> bool:
    """The club removing one of its own cards (it asked, and confirmed). Also takes it out
    of the layout so the order list does not keep a card that is gone."""
    current = await get_row(db, club.id, module_id)
    if current is None:
        return False
    await db.execute(text(
        "DELETE FROM player_dashboard_custom_modules WHERE id = CAST(:id AS uuid) AND organisation_id = CAST(:o AS uuid)"
    ), {"id": str(current["id"]), "o": str(club.id)})
    if isinstance(club.player_dashboard_layout, list):
        gone = f"{CUSTOM_PREFIX}{current['id']}"
        club.player_dashboard_layout = [x for x in club.player_dashboard_layout if x != gone]
    return True


async def set_image(db: AsyncSession, club: Organisation, module_id: str, data: Optional[bytes], mime: Optional[str]) -> Optional[dict]:
    current = await get_row(db, club.id, module_id)
    if current is None:
        return None
    await db.execute(text(
        "UPDATE player_dashboard_custom_modules SET image_data = :d, image_mime = :m, image_version = :v, updated_at = now() "
        "WHERE id = CAST(:id AS uuid) AND organisation_id = CAST(:o AS uuid)"
    ), {"d": data, "m": mime if data else None, "v": uuid.uuid4().hex[:10] if data else None,
        "id": str(current["id"]), "o": str(club.id)})
    return await get_row(db, club.id, module_id)


async def record_click(db: AsyncSession, club_id, module_id: str) -> bool:
    """Add one to a module's tap count. Only for a card of this club's that has a link."""
    try:
        mid = uuid.UUID(str(module_id))
    except ValueError:
        return False
    res = await db.execute(text(
        "UPDATE player_dashboard_custom_modules SET click_count = click_count + 1, last_clicked_at = now() "
        "WHERE id = CAST(:id AS uuid) AND organisation_id = CAST(:o AS uuid) AND url IS NOT NULL"
    ), {"id": str(mid), "o": str(club_id)})
    return (res.rowcount or 0) > 0


# ── The grid's order ────────────────────────────────────────────────────────────

def _valid_ids(custom_ids: list[str]) -> set[str]:
    return set(SECTION_IDS) | {f"{CUSTOM_PREFIX}{c}" for c in custom_ids}


def normalise_layout(ids, custom_ids: list[str]) -> list[str]:
    """Known card ids only, once each, in the order given."""
    valid = _valid_ids(custom_ids)
    out: list[str] = []
    for i in ids or []:
        if isinstance(i, str) and i in valid and i not in out:
            out.append(i)
    return out


def layout_for(club: Organisation, custom_ids: list[str]) -> list[str]:
    """Every card id in the club's order. A card missing from the saved order (a built-in
    section added later, or a list saved before a card existed) goes after the rest, the
    built-in ones in their standard order, then the club's own by when they were made."""
    saved = club.player_dashboard_layout if isinstance(club.player_dashboard_layout, list) else []
    order = normalise_layout(saved, custom_ids)
    for sid in SECTION_IDS:
        if sid not in order:
            order.append(sid)
    for cid in custom_ids:
        key = f"{CUSTOM_PREFIX}{cid}"
        if key not in order:
            order.append(key)
    return order


def section_note(club: Organisation, section: dict) -> Optional[str]:
    """Why a built-in card is not on the dashboard, for the order list. None when it shows
    (a section can still drop out for one player who has nothing in it)."""
    if section["id"] == "availability":
        if not org_has_module(club, MODULE_SELECT):
            return "Needs BetterSelect."
        return None if player_dashboard.availability_live(club) else "The availability link is off in BetterSelect."
    served = player_dashboard.served_modules(club)
    if not any(k in served for k in section["keys"]):
        return "Nothing ticked under Player dashboard below is showing in it."
    return None


def admin_layout(club: Organisation, rows: list[dict], today: date) -> list[dict]:
    """The order list the settings screen draws: every card, built-in and the club's own,
    with whether players see it."""
    by_custom = {str(r["id"]): r for r in rows}
    by_section = {s["id"]: s for s in SECTIONS}
    out = []
    for cid in layout_for(club, list(by_custom)):
        if cid.startswith(CUSTOM_PREFIX):
            r = by_custom[cid[len(CUSTOM_PREFIX):]]
            reason = hidden_reason(r, today)
            out.append({"id": cid, "type": "custom", "label": r["title"], "kind": r["kind"],
                        "kind_label": KIND_LABELS.get(r["kind"]), "emoji": r.get("emoji"),
                        "shown": reason is None, "note": reason})
        else:
            s = by_section[cid]
            note = section_note(club, s)
            out.append({"id": cid, "type": "builtin", "label": s["label"], "shown": note is None, "note": note})
    return out


async def for_player(db: AsyncSession, club: Organisation, today: date) -> tuple[list[dict], list[str]]:
    """``(custom modules a player sees today, the grid's order)``. Nothing when the dashboard
    side of the link is off: the club's own cards belong to it."""
    rows = await list_rows(db, club.id)
    layout = layout_for(club, [str(r["id"]) for r in rows])
    if not player_dashboard.dashboard_live(club):
        return [], [x for x in layout if not x.startswith(CUSTOM_PREFIX)]
    live = [r for r in rows if is_live(r, today)]
    live_ids = {f"{CUSTOM_PREFIX}{r['id']}" for r in live}
    return [serialise_public(r) for r in live], [x for x in layout if not x.startswith(CUSTOM_PREFIX) or x in live_ids]


def today_for(local_now: Optional[datetime]) -> date:
    return local_now.date() if local_now else date.today()
