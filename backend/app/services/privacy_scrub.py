"""Scrub a removed person from every PUBLIC response (migration 316).

Hiding a person's profile page is not the same as removing them from the site.
A match scorecard, a teammate's "played with", StatLab, a yearbook's top-batter
line, an honour board typed in by hand: each names a player by id and by name,
and there are hundreds of routes. Closing them one by one leaves whichever one
nobody remembered. Because the set of people who asked to be removed is tiny,
this does the opposite: every response a public visitor can get is scrubbed of
those people, by id and by every way their name is written.

WHAT IT DOES
------------
For a GET whose response is text (JSON, CSV, HTML, XML), replaces

  * each removed person's ids (every club's row for them) with the nil UUID,
    so a JSON shape stays valid and a link goes nowhere;
  * their name, in the forms a scorecard writes it ("Trent Steenholdt",
    "Steenholdt, Trent", "T Steenholdt", "T. Steenholdt", "Steenholdt T"), and
    any alias, with "Player removed";
  * their bare surname too, but ONLY when nobody else the club holds shares it,
    so removing a rare surname also catches a dismissal line that writes just
    "c Steenholdt b Smith" without renaming somebody's brother.

WHO IS NOT SCRUBBED
-------------------
A request carrying a sign-in token (``Authorization`` header) to one of the
club-management prefixes below (``/club-admin``, ``/admin``, selection and so
on). The club needs its own record of the person to run the club, and those
routes are capability-gated. Everything else is scrubbed for everyone,
including a signed-in visitor on a public page: a token alone does not make a
request a club admin, and the cost of scrubbing a screen that did not need it
is a name reading "Player removed", where the cost of the reverse is the leak.

LIMITS, SAID PLAINLY
--------------------
It can only remove what it can recognise. A nickname nobody recorded, a typo,
a photo, text inside an image or a PDF, and a surname shared with another
player (initials and full name are still caught) are not caught. It does not
touch what is already in a search engine, an archive, a screenshot or Cricket
Australia's own site.

Cost: one cached lookup (30 seconds) per process. With nobody removed, the
middleware passes every response straight through without buffering it.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Optional

from sqlalchemy import text

log = logging.getLogger(__name__)

REMOVED_NAME = "Player removed"
NIL_UUID = "00000000-0000-0000-0000-000000000000"
CACHE_SECONDS = 30

# Routes where a signed-in club works with its own people. Everything not
# listed is scrubbed. An unlisted management screen shows "Player removed"
# for the one person, which is the safe way to be wrong.
MANAGEMENT_PREFIXES = (
    "/club-admin", "/admin", "/auth", "/selection", "/selection-rules", "/availability",
    "/teams", "/fixtures", "/nets", "/votes", "/scout", "/iq", "/families",
)

_SCRUBBABLE_TYPES = ("application/json", "text/csv", "text/plain", "text/html", "application/xml", "text/xml")


def name_variants(raw: str) -> set[str]:
    """Every way a scorecard or a list might write this name (no bare surname)."""
    raw = " ".join((raw or "").split())
    if not raw:
        return set()
    out = {raw}
    if "," in raw:
        last, _, first = (p.strip() for p in raw.partition(","))
    else:
        parts = raw.split(" ")
        if len(parts) == 1:
            return out
        first, last = " ".join(parts[:-1]), parts[-1]
    if not first or not last:
        return out
    i = first[0]
    out |= {
        f"{first} {last}", f"{last}, {first}", f"{last} {first}",
        f"{i} {last}", f"{i}. {last}", f"{last}, {i}", f"{last} {i}", f"{last} {i}.",
        f"{last}, {i}.",
    }
    return {v for v in out if v}


def surname_of(raw: str) -> Optional[str]:
    raw = " ".join((raw or "").split())
    if not raw:
        return None
    if "," in raw:
        return raw.split(",", 1)[0].strip() or None
    parts = raw.split(" ")
    return parts[-1] if len(parts) > 1 else None


class Scrubber:
    __slots__ = ("_name_re", "_id_re")

    def __init__(self, names: set[str], ids: set[str]):
        names = {n for n in names if n and len(n) >= 3}
        # Longest first, so "Steenholdt, Trent" wins over "Steenholdt".
        pats = sorted(names, key=len, reverse=True)
        self._name_re = (
            re.compile(r"(?<![\w])(?:" + "|".join(re.escape(p) for p in pats) + r")(?![\w])", re.IGNORECASE)
            if pats else None
        )
        idl = sorted({i.lower() for i in ids if i})
        self._id_re = (
            re.compile("|".join(re.escape(i) for i in idl), re.IGNORECASE) if idl else None
        )

    def scrub(self, body: str) -> str:
        if self._id_re is not None:
            body = self._id_re.sub(NIL_UUID, body)
        if self._name_re is not None:
            body = self._name_re.sub(REMOVED_NAME, body)
        return body


_cache: dict = {"at": 0.0, "scrubber": None, "loaded": False}


def forget() -> None:
    _cache.update(at=0.0, scrubber=None, loaded=False)


async def _load(session) -> Optional[Scrubber]:
    rows = (await session.execute(text("""
        SELECT id::text, name, display_name_override, grassroots_id
          FROM players WHERE privacy_hidden_at IS NOT NULL
    """))).fetchall()
    if not rows:
        return None
    ids: set[str] = set()
    names: set[str] = set()
    surnames: set[str] = set()
    hidden_ids = [r[0] for r in rows]
    for pid, name, override, guid in rows:
        ids.add(pid)
        if guid:
            ids.add(str(guid))
        for n in (name, override):
            names |= name_variants(n or "")
            s = surname_of(n or "")
            if s:
                surnames.add(s)
    # Recorded aliases for the same people.
    try:
        async with session.begin_nested():
            for (alias,) in (await session.execute(
                text("SELECT alias_name FROM player_name_aliases WHERE player_id::text = ANY(:ids)"),
                {"ids": hidden_ids},
            )).fetchall():
                names |= name_variants(alias or "")
                s = surname_of(alias or "")
                if s:
                    surnames.add(s)
    except Exception:
        pass
    # A bare surname is only scrubbed when no OTHER player holds it.
    for s in surnames:
        if len(s) < 4:
            continue
        shared = await session.scalar(text("""
            SELECT COUNT(*) FROM players
             WHERE privacy_hidden_at IS NULL
               AND (name ILIKE :a OR name ILIKE :b OR name ILIKE :c OR display_name_override ILIKE :a
                    OR display_name_override ILIKE :b OR display_name_override ILIKE :c)
        """), {"a": f"%{s}", "b": f"{s},%", "c": f"% {s} %"})
        if not shared:
            names.add(s)
    return Scrubber(names, ids)


async def get_scrubber() -> Optional[Scrubber]:
    """The current scrubber, or None when nobody has asked. Never raises."""
    now = time.monotonic()
    if _cache["loaded"] and now - _cache["at"] < CACHE_SECONDS:
        return _cache["scrubber"]
    try:
        from app.models.db import async_session_maker
        async with async_session_maker() as session:
            scrubber = await _load(session)
        _cache.update(at=now, scrubber=scrubber, loaded=True)
        return scrubber
    except Exception:   # a failed lookup must not take the site down
        log.exception("privacy scrub: could not load the removed-people list")
        _cache["at"] = now
        return _cache["scrubber"]


def _is_management(scope) -> bool:
    path = scope.get("path", "") or ""
    if not any(path == p or path.startswith(p + "/") for p in MANAGEMENT_PREFIXES):
        return False
    return any(k == b"authorization" for k, _ in scope.get("headers", []))


class PrivacyScrubMiddleware:
    """Pure ASGI: buffers a response only when it is text AND somebody is removed."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "GET":
            return await self.app(scope, receive, send)
        scrubber = await get_scrubber()
        if scrubber is None or _is_management(scope):
            return await self.app(scope, receive, send)

        held: dict = {"start": None, "chunks": [], "pass": False}

        async def send_wrapper(message):
            if held["pass"]:
                return await send(message)
            if message["type"] == "http.response.start":
                headers = {k.lower(): v for k, v in message.get("headers", [])}
                ctype = headers.get(b"content-type", b"").decode("latin-1").lower()
                encoded = headers.get(b"content-encoding")
                if encoded or not any(ctype.startswith(t) for t in _SCRUBBABLE_TYPES):
                    held["pass"] = True
                    return await send(message)
                held["start"] = message
                return
            if message["type"] == "http.response.body":
                held["chunks"].append(message.get("body", b""))
                if message.get("more_body"):
                    return
                body = b"".join(held["chunks"])
                try:
                    cleaned = scrubber.scrub(body.decode("utf-8")).encode("utf-8")
                except UnicodeDecodeError:
                    cleaned = body
                start = dict(held["start"])
                start["headers"] = [
                    (k, (str(len(cleaned)).encode() if k.lower() == b"content-length" else v))
                    for k, v in start.get("headers", [])
                ]
                await send(start)
                await send({"type": "http.response.body", "body": cleaned})
                return
            await send(message)

        await self.app(scope, receive, send_wrapper)
