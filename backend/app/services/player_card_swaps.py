"""Player Cards: swapping cards between two players of a club.

The rules, kept small on purpose:

* ANY card a player holds can be offered, a single copy as well as a double. What a swap cannot do is take
  away a player's own card: it is theirs without a row, so there is nothing to hand over, and only the extra
  copies of it they have pulled can go. `tradeable()` is the one definition.
* A request is any number of cards each way (a card at a time, or several copies of one), from one player to
  one other: one card for four of theirs, or six for two. Nothing moves until the person asked accepts, and
  the check that both players still hold every card is made again at that moment, under row locks, because
  either of them may have swapped since the request was made. It is all or nothing: if any one card has gone,
  none moves.
* Requests expire after `SWAP_DAYS` (read from the age, nothing is stored), a player may have
  `MAX_OUTGOING` open at once, and a request is never deleted: it ends accepted, declined or cancelled.
* Another player can see the cards a person could offer, a card at a time. Nobody can see how many copies
  they hold, or anything about their packs.
* Both people are known by the same PIN cookie as the rest of the page (no separate sign-in); the safeguard is
  that nothing happens without the second person's yes.

A card is named by a key: `p:<player id>` for a regular card, `s:<special card id>` for a special one.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation, Player
from app.services import player_cards as cards

SWAP_DAYS = 14
MAX_OUTGOING = 10
RECENT_SHOWN = 15
RECENT_DAYS = 30
MAX_CARDS = 50   # different cards on one side of a request
MAX_COPIES = 99  # copies of one card


class SwapError(Exception):
    """A refusal the player can read. `status` is the HTTP code the route answers with."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.status = status


Card = tuple[str, Optional[str]]  # (subject player id, special card id or None)


def parse_key(key: str) -> Card:
    try:
        kind, _, ident = (key or "").partition(":")
        uuid.UUID(ident)
    except (ValueError, AttributeError):
        raise SwapError("That card could not be found.", 422)
    if kind == "p":
        return ident, None
    if kind == "s":
        return "", ident  # the subject is read off the special card itself
    raise SwapError("That card could not be found.", 422)


def key_of(subject: str, special_id: Optional[str]) -> str:
    return f"s:{special_id}" if special_id else f"p:{subject}"


def tradeable(owner: str, card: Card, rows: int) -> int:
    """How many copies of `card` the owner could part with: every row they hold. A player's own card is
    theirs without a row, so it never counts, and only the copies of it they have pulled can go."""
    return max(rows, 0)


async def _rows_by_card(db: AsyncSession, org_id, owner: Optional[str] = None) -> dict[str, dict[Card, int]]:
    """`{owner: {(subject, special_id): rows held}}` for the club (or one owner)."""
    owner_sql = " AND owner_player_id = CAST(:o AS UUID)" if owner else ""
    res = await db.execute(text(
        "SELECT owner_player_id::text, subject_player_id::text, special_id::text, COUNT(*) "
        "FROM player_card_copies WHERE organisation_id = CAST(:org AS UUID)" + owner_sql +
        " GROUP BY owner_player_id, subject_player_id, special_id"
    ), {"org": str(org_id), **({"o": owner} if owner else {})})
    out: dict[str, dict[Card, int]] = {}
    for o, subject, special_id, n in res.fetchall():
        out.setdefault(o, {})[(subject, special_id)] = int(n)
    return out


async def _special_subjects(db: AsyncSession, org_id, special_ids: list[str]) -> dict[str, dict]:
    return await cards._specials_by_id(db, org_id, special_ids)


def _payload(snap: dict, card: Card, specials: dict[str, dict]) -> Optional[dict]:
    subject, special_id = card
    if special_id:
        row = specials.get(special_id)
        return cards.special_card(snap, row) if row else None
    return cards.regular_card(snap, subject)


async def _resolve(db: AsyncSession, org_id, snap: dict, key: str) -> tuple[Card, dict]:
    """The card a key names, as (card, payload), or a refusal. A card whose player is out of the pool is
    not tradeable."""
    subject, special_id = parse_key(key)
    specials = await _special_subjects(db, org_id, [special_id] if special_id else [])
    if special_id:
        row = specials.get(special_id)
        if not row:
            raise SwapError("That card could not be found.", 404)
        subject = str(row["player_id"])
    card: Card = (subject, special_id)
    payload = _payload(snap, card, specials)
    if payload is None:
        raise SwapError("That card is not available to swap.", 409)
    return card, payload


async def tradeable_cards(db: AsyncSession, club: Organisation, snap: dict, owner: str) -> list[dict]:
    """The cards the owner could offer, as payloads, each with `tradeable` (how many copies could go)."""
    held = (await _rows_by_card(db, club.id, owner)).get(owner, {})
    wanted = {c: tradeable(owner, c, n) for c, n in held.items()}
    wanted = {c: n for c, n in wanted.items() if n > 0}
    specials = await _special_subjects(db, club.id, [c[1] for c in wanted if c[1]])
    out = []
    for card, n in wanted.items():
        payload = _payload(snap, card, specials)
        if payload:
            out.append({**payload, "tradeable": n, "key": key_of(*card)})
    out.sort(key=lambda c: (c["kind"] != "special", (c.get("name") or "")))
    return out


async def swap_people(db: AsyncSession, club: Organisation, snap: dict, me: str) -> list[dict]:
    """Who has cards to offer: `[{player_id, name, tradeable}]`, for the players in the pool."""
    everyone = await _rows_by_card(db, club.id)
    out = []
    for owner, held in everyone.items():
        if owner == me or owner not in snap["people"]:
            continue
        n = sum(tradeable(owner, c, rows) for c, rows in held.items()
                if (c[1] or c[0] in snap["people"]))
        if n > 0:
            out.append({"player_id": owner, "name": snap["people"][owner]["display_name"], "tradeable": n})
    out.sort(key=lambda p: p["name"].lower())
    return out


FIND_MAX = 30   # cards one search returns
FIND_MIN = 2    # shortest search


def _tokens(q: str) -> list[str]:
    return [t for t in (q or "").lower().replace(",", " ").split() if t]


async def find_cards(db: AsyncSession, club: Organisation, snap: dict, me: str, q: str) -> dict:
    """Cards matching a search (a player's name, a special card's title or kind, a season or grade), each with who
    holds copies that could be swapped: `{cards: [{...card, holders: [{player_id, name, tradeable}]}], unheld: [names]}`.
    Only players in the pool are listed as holders, never the asker, and never how many copies a person holds
    beyond what could go. `unheld` names matching players nobody holds a card of yet."""
    tokens = _tokens(q)
    if not tokens or sum(len(t) for t in tokens) < FIND_MIN:
        raise SwapError(f"Type at least {FIND_MIN} letters to search.", 422)
    everyone = await _rows_by_card(db, club.id)
    holders: dict[Card, list[dict]] = {}
    for owner, held in everyone.items():
        if owner == me or owner not in snap["people"]:
            continue
        for card, rows in held.items():
            n = tradeable(owner, card, rows)
            if n > 0 and (card[1] or card[0] in snap["people"]):
                holders.setdefault(card, []).append({"player_id": owner, "name": snap["people"][owner]["display_name"], "tradeable": n})
    special_ids = [c[1] for c in holders if c[1]]
    specials: dict[str, dict] = {}
    if special_ids:
        rows = await db.execute(text(
            "SELECT id::text AS id, player_id::text AS player_id, kind, title, occurred_on, detail FROM player_special_cards "
            "WHERE organisation_id = CAST(:o AS UUID) AND id = ANY(CAST(:ids AS uuid[]))"
        ), {"o": str(club.id), "ids": special_ids})
        specials = {r["id"]: dict(r) for r in rows.mappings()}

    def haystack(card: Card) -> str:
        subject, special_id = card
        if special_id:
            row = specials.get(special_id) or {}
            detail = row.get("detail") or {}
            extra = " ".join(str(detail.get(k) or "") for k in ("season", "grade", "opposition"))
            name = (snap["people"].get(str(row.get("player_id"))) or {}).get("display_name", "")
            return f"{name} {row.get('title') or ''} {cards.SPECIAL_KINDS.get(row.get('kind'), '')} {extra}".lower()
        return (snap["people"].get(subject) or {}).get("display_name", "").lower()

    found = [c for c in holders if all(t in haystack(c) for t in tokens)]
    out = []
    for card in found:
        payload = _payload(snap, card, specials)
        if payload:
            hs = sorted(holders[card], key=lambda h: h["name"].lower())
            out.append({**payload, "key": key_of(*card), "holders": hs, "tradeable": max(h["tradeable"] for h in hs)})
    # Players first (best tier first), then special cards by name; a stable order a search can be re-run into.
    rank = {"legendary": 0, "epic": 1, "rare": 2, "common": 3}
    out.sort(key=lambda c: (c["kind"] == "special", rank.get(c.get("tier"), 4) if c["kind"] != "special" else 0, (c.get("name") or "").lower(), c.get("title") or ""))
    unheld = sorted(
        p["display_name"] for pid, p in snap["people"].items()
        if pid != me and all(t in p["display_name"].lower() for t in tokens) and (pid, None) not in holders
    )
    return {"cards": out[:FIND_MAX], "more": max(0, len(out) - FIND_MAX), "unheld": unheld[:5]}


def _live_sql(alias: str = "s") -> str:
    return f"({alias}.status = 'pending' AND {alias}.created_at > NOW() - INTERVAL '{SWAP_DAYS} days')"


Item = tuple[Card, int]  # (card, how many copies)


async def _items_of(db: AsyncSession, swap_ids: list[str]) -> dict[str, dict[str, list[Item]]]:
    """`{swap id: {"give": [(card, qty)], "want": [...]}}`, in a steady order."""
    out: dict[str, dict[str, list[Item]]] = {i: {"give": [], "want": []} for i in swap_ids}
    if not swap_ids:
        return out
    rows = (await db.execute(text(
        "SELECT swap_id::text, side, subject_player_id::text, special_id::text, qty FROM player_card_swap_items "
        "WHERE swap_id = ANY(CAST(:ids AS uuid[])) ORDER BY side, special_id NULLS FIRST, subject_player_id"
    ), {"ids": swap_ids})).fetchall()
    for sid, side, subject, special_id, qty in rows:
        if side in ("give", "want"):
            out[sid][side].append(((subject, special_id), int(qty)))
    return out


async def _parse_items(db: AsyncSession, club: Organisation, snap: dict, raw) -> list[Item]:
    """The cards one side of a request names, as `[{key, qty}]`. A card named twice is added up."""
    if not isinstance(raw, list) or not raw:
        raise SwapError("Pick at least one card on each side.", 422)
    wanted: dict[Card, int] = {}
    for entry in raw:
        key = entry.get("key") if isinstance(entry, dict) else entry
        try:
            qty = int(entry.get("qty", 1)) if isinstance(entry, dict) else 1
        except (TypeError, ValueError):
            raise SwapError("That quantity is not a number.", 422)
        if qty < 1 or qty > MAX_COPIES:
            raise SwapError(f"Swap between 1 and {MAX_COPIES} copies of a card.", 422)
        card, _ = await _resolve(db, club.id, snap, key)
        wanted[card] = wanted.get(card, 0) + qty
    if len(wanted) > MAX_CARDS:
        raise SwapError(f"A swap can carry up to {MAX_CARDS} different cards on each side.", 422)
    return list(wanted.items())


def _signature(give: list[Item], want: list[Item]) -> tuple:
    return (tuple(sorted(((c, n) for c, n in give), key=repr)), tuple(sorted(((c, n) for c, n in want), key=repr)))


async def waiting_count(db: AsyncSession, me: str) -> int:
    return int((await db.execute(text(
        "SELECT COUNT(*) FROM player_card_swaps s WHERE s.to_player_id = CAST(:me AS UUID) AND " + _live_sql()
    ), {"me": me})).scalar() or 0)


async def list_swaps(db: AsyncSession, club: Organisation, snap: dict, me: str) -> dict:
    rows = (await db.execute(text(f"""
        SELECT s.id::text AS id, s.from_player_id::text AS from_id, s.to_player_id::text AS to_id,
               s.status, s.created_at, s.resolved_at, {_live_sql()} AS live
          FROM player_card_swaps s
         WHERE s.organisation_id = CAST(:org AS UUID)
           AND (s.from_player_id = CAST(:me AS UUID) OR s.to_player_id = CAST(:me AS UUID))
           AND (s.status = 'pending' OR s.created_at > NOW() - INTERVAL '{RECENT_DAYS} days')
         ORDER BY s.created_at DESC
    """), {"org": str(club.id), "me": me})).mappings().all()
    items = await _items_of(db, [r["id"] for r in rows])
    special_ids = [c[1] for sides in items.values() for side in sides.values() for c, _ in side if c[1]]
    specials = await _special_subjects(db, club.id, special_ids)

    def cards_of(r, side) -> Optional[list[dict]]:
        """The cards on a side, or None if any of them can no longer be drawn (out of the pool)."""
        out = []
        for card, qty in items[r["id"]][side]:
            payload = _payload(snap, card, specials)
            if payload is None:
                return None
            out.append({**payload, "qty": qty, "key": key_of(*card)})
        return out

    def shape(r):
        outgoing = r["from_id"] == me
        other = r["to_id"] if outgoing else r["from_id"]
        status = r["status"] if (r["status"] != "pending" or r["live"]) else "expired"
        return {
            "id": r["id"], "direction": "out" if outgoing else "in", "status": status,
            "other": {"player_id": other, "name": (snap["people"].get(other) or {}).get("display_name") or "A player"},
            "give": cards_of(r, "give"), "want": cards_of(r, "want"),
            "created_at": r["created_at"].isoformat(), "resolved_at": r["resolved_at"].isoformat() if r["resolved_at"] else None,
        }

    shaped = [shape(r) for r in rows]
    live = [s for s in shaped if s["status"] == "pending"]
    return {
        "incoming": [s for s in live if s["direction"] == "in" and s["give"] and s["want"]],
        "outgoing": [s for s in live if s["direction"] == "out" and s["give"] and s["want"]],
        "recent": [s for s in shaped if s["status"] not in ("pending", "expired")][:RECENT_SHOWN],
    }


async def create_swap(db: AsyncSession, club: Organisation, snap: dict, me: str, to_id: str, give_raw, want_raw) -> str:
    """`give_raw` and `want_raw` are lists of `{key, qty}`."""
    if to_id == me or to_id not in snap["people"]:
        raise SwapError("That player is not available to swap with.", 404)
    give = await _parse_items(db, club, snap, give_raw)
    want = await _parse_items(db, club, snap, want_raw)
    if {c for c, _ in give} & {c for c, _ in want}:
        raise SwapError("A card cannot be on both sides of a swap.", 422)
    mine = (await _rows_by_card(db, club.id, me)).get(me, {})
    for card, qty in give:
        if tradeable(me, card, mine.get(card, 0)) < qty:
            raise SwapError("You can only offer cards you hold, and no more copies than you have.")
    theirs = (await _rows_by_card(db, club.id, to_id)).get(to_id, {})
    for card, qty in want:
        if tradeable(to_id, card, theirs.get(card, 0)) < qty:
            raise SwapError("They no longer have all of those cards.")
    open_out = int((await db.execute(text(
        "SELECT COUNT(*) FROM player_card_swaps s WHERE s.from_player_id = CAST(:me AS UUID) AND " + _live_sql()
    ), {"me": me})).scalar() or 0)
    if open_out >= MAX_OUTGOING:
        raise SwapError(f"You have {MAX_OUTGOING} swap requests open already. Cancel one or wait for an answer.")
    live = (await db.execute(text(
        "SELECT s.id::text FROM player_card_swaps s WHERE s.from_player_id = CAST(:me AS UUID) "
        "AND s.to_player_id = CAST(:to AS UUID) AND " + _live_sql()
    ), {"me": me, "to": to_id})).scalars().all()
    if live:
        mine_sig = _signature(give, want)
        for sid, sides in (await _items_of(db, list(live))).items():
            if _signature(sides["give"], sides["want"]) == mine_sig:
                raise SwapError("You have already asked them for that swap.")
    new_id = (await db.execute(text("""
        INSERT INTO player_card_swaps (organisation_id, from_player_id, to_player_id)
        VALUES (CAST(:org AS UUID), CAST(:me AS UUID), CAST(:to AS UUID))
        RETURNING id::text
    """), {"org": str(club.id), "me": me, "to": to_id})).scalar()
    for side, side_items in (("give", give), ("want", want)):
        for (subject, special_id), qty in side_items:
            await db.execute(text("""
                INSERT INTO player_card_swap_items (organisation_id, swap_id, side, subject_player_id, special_id, qty)
                VALUES (CAST(:org AS UUID), CAST(:sw AS UUID), :side, CAST(:s AS UUID), CAST(:sp AS UUID), :q)
            """), {"org": str(club.id), "sw": new_id, "side": side, "s": subject, "sp": special_id, "q": qty})
    return new_id


async def _lock_copies(db: AsyncSession, org_id, owner: str, card: Card) -> list[str]:
    """Lock the owner's copies of a card and return the ids of those that can go, a pulled copy before a gifted
    one. Fewer than the quantity asked for means the owner no longer holds enough."""
    rows = (await db.execute(text("""
        SELECT id::text FROM player_card_copies
         WHERE organisation_id = CAST(:org AS UUID) AND owner_player_id = CAST(:o AS UUID)
           AND subject_player_id = CAST(:s AS UUID) AND special_id IS NOT DISTINCT FROM CAST(:sp AS UUID)
         ORDER BY (source = 'gift') ASC, obtained_at DESC, id
         FOR UPDATE
    """), {"org": str(org_id), "o": owner, "s": card[0], "sp": card[1]})).fetchall()
    n = tradeable(owner, card, len(rows))
    return [r[0] for r in rows][:n]


async def respond(db: AsyncSession, club: Organisation, snap: dict, me: str, swap_id: str, action: str) -> str:
    """Accept, decline (the person asked) or cancel (the person who asked). Returns the new status."""
    if action not in ("accept", "decline", "cancel"):
        raise SwapError("Unknown action.", 422)
    try:
        uuid.UUID(swap_id)
    except ValueError:
        raise SwapError("That swap could not be found.", 404)
    s = (await db.execute(text(f"""
        SELECT s.from_player_id::text AS from_id, s.to_player_id::text AS to_id,
               {_live_sql()} AS live, s.status
          FROM player_card_swaps s
         WHERE s.id = CAST(:id AS UUID) AND s.organisation_id = CAST(:org AS UUID)
           AND (s.from_player_id = CAST(:me AS UUID) OR s.to_player_id = CAST(:me AS UUID))
         FOR UPDATE
    """), {"id": swap_id, "org": str(club.id), "me": me})).mappings().first()
    if not s:
        raise SwapError("That swap could not be found.", 404)
    if s["status"] != "pending":
        raise SwapError("That swap has already been dealt with.")
    if not s["live"]:
        raise SwapError("That swap request has expired.")
    if action == "cancel":
        if s["from_id"] != me:
            raise SwapError("Only the person who asked can cancel it.", 403)
        new = "cancelled"
    elif action == "decline":
        if s["to_id"] != me:
            raise SwapError("Only the person asked can decline it.", 403)
        new = "declined"
    else:
        if s["to_id"] != me:
            raise SwapError("Only the person asked can accept it.", 403)
        sides = (await _items_of(db, [swap_id]))[swap_id]
        if not sides["give"] or not sides["want"]:
            raise SwapError("That swap has no cards in it, so it cannot go ahead.")
        # [(owner, new owner, [(card, qty)])]: what each of them hands over.
        legs = [(s["from_id"], s["to_id"], sides["give"]), (s["to_id"], s["from_id"], sides["want"])]
        for owner, _, items in legs:
            if owner not in snap["people"] or any(c[1] is None and c[0] not in snap["people"] for c, _ in items):
                raise SwapError("One of those players, or a player on one of the cards, is no longer in the card pool, so this swap cannot go ahead.")
        # Lock in a fixed order (lower player id first, and each person's cards in a fixed order) so two swaps
        # over the same cards cannot deadlock. Nothing moves until every card is found.
        found: dict[tuple[str, Card], list[str]] = {}
        for owner, _, items in sorted(legs, key=lambda leg: leg[0]):
            for card, _qty in sorted(items, key=lambda it: repr(it[0])):
                found[(owner, card)] = await _lock_copies(db, club.id, owner, card)
        for owner, _, items in legs:
            if any(len(found[(owner, card)]) < qty for card, qty in items):
                if owner == s["from_id"]:
                    raise SwapError("Some of the cards they offered are no longer theirs to give, so this swap cannot go ahead. You can decline it.")
                raise SwapError("Some of the cards they asked for are no longer yours to give, so this swap cannot go ahead. You can decline it.")
        for owner, new_owner, items in legs:
            for card, qty in items:
                await db.execute(text(
                    "UPDATE player_card_copies SET owner_player_id = CAST(:new AS UUID), source = 'swap', obtained_at = NOW() "
                    "WHERE id = ANY(CAST(:ids AS uuid[]))"
                ), {"new": new_owner, "ids": found[(owner, card)][:qty]})
        new = "accepted"
    await db.execute(text(
        "UPDATE player_card_swaps SET status = :st, resolved_at = NOW() WHERE id = CAST(:id AS UUID)"
    ), {"st": new, "id": swap_id})
    return new
