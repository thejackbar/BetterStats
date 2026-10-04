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
    any alias, with "********";
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
is a name reading "********", where the cost of the reverse is the leak.

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

REMOVED_NAME = "********"   # the redaction Cricket Australia uses for a junior; the app already treats it as redacted
NIL_UUID = "00000000-0000-0000-0000-000000000000"
CACHE_SECONDS = 30

# Routes where a signed-in club works with its own people. Everything not
# listed is scrubbed. An unlisted management screen shows "********"
# for the one person, which is the safe way to be wrong.
MANAGEMENT_PREFIXES = (
    "/club-admin", "/admin", "/auth", "/selection", "/selection-rules", "/availability",
    "/teams", "/fixtures", "/nets", "/votes", "/scout", "/iq", "/families",
)

_SCRUBBABLE_TYPES = ("application/json", "text/csv", "text/plain", "text/html", "application/xml", "text/xml")


def parse_name(raw: str) -> Optional[tuple[Optional[str], str]]:
    """(first, last) from "Last, First" or "First Last"; (None, last) for one word."""
    raw = " ".join((raw or "").split())
    if not raw:
        return None
    if "," in raw:
        last, _, first = (p.strip() for p in raw.partition(","))
        return (first or None, last) if last else None
    parts = raw.split(" ")
    if len(parts) == 1:
        return (None, parts[0])
    return (" ".join(parts[:-1]), parts[-1])


def _initial(first: str) -> str:
    return first.strip().rstrip(".")[:1]


def forms_by_kind(first: Optional[str], last: str) -> dict[str, set[str]]:
    """Every way a scorecard writes this name, grouped by how ambiguous it is.

    full:    "Trent Steenholdt", "Steenholdt, Trent", "Steenholdt Trent"
    initial: "T Steenholdt", "T. Steenholdt", "Steenholdt, T", "Steenholdt T"
    bare:    "Steenholdt" (Cricket Australia writes a keeper as "st †Steenholdt")
    """
    out: dict[str, set[str]] = {"full": set(), "initial": set(), "bare": set()}
    if last and len(last) >= 4:
        out["bare"].add(last)
    if first and last:
        i = _initial(first)
        if len(first.rstrip(".")) > 1:
            out["full"] |= {f"{first} {last}", f"{last}, {first}", f"{last} {first}"}
        if i:
            out["initial"] |= {
                f"{i} {last}", f"{i}. {last}", f"{last}, {i}", f"{last} {i}", f"{last} {i}.", f"{last}, {i}.",
            }
    return out


def name_variants(raw: str) -> set[str]:
    """Every written form of a name, ignoring ambiguity (kept for callers and tests)."""
    raw = " ".join((raw or "").split())
    pn = parse_name(raw)
    if not pn:
        return set()
    forms = forms_by_kind(*pn)
    return {raw} | forms["full"] | forms["initial"]


def surname_of(raw: str) -> Optional[str]:
    pn = parse_name(raw)
    return pn[1] if pn and pn[0] else None


class Person:
    """One removed person: their ids, and their name forms split by whether the
    form can only mean them (``safe``) or might also mean somebody else the
    system holds (``ambiguous``, with the kind: full, initial or bare)."""
    __slots__ = ("ids", "safe", "ambiguous", "own")

    def __init__(self):
        self.ids: set[str] = set()
        self.safe: set[str] = set()
        self.ambiguous: dict[str, str] = {}
        self.own: set[str] = set()      # every form of their name, lowercased


def _compile(names) -> Optional[re.Pattern]:
    names = sorted({n for n in names if n and len(n) >= 3}, key=len, reverse=True)
    if not names:
        return None
    return re.compile(r"(?<![\w])(?:" + "|".join(re.escape(n) for n in names) + r")(?![\w])", re.IGNORECASE)


class Scrubber:
    __slots__ = ("_name_re", "_id_re", "persons")

    def __init__(self, persons: list[Person]):
        self.persons = persons
        safe: set[str] = set()
        ids: set[str] = set()
        for p in persons:
            safe |= p.safe
            ids |= p.ids
        # Longest first, so "Steenholdt, Trent" wins over "Steenholdt".
        self._name_re = _compile(safe)
        idl = sorted({i.lower() for i in ids if i})
        self._id_re = re.compile("|".join(re.escape(i) for i in idl), re.IGNORECASE) if idl else None

    def scrub(self, body: str) -> str:
        if self._id_re is not None:
            body = self._id_re.sub(NIL_UUID, body)
        if self._name_re is not None:
            body = self._name_re.sub(REMOVED_NAME, body)
        return body

    # ---- one match scorecard ------------------------------------------------
    def scrub_card(self, obj):
        """Scrub a parsed scorecard, resolving the forms that are ambiguous
        across the whole club using the people actually in THIS match.

        "T Steenholdt" cannot be scrubbed site-wide when a Tom Steenholdt also
        exists. In one match it usually can: if the removed person is in the
        card (their id is there) and no other Steenholdt with a T is, the line
        can only be them. If another is in the card too, it is left alone.
        """
        strings = list(_walk_strings(obj))
        present_ids = {s.lower() for s in strings}
        names_in_card = [v.lower() for v in _walk_name_values(obj)]
        extra: set[str] = set()
        for person in self.persons:
            if not (person.ids & present_ids):
                continue   # not in this match: an ambiguous line is somebody else
            for form, kind in person.ambiguous.items():
                if _card_resolves(form, kind, person, names_in_card):
                    extra.add(form)
        rx = _compile(extra)
        if rx is None:
            return obj
        return _map_strings(obj, lambda t: rx.sub(REMOVED_NAME, t))


def _walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_strings(v)


def _walk_name_values(obj):
    """Strings held under a key that ends in "name" (player_name, batter1_name...)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and str(k).lower().endswith("name"):
                yield v
            else:
                yield from _walk_name_values(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_name_values(v)


def _map_strings(obj, fn):
    if isinstance(obj, str):
        return fn(obj)
    if isinstance(obj, dict):
        return {k: _map_strings(v, fn) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_map_strings(v, fn) for v in obj]
    return obj


def _card_resolves(form: str, kind: str, person: Person, names_in_card: list[str]) -> bool:
    """Can this ambiguous form be attributed to the removed person in this match?"""
    pn = parse_name(form)
    surname = (pn[1] if pn else form).lower()
    others = [n for n in names_in_card if surname in n and n not in person.own]
    if kind == "bare":
        return not others
    # initial / full: another person in the card with the same surname AND the
    # same first initial (or no first name to tell them apart) keeps it ambiguous.
    mine = _initial(pn[0]).lower() if pn and pn[0] else ""
    for n in others:
        opn = parse_name(n)
        if not opn or not opn[0] or _initial(opn[0]).lower() == mine:
            return False
    return True


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
    hidden_ids = [r[0] for r in rows]
    # The same person has one row per club: group on the participant id.
    by_person: dict[str, dict] = {}
    for pid, name, override, guid in rows:
        key = str(guid or pid).lower()
        d = by_person.setdefault(key, {"ids": set(), "names": set()})
        d["ids"] |= {pid, str(guid)} if guid else {pid}
        for n in (name, override):
            if n:
                d["names"].add(" ".join(n.split()))
    try:
        async with session.begin_nested():
            for pid, alias in (await session.execute(
                text("SELECT player_id::text, alias_name FROM player_name_aliases WHERE player_id::text = ANY(:ids)"),
                {"ids": hidden_ids},
            )).fetchall():
                for d in by_person.values():
                    if pid in d["ids"] and alias:
                        d["names"].add(" ".join(alias.split()))
    except Exception:
        pass

    persons: list[Person] = []
    for d in by_person.values():
        person = Person()
        person.ids = {i.lower() for i in d["ids"] if i}
        for raw in d["names"]:
            person.own.add(raw.lower())
            pn = parse_name(raw)
            if not pn:
                continue
            first, last = pn
            others = await _other_players_with_surname(session, last)
            for kind, forms in forms_by_kind(first, last).items():
                for form in forms:
                    person.own.add(form.lower())
                    if _unambiguous(kind, first, others):
                        person.safe.add(form)
                    else:
                        person.ambiguous[form] = kind
            person.safe.add(raw) if _unambiguous("full", first, others) else person.ambiguous.setdefault(raw, "full")
        persons.append(person)
    return Scrubber(persons)


async def _other_players_with_surname(session, surname: str) -> list[Optional[str]]:
    """First names (None when the record holds only a surname) of every OTHER
    player at any club who shares this surname. Removed people are excluded."""
    rows = (await session.execute(text("""
        SELECT name, display_name_override FROM players
         WHERE privacy_hidden_at IS NULL
           AND (name ILIKE :a OR name ILIKE :b OR name ILIKE :c OR display_name_override ILIKE :a
                OR display_name_override ILIKE :b OR display_name_override ILIKE :c)
    """), {"a": f"%{surname}", "b": f"{surname},%", "c": f"% {surname} %"})).fetchall()
    out: list[Optional[str]] = []
    for name, override in rows:
        for raw in (name, override):
            pn = parse_name(raw or "")
            if pn and pn[1].lower() == surname.lower():
                out.append(pn[0])
    return out


def _unambiguous(kind: str, first: Optional[str], others: list[Optional[str]]) -> bool:
    """Can this form only mean the removed person, given who else shares the surname?"""
    if not others:
        return True
    if kind == "bare":
        return False
    mine_full = (first or "").rstrip(".").lower()
    mine_i = _initial(first or "").lower()
    for of in others:
        if of is None:
            return False                       # a record we cannot tell apart
        if kind == "full" and of.rstrip(".").lower() == mine_full:
            return False                       # the identical name
        if kind == "initial" and _initial(of).lower() == mine_i:
            return False                       # same surname, same initial
    return True


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


# A match scorecard: the one response where the ambiguous name forms can be
# resolved, because the card says who played.
_CARD_PATH_RE = re.compile(r"^/games/[^/]+/scorecard/?$")


def _scrub_card_json(scrubber: Scrubber, decoded: str) -> str:
    import json
    try:
        obj = json.loads(decoded)
    except ValueError:
        return decoded
    return json.dumps(scrubber.scrub_card(obj), ensure_ascii=False, separators=(",", ":"))


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

        held: dict = {"start": None, "chunks": [], "pass": False, "json": False}
        is_card = bool(_CARD_PATH_RE.match(scope.get("path", "") or ""))

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
                held["json"] = ctype.startswith("application/json")
                return
            if message["type"] == "http.response.body":
                held["chunks"].append(message.get("body", b""))
                if message.get("more_body"):
                    return
                body = b"".join(held["chunks"])
                try:
                    decoded = body.decode("utf-8")
                    if is_card and held["json"]:
                        decoded = _scrub_card_json(scrubber, decoded)
                    cleaned = scrubber.scrub(decoded).encode("utf-8")
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
