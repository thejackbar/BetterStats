"""A club's own names for its public sections (migration 319).

A club sponsored by someone who wants their name on a section (a Fantasy game
called "Froth Fantasy Cricket", a Leaderboard presented by a bank) renames that
section here, and optionally links a sponsor so the sponsor's logo shows on the
page as "Presented by".

Stored: only what the club set, in ``organisations.section_names``, as
{key: {"name": str | None, "sponsor_id": str | None}}. Derived on read: the
sponsor's logo and link come live from ``org_sponsors``, so a deleted sponsor
simply stops being drawn. Unknown keys are ignored on read and refused on write.

The standard name of a section is NOT stored; the screens keep it as their
fallback, and ``SECTIONS`` below only carries it so the admin screen can show
what the section is called today.
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Iterable, Optional

# key -> (standard name, where it shows)
SECTIONS: dict[str, tuple[str, str]] = {
    "leaderboard": ("Leaderboard", "Stats menu and the leaderboard page"),
    "records": ("Records", "Stats menu and the records page"),
    "statlab": ("StatLab", "Stats menu and the StatLab page"),
    "premierships": ("Premierships", "Stats menu and the premierships page"),
    "honour_board": ("Honour Board", "Stats menu and the honour board page"),
    "ladders": ("Ladders", "Games menu and the ladders page"),
    "players": ("Players", "Main menu and the players page"),
    "player_profile": ("Player Profiles", "The 'presented by' strip on every player profile"),
    "compare": ("Compare", "Main menu and the comparison page"),
    "yearbook": ("Yearbook", "Main menu and the yearbook"),
    "fantasy": ("Fantasy", "The fantasy game's header, sign-in and share cards"),
}

# Public URL segment -> section key, for the pages that carry a club slug.
PATH_SEGMENT_TO_KEY: dict[str, str] = {
    "leaderboard": "leaderboard",
    "records": "records",
    "statlab": "statlab",
    "premierships": "premierships",
    "honour-board": "honour_board",
    "ladders": "ladders",
    "players": "players",
    "compare": "compare",
    "yearbook": "yearbook",
    "yearbooks": "yearbook",
}

NAME_MAX_CHARS = 60
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def clean_name(raw: Any) -> Optional[str]:
    """A tidy single-line name, clipped, or None when blank."""
    if not isinstance(raw, str):
        return None
    name = _CONTROL.sub(" ", raw)
    name = re.sub(r"\s+", " ", name).strip()[:NAME_MAX_CHARS].strip()
    return name or None


def clean_input(raw: Any, valid_sponsor_ids: Iterable[str]) -> Optional[dict[str, dict]]:
    """What to store for a save. Unknown sections are dropped, a name equal to
    the standard one is no rename, a sponsor that is not this club's is dropped,
    and a section with neither a name nor a sponsor is not stored. None (stored
    as NULL) when nothing is left.

    ValueError for a section key that does not exist, so a typo is a 422 and not
    a silent no-op."""
    if not isinstance(raw, dict):
        return None
    valid = {str(s) for s in valid_sponsor_ids}
    out: dict[str, dict] = {}
    for key, entry in raw.items():
        if key not in SECTIONS:
            raise ValueError(f"Unknown section: {key}")
        if not isinstance(entry, dict):
            continue
        name = clean_name(entry.get("name"))
        if name and name.lower() == SECTIONS[key][0].lower():
            name = None
        sponsor_id = entry.get("sponsor_id")
        sponsor_id = str(sponsor_id) if sponsor_id and str(sponsor_id) in valid else None
        if name or sponsor_id:
            out[key] = {"name": name, "sponsor_id": sponsor_id}
    return out or None


def _sponsor_card(s: Any) -> dict:
    return {
        "id": str(s.id),
        "name": s.name,
        "logo_url": s.logo_url,
        "website_url": s.website_url,
    }


def resolve(stored: Any, sponsors: Iterable[Any]) -> dict[str, dict]:
    """The public view: {key: {"name", "sponsor"}} for each configured section.
    `sponsor` is None when none is linked or the linked one no longer exists."""
    if not isinstance(stored, dict):
        return {}
    by_id = {str(s.id): s for s in sponsors}
    out: dict[str, dict] = {}
    for key, entry in stored.items():
        if key not in SECTIONS or not isinstance(entry, dict):
            continue
        name = clean_name(entry.get("name"))
        sp = by_id.get(str(entry.get("sponsor_id") or ""))
        if not name and sp is None:
            continue
        out[key] = {"name": name, "sponsor": _sponsor_card(sp) if sp is not None else None}
    return out


def admin_view(stored: Any) -> dict:
    """What the admin screen draws from: each section with its standard name and
    whatever the club has set. Sponsor ids are returned as stored."""
    stored = stored if isinstance(stored, dict) else {}
    return {
        "sections": [
            {
                "key": key,
                "default_label": label,
                "where": where,
                "name": (stored.get(key) or {}).get("name"),
                "sponsor_id": (stored.get(key) or {}).get("sponsor_id"),
            }
            for key, (label, where) in SECTIONS.items()
        ]
    }


def display_name(resolved: dict, key: str, fallback: str) -> str:
    """The club's name for a section, or the standard one."""
    entry = resolved.get(key) or {}
    return entry.get("name") or fallback


def valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError):
        return False
