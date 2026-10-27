"""Player Cards, the social side: the wish list, spares a player is open to swapping, one card in full, and a player's
alert settings.

* A wish list is private to its owner. A card on it is listed with who could swap one right now, which is the same thing
  anyone can already see in Club cards. Nobody else is ever told what is on someone's list.
* A holder who marks a spare "open to offers" is told how many players want it, as a number, never as names.
* A spare is a copy beyond the one a player keeps: two copies of a card is one spare. A player's own card is theirs without a
  row, so every pulled copy of it is a spare.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation
from app.services import player_card_catalogue as catalogue, player_card_swaps as swaps
from app.services.player_card_swaps import Card, SwapError

MAX_WANTS = 100


def _card_args(card: Card) -> dict:
    return {"s": card[0], "sp": card[1]}


async def _specials(db: AsyncSession, club: Organisation, wanted: list[Card]) -> dict:
    return await swaps._special_subjects(db, club.id, [c[1] for c in wanted if c[1]])


# ── The wish list ─────────────────────────────────────────────────────────────────────────────────────────────

async def wanted_cards(db: AsyncSession, club: Organisation, me: str) -> list[tuple[Card, object]]:
    rows = (await db.execute(text(
        "SELECT subject_player_id::text, special_id::text, created_at FROM player_card_wants "
        "WHERE organisation_id = CAST(:o AS UUID) AND player_id = CAST(:me AS UUID) ORDER BY created_at DESC"
    ), {"o": str(club.id), "me": me})).fetchall()
    return [((r[0], r[1]), r[2]) for r in rows]


async def list_wants(db: AsyncSession, club: Organisation, snap: dict, me: str) -> dict:
    """The player's wish list, each card with who could swap one now. `ready` counts cards someone has."""
    wanted = await wanted_cards(db, club, me)
    specials = await _specials(db, club, [c for c, _ in wanted])
    holders = await catalogue._holder_map(db, club, snap, me)
    mine = (await swaps._rows_by_card(db, club.id, me)).get(me, {})
    out = []
    for card, added in wanted:
        payload = swaps._payload(snap, card, specials)
        if payload is None:   # the player has left the pool: kept on the list, shown again if they come back
            continue
        hs = sorted(holders.get(card, []), key=lambda h: h["name"].lower())
        out.append({**payload, "key": swaps.key_of(*card), "holders": hs, "others": len(hs),
                    "mine_copies": mine.get(card, 0), "added_at": added.isoformat()})
    return {"wants": out, "ready": sum(1 for w in out if w["holders"]), "limit": MAX_WANTS}


async def add_want(db: AsyncSession, club: Organisation, snap: dict, me: str, key: str) -> None:
    card, _payload = await swaps._resolve(db, club.id, snap, key)
    mine = (await swaps._rows_by_card(db, club.id, me)).get(me, {})
    if card == (me, None) or mine.get(card, 0) > 0:
        raise SwapError("You already have that card.")
    n = (await db.execute(text(
        "SELECT COUNT(*) FROM player_card_wants WHERE player_id = CAST(:me AS UUID)"), {"me": me})).scalar() or 0
    if n >= MAX_WANTS:
        raise SwapError(f"Your wish list holds up to {MAX_WANTS} cards. Take one off to add another.")
    await db.execute(text(
        "INSERT INTO player_card_wants (organisation_id, player_id, subject_player_id, special_id) "
        "VALUES (CAST(:o AS UUID), CAST(:me AS UUID), CAST(:s AS UUID), CAST(:sp AS UUID)) ON CONFLICT DO NOTHING"
    ), {"o": str(club.id), "me": me, **_card_args(card)})


async def remove_want(db: AsyncSession, club: Organisation, me: str, key: str) -> None:
    card = swaps.parse_key(key)
    if card[0] == "":   # a special card: its subject is read off the card itself
        row = (await db.execute(text(
            "SELECT player_id::text FROM player_special_cards WHERE id = CAST(:i AS UUID) AND organisation_id = CAST(:o AS UUID)"
        ), {"i": card[1], "o": str(club.id)})).first()
        if not row:
            return
        card = (row[0], card[1])
    await db.execute(text(
        "DELETE FROM player_card_wants WHERE organisation_id = CAST(:o AS UUID) AND player_id = CAST(:me AS UUID) "
        "AND subject_player_id = CAST(:s AS UUID) AND special_id IS NOT DISTINCT FROM CAST(:sp AS UUID)"
    ), {"o": str(club.id), "me": me, **_card_args(card)})


async def wanted_keys(db: AsyncSession, club: Organisation, me: str) -> set[str]:
    return {swaps.key_of(*c) for c, _ in await wanted_cards(db, club, me)}


# ── Spares and "open to offers" ───────────────────────────────────────────────────────────────────────────────

async def spares(db: AsyncSession, club: Organisation, snap: dict, me: str) -> dict:
    """The cards the player holds more of than they keep, each with how many spares, whether they are open to offers, and,
    when they are, how many other players want it."""
    held = (await swaps._rows_by_card(db, club.id, me)).get(me, {})
    spare_n = {c: (n if c == (me, None) else n - 1) for c, n in held.items()}
    spare_n = {c: n for c, n in spare_n.items() if n >= 1}
    specials = await _specials(db, club, list(spare_n))
    open_rows = (await db.execute(text(
        "SELECT subject_player_id::text, special_id::text FROM player_card_open_offers "
        "WHERE organisation_id = CAST(:o AS UUID) AND player_id = CAST(:me AS UUID)"
    ), {"o": str(club.id), "me": me})).fetchall()
    open_set = {(r[0], r[1]) for r in open_rows}
    wanters = {}
    if open_set:
        for r in (await db.execute(text(
            "SELECT subject_player_id::text, special_id::text, COUNT(*) FROM player_card_wants "
            "WHERE organisation_id = CAST(:o AS UUID) AND player_id <> CAST(:me AS UUID) "
            "GROUP BY subject_player_id, special_id"), {"o": str(club.id), "me": me})).fetchall():
            wanters[(r[0], r[1])] = int(r[2])
    out = []
    for card, n in spare_n.items():
        payload = swaps._payload(snap, card, specials)
        if payload is None:
            continue
        is_open = card in open_set
        out.append({**payload, "key": swaps.key_of(*card), "spare": n, "tradeable": n, "open": is_open,
                    **({"wanted_by": wanters.get(card, 0)} if is_open else {})})
    out.sort(key=lambda c: (c["kind"] != "special", (c.get("name") or "").lower(), c.get("title") or ""))
    return {"cards": out, "total": sum(c["spare"] for c in out)}


async def set_open(db: AsyncSession, club: Organisation, snap: dict, me: str, key: str, on: bool) -> None:
    card, _payload = await swaps._resolve(db, club.id, snap, key)
    if on:
        held = (await swaps._rows_by_card(db, club.id, me)).get(me, {}).get(card, 0)
        spare = held if card == (me, None) else held - 1
        if spare < 1:
            raise SwapError("You can only be open to offers on a card you have a spare of.")
        await db.execute(text(
            "INSERT INTO player_card_open_offers (organisation_id, player_id, subject_player_id, special_id) "
            "VALUES (CAST(:o AS UUID), CAST(:me AS UUID), CAST(:s AS UUID), CAST(:sp AS UUID)) ON CONFLICT DO NOTHING"
        ), {"o": str(club.id), "me": me, **_card_args(card)})
    else:
        await db.execute(text(
            "DELETE FROM player_card_open_offers WHERE organisation_id = CAST(:o AS UUID) AND player_id = CAST(:me AS UUID) "
            "AND subject_player_id = CAST(:s AS UUID) AND special_id IS NOT DISTINCT FROM CAST(:sp AS UUID)"
        ), {"o": str(club.id), "me": me, **_card_args(card)})


# ── One card in full ──────────────────────────────────────────────────────────────────────────────────────────

async def card_detail(db: AsyncSession, club: Organisation, snap: dict, me: str, key: str) -> dict:
    """What the card page shows: the card, who could swap one, how many the asker holds, and whether it is on their list."""
    out = await catalogue.holders_of(db, club, snap, me, key)
    card = swaps.parse_key(key)
    row = (await db.execute(text(
        "SELECT 1 FROM player_card_wants WHERE organisation_id = CAST(:o AS UUID) AND player_id = CAST(:me AS UUID) "
        "AND special_id IS NOT DISTINCT FROM CAST(:sp AS UUID) AND subject_player_id = CAST(:s AS UUID)"
    ), {"o": str(club.id), "me": me, "sp": card[1], "s": out["card"].get("player_id") or card[0]})).first()
    return {**out, "wanted": bool(row)}


# ── Alert settings ────────────────────────────────────────────────────────────────────────────────────────────

PREF_FIELDS = ("alert_swaps", "alert_wants")


async def load_prefs(db: AsyncSession, me: str) -> dict:
    row = (await db.execute(text(
        "SELECT alert_swaps, alert_wants FROM player_card_prefs WHERE player_id = CAST(:me AS UUID)"
    ), {"me": me})).mappings().first()
    out = {"alert_swaps": True, "alert_wants": True}
    if row:
        out.update({k: bool(row[k]) for k in PREF_FIELDS})
    return out


async def save_prefs(db: AsyncSession, club: Organisation, me: str, patch: dict) -> dict:
    """Only the keys sent are changed: an absent key leaves the setting alone."""
    current = await load_prefs(db, me)
    for k in PREF_FIELDS:
        if k in patch and patch[k] is not None:
            current[k] = bool(patch[k])
    await db.execute(text(
        "INSERT INTO player_card_prefs (player_id, organisation_id, alert_swaps, alert_wants) "
        "VALUES (CAST(:me AS UUID), CAST(:o AS UUID), :a, :w) "
        "ON CONFLICT (player_id) DO UPDATE SET alert_swaps = :a, alert_wants = :w, updated_at = NOW()"
    ), {"me": me, "o": str(club.id), "a": current["alert_swaps"], "w": current["alert_wants"]})
    return current
