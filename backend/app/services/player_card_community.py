"""Player Cards, the community side: the showcase, the collectors board and the club feed.

* The showcase is up to six cards a player pins up. It is shown to the club (their board entry, Home) and only ever holds cards the
  player holds: it is checked when saved and again when read, so a card swapped away drops off.
* The collectors board lists only players who opted in. It ranks by the share of the club's set a player holds (distinct cards over
  all cards), never by how many cards they hold, so nobody gains by hoarding. It shows names, a showcase and the rarest player card
  held, never the rest of anyone's collection.
* The club feed is built from records the club already has (special cards for things that happened this week, big pulls, swaps
  completed). A player who opted out is left out of it entirely.
Both are derived on read and store nothing.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation
from app.services import player_card_swaps as swaps, player_cards as cards
from app.services.player_card_swaps import SwapError

SHOWCASE_MAX = 6
BOARD_MAX = 50
FEED_DAYS = 7
FEED_MAX = 30
_TIER_RANK = {"legendary": 3, "epic": 2, "rare": 1, "common": 0}


# ── Showcase ──────────────────────────────────────────────────────────────────────────────────────────────────

async def _held_set(db: AsyncSession, club: Organisation, owner: str) -> set:
    held = (await swaps._rows_by_card(db, club.id, owner)).get(owner, {})
    out = {c for c, n in held.items() if n > 0}
    out.add((owner, None))
    return out


async def showcase_for(db: AsyncSession, club: Organisation, snap: dict, owners: list[str]) -> dict[str, list[dict]]:
    """`{owner: [card payload]}` in the order pinned, leaving out any card the owner no longer holds or that left the pool."""
    if not owners:
        return {}
    rows = (await db.execute(text(
        "SELECT player_id::text, subject_player_id::text, special_id::text FROM player_card_showcase "
        "WHERE organisation_id = CAST(:o AS UUID) AND player_id = ANY(CAST(:ids AS uuid[])) ORDER BY player_id, slot"
    ), {"o": str(club.id), "ids": owners})).fetchall()
    everyone = await swaps._rows_by_card(db, club.id)
    specials = await swaps._special_subjects(db, club.id, [r[2] for r in rows if r[2]])
    out: dict[str, list[dict]] = {o: [] for o in owners}
    for owner, subject, special_id in rows:
        card = (subject, special_id)
        if card != (owner, None) and everyone.get(owner, {}).get(card, 0) < 1:
            continue
        payload = swaps._payload(snap, card, specials)
        if payload:
            out[owner].append({**payload, "key": swaps.key_of(*card)})
    return out


async def get_showcase(db: AsyncSession, club: Organisation, snap: dict, me: str) -> dict:
    return {"cards": (await showcase_for(db, club, snap, [me])).get(me, []), "max": SHOWCASE_MAX}


async def set_showcase(db: AsyncSession, club: Organisation, snap: dict, me: str, keys: list[str]) -> None:
    """Replace the showcase with these cards, in this order."""
    if len(keys) > SHOWCASE_MAX:
        raise SwapError(f"A showcase holds up to {SHOWCASE_MAX} cards.", 422)
    if len(set(keys)) != len(keys):
        raise SwapError("Pick each card once.", 422)
    held = await _held_set(db, club, me)
    resolved = []
    for key in keys:
        card, _payload = await swaps._resolve(db, club.id, snap, key)
        if card not in held:
            raise SwapError("You can only pin a card you hold.")
        resolved.append(card)
    await db.execute(text("DELETE FROM player_card_showcase WHERE organisation_id = CAST(:o AS UUID) AND player_id = CAST(:me AS UUID)"),
                     {"o": str(club.id), "me": me})
    for slot, (subject, special_id) in enumerate(resolved):
        await db.execute(text(
            "INSERT INTO player_card_showcase (organisation_id, player_id, slot, subject_player_id, special_id) "
            "VALUES (CAST(:o AS UUID), CAST(:me AS UUID), :slot, CAST(:s AS UUID), CAST(:sp AS UUID))"
        ), {"o": str(club.id), "me": me, "slot": slot, "s": subject, "sp": special_id})


# ── The collectors board ──────────────────────────────────────────────────────────────────────────────────────

async def board(db: AsyncSession, club: Organisation, snap: dict, me: str) -> dict:
    """Players who opted in, by share of the set held. `me` says whether the viewer is on it and where."""
    opted = [r[0] for r in (await db.execute(text(
        "SELECT p.player_id::text FROM player_card_prefs p WHERE p.organisation_id = CAST(:o AS UUID) AND p.board_opt_in"
    ), {"o": str(club.id)})).fetchall() if r[0] in snap["people"]]
    drawable = [pid for pid, f in snap["figs"].items() if f["matches"] > 0 and pid in snap["people"]]
    spec_rows = (await db.execute(text("SELECT id::text, player_id::text FROM player_special_cards WHERE organisation_id = CAST(:o AS UUID)"),
                                  {"o": str(club.id)})).fetchall()
    special_ids = {r[0] for r in spec_rows if r[1] in snap["people"]}
    total = len(drawable) + len(special_ids)
    everyone = await swaps._rows_by_card(db, club.id)
    shown = await showcase_for(db, club, snap, opted)
    entries = []
    for pid in opted:
        held = everyone.get(pid, {})
        distinct = {c for c, n in held.items() if n > 0 and ((c[1] and c[1] in special_ids) or (not c[1] and c[0] in drawable))}
        if pid in drawable:
            distinct.add((pid, None))
        players_held = [c[0] for c in distinct if not c[1] and c[0] != pid]
        best = max(players_held, key=lambda s: (_TIER_RANK.get((snap["rating"].get(s) or {}).get("tier"), 0), (snap["rating"].get(s) or {}).get("score", 0)), default=None)
        entries.append({
            "player_id": pid, "name": snap["people"][pid]["display_name"],
            "percent": round(100 * len(distinct) / total, 1) if total else 0.0, "held": len(distinct),
            "rarest": ({**cards.regular_card(snap, best), "key": f"p:{best}"} if best else None),
            "showcase": shown.get(pid, []),
        })
    entries.sort(key=lambda e: (-e["percent"], e["name"].lower()))
    for i, e in enumerate(entries, 1):
        e["rank"] = i
    mine_entry = next((e for e in entries if e["player_id"] == me), None)
    return {"entries": entries[:BOARD_MAX], "total_cards": total, "me_opted_in": mine_entry is not None, "me_rank": mine_entry["rank"] if mine_entry else None,
            "count": len(entries)}


# ── The club feed ─────────────────────────────────────────────────────────────────────────────────────────────

async def feed(db: AsyncSession, club: Organisation, snap: dict, me: str, today: Optional[date] = None) -> dict:
    """What has happened in the club's cards this week, newest first, leaving out anyone who opted out."""
    today = today or date.today()
    since = today - timedelta(days=FEED_DAYS)
    hidden = {r[0] for r in (await db.execute(text(
        "SELECT player_id::text FROM player_card_prefs WHERE organisation_id = CAST(:o AS UUID) AND feed_hidden"), {"o": str(club.id)})).fetchall()}
    events: list[dict] = []
    # Things that happened this week: a special card for a dated event (an undated card, or an old one made later, is not news).
    rows = (await db.execute(text(
        "SELECT id, player_id, kind, title, occurred_on, detail FROM player_special_cards WHERE organisation_id = CAST(:o AS UUID) "
        "AND occurred_on >= :since AND kind NOT IN ('debut', 'games') ORDER BY occurred_on DESC LIMIT 60"), {"o": str(club.id), "since": since})).mappings().all()
    for r in rows:
        pid = str(r["player_id"])
        if pid in hidden or pid not in snap["people"]:
            continue
        card = cards.special_card(snap, dict(r))
        if card:
            events.append({"type": "special", "on": r["occurred_on"].isoformat(), "text": f"{snap['people'][pid]['display_name']}: {r['title']}", "card": card})
    # Big pulls: an Epic, a Legendary or a special card out of a pack.
    pulls = (await db.execute(text(
        "SELECT owner_player_id::text AS owner, subject_player_id::text AS subject, special_id::text AS special_id, obtained_at "
        "FROM player_card_copies WHERE organisation_id = CAST(:o AS UUID) AND source = 'pack' AND obtained_at >= :since "
        "ORDER BY obtained_at DESC LIMIT 200"), {"o": str(club.id), "since": since})).mappings().all()
    specials = await swaps._special_subjects(db, club.id, [p["special_id"] for p in pulls if p["special_id"]])
    for p in pulls:
        owner = p["owner"]
        if owner in hidden or owner not in snap["people"] or owner == p["subject"]:
            continue
        payload = swaps._payload(snap, (p["subject"], p["special_id"]), specials)
        if not payload or not (payload["kind"] == "special" or payload["tier"] in ("epic", "legendary")):
            continue
        label = payload.get("title") or (payload["tier"].title() + " card")
        events.append({"type": "pull", "on": p["obtained_at"].date().isoformat(),
                       "text": f"{snap['people'][owner]['display_name']} pulled {payload['name']}" + (f": {payload['title']}" if payload.get("title") else f" ({label})"), "card": payload})
    # Swaps agreed this week.
    sw = (await db.execute(text(
        "SELECT s.id::text AS id, s.from_player_id::text AS f, s.to_player_id::text AS t, s.resolved_at, "
        "COALESCE((SELECT SUM(qty) FROM player_card_swap_items i WHERE i.swap_id = s.id), 0) AS n "
        "FROM player_card_swaps s WHERE s.organisation_id = CAST(:o AS UUID) AND s.status = 'accepted' AND s.resolved_at >= :since "
        "ORDER BY s.resolved_at DESC LIMIT 40"), {"o": str(club.id), "since": since})).mappings().all()
    for s in sw:
        if s["f"] in hidden or s["t"] in hidden or s["f"] not in snap["people"] or s["t"] not in snap["people"]:
            continue
        events.append({"type": "swap", "on": s["resolved_at"].date().isoformat(),
                       "text": f"{snap['people'][s['f']]['display_name']} and {snap['people'][s['t']]['display_name']} swapped {int(s['n'])} cards", "card": None})
    events.sort(key=lambda e: e["on"], reverse=True)
    return {"events": events[:FEED_MAX], "days": FEED_DAYS}
