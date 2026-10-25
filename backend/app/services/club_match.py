"""Shared helper for recognising a club's own teams in upstream payloads.

Both the fixtures home/away derivation and the ladder "is this us?" highlight
need the same set of lowercased match keys for an organisation. Keeping the key
construction in one place stops the two copies from drifting.

A team name says little about which club a team belongs to: the first word of
"North Perth" is also the first word of "North Beach", and a sponsor-named side
carries no part of its club's name at all. So the answer comes from the owning
organisation id Cricket Australia puts on every team (our ``organisations.id``
IS that GUID for a synced club) whenever the payload carries one. The name keys
are the fallback for a payload with no organisation id, and they match whole
words, never a fragment of one.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional


def club_match_keys(club) -> list[str]:
    """Lowercased/stripped keys for matching the club in opponent/ladder names.

    Returns the short name, the full name, and the first word of the name
    (e.g. ``"applecross"`` from ``"Applecross Cricket Club"``). Empty/missing
    values are dropped. Callers decide how to test (substring vs equality).
    """
    name = (club.name or "").strip()
    first_word = name.split()[0] if name else ""
    candidates = [club.short_name, club.name, first_word]
    return [k.lower().strip() for k in candidates if k and k.strip()]


def club_org_ids(club) -> set[str]:
    """Every id the club's teams may carry as their owning organisation."""
    ids = {str(club.id).lower()}
    playhq_id = getattr(club, "playhq_id", None)
    if playhq_id:
        ids.add(str(playhq_id).lower())
    return ids


def _has_word(hay: str, key: str) -> bool:
    """``key`` appears in ``hay`` as whole words (so "north" is not in "northern")."""
    return re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", hay) is not None


_TRAILING_GENERIC = {"cricket", "club", "cc", "c.c.", "inc", "inc.", "incorporated", "association"}


def _core_name(name: str) -> str:
    """"north perth cricket club" -> "north perth": the name a team is listed under."""
    words = name.split()
    while len(words) > 1 and words[-1].strip(".,") in _TRAILING_GENERIC:
        words.pop()
    return " ".join(words)


def name_score(club, text: Optional[str]) -> int:
    """How strongly ``text`` names the club by name alone: 0 none, 1 the first
    word only, 2 the short name, 3 the full name (or the name less "Cricket
    Club")."""
    hay = (text or "").lower()
    if not hay.strip():
        return 0
    name = (club.name or "").strip().lower()
    short = (club.short_name or "").strip().lower()
    first = name.split()[0] if name else ""
    if name and (_has_word(hay, name) or _has_word(hay, _core_name(name))):
        return 3
    if short and _has_word(hay, short):
        return 2
    if first and _has_word(hay, first):
        return 1
    return 0


def name_is_club(club, text: Optional[str]) -> bool:
    """The name-only test: used when a payload gives no owning organisation id."""
    return name_score(club, text) > 0


def side_is_club(club, name: Optional[str], org_id: Optional[str] = None) -> bool:
    """Is this team the club's: by owning organisation id when there is one,
    else by name."""
    if org_id:
        return str(org_id).lower() in club_org_ids(club)
    return name_is_club(club, name)


def fixture_side(club, home_name, away_name, home_org_id=None, away_org_id=None) -> Optional[str]:
    """Which side of a match is the club: ``"home"``, ``"away"`` or ``None``.

    Owning organisation ids decide when the payload has them. Without ids the
    name decides, the stronger name match winning ("North Perth" beats the
    shared word "North"); a dead heat goes to the home side, as it always has.
    """
    ids = club_org_ids(club)
    h_id = str(home_org_id).lower() if home_org_id else None
    a_id = str(away_org_id).lower() if away_org_id else None
    if h_id and h_id in ids:
        return "home"
    if a_id and a_id in ids:
        return "away"
    if h_id and a_id:
        return None  # both sides name a club, and neither is ours
    h = name_score(club, home_name) if not h_id else 0
    a = name_score(club, away_name) if not a_id else 0
    if not h and not a:
        return None
    return "away" if a > h else "home"


def fixture_involves_club(club, fx: dict) -> bool:
    """A fixture or result dict (``home_team``/``away_team`` and, when the
    source carried them, ``home_org_id``/``away_org_id``) that has the club on
    either side."""
    return fixture_side(
        club, fx.get("home_team"), fx.get("away_team"),
        fx.get("home_org_id"), fx.get("away_org_id"),
    ) is not None


def fixture_is_in_house(club, fx: dict) -> bool:
    """True when BOTH sides are the club's own teams (Applecross 8th XI v 10th XI).

    Owning organisation ids only, and both must be present: two names that share
    a first word prove nothing ("North Beach" and "North Perth"). A fixture like
    this is one match with two sides to pick, so it needs a row for each."""
    ids = club_org_ids(club)
    home, away = fx.get("home_org_id"), fx.get("away_org_id")
    return bool(home and away and str(home).lower() in ids and str(away).lower() in ids)


def fixture_is_between_others(club, fx: dict) -> bool:
    """True only when the payload NAMES both owning clubs and neither is ours.

    The strict form of "not ours", for acting on a stored row (removing it): a
    side with no organisation id is never enough, because a sponsor-named side
    of the club's own would read as foreign by name.
    """
    if not (fx.get("home_org_id") and fx.get("away_org_id")):
        return False
    return not fixture_involves_club(club, fx)


def keys_match_any(keys: Iterable[str], *texts: Optional[str]) -> bool:
    """Whole-word test of pre-built keys (``club_match_keys``) against names."""
    return any(_has_word((t or "").lower(), k) for t in texts for k in keys if k)


def team_is_club(club, team: dict) -> bool:
    """A raw Grassroots ``teams[]`` entry that is the club's: by its owning
    organisation id when it has one, else by its display name."""
    oid = ((team.get("owningOrganisation") or {}).get("id")) or None
    return side_is_club(club, team.get("displayName") or team.get("name"), oid)
