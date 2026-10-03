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

# (url, bytes, mime) groups. Carried as a unit, and only when the keeper has no
# picture of that kind at all.
PHOTO_GROUPS: tuple[tuple[str, str, str], ...] = (
    ("photo_url", "photo_data", "photo_mime"),
    ("hero_photo_url", "hero_photo_data", "hero_photo_mime"),
)

# Single columns, filled when the keeper's is empty.
FIELDS: tuple[str, ...] = (
    "gender", "player_role", "is_overseas", "overseas_country",
    "batting_hand", "bowling_action", "bowling_type", "is_opening_batsman",
    "squad_team_id", "email", "phone", "date_of_birth", "shirt_number",
    "is_financial_override", "trained_override", "skill_positions",
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
        keep_has = any(not _empty(getattr(keep, c, None)) for c in group)
        remove_has = any(not _empty(getattr(remove, c, None)) for c in group)
        if remove_has and not keep_has:
            for c in group:
                setattr(keep, c, getattr(remove, c, None))
            filled.append(group[0])

    for c in FIELDS:
        if c in skip:
            continue
        if _empty(getattr(keep, c, None)) and not _empty(getattr(remove, c, None)):
            setattr(keep, c, getattr(remove, c))
            filled.append(c)

    return filled
