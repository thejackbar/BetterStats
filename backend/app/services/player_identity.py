"""Tie a hand-made player to their Cricket Australia identity.

A player created by hand (Add player, a nets registration, Fantasy's "new
player", an import) has no ``grassroots_id``, so when they play their first game
the sync finds no row for their participant GUID and mints a SECOND player.
Games land on the duplicate and the hand-made record, the one a squad or a
Fantasy pick points at, sits empty until somebody merges the two.

This module is the fix at the front door. It searches the same national index
play.cricket.com.au's own search box uses, offers the person's real profile, and
stores that participant GUID as ``players.grassroots_id``. The sync already
builds its participant-to-player map from that column (the aggregate pass and
the game-level pass both), so once it is set the first game attaches to the
record that already exists.

**The search id IS the participant id**, checked live rather than assumed: the
id ``/ca-search`` returns for a person is the ``id`` that club's
``/participants/organisations/{org}/*-statistics`` feed carries, and the
``participantId`` on a scorecard. Twelve players taken from one club's feed and
searched by "First Last" came back with their exact GUID for ten; the two misses
were common names that fell outside the first page of results.

Three rules keep this from creating the problem it exists to prevent:

* **An identity has one holder per club.** ``uq_player_org_grassroots``
  already enforces it; ``holder_of`` reports WHO holds it first, so the screen
  can say "already in your club as X" instead of failing on the index.
* **The player's own id is never changed.** Squads, availability, lineups and
  Fantasy picks all key on it. Only ``grassroots_id`` is set, and the sync's
  ``pid_by_guid`` map already copes with an id that differs from the GUID (that
  is what a per-club ``uuid5`` player is).
* **Nothing about the person's other clubs is stored.** Search results are shown
  and discarded; only the GUID the admin confirmed is written.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Player
from app.services import scout_live_search
from app.services.player_aliases import normalise_name_key

logger = logging.getLogger(__name__)

MIN_TERM_CHARS = 3
# ``search_playcommunity`` returns 20 a page; a second page is fetched only when
# the first is full, which is what a common name ("Michael Simpson") looks like.
PAGE_SIZE = scout_live_search.DEFAULT_SIZE
MAX_PAGES = 2
_CACHE_TTL = 60.0
_CACHE: dict[str, tuple[float, list[dict]]] = {}

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def clean_participant_id(value) -> Optional[str]:
    """The participant GUID, lower-cased, or None for a blank. Anything else that
    is not a GUID is a 400: this value goes straight onto a player row and is then
    used as an API key, so a typo must not be stored."""
    v = str(value or "").strip()
    if not v:
        return None
    if not _UUID_RE.match(v):
        raise HTTPException(status_code=400, detail="That is not a valid PlayCricket player id.")
    return v.lower()


def search_term(raw: str) -> str:
    """"Green, Spencer" (how a club feed and our own roster write a name) becomes
    "Spencer Green", which is what the national search answers to. The comma form
    returns nothing, found by trying it."""
    t = " ".join(str(raw or "").replace(";", " ").split())
    if "," in t:
        last, _, first = t.partition(",")
        t = f"{first.strip()} {last.strip()}".strip()
    return t


async def _fetch_players(term: str) -> list[dict]:
    key = term.lower()
    hit = _CACHE.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    players: list[dict] = []
    for page in range(MAX_PAGES):
        res = await scout_live_search.search_playcommunity(
            term, types=("PLAYCOMM_PLAYER",), size=PAGE_SIZE, page=page,
        )
        got = res.get("players") or []
        players.extend(got)
        if len(got) < PAGE_SIZE:
            break
    if len(_CACHE) > 200:
        _CACHE.clear()
    _CACHE[key] = (now, players)
    return players


async def holders_of(db: AsyncSession, org_id, guids: list[str]) -> dict[str, dict]:
    """``{guid: {id, name}}`` for the club's players that already hold any of these
    identities. A legacy raw-GUID player (whose ``id`` IS the participant GUID and
    whose ``grassroots_id`` was backfilled from it) is found either way."""
    if not guids:
        return {}
    rows = (await db.execute(
        text("""
            SELECT id::text AS id, name, display_name_override, lower(grassroots_id) AS gid
            FROM players
            WHERE organisation_id = CAST(:org AS UUID)
              AND (lower(grassroots_id) = ANY(:g) OR id::text = ANY(:g))
        """),
        {"org": str(org_id), "g": [g.lower() for g in guids]},
    )).mappings().all()
    wanted = {g.lower() for g in guids}
    out: dict[str, dict] = {}
    for r in rows:
        info = {"id": r["id"], "name": r["display_name_override"] or r["name"]}
        for key in (r["gid"], r["id"]):
            if key in wanted:
                out.setdefault(key, info)
    return out


async def holder_of(db: AsyncSession, org_id, guid: str, *, exclude_player_id=None) -> Optional[dict]:
    held = (await holders_of(db, org_id, [guid])).get(guid.lower())
    if held and exclude_player_id and held["id"] == str(exclude_player_id):
        return None
    return held


async def search_candidates(db: AsyncSession, club, term: str) -> dict:
    """People matching a name, each with the clubs PlayCricket lists them at, marked
    with whether they are already registered at THIS club and whether this club
    already has a player row for them."""
    t = search_term(term)
    if len(t) < MIN_TERM_CHARS:
        return {"term": t, "candidates": [], "capped": False}
    raw = await _fetch_players(t)
    guids = [p["id"] for p in raw if p.get("id")]
    held = await holders_of(db, club.id, guids)
    our = str(club.id).lower()
    out = []
    for p in raw:
        pid = (p.get("id") or "").lower()
        if not pid:
            continue
        orgs = p.get("organisations") or []
        out.append({
            "participant_id": pid,
            "name": p.get("name"),
            "clubs": [{"id": o["id"], "name": o["name"]} for o in orgs],
            "at_this_club": any((o.get("id") or "").lower() == our for o in orgs),
            "existing_player": held.get(pid),
        })
    # Someone already at this club, then someone we hold, then the rest.
    out.sort(key=lambda c: (not c["at_this_club"], c["existing_player"] is None))
    return {"term": t, "candidates": out, "capped": len(raw) >= PAGE_SIZE * MAX_PAGES}


async def assert_identity_free(db: AsyncSession, club, participant_id: Optional[str], *, exclude_player_id=None) -> Optional[str]:
    """Validate an identity about to be written. Returns the cleaned GUID (None for
    "no identity"), or raises 409 naming the player already holding it."""
    guid = clean_participant_id(participant_id)
    if guid is None:
        return None
    held = await holder_of(db, club.id, guid, exclude_player_id=exclude_player_id)
    if held:
        raise HTTPException(status_code=409, detail={
            "code": "identity_in_use",
            "message": f"That person is already in your club as {held['name']}.",
            "player_id": held["id"], "name": held["name"],
        })
    return guid


async def link_player(db: AsyncSession, club, player: Player, participant_id: str) -> dict:
    """Store the participant GUID on an existing hand-made player, so the next sync
    attaches their games to this record. Idempotent; refuses to re-point a player
    already linked to somebody else, and refuses an identity another player at the
    club already holds (that is a duplicate to merge, not a link)."""
    if str(player.organisation_id) != str(club.id):
        raise HTTPException(status_code=404, detail="Player not found")
    guid = clean_participant_id(participant_id)
    if guid is None:
        raise HTTPException(status_code=400, detail="Choose a PlayCricket player to link.")
    current = (player.grassroots_id or "").lower() or None
    if current == guid:
        return {"ok": True, "linked": True, "changed": False}
    if current and current != str(player.id).lower():
        raise HTTPException(status_code=409, detail={
            "code": "already_linked",
            "message": "This player is already linked to a different PlayCricket profile.",
        })
    await assert_identity_free(db, club, guid, exclude_player_id=player.id)
    player.grassroots_id = guid
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail={
            "code": "identity_in_use",
            "message": "Another player at your club holds that PlayCricket profile.",
        })
    return {"ok": True, "linked": True, "changed": True}


# ── sync-side adoption ──────────────────────────────────────────────────────────

async def load_unlinked_candidates(session: AsyncSession, org_id) -> dict[str, list[uuid.UUID]]:
    """Players a sync could safely tie to a participant it has never seen: created
    by hand (no ``grassroots_id``, no ``playhq_id``) and holding NO record of any
    kind, so there is nothing that a wrong link could attach to the wrong person.
    Keyed on ``normalise_name_key`` (comma and word-order independent), against the
    stored name and the display override."""
    rows = (await session.execute(
        text("""
            SELECT p.id, p.name, p.display_name_override
            FROM players p
            WHERE p.organisation_id = CAST(:org AS UUID)
              AND p.grassroots_id IS NULL AND p.playhq_id IS NULL
              AND NOT EXISTS (SELECT 1 FROM player_season_stats x WHERE x.player_id = p.id)
              AND NOT EXISTS (SELECT 1 FROM batting_innings x WHERE x.player_id = p.id)
              AND NOT EXISTS (SELECT 1 FROM bowling_spells x WHERE x.player_id = p.id)
              AND NOT EXISTS (SELECT 1 FROM game_appearances x WHERE x.player_id = p.id)
              AND NOT EXISTS (SELECT 1 FROM imported_stats x WHERE x.player_id = p.id)
              AND NOT EXISTS (SELECT 1 FROM manual_batting_innings x WHERE x.player_id = p.id)
              AND NOT EXISTS (SELECT 1 FROM manual_bowling_spells x WHERE x.player_id = p.id)
        """),
        {"org": str(org_id)},
    )).all()
    out: dict[str, list[uuid.UUID]] = {}
    for pid, name, override in rows:
        for nm in {normalise_name_key(name), normalise_name_key(override)}:
            if nm:
                out.setdefault(nm, [])
                if pid not in out[nm]:
                    out[nm].append(pid)
    return out


def unique_candidate(candidates: dict[str, list[uuid.UUID]], name: str, feed_name_counts: dict[str, int]) -> Optional[uuid.UUID]:
    """The one player a new participant may be tied to, or None. Refuses when two
    hand-made players fit, and when the feed itself names two people the same
    (a father and son under one name): guessing there puts a career on the wrong
    person, which is worse than the duplicate the merge screen already finds."""
    key = normalise_name_key(name)
    if not key or feed_name_counts.get(key, 0) != 1:
        return None
    ids = candidates.get(key) or []
    return ids[0] if len(ids) == 1 else None
