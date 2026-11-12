"""Player Cards, the Market: what other players are after, and which of it you hold.

Wish lists are visible to the club by name (a player can keep theirs out in Settings: `player_card_prefs.wants_hidden`).
Three views, all read-only:

* `demand`: the cards the asker could trade that somebody wants, each with the players who want it. A hidden list is counted
  (`hidden`) and never named.
* `players`: every player with a visible wish list, with how well the two collections line up: how many of the asker's cards
  they want (`they_want_mine`), and how many of their cards the asker wants (`i_want_theirs`). A player who is both has a direct
  swap on offer.
* `player_detail`: one player's whole wish list with the asker's copies marked, beside the cards they could trade with the ones
  on the asker's list marked, so a player can see what to give and what to ask for.

Anything about another player's cards goes through `swaps.tradeable`. A player outside the pool, the asker, and a hidden list never
appear. Cards a wisher already holds are left out (a list is only cleaned when its owner reads it).
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
    """The Market home: the asker's cards in demand, and the players with a visible wish list."""
    wants = await _all_wants(db, club, me)
    hidden = await _hidden_wishers(db, club)
    everyone = await swaps._rows_by_card(db, club.id)
    held_me = everyone.get(me, {})
    mine_tradeable = _tradeable_set(me, held_me)
    my_wants = {c for c, _ in await social.wanted_cards(db, club, me)}

    # Who wants each card the asker could trade (not people who already hold it; they are not really after it).
    wanters: dict[Card, list[str]] = {}
    hidden_n: dict[Card, int] = {}
    players = []
    for owner, ws in wants.items():
        if owner not in snap["people"]:
            continue
        theirs = everyone.get(owner, {})
        live = {c for c in ws if theirs.get(c, 0) == 0}
        for c in live & mine_tradeable:
            if owner in hidden:
                hidden_n[c] = hidden_n.get(c, 0) + 1
            else:
                wanters.setdefault(c, []).append(owner)
        if owner in hidden or not live:
            continue
        they_want_mine = len(live & mine_tradeable)
        i_want_theirs = len(my_wants & _tradeable_set(owner, theirs))
        players.append({"player_id": owner, "name": snap["people"][owner]["display_name"], "wants": len(live),
                        "they_want_mine": they_want_mine, "i_want_theirs": i_want_theirs,
                        "swap_possible": they_want_mine > 0 and i_want_theirs > 0})
    players.sort(key=lambda p: (not p["swap_possible"], -(p["they_want_mine"] + p["i_want_theirs"]), p["name"].lower()))

    in_demand = sorted(set(wanters) | set(hidden_n), key=lambda c: (-(len(wanters.get(c, [])) + hidden_n.get(c, 0)), swaps.key_of(*c)))[:MAX_DEMAND]
    specials = await social._specials(db, club, in_demand)
    demand = []
    for card in in_demand:
        payload = swaps._payload(snap, card, specials)
        if payload is None:
            continue
        names = sorted(({"player_id": o, "name": snap["people"][o]["display_name"]} for o in wanters.get(card, [])), key=lambda w: w["name"].lower())
        demand.append({**payload, "key": swaps.key_of(*card), "tradeable": held_me.get(card, 0), "wanted_by": names, "hidden": hidden_n.get(card, 0)})
    return {"demand": demand, "players": players, "my_wants": len(my_wants)}


async def player_detail(db: AsyncSession, club: Organisation, snap: dict, me: str, other: str) -> dict:
    """One player's wish list and tradeable cards, each marked against the asker's own."""
    if other == me or other not in snap["people"] or other in await _hidden_wishers(db, club):
        raise SwapError("That wish list is not available.", 404)
    wanted = await social.wanted_cards(db, club, other)
    everyone = await swaps._rows_by_card(db, club.id)
    held_me, held_other = everyone.get(me, {}), everyone.get(other, {})
    specials = await social._specials(db, club, [c for c, _ in wanted])
    wants = []
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
    theirs = await swaps.tradeable_cards(db, club, snap, other)
    for c in theirs:
        parsed = swaps.parse_key(c["key"])
        subject = parsed[0] or c.get("player_id") or ""
        c["on_my_list"] = (subject, parsed[1]) in my_wants
    theirs.sort(key=lambda c: (not c["on_my_list"], -(c.get("rarity") or 0), (c.get("name") or "").lower()))
    return {"player": {"player_id": other, "name": snap["people"][other]["display_name"]}, "wants": wants, "theirs": theirs}
