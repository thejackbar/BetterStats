"""Player Cards: swapping cards between two players of a club.

The rules, kept small on purpose:

* ANY card a player holds can be offered, a single copy as well as a double. What a swap cannot do is take
  away a player's own card: it is theirs without a row, so there is nothing to hand over, and only the extra
  copies of it they have pulled can go. `tradeable()` is the one definition.
* A request is one card for one card, from one player to one other. Nothing moves until the person asked
  accepts, and the check that both players still hold their card is made again at that moment, under row
  locks, because either of them may have swapped since the request was made.
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


def _live_sql(alias: str = "s") -> str:
    return f"({alias}.status = 'pending' AND {alias}.created_at > NOW() - INTERVAL '{SWAP_DAYS} days')"


async def waiting_count(db: AsyncSession, me: str) -> int:
    return int((await db.execute(text(
        "SELECT COUNT(*) FROM player_card_swaps s WHERE s.to_player_id = CAST(:me AS UUID) AND " + _live_sql()
    ), {"me": me})).scalar() or 0)


async def list_swaps(db: AsyncSession, club: Organisation, snap: dict, me: str) -> dict:
    rows = (await db.execute(text(f"""
        SELECT s.id::text AS id, s.from_player_id::text AS from_id, s.to_player_id::text AS to_id,
               s.give_subject_player_id::text AS give_subject, s.give_special_id::text AS give_special,
               s.want_subject_player_id::text AS want_subject, s.want_special_id::text AS want_special,
               s.status, s.created_at, s.resolved_at, {_live_sql()} AS live
          FROM player_card_swaps s
         WHERE s.organisation_id = CAST(:org AS UUID)
           AND (s.from_player_id = CAST(:me AS UUID) OR s.to_player_id = CAST(:me AS UUID))
           AND (s.status = 'pending' OR s.created_at > NOW() - INTERVAL '{RECENT_DAYS} days')
         ORDER BY s.created_at DESC
    """), {"org": str(club.id), "me": me})).mappings().all()
    special_ids = [r[k] for r in rows for k in ("give_special", "want_special") if r[k]]
    specials = await _special_subjects(db, club.id, special_ids)

    def card_of(r, side):
        return _payload(snap, (r[f"{side}_subject"], r[f"{side}_special"]), specials)

    def shape(r):
        outgoing = r["from_id"] == me
        other = r["to_id"] if outgoing else r["from_id"]
        status = r["status"] if (r["status"] != "pending" or r["live"]) else "expired"
        return {
            "id": r["id"], "direction": "out" if outgoing else "in", "status": status,
            "other": {"player_id": other, "name": (snap["people"].get(other) or {}).get("display_name") or "A player"},
            "give": card_of(r, "give"), "want": card_of(r, "want"),
            "created_at": r["created_at"].isoformat(), "resolved_at": r["resolved_at"].isoformat() if r["resolved_at"] else None,
        }

    shaped = [shape(r) for r in rows]
    live = [s for s in shaped if s["status"] == "pending"]
    return {
        "incoming": [s for s in live if s["direction"] == "in" and s["give"] and s["want"]],
        "outgoing": [s for s in live if s["direction"] == "out" and s["give"] and s["want"]],
        "recent": [s for s in shaped if s["status"] not in ("pending", "expired")][:RECENT_SHOWN],
    }


async def create_swap(db: AsyncSession, club: Organisation, snap: dict, me: str, to_id: str, give_key: str, want_key: str) -> str:
    if to_id == me or to_id not in snap["people"]:
        raise SwapError("That player is not available to swap with.", 404)
    give, _ = await _resolve(db, club.id, snap, give_key)
    want, _ = await _resolve(db, club.id, snap, want_key)
    if give == want:
        raise SwapError("Pick two different cards.", 422)
    mine = (await _rows_by_card(db, club.id, me)).get(me, {})
    if tradeable(me, give, mine.get(give, 0)) < 1:
        raise SwapError("You can only offer a card you hold.")
    theirs = (await _rows_by_card(db, club.id, to_id)).get(to_id, {})
    if tradeable(to_id, want, theirs.get(want, 0)) < 1:
        raise SwapError("They no longer have that card.")
    open_out = int((await db.execute(text(
        "SELECT COUNT(*) FROM player_card_swaps s WHERE s.from_player_id = CAST(:me AS UUID) AND " + _live_sql()
    ), {"me": me})).scalar() or 0)
    if open_out >= MAX_OUTGOING:
        raise SwapError(f"You have {MAX_OUTGOING} swap requests open already. Cancel one or wait for an answer.")
    same = (await db.execute(text(
        "SELECT 1 FROM player_card_swaps s WHERE s.from_player_id = CAST(:me AS UUID) AND s.to_player_id = CAST(:to AS UUID) "
        "AND s.give_subject_player_id = CAST(:gs AS UUID) AND s.give_special_id IS NOT DISTINCT FROM CAST(:gsp AS UUID) "
        "AND s.want_subject_player_id = CAST(:ws AS UUID) AND s.want_special_id IS NOT DISTINCT FROM CAST(:wsp AS UUID) "
        "AND " + _live_sql() + " LIMIT 1"
    ), {"me": me, "to": to_id, "gs": give[0], "gsp": give[1], "ws": want[0], "wsp": want[1]})).first()
    if same:
        raise SwapError("You have already asked them for that swap.")
    new_id = (await db.execute(text("""
        INSERT INTO player_card_swaps (organisation_id, from_player_id, to_player_id,
            give_subject_player_id, give_special_id, want_subject_player_id, want_special_id)
        VALUES (CAST(:org AS UUID), CAST(:me AS UUID), CAST(:to AS UUID), CAST(:gs AS UUID), CAST(:gsp AS UUID),
                CAST(:ws AS UUID), CAST(:wsp AS UUID))
        RETURNING id::text
    """), {"org": str(club.id), "me": me, "to": to_id, "gs": give[0], "gsp": give[1], "ws": want[0], "wsp": want[1]})).scalar()
    return new_id


async def _lock_copy(db: AsyncSession, org_id, owner: str, card: Card) -> Optional[str]:
    """Lock the owner's copies of a card and return the id of one that can go, or None if they hold none.
    A pulled copy goes before a gifted one."""
    rows = (await db.execute(text("""
        SELECT id::text FROM player_card_copies
         WHERE organisation_id = CAST(:org AS UUID) AND owner_player_id = CAST(:o AS UUID)
           AND subject_player_id = CAST(:s AS UUID) AND special_id IS NOT DISTINCT FROM CAST(:sp AS UUID)
         ORDER BY (source = 'gift') ASC, obtained_at DESC
         FOR UPDATE
    """), {"org": str(org_id), "o": owner, "s": card[0], "sp": card[1]})).fetchall()
    if tradeable(owner, card, len(rows)) < 1:
        return None
    return rows[0][0]


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
               s.give_subject_player_id::text AS gs, s.give_special_id::text AS gsp,
               s.want_subject_player_id::text AS ws, s.want_special_id::text AS wsp,
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
        give, want = (s["gs"], s["gsp"]), (s["ws"], s["wsp"])
        for owner, card in ((s["from_id"], give), (s["to_id"], want)):
            if owner not in snap["people"] or (card[1] is None and card[0] not in snap["people"]):
                raise SwapError("One of those players is no longer in the card pool, so this swap cannot go ahead.")
        # Lock in a fixed order (lower player id first) so two swaps over the same cards cannot deadlock.
        order = sorted([(s["from_id"], give), (s["to_id"], want)], key=lambda t: t[0])
        found: dict[str, Optional[str]] = {}
        for owner, card in order:
            found[owner] = await _lock_copy(db, club.id, owner, card)
        if found.get(s["from_id"]) is None:
            raise SwapError("The card they offered is no longer theirs to give, so this swap cannot go ahead. You can decline it.")
        if found.get(s["to_id"]) is None:
            raise SwapError("The card they asked for is no longer yours to give, so this swap cannot go ahead. You can decline it.")
        await db.execute(text(
            "UPDATE player_card_copies SET owner_player_id = CAST(:new AS UUID), source = 'swap', obtained_at = NOW() "
            "WHERE id = CAST(:id AS UUID)"
        ), {"new": s["to_id"], "id": found[s["from_id"]]})
        await db.execute(text(
            "UPDATE player_card_copies SET owner_player_id = CAST(:new AS UUID), source = 'swap', obtained_at = NOW() "
            "WHERE id = CAST(:id AS UUID)"
        ), {"new": s["from_id"], "id": found[s["to_id"]]})
        new = "accepted"
    await db.execute(text(
        "UPDATE player_card_swaps SET status = :st, resolved_at = NOW() WHERE id = CAST(:id AS UUID)"
    ), {"st": new, "id": swap_id})
    return new
