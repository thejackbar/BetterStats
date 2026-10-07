"""An online icon search for BetterPosts, through Iconify (api.iconify.design).

Iconify indexes open icon sets. The club's browser never talks to it: this module
does, so that

  * only sets whose licence lets a club put the artwork on its own post without a
    credit line are searched (``SETS``: Apache-2.0, MIT, ISC);
  * the answer is cached, so a popular search is one outbound request an hour and
    an icon is one request a day, however many clubs ask;
  * the outbound traffic is paced and bounded: one request in flight at a time,
    an eight second ceiling, and a per-club ceiling on searches and fetches a minute;
  * the picture the post stores comes from OUR origin, so the export (which cannot
    read another site's image) always works;
  * an SVG that carries script, event handlers, external references or embedded
    HTML is refused before it reaches a post.

Nothing here writes to the database.
"""
from __future__ import annotations

import asyncio
import re
import time
from collections import OrderedDict, defaultdict, deque

import httpx

BASE = "https://api.iconify.design"
TIMEOUT = 8.0
USER_AGENT = "BetterCricket-icon-search/1.0 (+https://betterat.cricket)"

# prefix -> (label, coloured, licence). `coloured` sets keep their own colours; the
# rest are single-colour and take the colour the editor asks for. Coloured sets
# are listed first because they read better on a poster.
SETS: "OrderedDict[str, tuple[str, bool, str]]" = OrderedDict([
    ("noto", ("Noto Emoji", True, "Apache-2.0")),
    ("fluent-emoji", ("Fluent Emoji", True, "MIT")),
    ("fluent-emoji-flat", ("Fluent Emoji Flat", True, "MIT")),
    ("ph", ("Phosphor", False, "MIT")),
    ("lucide", ("Lucide", False, "ISC")),
    ("tabler", ("Tabler", False, "MIT")),
    ("mdi", ("Material Design Icons", False, "Apache-2.0")),
])

# Club words that do not match an icon's own name. A search for the left side also
# searches the right.
SYNONYMS = {
    "pumpkin": ["jack-o-lantern"],
    "halloween": ["jack-o-lantern", "ghost", "skull", "spider-web", "bat"],
    "golf": ["flag-in-hole", "person-golfing", "golf"],
    "curry": ["curry-rice", "hot-pepper"],
    "party": ["party-popper", "confetti-ball", "balloon"],
    "quiz": ["brain", "question", "light-bulb"],
    "music": ["musical-note", "guitar", "microphone"],
    "band": ["guitar", "microphone", "drum"],
    "beer": ["beer-mug", "clinking-beer-mugs"],
    "bbq": ["cut-of-meat", "poultry-leg", "fire"],
    "christmas": ["christmas-tree", "santa-claus", "wrapped-gift"],
    "dinner": ["fork-and-knife-with-plate", "fork-and-knife"],
    "raffle": ["admission-tickets", "ticket"],
    "auction": ["hammer", "money-bag"],
    "presentation": ["trophy", "sports-medal", "1st-place-medal"],
    "training": ["person-running", "stopwatch", "whistle"],
    "nets": ["cricket-game", "cricket-bat-and-ball"],
    "junior": ["child", "baby", "balloon"],
    "kids": ["child", "balloon"],
    "social": ["clinking-glasses", "party-popper"],
    "meeting": ["speech-balloon", "busts-in-silhouette"],
    "working bee": ["hammer-and-wrench", "broom", "shovel"],
    "fundraiser": ["money-bag", "heart", "coin"],
    "sausage": ["hot-dog"],
}

# Phosphor ships six weights of every icon. One of each is enough for a picker.
_PH_WEIGHT = re.compile(r"-(bold|thin|light|fill|duotone)$")
_ID = re.compile(r"^([a-z0-9-]{1,40}):([a-z0-9][a-z0-9-]{0,80})$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_SVG_BYTES = 60_000
MAX_RESULTS = 60

SEARCHES_PER_MIN = 40
FETCHES_PER_MIN = 150


class IconError(Exception):
    """Carries a message a club can read."""


_cache: "OrderedDict[str, tuple[float, object]]" = OrderedDict()
_CACHE_MAX = 600
_hits: dict = defaultdict(deque)
_gate = asyncio.Semaphore(1)


def _cached(key, ttl):
    v = _cache.get(key)
    if v and time.monotonic() - v[0] < ttl:
        _cache.move_to_end(key)
        return v[1]
    return None


def _store(key, value):
    _cache[key] = (time.monotonic(), value)
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)


def _allow(club_key, kind, limit):
    q = _hits[(club_key, kind)]
    now = time.monotonic()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


async def _get(client: httpx.AsyncClient, url: str, params=None):
    # One request at a time, politely: the gate is process-wide.
    async with _gate:
        try:
            r = await client.get(url, params=params, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
        except (httpx.TimeoutException, httpx.TransportError) as e:
            raise IconError("The icon library did not answer. Try again in a moment.") from e
    if r.status_code == 404:
        raise IconError("That icon is not in the library.")
    if r.status_code >= 400:
        raise IconError("The icon library could not be reached right now.")
    return r


def split_id(icon_id: str) -> tuple[str, str]:
    m = _ID.match(icon_id or "")
    if not m or m.group(1) not in SETS:
        raise IconError("That icon is not from a set we search.")
    return m.group(1), m.group(2)


def _terms(q: str) -> list[str]:
    q = " ".join((q or "").lower().split())[:60]
    if not q:
        return []
    out = [q]
    for word in [q, *q.split()]:
        for s in SYNONYMS.get(word, []):
            if s not in out:
                out.append(s)
    return out[:6]


def _shape(icon_id: str) -> dict | None:
    prefix, name = split_id(icon_id)
    if prefix == "ph" and _PH_WEIGHT.search(name):
        return None
    label, coloured, _lic = SETS[prefix]
    return {"id": icon_id, "name": name.replace("-", " "), "set": label, "coloured": coloured}


async def search(club_key: str, query: str, limit: int = 48, client: httpx.AsyncClient | None = None) -> dict:
    terms = _terms(query)
    if not terms:
        return {"icons": [], "total": 0}
    limit = max(1, min(int(limit or 48), MAX_RESULTS))
    key = f"s:{limit}:{'|'.join(terms)}"
    hit = _cached(key, 3600)
    if hit is not None:
        return hit
    if not _allow(club_key, "search", SEARCHES_PER_MIN):
        raise IconError("That is a lot of searches in a minute. Wait a few seconds and try again.")
    own = client is None
    client = client or httpx.AsyncClient()
    try:
        found: list[str] = []
        for t in terms:
            r = await _get(client, f"{BASE}/search", {"query": t, "limit": 64, "prefixes": ",".join(SETS)})
            for i in r.json().get("icons", []):
                if i not in found:
                    found.append(i)
    finally:
        if own:
            await client.aclose()
    order = {p: n for n, p in enumerate(SETS)}

    def rank(i):
        p = i.split(":", 1)[0]
        return order.get(p, 99)

    icons = []
    for i in sorted(found, key=rank):  # stable: the library's own relevance order within a set
        try:
            s = _shape(i)
        except IconError:
            continue
        if s:
            icons.append(s)
        if len(icons) >= limit:
            break
    result = {"icons": icons, "total": len(icons)}
    _store(key, result)
    return result


_BAD_SVG = re.compile(r"<\s*(script|foreignObject|iframe|object|embed|style\b[^>]*@import)|\son[a-z]+\s*=|javascript:|data:text/html|<!ENTITY|<!DOCTYPE|xlink:href\s*=\s*[\"'](?!#)|href\s*=\s*[\"']https?:", re.I)


def clean_svg(body: str) -> str:
    body = (body or "").strip()
    if not body.startswith("<svg") or len(body.encode()) > MAX_SVG_BYTES:
        raise IconError("That icon could not be used.")
    if _BAD_SVG.search(body):
        raise IconError("That icon could not be used.")
    return body


async def svg(club_key: str, icon_id: str, color: str | None = None, client: httpx.AsyncClient | None = None) -> str:
    prefix, name = split_id(icon_id)
    coloured = SETS[prefix][1]
    color = color if color and _COLOR.match(color) and not coloured else None
    key = f"v:{icon_id}:{color or ''}"
    hit = _cached(key, 86400)
    if hit is not None:
        return hit
    if not _allow(club_key, "svg", FETCHES_PER_MIN):
        raise IconError("That is a lot of icons in a minute. Wait a few seconds and try again.")
    own = client is None
    client = client or httpx.AsyncClient()
    try:
        r = await _get(client, f"{BASE}/{prefix}/{name}.svg", {"color": color} if color else None)
    finally:
        if own:
            await client.aclose()
    body = clean_svg(r.text)
    _store(key, body)
    return body
