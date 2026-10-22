"""The profile a merged-away player carries: photos, contact details, squad.

`admin._merge_players_core` moved a player's cricket and then deleted the row,
and the row is where everything a club typed *about the person* lives: the
headshot and action shot, email and phone, date of birth, shirt number, squad,
batting and bowling style. None of it was copied, so merging a freshly added
roster record (which has the photo and the details) into the synced one (which
has the games) kept the games and threw the rest away.

The keeper's own value always wins. A field is filled only where the keeper has
nothing, so a merge can add to a profile and never overwrite one. A photo and
its bytes and mime type travel as one: half of one is not a picture.
"""
from __future__ import annotations

import re
import uuid

# (url, bytes, mime) groups. Carried as a unit, and only when the keeper has no
# picture of that kind at all.
PHOTO_GROUPS: tuple[tuple[str, str, str], ...] = (
    ("photo_url", "photo_data", "photo_mime"),
    ("hero_photo_url", "hero_photo_data", "hero_photo_mime"),
)

# The route each photo URL column is served from (routers/images.py). The URL
# names the player's own row, so it cannot be copied to another player: the
# bytes would move and the address would still point at the row being deleted,
# which serves a 404 and reads on screen as a wiped photo.
PHOTO_ROUTES: dict[str, str] = {"photo_url": "photo", "hero_photo_url": "hero-photo"}

_IMAGE_URL = re.compile(r"^/api/images/players/([0-9a-fA-F-]{36})/(photo|hero-photo)(\?|$)")


def player_image_url(player_id, url_col: str) -> str:
    """The address a player's own stored photo is served from, with a fresh cache buster."""
    return f"/api/images/players/{player_id}/{PHOTO_ROUTES[url_col]}?v={uuid.uuid4().hex[:8]}"


def image_url_owner(url) -> str | None:
    """The player id inside one of our own image addresses, or None for anything else
    (a legacy /uploads file, an outside address, blank)."""
    m = _IMAGE_URL.match(url or "")
    return m.group(1).lower() if m else None


def _has_picture(row, group) -> bool:
    """Bytes are a picture. So is an address that is not one of our own image routes
    (a legacy file on disk). One of our own routes with no bytes behind it is a
    dead link, not a picture, and must not stop a real one being carried in."""
    url_col, data_col, _ = group
    if not _empty(getattr(row, data_col, None)):
        return True
    url = getattr(row, url_col, None)
    return not _empty(url) and image_url_owner(url) is None


# Single columns, filled when the keeper's is empty.
FIELDS: tuple[str, ...] = (
    "gender", "player_role", "is_overseas", "overseas_country",
    "batting_hand", "bowling_action", "bowling_type", "is_opening_batsman",
    "squad_team_id", "email", "phone", "date_of_birth", "shirt_number",
    "address_line1", "suburb", "state", "postcode", "emergency_contact_name", "emergency_contact_phone",
    "is_financial_override", "trained_override", "skill_positions", "dormancy_cleared_on",
)


def _empty(value) -> bool:
    """None, blank text, an empty list or empty bytes. False and 0 are answers."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, bytes, bytearray)):
        return len(value) == 0
    return False


def carry_profile(keep, remove, skip: tuple[str, ...] = ()) -> list[str]:
    """Copy what `remove` holds onto `keep` where `keep` has nothing.

    Works on the loaded ORM rows, before the removed one is deleted. Returns the
    names of the columns that were filled, for the audit entry. `skip` names
    columns to leave alone (the squad, when the removed player's belongs to
    another club).
    """
    filled: list[str] = []

    for group in PHOTO_GROUPS:
        if _has_picture(remove, group) and not _has_picture(keep, group):
            for c in group:
                setattr(keep, c, getattr(remove, c, None))
            # Bytes travel; the address must be rebuilt for the keeper's own id.
            if not _empty(getattr(keep, group[1], None)):
                setattr(keep, group[0], player_image_url(keep.id, group[0]))
            filled.append(group[0])

    for c in FIELDS:
        if c in skip:
            continue
        if _empty(getattr(keep, c, None)) and not _empty(getattr(remove, c, None)):
            setattr(keep, c, getattr(remove, c))
            filled.append(c)

    return filled
