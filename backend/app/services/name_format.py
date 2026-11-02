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


def first_name(name: str | None) -> str:
    """Extract the given (first) name, preserving case, from either stored shape:
    - ``"Last, First"`` (canonical / synced)  → ``"First"`` (the part after the comma)
    - free-text ``"First Last"``              → ``"First"`` (the first token)
    - a single token (e.g. a nickname)        → that token

    This is what powers ``{{first_name}}`` — a club stores players surname-first,
    so a naive first-token split would return the surname. Empty/None → ``""``.
    """
    n = (name or "").strip()
    if not n:
        return ""
    if "," in n:
        _, _, given = n.partition(",")
        toks = given.strip().split()
        return toks[0] if toks else ""
    words = [w for w in re.split(r"\s+", n) if w]
    return words[0] if words else ""


def format_player_name(name: str | None, fmt: str | None) -> str:
    """A stored name printed the way the club chose under Settings (Player name
    format). Mirrors the frontend ``formatPlayerName`` so an email and the site
    show the same name. ``fmt`` is one of ``last_first`` (the default),
    ``first_last``, ``first_initial_last``, ``last_first_initial``; anything else
    leaves the canonical "Last, First". A name with no comma we cannot split
    (a nickname, three words) is returned as it is stored.

    Use it to PRINT a name. To greet someone use ``first_name`` on the stored
    name, not on this: "I. Oliphant" has no given name left to find.
    """
    canon = canonical_player_name(name)
    if not fmt or fmt == "last_first" or "," not in canon:
        return canon
    last, _, first = canon.partition(",")
    last, first = last.strip(), first.strip()
    if not first:
        return canon
    if fmt == "first_last":
        return f"{first} {last}"
    if fmt == "first_initial_last":
        return f"{first[0]}. {last}"
    if fmt == "last_first_initial":
        return f"{last}, {first[0]}."
    return canon


def natural_name(name: str | None) -> str:
    """A name for running prose ("Hi {{name}}", "thanks to ..."): "Iain Oliphant"
    for a stored "Oliphant, Iain". A name with no comma is already in the order
    somebody typed it and is returned as it is, so a contact typed "Sam Taylor"
    is never turned round."""
    n = (name or "").strip()
    return format_player_name(n, "first_last") if "," in n else n


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


def canonical_player_name(name: str | None) -> str:
    """Return a stored player name in the canonical ``"Last, First"`` shape.

    A name that already has a comma, a single token (a nickname) or three or
    more words is returned untouched: with three words we cannot tell a middle
    name from a double-barrelled surname, so we do not guess. Only the
    unambiguous free-text ``"First Last"`` override is flipped to
    ``"Last, First"``, so it lists and sorts beside the synced names.
    Derived on read: nothing is rewritten in the database.
    """
    n = (name or "").strip()
    if not n or "," in n:
        return name or ""
    words = n.split()
    if len(words) != 2:
        return name or ""
    return f"{words[1]}, {words[0]}"
