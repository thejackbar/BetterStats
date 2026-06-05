"""Player-name helpers shared across routers.

Players are stored canonically as ``"Last, First"`` (the format Cricket
Australia syncs), and an optional ``display_name_override`` lets admins
customise how a name is shown. Historically that override was free text, so a
custom name like ``"John Smith"`` (no comma) sorted by *first* name while every
synced ``"Last, First"`` name sorted by *surname* — the list interleaved
inconsistently. ``name_sort_key`` extracts a surname-first sort key from either
shape so overrides slot alphabetically by surname alongside synced names,
regardless of how the override was typed (mirrors the frontend ``nameSortKey``).
"""
from __future__ import annotations

import re


def name_sort_key(name: str | None) -> tuple[str, str]:
    """Return a ``(surname, given)`` sort key for a player name.

    Handles both stored shapes:
    - ``"Last, First"`` (canonical / synced) → ``("last", "first")``
    - free-text ``"First Last"`` overrides   → ``("last", "first")``
    - a single token (e.g. a nickname)       → ``("token", "")``

    Lowercased so the sort is case-insensitive. Empty/None → ``("", "")``.
    """
    n = (name or "").strip()
    if not n:
        return ("", "")
    if "," in n:
        last, _, first = n.partition(",")
        return (last.strip().lower(), first.strip().lower())
    words = [w for w in re.split(r"\s+", n) if w]
    if len(words) <= 1:
        return (n.lower(), "")
    # "First [Middle] Last" → the last token is the surname.
    return (words[-1].lower(), " ".join(words[:-1]).lower())
