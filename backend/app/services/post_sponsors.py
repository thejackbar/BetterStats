"""Which sponsors a BetterPosts post starts with (migration 320).

Every post carries at least one sponsor. The editor asks this module which, with
the team and grade the post is about, and gets the first answer that exists:

  1. the sponsors pinned to the team (``teams``),
  2. the sponsors pinned to the grade (``grades``),
  3. the club's own default: sponsors whose Social posts spot is on (a tier's
     default or a hand-set switch, see services/sponsor_tiers.py), at most 4,
  4. the club's top sponsor that has a logo, so a club that has never touched
     any of this still gets one.

Only what a club pinned is stored (``organisations.post_sponsor_defaults``).
Everything else is derived, so a deleted sponsor, a removed logo or a changed
tier is never stale. A sponsor with no logo cannot be drawn on a post and is
skipped at every step. A pin to a name nobody plays under does nothing.

Keys are the lower-cased, space-collapsed name of the team or grade, because a
post only knows the names it was built from, and a team's grade changes season
to season while its name does not.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from app.services import sponsor_tiers

MAX_PER_PIN = 6
CLUB_DEFAULT_CAP = 4
NAME_MAX_CHARS = 80
KINDS = ("teams", "grades")

_SPACES = re.compile(r"\s+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def clean_name(raw: Any) -> str:
    if not isinstance(raw, str):
        return ""
    return _SPACES.sub(" ", _CONTROL.sub(" ", raw)).strip()[:NAME_MAX_CHARS].strip()


def norm_key(raw: Any) -> str:
    return clean_name(raw).lower()


def clean_assignments(raw: Any, valid_sponsor_ids: Iterable[str]) -> Optional[dict]:
    """What to store for a save. `raw` is {"teams": {name: [ids]}, "grades": {...}}.
    Ids that are not this club's are dropped, duplicates removed, each pin capped,
    and a name with no sponsors left is not stored. None when nothing is left.
    ValueError for a kind that does not exist, so a typo is a 422."""
    if not isinstance(raw, dict):
        return None
    valid = {str(v) for v in valid_sponsor_ids}
    out: dict[str, dict] = {}
    for kind, pins in raw.items():
        if kind not in KINDS:
            raise ValueError(f"Unknown kind: {kind}")
        if not isinstance(pins, dict):
            continue
        kept: dict[str, dict] = {}
        for name, ids in pins.items():
            shown = clean_name(name)
            key = norm_key(name)
            if not key or not isinstance(ids, (list, tuple)):
                continue
            seen: list[str] = []
            for i in ids:
                i = str(i)
                if i in valid and i not in seen:
                    seen.append(i)
            if seen:
                kept[key] = {"name": shown, "sponsor_ids": seen[:MAX_PER_PIN]}
        if kept:
            out[kind] = kept
    return out or None


def assignments_view(stored: Any, valid_sponsor_ids: Iterable[str]) -> dict:
    """The admin screen's view: {"teams": {name: [ids]}, "grades": {name: [ids]}},
    by display name, with ids that no longer exist pruned."""
    valid = {str(v) for v in valid_sponsor_ids}
    view: dict[str, dict] = {k: {} for k in KINDS}
    if isinstance(stored, dict):
        for kind in KINDS:
            for entry in (stored.get(kind) or {}).values():
                if not isinstance(entry, dict):
                    continue
                ids = [i for i in (entry.get("sponsor_ids") or []) if str(i) in valid]
                name = clean_name(entry.get("name"))
                if name and ids:
                    view[kind][name] = [str(i) for i in ids]
    return view


def _usable(sponsors: Iterable[Any]) -> list[Any]:
    """Sponsors that can be drawn on a post (they have a logo), tier first then
    the club's own order."""
    return sponsor_tiers.sort_sponsors([s for s in sponsors if getattr(s, "logo_url", None)])


def club_default_ids(sponsors: Iterable[Any]) -> list[str]:
    usable = _usable(sponsors)
    on = [
        s for s in usable
        if "posts" in sponsor_tiers.resolve_placements(getattr(s, "tier", None), getattr(s, "placements", None))
    ]
    if on:
        return [str(s.id) for s in on[:CLUB_DEFAULT_CAP]]
    return [str(usable[0].id)] if usable else []


def _pinned(stored: Any, kind: str, name: Any, usable_ids: set[str]) -> list[str]:
    key = norm_key(name)
    if not key or not isinstance(stored, dict):
        return []
    entry = (stored.get(kind) or {}).get(key)
    if not isinstance(entry, dict):
        return []
    return [str(i) for i in (entry.get("sponsor_ids") or []) if str(i) in usable_ids]


def resolve(stored: Any, sponsors: Iterable[Any], team: Any = None, grade: Any = None) -> tuple[list[str], str]:
    """(sponsor ids, where they came from). `source` is team, grade, club, top
    or none. Order is the pin's own order for a pin and tier order otherwise."""
    sponsors = list(sponsors)
    usable_ids = {str(s.id) for s in _usable(sponsors)}
    ids = _pinned(stored, "teams", team, usable_ids)
    if ids:
        return ids, "team"
    ids = _pinned(stored, "grades", grade, usable_ids)
    if ids:
        return ids, "grade"
    ids = club_default_ids(sponsors)
    if not ids:
        return [], "none"
    on = [
        s for s in _usable(sponsors)
        if "posts" in sponsor_tiers.resolve_placements(getattr(s, "tier", None), getattr(s, "placements", None))
    ]
    return ids, "club" if on else "top"
