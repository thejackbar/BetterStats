"""Player Cards: the club's whole set of cards, for a player to look through.

Every card that can come out of a pack (a card for each player in the pool who has a match, and every special card of a
player in the pool), laid out as the book lays out a player's own collection: the players first, then the special cards
filed by category, one player's cards of one kind on one slot (a stack). A player does not have to hold a card to see it,
and no swap has to be started. Each card says how many OTHER players hold a copy that could be swapped, and
`holders_of` names them. A person's holdings beyond what could go, and their packs, are never shown.

The page is built on the server because a club can have tens of thousands of special cards: the list is grouped and
ordered from light rows, and only the cards on the page asked for are built in full.
"""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation
from app.services import player_card_swaps as swaps, player_cards as cards

PAGE_MAX = 36
STACK_MAX = 100  # cards sent for one opened stack; `count` is always the true number

# The order special cards are filed in. Mirrors CATEGORIES in components/cards/CardGallery.jsx.
CATEGORIES = [
    ("awards", ["award"]),
    ("milestones", ["games", "runs_milestone", "wickets_milestone", "dismissals_milestone"]),
    ("centuries", ["century"]),
    ("fifties", ["fifty"]),
    ("wickets", ["five_for", "hat_trick"]),
    ("debuts", ["debut"]),
]
CAT_OF = {k: cat for cat, kinds in CATEGORIES for k in kinds}
_MILESTONE_ORDER = ["games", "runs_milestone", "wickets_milestone", "dismissals_milestone"]
_TIER_RANK = {"legendary": 0, "epic": 1, "rare": 2, "common": 3}
SORTS = ("recent", "name", "rarity", "matches", "runs", "bat_avg", "wickets", "bowl_avg", "dismissals")


def _surname(name: str) -> str:
    name = (name or "").strip().lower()
    return name.split(",")[0].strip() if "," in name else (name.split(" ")[-1] if name else "")


def _player_sort(sort: str):
    """A key for a list of player cards. A missing figure always goes last, whichever way the sort runs."""
    if sort in ("matches", "runs", "bat_avg", "wickets", "dismissals", "bowl_avg"):
        sign = 1 if sort == "bowl_avg" else -1  # a lower bowling average is the better one
        return lambda c: (c.get(sort) is None, sign * (c.get(sort) or 0), _surname(c["name"]), c["name"].lower())
    if sort == "name":
        return lambda c: (_surname(c["name"]), c["name"].lower())
    # rarity, and "recent" (a player's card has no date, so the best come first)
    return lambda c: (_TIER_RANK.get(c.get("tier"), 4), -(c.get("rarity") or 0), _surname(c["name"]))


def _milestone_value(detail: dict) -> int:
    try:
        return int((detail or {}).get("threshold") or (detail or {}).get("games") or 0)
    except (TypeError, ValueError):
        return 0


def _event_key(row: dict):
    """Inside a stack: milestones in order (games, runs, wickets, dismissals, smallest step first), else newest first."""
    detail = row["detail"] or {}
    if row["kind"] in _MILESTONE_ORDER:
        return (0, _MILESTONE_ORDER.index(row["kind"]), _milestone_value(detail), "")
    when = row["occurred_on"].isoformat() if row["occurred_on"] else ""
    return (1, 0, 0, "".join(chr(0x10FFFF - ord(ch)) for ch in when) + (row["title"] or ""))  # newest date first, then title


def _matches(words: list[str], *parts: str) -> bool:
    hay = " ".join(p for p in parts if p).lower()
    return all(w in hay for w in words)


async def _holder_map(db: AsyncSession, club: Organisation, snap: dict, me: str) -> dict[tuple, list[dict]]:
    """`{(subject, special id): [{player_id, name, tradeable}]}`: who could swap a copy, never the asker."""
    everyone = await swaps._rows_by_card(db, club.id)
    out: dict[tuple, list[dict]] = {}
    for owner, held in everyone.items():
        if owner == me or owner not in snap["people"]:
            continue
        for card, rows in held.items():
            n = swaps.tradeable(owner, card, rows)
            if n > 0 and (card[1] or card[0] in snap["people"]):
                out.setdefault(card, []).append({"player_id": owner, "name": snap["people"][owner]["display_name"], "tradeable": n})
    return out


async def page(db: AsyncSession, club: Organisation, snap: dict, me: str, *, filter: str = "all", sort: str = "rarity",
               q: str = "", offset: int = 0, limit: int = 12) -> dict:
    """One window of the book. `filter` is all, regular, special or a category key. Returns `{total, counts, items}`
    where an item is a card or, for a player's several cards of one category, a stack `{stack, key, cat, cards, name, count}`."""
    limit = max(1, min(int(limit or 12), PAGE_MAX))
    offset = max(0, int(offset or 0))
    words = [w for w in (q or "").lower().replace(",", " ").split() if w][:6]
    holders = await _holder_map(db, club, snap, me)
    mine = (await swaps._rows_by_card(db, club.id, me)).get(me, {})

    def decorate(card: dict, key: tuple) -> dict:
        hs = holders.get(key, [])
        return {**card, "others": len(hs), "mine_copies": mine.get(key, 0) + (1 if key == (me, None) else 0)}

    # Player cards.
    players = []
    for pid, f in snap["figs"].items():
        if f["matches"] <= 0 or pid not in snap["people"]:
            continue
        c = cards.regular_card(snap, pid)
        if c and (not words or _matches(words, c["name"])):
            players.append(c)
    players.sort(key=_player_sort(sort))

    # Special cards, from light rows: grouped by category and player before anything is built.
    rows = (await db.execute(text(
        "SELECT id, player_id, kind, title, occurred_on, detail, created_at FROM player_special_cards "
        "WHERE organisation_id = CAST(:o AS UUID)"), {"o": str(club.id)})).mappings().all()
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        pid = str(r["player_id"])
        person = snap["people"].get(pid)
        cat = CAT_OF.get(r["kind"])
        if not person or not cat:
            continue
        if words:
            d = r["detail"] or {}
            if not _matches(words, person["display_name"], r["title"], cards.SPECIAL_KINDS.get(r["kind"], ""),
                            str(d.get("season") or ""), str(d.get("grade") or "")):
                continue
        groups.setdefault((cat, pid), []).append(dict(r))

    counts = {"regular": len(players), "special": sum(len(v) for v in groups.values())}
    for cat, _kinds in CATEGORIES:
        counts[cat] = sum(len(v) for (c, _p), v in groups.items() if c == cat)

    want_players = filter in ("all", "regular")
    want_cat = filter if filter in dict(CATEGORIES) else None
    want_specials = filter in ("all", "special") or want_cat is not None
    plan: list[tuple] = []  # ("p", card) or ("g", cat, pid, rows)
    if want_players:
        plan += [("p", c) for c in players]
    if want_specials:
        for cat, _kinds in CATEGORIES:
            if want_cat and want_cat != cat:
                continue
            mine_first = lambda pid: 0 if pid == me else 1
            if sort == "recent":
                order = sorted(((p, v) for (c, p), v in groups.items() if c == cat),
                               key=lambda pv: (mine_first(pv[0]), "".join(chr(0x10FFFF - ord(ch)) for ch in max(str(x["created_at"]) for x in pv[1]))))
            else:
                order = sorted(((p, v) for (c, p), v in groups.items() if c == cat),
                               key=lambda pv: (mine_first(pv[0]), _surname(snap["people"][pv[0]]["display_name"]), snap["people"][pv[0]]["display_name"].lower()))
            plan += [("g", cat, p, v) for p, v in order]

    total = len(plan)
    items: list[dict] = []
    for entry in plan[offset:offset + limit]:
        if entry[0] == "p":
            items.append(decorate(entry[1], (entry[1]["player_id"], None)))
            continue
        _g, cat, pid, grows = entry
        grows = sorted(grows, key=_event_key)
        built = []
        for r in grows[:STACK_MAX]:
            c = cards.special_card(snap, r)
            if c:
                c["obtained_at"] = r["created_at"].isoformat() if r["created_at"] else None
                built.append(decorate(c, (pid, str(r["id"]))))
        if not built:
            continue
        if len(grows) == 1:
            items.append(built[0])
        else:
            items.append({"stack": True, "key": f"stack:{cat}:{pid}", "cat": cat, "cards": built, "name": built[0]["name"], "count": len(grows)})
    return {"total": total, "counts": counts, "items": items, "offset": offset, "limit": limit}


async def holders_of(db: AsyncSession, club: Organisation, snap: dict, me: str, key: str) -> dict:
    """Who could swap a copy of one card, and how many copies the asker holds of it."""
    card, payload = await swaps._resolve(db, club.id, snap, key)
    holders = (await _holder_map(db, club, snap, me)).get(card, [])
    mine = (await swaps._rows_by_card(db, club.id, me)).get(me, {})
    return {
        "card": {**payload, "key": key}, "holders": sorted(holders, key=lambda h: h["name"].lower()),
        "mine_copies": mine.get(card, 0) + (1 if card == (me, None) else 0),
    }
