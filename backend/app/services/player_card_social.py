"""Player Cards, the social side: the wish list, spares a player is open to swapping, one card in full, and a player's
alert settings.

* A wish list is visible to the club by name in the Market (`services/player_card_market.py`), unless its owner switches that off
  (`player_card_prefs.wants_hidden`, Settings). A list kept private is never shown or named there, but it still counts in the
  "wanted by" numbers, and it still drives a suggested swap (below) with the one player it matches.
* A card on a list is listed to its owner with who could swap one right now, which is the same thing anyone can already see in Club
  cards. A suggested swap shows each of two players a card of theirs the other is after, and a card of the other's they are after.
* A card comes off the wish list the moment the player holds a copy, however it came (`player_cards.drop_fulfilled_wants`).
* A player is told how many other players have a card they HOLD on their wish list, as a number, never as names
  (`wanted_counts`): in the book, on the card page and on Spares. A player already holding a copy does not count.
* A suggested swap can be dismissed. It hides that exact pairing for the player who dismissed it and nobody else.
* A spare is a copy beyond the one a player keeps: two copies of a card is one spare. A player's own card is theirs without a
  row, so every pulled copy of it is a spare.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation
from app.services import player_card_catalogue as catalogue, player_card_swaps as swaps, player_cards as cards
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
    await cards.drop_fulfilled_wants(db, me)   # a card obtained some way that did not clean up after itself (a gift, a challenge)
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


async def wanted_counts(db: AsyncSession, club: Organisation, snap: dict, me: str, held: Optional[set[Card]] = None) -> dict[Card, int]:
    """How many OTHER players have each card on their wish list, for the cards `me` holds (every card with a row, and their own
    card). A count and never names. Someone out of the pool, or who already holds a copy (their list is cleaned lazily), is not
    counted. Only cards in `held` come back, so a card the asker does not hold is never counted for them."""
    if held is None:
        held = set((await swaps._rows_by_card(db, club.id, me)).get(me, {}))
        held.add((me, None))
    if not held:
        return {}
    rows = (await db.execute(text(
        "SELECT player_id::text, subject_player_id::text, special_id::text FROM player_card_wants "
        "WHERE organisation_id = CAST(:o AS UUID) AND player_id <> CAST(:me AS UUID) "
        "AND subject_player_id = ANY(CAST(:subjects AS uuid[]))"
    ), {"o": str(club.id), "me": me, "subjects": sorted({c[0] for c in held})})).fetchall()
    if not rows:
        return {}
    everyone = await swaps._rows_by_card(db, club.id)
    out: dict[Card, int] = {}
    for owner, subject, special_id in rows:
        card = (subject, special_id)
        if card not in held or owner not in snap["people"]:
            continue
        if everyone.get(owner, {}).get(card, 0) > 0:
            continue
        out[card] = out.get(card, 0) + 1
    return out


async def with_wanted_by(db: AsyncSession, club: Organisation, snap: dict, me: str, cards_out: list[dict]) -> list[dict]:
    """Put `wanted_by` on each of the asker's own card payloads, from `wanted_counts`. Both kinds of payload carry `player_id`
    (the subject) and a key that is `p:<player>` or `s:<special>`."""
    def card_of(c: dict) -> Card:
        return (str(c.get("player_id") or ""), c.get("special_id") or None)
    counts = await wanted_counts(db, club, snap, me, {card_of(c) for c in cards_out if c.get("player_id")})
    for c in cards_out:
        c["wanted_by"] = counts.get(card_of(c), 0)
    return cards_out


# ── Suggested swaps ───────────────────────────────────────────────────────────────────────────────────────────

MAX_SUGGESTIONS = 12


async def _dismissed(db: AsyncSession, club: Organisation, me: str) -> set[tuple[str, Card, Card]]:
    """The pairings `me` has dismissed: (other player, the card I would give, the card I would get)."""
    rows = (await db.execute(text(
        "SELECT other_player_id::text, give_subject_player_id::text, give_special_id::text, "
        "want_subject_player_id::text, want_special_id::text FROM player_card_dismissed_swaps "
        "WHERE organisation_id = CAST(:o AS UUID) AND player_id = CAST(:me AS UUID)"
    ), {"o": str(club.id), "me": me})).fetchall()
    return {(r[0], (r[1], r[2]), (r[3], r[4])) for r in rows}


async def dismiss_suggestion(db: AsyncSession, club: Organisation, snap: dict, me: str, other: str, give_key: str, want_key: str) -> None:
    """Hide one suggested pairing for `me`. The other player still sees their side of it; a different pairing is still suggested."""
    if other == me or other not in snap["people"]:
        raise SwapError("That player is not available to swap with.", 404)
    give, _ = await swaps._resolve(db, club.id, snap, give_key)
    want, _ = await swaps._resolve(db, club.id, snap, want_key)
    await db.execute(text(
        "INSERT INTO player_card_dismissed_swaps (organisation_id, player_id, other_player_id, give_subject_player_id, give_special_id, "
        "want_subject_player_id, want_special_id) VALUES (CAST(:o AS UUID), CAST(:me AS UUID), CAST(:other AS UUID), "
        "CAST(:gs AS UUID), CAST(:gsp AS UUID), CAST(:ws AS UUID), CAST(:wsp AS UUID)) ON CONFLICT DO NOTHING"
    ), {"o": str(club.id), "me": me, "other": other, "gs": give[0], "gsp": give[1], "ws": want[0], "wsp": want[1]})


async def restore_suggestion(db: AsyncSession, club: Organisation, me: str, other: str, give_key: str, want_key: str) -> None:
    """Undo a dismissal (the row is the player's own and nobody else decided anything about it, so it is deleted)."""
    give, want = swaps.parse_key(give_key), swaps.parse_key(want_key)
    # A special card's subject is read off the card itself, as `remove_want` does.
    resolved = []
    for card in (give, want):
        if card[0] == "":
            row = (await db.execute(text(
                "SELECT player_id::text FROM player_special_cards WHERE id = CAST(:i AS UUID) AND organisation_id = CAST(:o AS UUID)"
            ), {"i": card[1], "o": str(club.id)})).first()
            if not row:
                return
            card = (row[0], card[1])
        resolved.append(card)
    give, want = resolved
    await db.execute(text(
        "DELETE FROM player_card_dismissed_swaps WHERE organisation_id = CAST(:o AS UUID) AND player_id = CAST(:me AS UUID) "
        "AND other_player_id = CAST(:other AS UUID) AND give_subject_player_id = CAST(:gs AS UUID) "
        "AND give_special_id IS NOT DISTINCT FROM CAST(:gsp AS UUID) AND want_subject_player_id = CAST(:ws AS UUID) "
        "AND want_special_id IS NOT DISTINCT FROM CAST(:wsp AS UUID)"
    ), {"o": str(club.id), "me": me, "other": other, "gs": give[0], "gsp": give[1], "ws": want[0], "wsp": want[1]})


async def suggested_swaps(db: AsyncSession, club: Organisation, snap: dict, me: str) -> list[dict]:
    """Players who hold a card on MY wish list and want a card I hold, one suggestion per player: my card for theirs. It reads the same
    from either side, so both players are prompted, except that a pairing one of them dismissed (`dismiss_suggestion`) is hidden from
    that player only. A player who already has a live request with me over either card is left out (it is being dealt with). Where a player offers several, the pair is the best match: a spare of mine before a card I only have
    one of, then the two cards closest in rarity, then the rarer card I am after."""
    mine_wants = {c for c, _ in await wanted_cards(db, club, me)}
    if not mine_wants:
        return []
    org = str(club.id)
    their_wants: dict[str, set[Card]] = {}
    for owner, subject, special_id in (await db.execute(text(
            "SELECT player_id::text, subject_player_id::text, special_id::text FROM player_card_wants "
            "WHERE organisation_id = CAST(:o AS UUID) AND player_id <> CAST(:me AS UUID)"), {"o": org, "me": me})).fetchall():
        their_wants.setdefault(owner, set()).add((subject, special_id))
    if not their_wants:
        return []
    everyone = await swaps._rows_by_card(db, club.id)
    held_me = everyone.get(me, {})
    dismissed = await _dismissed(db, club, me)
    # Cards already in a live request between me and each other player.
    busy: dict[str, set[Card]] = {}
    live = (await db.execute(text(
        "SELECT s.id::text, s.from_player_id::text, s.to_player_id::text FROM player_card_swaps s "
        "WHERE s.organisation_id = CAST(:o AS UUID) AND (s.from_player_id = CAST(:me AS UUID) OR s.to_player_id = CAST(:me AS UUID)) AND " + swaps._live_sql()),
        {"o": org, "me": me})).fetchall()
    if live:
        sides = await swaps._items_of(db, [r[0] for r in live])
        for sid, frm, to in live:
            other = to if frm == me else frm
            busy.setdefault(other, set()).update(c for side in sides[sid].values() for c, _ in side)

    def spare(card: Card) -> bool:
        n = held_me.get(card, 0)
        return (n >= 1) if card == (me, None) else n >= 2

    picks: list[tuple[tuple, str, Card, Card, dict, dict, int]] = []
    for other, wants in their_wants.items():
        if other not in snap["people"]:
            continue
        theirs = everyone.get(other, {})
        can_get = [c for c in mine_wants & set(theirs) if swaps.tradeable(other, c, theirs[c]) > 0 and c not in busy.get(other, set())]
        can_give = [c for c in wants & set(held_me) if swaps.tradeable(me, c, held_me[c]) > 0 and c not in busy.get(other, set())]
        if not can_get or not can_give:
            continue
        specials = await _specials(db, club, can_get + can_give)
        got = {c: swaps._payload(snap, c, specials) for c in can_get}
        gave = {c: swaps._payload(snap, c, specials) for c in can_give}
        can_get, can_give = [c for c in can_get if got[c]], [c for c in can_give if gave[c]]
        if not can_get or not can_give:
            continue

        def rank(gw: tuple[Card, Card]) -> tuple:
            g_, w_ = gw
            return (not spare(g_), abs((gave[g_].get("rarity") or 0) - (got[w_].get("rarity") or 0)), -(got[w_].get("rarity") or 0),
                    swaps.key_of(*g_), swaps.key_of(*w_))

        pairs = [(g_, w_) for g_ in can_give for w_ in can_get if (other, g_, w_) not in dismissed]
        if not pairs:
            continue
        g, w = min(pairs, key=rank)
        picks.append(((not spare(g), abs((gave[g].get("rarity") or 0) - (got[w].get("rarity") or 0)), snap["people"][other]["display_name"].lower()),
                      other, g, w, gave[g], got[w], len(pairs)))
    picks.sort(key=lambda p: p[0])
    out = []
    for _rank, other, g, w, gp, wp, combos in picks[:MAX_SUGGESTIONS]:
        out.append({"player": {"player_id": other, "name": snap["people"][other]["display_name"]},
                    "give": {**gp, "key": swaps.key_of(*g), "spare": spare(g)}, "want": {**wp, "key": swaps.key_of(*w)}, "options": combos})
    return out


# ── Spares and "open to offers" ───────────────────────────────────────────────────────────────────────────────

async def spares(db: AsyncSession, club: Organisation, snap: dict, me: str) -> dict:
    """The cards the player holds more of than they keep, each with how many spares, whether they are open to offers, and how many
    other players have it on their wish list (a count for every spare, whether or not they are open to offers)."""
    held = (await swaps._rows_by_card(db, club.id, me)).get(me, {})
    spare_n = {c: (n if c == (me, None) else n - 1) for c, n in held.items()}
    spare_n = {c: n for c, n in spare_n.items() if n >= 1}
    specials = await _specials(db, club, list(spare_n))
    open_rows = (await db.execute(text(
        "SELECT subject_player_id::text, special_id::text FROM player_card_open_offers "
        "WHERE organisation_id = CAST(:o AS UUID) AND player_id = CAST(:me AS UUID)"
    ), {"o": str(club.id), "me": me})).fetchall()
    open_set = {(r[0], r[1]) for r in open_rows}
    wanters = await wanted_counts(db, club, snap, me, set(spare_n))
    out = []
    for card, n in spare_n.items():
        payload = swaps._payload(snap, card, specials)
        if payload is None:
            continue
        is_open = card in open_set
        out.append({**payload, "key": swaps.key_of(*card), "spare": n, "tradeable": n, "open": is_open, "wanted_by": wanters.get(card, 0)})
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
    wanted_by = None
    if out.get("mine_copies", 0) > 0:   # only a card the asker holds says how many others are after it
        subject = out["card"].get("player_id") or card[0]
        wanted_by = (await wanted_counts(db, club, snap, me, {(subject, card[1])})).get((subject, card[1]), 0)
    return {**out, "wanted": bool(row), **({"wanted_by": wanted_by} if wanted_by is not None else {})}


# ── Alert settings ────────────────────────────────────────────────────────────────────────────────────────────

# Nobody is emailed until they ask (both alerts default OFF); everyone is on the collectors board until they leave it.
PREF_FIELDS = ("alert_swaps", "alert_wants", "board_hidden", "feed_hidden", "wants_hidden")
_PREF_DEFAULTS = {"alert_swaps": False, "alert_wants": False, "board_hidden": False, "feed_hidden": False, "wants_hidden": False}


async def load_prefs(db: AsyncSession, me: str) -> dict:
    row = (await db.execute(text(
        "SELECT alert_swaps, alert_wants, board_hidden, feed_hidden, wants_hidden FROM player_card_prefs WHERE player_id = CAST(:me AS UUID)"
    ), {"me": me})).mappings().first()
    out = dict(_PREF_DEFAULTS)
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
        "INSERT INTO player_card_prefs (player_id, organisation_id, alert_swaps, alert_wants, board_hidden, feed_hidden, wants_hidden) "
        "VALUES (CAST(:me AS UUID), CAST(:o AS UUID), :a, :w, :b, :f, :h) "
        "ON CONFLICT (player_id) DO UPDATE SET alert_swaps = :a, alert_wants = :w, board_hidden = :b, feed_hidden = :f, wants_hidden = :h, updated_at = NOW()"
    ), {"me": me, "o": str(club.id), "a": current["alert_swaps"], "w": current["alert_wants"], "b": current["board_hidden"], "f": current["feed_hidden"],
        "h": current["wants_hidden"]})
    return current
