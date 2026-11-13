"""Player Cards, the Market: what other players are after, and which of it you hold.

Wish lists are visible to the club by name (a player can keep theirs out in Settings: `player_card_prefs.wants_hidden`).
Three views, all read-only:

* `demand`: the cards the asker could trade that somebody wants, each with the players who want it. A hidden list is counted
  (`hidden`) and never named.
* `my_doubles`: cards on the asker's wish list that other players hold a spare of (a double), with who, and whether it is in their pile.
* `players`: every player with a visible wish list or a pile, with how well the two collections line up: how many of the asker's cards
  they want (`they_want_mine`), and how many of their cards the asker wants (`i_want_theirs`). A player who is both has a direct
  swap on offer.
* `player_detail`: one player's pile, their whole wish list with the asker's copies marked (empty when they keep it private), and the
  cards they could trade with the ones on the asker's list marked, so a player can see what to give and what to ask for.

Anything about another player's cards goes through `swaps.tradeable`. A player outside the pool and the asker never appear, and a
hidden wish list is never listed, named or ranked on; only the player's pile and tradeable cards, which anyone can see, remain. Cards a wisher already holds are left out (a list is only cleaned when its owner reads it).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation
from app.services import player_card_social as social, player_card_swaps as swaps
from app.services.player_card_swaps import Card, SwapError

MAX_DEMAND = 100   # cards in "your cards in demand"


async def _hidden_wishers(db: AsyncSession, club: Organisation) -> set[str]:
    return {r[0] for r in (await db.execute(text(
        "SELECT player_id::text FROM player_card_prefs WHERE organisation_id = CAST(:o AS UUID) AND wants_hidden"),
        {"o": str(club.id)})).fetchall()}


async def _all_wants(db: AsyncSession, club: Organisation, me: str) -> dict[str, set[Card]]:
    out: dict[str, set[Card]] = {}
    for owner, subject, special_id in (await db.execute(text(
            "SELECT player_id::text, subject_player_id::text, special_id::text FROM player_card_wants "
            "WHERE organisation_id = CAST(:o AS UUID) AND player_id <> CAST(:me AS UUID)"), {"o": str(club.id), "me": me})).fetchall():
        out.setdefault(owner, set()).add((subject, special_id))
    return out


def _tradeable_set(owner: str, held: dict[Card, int]) -> set[Card]:
    return {c for c, n in held.items() if swaps.tradeable(owner, c, n) > 0}


async def overview(db: AsyncSession, club: Organisation, snap: dict, me: str) -> dict:
    """The Market home: spares of cards on the asker's wish list, the asker's cards in demand, and the players to trade with."""
    wants = await _all_wants(db, club, me)
    hidden = await _hidden_wishers(db, club)
    everyone = await swaps._rows_by_card(db, club.id)
    piles = await social.piles(db, club, snap, everyone)
    held_me = everyone.get(me, {})
    mine_tradeable = _tradeable_set(me, held_me)
    my_wants = {c for c, _ in await social.wanted_cards(db, club, me)}

    wanters: dict[Card, list[str]] = {}
    hidden_n: dict[Card, int] = {}
    players = []
    for owner in set(wants) | set(piles):
        if owner not in snap["people"]:
            continue
        theirs = everyone.get(owner, {})
        private = owner in hidden
        live = {c for c in wants.get(owner, set()) if theirs.get(c, 0) == 0}
        # Who wants each card the asker could trade. A private list is counted and never named.
        for c in live & mine_tradeable:
            if private:
                hidden_n[c] = hidden_n.get(c, 0) + 1
            else:
                wanters.setdefault(c, []).append(owner)
        pile = piles.get(owner, set())
        if (private or not live) and not pile:
            continue
        i_want_theirs = len(my_wants & _tradeable_set(owner, theirs))
        # A private list contributes nothing here: what it wants is not shown, so it cannot rank or mark the player.
        they_want_mine = 0 if private else len(live & mine_tradeable)
        players.append({"player_id": owner, "name": snap["people"][owner]["display_name"], "wants": 0 if private else len(live), "wants_private": private,
                        "they_want_mine": they_want_mine, "i_want_theirs": i_want_theirs, "pile": len(pile), "pile_i_want": len(pile & my_wants),
                        "swap_possible": they_want_mine > 0 and i_want_theirs > 0})
    players.sort(key=lambda p: (not p["swap_possible"], -(p["they_want_mine"] + p["i_want_theirs"] + p["pile_i_want"]), p["name"].lower()))

    # Spares of cards on the asker's wish list: who holds a copy beyond the one they keep (a double), and whether it is in their pile.
    doubles = []
    for card in my_wants:
        holders = []
        for owner, held in everyone.items():
            if owner == me or owner not in snap["people"]:
                continue
            n = swaps.spare_copies(owner, card, held.get(card, 0))
            if n > 0:
                holders.append({"player_id": owner, "name": snap["people"][owner]["display_name"], "spare": n, "piled": card in piles.get(owner, set())})
        if holders:
            holders.sort(key=lambda h: (not h["piled"], h["name"].lower()))
            doubles.append((card, holders))
    doubles.sort(key=lambda d: (not any(h["piled"] for h in d[1]), -len(d[1]), swaps.key_of(*d[0])))
    doubles = doubles[:MAX_DEMAND]
    dspecials = await social._specials(db, club, [c for c, _ in doubles])
    my_doubles = []
    for card, holders in doubles:
        payload = swaps._payload(snap, card, dspecials)
        if payload is not None:
            my_doubles.append({**payload, "key": swaps.key_of(*card), "holders": holders})

    in_demand = sorted(set(wanters) | set(hidden_n), key=lambda c: (-(len(wanters.get(c, [])) + hidden_n.get(c, 0)), swaps.key_of(*c)))[:MAX_DEMAND]
    specials = await social._specials(db, club, in_demand)
    demand = []
    for card in in_demand:
        payload = swaps._payload(snap, card, specials)
        if payload is None:
            continue
        names = sorted(({"player_id": o, "name": snap["people"][o]["display_name"]} for o in wanters.get(card, [])), key=lambda w: w["name"].lower())
        demand.append({**payload, "key": swaps.key_of(*card), "tradeable": held_me.get(card, 0), "wanted_by": names, "hidden": hidden_n.get(card, 0)})
    return {"demand": demand, "players": players, "my_wants": len(my_wants), "my_doubles": my_doubles}


async def player_detail(db: AsyncSession, club: Organisation, snap: dict, me: str, other: str) -> dict:
    """One player's pile, wish list and tradeable cards, each marked against the asker's own. A private wish list comes back empty
    with `wants_private`: the page still shows the pile and the cards they could swap, which anyone can already see."""
    if other == me or other not in snap["people"]:
        raise SwapError("That player is not available.", 404)
    private = other in await _hidden_wishers(db, club)
    everyone = await swaps._rows_by_card(db, club.id)
    held_me, held_other = everyone.get(me, {}), everyone.get(other, {})
    wants = []
    if not private:
        wanted = await social.wanted_cards(db, club, other)
        specials = await social._specials(db, club, [c for c, _ in wanted])
        for card, _added in wanted:
            if held_other.get(card, 0) > 0:
                continue   # they hold it now; the list is only cleaned when they read it
            payload = swaps._payload(snap, card, specials)
            if payload is None:
                continue
            mine = swaps.tradeable(me, card, held_me.get(card, 0))
            wants.append({**payload, "key": swaps.key_of(*card), "tradeable": mine, "mine": mine > 0})
        wants.sort(key=lambda c: (not c["mine"], -(c.get("rarity") or 0), (c.get("name") or "").lower()))
    my_wants = {c for c, _ in await social.wanted_cards(db, club, me)}
    in_pile = (await social.piles(db, club, snap, everyone, only=other)).get(other, set())
    theirs = await swaps.tradeable_cards(db, club, snap, other)
    for c in theirs:
        parsed = swaps.parse_key(c["key"])
        card = (parsed[0] or c.get("player_id") or "", parsed[1])
        c["on_my_list"] = card in my_wants
        c["piled"] = card in in_pile
    theirs.sort(key=lambda c: (not c["on_my_list"], -(c.get("rarity") or 0), (c.get("name") or "").lower()))
    pile = [c for c in theirs if c["piled"]]
    return {"player": {"player_id": other, "name": snap["people"][other]["display_name"]}, "wants": wants, "wants_private": private,
            "pile": pile, "theirs": theirs}
