"""Recognise a rostered player by their full name when Cricket Australia's id for
them is one the club has never stored.

CA issues a participant id per registration, and the id on a match's team sheet is
not always the one the club's player was created with: the season aggregate feed
may hold the old id, or the player may be new to the club this season and only
exist hand-added. A game's rows are attached by id, so such a player's whole game
is dropped, and a Fantasy team full of them scores nothing.

The team sheet carries the FULL name ("David Gardner"), unlike the batting and
bowling rows ("D Gardner"). A full name that matches exactly one of the club's
players is strong enough to attach on. Anything ambiguous (two players with the
name) or short ("A Taylor") is left alone: a wrong attachment is worse than none.

One rule, used by sync (which stores the rows), the scorecard page (which links a
row to a profile) and the repair script that finds games sync dropped.
"""
from __future__ import annotations

import re
import uuid
from typing import Iterable, Optional

_WORD = re.compile(r"[a-z0-9']+")


def is_placeholder_id(guid: Optional[str]) -> bool:
    """Is this a participant id that does not identify anybody?

    Cricket Australia gives EVERY redacted or anonymous participant the same id,
    `00000000-0000-0000-0000-000000000001` (and in places `...0002`), whoever they are.
    It is a label for "somebody we are hiding", never a person, so a name match against it
    is meaningless and a lookup keyed on it would credit one player with every hidden
    participant's rows in every game. Found on Leederville's Jonah Cumming: 37 of 49 held
    games were rows CA carried under this id.
    """
    try:
        return uuid.UUID(str(guid or "")).int < (1 << 16)
    except ValueError:
        return False


def full_name_key(name: Optional[str]) -> str:
    """The words of the name, lower case and sorted, so "Taylor, Ashton" and
    "Ashton Taylor" are the same key."""
    return " ".join(sorted(_WORD.findall((name or "").lower())))


def looks_full(name: Optional[str]) -> bool:
    """A name that can identify someone: two or more words, none of them a bare
    initial or redacted asterisks. "D Gardner" and "********" are not."""
    words = _WORD.findall((name or "").lower())
    return len(words) >= 2 and all(len(w) > 1 for w in words)


def first_name(name: Optional[str]) -> str:
    """The given name of "Taylor, Ashton" or "Ashton Taylor", lower case."""
    n = (name or "").strip()
    if "," in n:
        n = n.split(",", 1)[1]
    words = _WORD.findall(n.lower())
    return words[0] if words else ""


def first_names_compatible(a: Optional[str], b: Optional[str]) -> bool:
    """Could these be the same given name? Equal, one a prefix of the other, or the
    same first three letters (Dan and Daniel). Ashton and Angus are not."""
    x, y = first_name(a), first_name(b)
    if not x or not y:
        return False
    return x.startswith(y) or y.startswith(x) or x[:3] == y[:3]


def unique_by_full_name(players: Iterable[tuple]) -> dict[str, object]:
    """``{full_name_key: player_id}`` for names held by exactly one player.
    ``players`` is ``(id, name)`` pairs. A name two players share is left out."""
    seen: dict[str, list] = {}
    for pid, name in players:
        if looks_full(name):
            seen.setdefault(full_name_key(name), []).append(pid)
    return {k: v[0] for k, v in seen.items() if len(set(v)) == 1}


def attachable_by_full_name(players: Iterable[tuple]) -> dict[str, object]:
    """``{full_name_key: player_id}`` for the players a team-sheet entry may be linked to by name.

    ``players`` is ``(id, name, has_id)`` triples, ``has_id`` true when the record already
    holds a Cricket Australia or PlayHQ participant id.

    A name is only offered when exactly ONE player holds it (so a shared name is never
    guessed), AND that player holds no id of their own. A record that already has an id is a
    person CA already knows; a different id turning up under the same name is as likely to be
    a different person (a junior with the same name, a namesake at another club's fixture) as
    a new registration, and a wrong link puts someone else's games on their record. Linking
    stays for a hand-added record, which has no id to be wrong about. A person who really did
    re-register under a new id is merged on the Merge Players screen, which also redirects
    their id for good.
    """
    triples = [(pid, name, has_id) for pid, name, has_id in players]
    unique = unique_by_full_name([(pid, name) for pid, name, _ in triples])
    without_id = {pid for pid, _, has_id in triples if not has_id}
    return {k: pid for k, pid in unique.items() if pid in without_id}


def resolve_roster_by_name(roster: Iterable[dict], known_guid: dict, unique_names: dict) -> dict[str, object]:
    """For one team sheet, ``{participant_guid: player_id}`` for every rostered
    player whose id is unknown (``known_guid`` has neither the id nor a redirect
    for it) but whose full name matches exactly one of the club's players.

    A player is claimed once: if two unknown ids carry the same name, or the
    matched player is already on the sheet under a known id, nothing is attached,
    since that would be a second appearance for one person (or a different
    person with the same name)."""
    on_sheet = {known_guid[p.get("participantId")] for p in roster if p.get("participantId") in known_guid}
    candidates: dict[str, object] = {}
    claims: dict[object, list] = {}
    for p in roster:
        guid = p.get("participantId") or ""
        if not guid or guid in known_guid or is_placeholder_id(guid):
            continue
        name = p.get("playerShortName") or p.get("displayName") or p.get("name")
        if not looks_full(name):
            continue
        pid = unique_names.get(full_name_key(name))
        if pid is None or pid in on_sheet:
            continue
        candidates[guid] = pid
        claims.setdefault(pid, []).append(guid)
    return {g: pid for g, pid in candidates.items() if len(claims[pid]) == 1}
