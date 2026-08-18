"""A club's founding year, its former names and the competitions it has
played in — validation for the ``organisations`` columns migrations 227 and
261 added.

Kept out of the router so the public read and the admin write agree on what a
stored value looks like, and so a second sport can adopt the same shape without
a second copy of these rules.

The years are deliberately forgiving. A club that knows it used to be Hampton
Football Club without knowing when that stopped must still be able to record
the name — so ``from_year``/``to_year`` are each optional, and a name with
neither is a perfectly valid entry rather than a rejected one.
"""
from __future__ import annotations

from typing import Any, Optional

# The lower bound is the founding of Australian football itself (1858), so a
# typo like 189 or 18889 is caught while a genuinely ancient club is not. The
# upper bound is left open at write time and clamped against the current year
# by the caller, which is the only place that knows what "now" is.
MIN_YEAR = 1800
MAX_YEAR = 2200

MAX_PREVIOUS_NAMES = 20
MAX_COMPETITIONS = 30
MAX_NAME_LEN = 120


def clean_year(value: Any) -> Optional[int]:
    """Coerce to a plausible four-digit year, or None.

    Anything unparseable or out of range reads as "not recorded" rather than
    raising: a year is a nice-to-have on a club profile, and refusing the whole
    settings save because one field was fat-fingered helps nobody.
    """
    if value is None or value == "":
        return None
    try:
        year = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return year if MIN_YEAR <= year <= MAX_YEAR else None


def _clean_year_spans(value: Any, limit: int) -> Optional[list[dict]]:
    """Normalise a list of named year spans.

    Accepts either the full ``{"name", "from_year", "to_year"}`` shape or a
    bare string (which a simpler client, or a paste, can produce) and always
    stores the full shape. A row with no usable name is dropped — an entry
    that names nothing is not a former name or a competition.

    Ordering is the caller's, preserved as given: a club lists its own history
    oldest-first and re-sorting that by year would scatter the entries whose
    years were never filled in.

    Returns None rather than [] for an empty result, so "cleared" and "never
    set" are the same NULL in the column instead of two states meaning one
    thing.

    Shared by both club-history lists deliberately: former names and
    competitions are the same three facts recorded the same way, and a second
    copy of these rules is how the two start disagreeing about what a year is.
    """
    if not isinstance(value, list):
        return None
    out: list[dict] = []
    for raw in value[:limit]:
        if isinstance(raw, str):
            raw = {"name": raw}
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()[:MAX_NAME_LEN]
        if not name:
            continue
        entry = {
            "name": name,
            "from_year": clean_year(raw.get("from_year")),
            "to_year": clean_year(raw.get("to_year")),
        }
        # A range entered backwards is the same two facts either way round, so
        # it is corrected rather than rejected.
        if (entry["from_year"] and entry["to_year"]
                and entry["from_year"] > entry["to_year"]):
            entry["from_year"], entry["to_year"] = entry["to_year"], entry["from_year"]
        out.append(entry)
    return out or None


def clean_previous_names(value: Any) -> Optional[list[dict]]:
    """The club's former names, oldest first."""
    return _clean_year_spans(value, MAX_PREVIOUS_NAMES)


def clean_competitions(value: Any) -> Optional[list[dict]]:
    """The competitions the club has played in, oldest first.

    A higher cap than the former names: a club changes leagues, and fields
    teams in several at once, far more often than it renames itself.
    """
    return _clean_year_spans(value, MAX_COMPETITIONS)


def previous_names_for_display(value: Any) -> list[dict]:
    """What a public reader gets. Always a list, never None, and re-cleaned on
    the way out so a row written before these rules existed (or by hand) can't
    put an unexpected shape in front of the frontend."""
    return clean_previous_names(value) or []


def competitions_for_display(value: Any) -> list[dict]:
    """The public read of the competitions list — same guarantees as
    ``previous_names_for_display``."""
    return clean_competitions(value) or []
