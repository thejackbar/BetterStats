"""Player Cards: what a club's admin can see about how the cards are being used.

All reads, nothing here writes. The club admin needs to answer: who has collected cards and when, what
is in a player's collection, what was added lately (special cards and pulls), what cards exist in the
club's set and how many are out there, who has opened packs, and who has swapped with whom.

Names come straight from the players table (an admin sees every player the club holds, including those
taken out of the card pool); a card payload is only built for a player who is in the pool, because that is
the one that can be drawn, so a card of a hidden player appears as a label and never as a card.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation, Player
from app.services import player_card_swaps as swaps
from app.services import player_cards as cards

PAGE_MAX = 120
ACTIVITY_ROWS = 40
DAYS = 14

_NAME_SQL = "COALESCE(NULLIF(display_name_override, ''), name)"


async def names(db: AsyncSession, org_id) -> dict[str, str]:
    rows = await db.execute(text(
        f"SELECT id::text, {_NAME_SQL} FROM players WHERE organisation_id = CAST(:o AS UUID)"
    ), {"o": str(org_id)})
    return {r[0]: r[1] for r in rows.fetchall()}


def _tier(snap: dict, subject: str, special_id: Optional[str]) -> str:
    if special_id:
        return "special"
    return (snap["rating"].get(subject) or {}).get("tier", "common")


def _label(nm: dict, snap: dict, subject: str, special_id: Optional[str], specials: dict) -> dict:
    """A card as a line of text: always available, even for a player out of the pool."""
    if special_id:
        row = specials.get(special_id) or {}
        return {"kind": "special", "special_kind": row.get("kind"), "title": row.get("title") or "Special card",
                "player": nm.get(subject) or nm.get(str(row.get("player_id"))) or "A player", "tier": "special",
                "key": f"s:{special_id}"}
    return {"kind": "player", "title": "Card", "player": nm.get(subject) or "A player", "tier": _tier(snap, subject, None),
            "rarity": (snap["rating"].get(subject) or {}).get("score"), "key": f"p:{subject}"}


async def _specials(db: AsyncSession, org_id, ids: list[str]) -> dict[str, dict]:
    return await cards._specials_by_id(db, org_id, [i for i in ids if i])


# ── Overview and per-player rows ──────────────────────────────────────────────────────────────────────────────

async def overview(db: AsyncSession, club: Organisation, snap: dict) -> dict:
    org = str(club.id)
    nm = await names(db, club.id)
    rows = (await db.execute(text("""
        WITH owned AS (
            SELECT owner_player_id AS pid, COUNT(*) AS copies,
                   COUNT(DISTINCT subject_player_id) FILTER (WHERE special_id IS NULL) AS uniq_reg,
                   COUNT(DISTINCT special_id) AS uniq_special,
                   BOOL_OR(special_id IS NULL AND subject_player_id = owner_player_id) AS has_own,
                   MIN(obtained_at) AS first_got, MAX(obtained_at) AS last_got
              FROM player_card_copies WHERE organisation_id = CAST(:o AS UUID) GROUP BY owner_player_id
        ), packs AS (
            SELECT player_id AS pid,
                   COUNT(*) FILTER (WHERE opened_at IS NOT NULL) AS opened,
                   COUNT(*) FILTER (WHERE opened_at IS NULL AND (source <> 'weekly' OR ref_key LIKE :wk)) AS waiting,
                   MIN(opened_at) AS first_opened, MAX(opened_at) AS last_opened,
                   COUNT(*) FILTER (WHERE opened_at IS NOT NULL AND opened_at > NOW() - INTERVAL '7 days') AS opened_7d
              FROM player_card_packs WHERE organisation_id = CAST(:o AS UUID) GROUP BY player_id
        ), sw AS (
            SELECT pid, COUNT(*) AS total, COUNT(*) FILTER (WHERE status = 'accepted') AS done FROM (
                SELECT from_player_id AS pid, status FROM player_card_swaps WHERE organisation_id = CAST(:o AS UUID)
                UNION ALL
                SELECT to_player_id, status FROM player_card_swaps WHERE organisation_id = CAST(:o AS UUID)
            ) x GROUP BY pid
        )
        SELECT p.id::text AS id, o.copies, o.uniq_reg, o.uniq_special, o.has_own, o.first_got, o.last_got,
               k.opened, k.waiting, k.first_opened, k.last_opened, k.opened_7d, s.total AS swaps, s.done AS swaps_done
          FROM players p
          LEFT JOIN owned o ON o.pid = p.id LEFT JOIN packs k ON k.pid = p.id LEFT JOIN sw s ON s.pid = p.id
         WHERE p.organisation_id = CAST(:o AS UUID) AND p.is_player IS TRUE
    """), {"o": org, "wk": f"{cards.week_key(snap['settings'])}:%"})).mappings().all()

    pool_total = sum(1 for f in snap["figs"].values() if f["matches"] > 0)
    players = []
    for r in rows:
        pid = r["id"]
        in_pool = pid in snap["people"]
        regular = int(r["uniq_reg"] or 0) + (0 if (r["has_own"] or not in_pool) else 1)
        special = int(r["uniq_special"] or 0)
        players.append({
            "id": pid, "name": nm.get(pid), "in_pool": in_pool,
            "rarity": (snap["rating"].get(pid) or {}).get("score"), "tier": (snap["rating"].get(pid) or {}).get("tier"),
            "cards": regular + special, "regular": regular, "specials": special,
            "copies": int(r["copies"] or 0) + (0 if r["has_own"] or not in_pool else 1),
            "collected_pct": min(100, round(100 * regular / pool_total)) if pool_total else 0,
            "packs_opened": int(r["opened"] or 0), "packs_waiting": int(r["waiting"] or 0), "opened_7d": int(r["opened_7d"] or 0),
            "first_opened_at": r["first_opened"].isoformat() if r["first_opened"] else None,
            "last_opened_at": r["last_opened"].isoformat() if r["last_opened"] else None,
            "last_card_at": r["last_got"].isoformat() if r["last_got"] else None,
            "swaps": int(r["swaps"] or 0), "swaps_done": int(r["swaps_done"] or 0),
        })
    players.sort(key=lambda p: (p["name"] or "").lower())

    tot = (await db.execute(text("""
        SELECT (SELECT COUNT(*) FROM player_card_copies WHERE organisation_id = CAST(:o AS UUID)) AS copies,
               (SELECT COUNT(*) FROM player_card_packs WHERE organisation_id = CAST(:o AS UUID) AND opened_at IS NOT NULL) AS opened,
               (SELECT COUNT(*) FROM player_special_cards WHERE organisation_id = CAST(:o AS UUID)) AS specials,
               (SELECT COUNT(*) FROM player_special_cards WHERE organisation_id = CAST(:o AS UUID) AND created_at > NOW() - INTERVAL '7 days') AS specials_7d,
               (SELECT COUNT(*) FROM player_card_swaps WHERE organisation_id = CAST(:o AS UUID)) AS swaps,
               (SELECT COUNT(*) FROM player_card_swaps WHERE organisation_id = CAST(:o AS UUID) AND status = 'accepted') AS swaps_done,
               (SELECT COUNT(*) FROM player_card_swaps WHERE organisation_id = CAST(:o AS UUID) AND status = 'pending'
                   AND created_at > NOW() - INTERVAL '14 days') AS swaps_open
    """), {"o": org})).mappings().first()
    in_pool_rows = [p for p in players if p["in_pool"]]
    return {
        "totals": {
            "pool": pool_total,
            "players_in_pool": len(in_pool_rows),
            "players_opened": sum(1 for p in in_pool_rows if p["packs_opened"] > 0),
            "players_never_opened": sum(1 for p in in_pool_rows if p["packs_opened"] == 0),
            "players_opened_7d": sum(1 for p in in_pool_rows if p["opened_7d"] > 0),
            "copies": int(tot["copies"]), "packs_opened": int(tot["opened"]),
            "specials": int(tot["specials"]), "specials_7d": int(tot["specials_7d"]),
            "swaps": int(tot["swaps"]), "swaps_done": int(tot["swaps_done"]), "swaps_open": int(tot["swaps_open"]),
        },
        "players": players,
    }


# ── Recent activity ───────────────────────────────────────────────────────────────────────────────────────────

async def activity(db: AsyncSession, club: Organisation, snap: dict) -> dict:
    org = str(club.id)
    nm = await names(db, club.id)
    sp_rows = (await db.execute(text("""
        SELECT sc.id::text AS id, sc.player_id::text AS pid, sc.kind, sc.title, sc.occurred_on, sc.created_at,
               (SELECT COUNT(*) FROM player_card_copies c WHERE c.special_id = sc.id) AS held
          FROM player_special_cards sc WHERE sc.organisation_id = CAST(:o AS UUID)
         ORDER BY sc.created_at DESC, sc.occurred_on DESC NULLS LAST LIMIT :n
    """), {"o": org, "n": ACTIVITY_ROWS})).mappings().all()
    recent_specials = [{
        "id": r["id"], "kind": r["kind"], "title": r["title"], "player": nm.get(r["pid"]), "player_id": r["pid"],
        "occurred_on": r["occurred_on"].isoformat() if r["occurred_on"] else None,
        "added_at": r["created_at"].isoformat(), "held": int(r["held"]),
    } for r in sp_rows]

    cp = (await db.execute(text("""
        SELECT c.id::text AS id, c.owner_player_id::text AS owner, c.subject_player_id::text AS subject, c.special_id::text AS special_id,
               c.source, c.obtained_at, c.pack_id::text AS pack_id,
               NOT EXISTS (SELECT 1 FROM player_card_copies c2
                            WHERE c2.owner_player_id = c.owner_player_id AND c2.subject_player_id = c.subject_player_id
                              AND c2.special_id IS NOT DISTINCT FROM c.special_id AND c2.obtained_at < c.obtained_at) AS is_new
          FROM player_card_copies c
         WHERE c.organisation_id = CAST(:o AS UUID) AND c.source IN ('pack', 'swap')
         ORDER BY c.obtained_at DESC LIMIT :n
    """), {"o": org, "n": ACTIVITY_ROWS})).mappings().all()
    specials = await _specials(db, club.id, [r["special_id"] for r in cp])
    recent_cards = [{
        "owner": nm.get(r["owner"]), "owner_id": r["owner"], "source": r["source"], "new_to_owner": bool(r["is_new"]),
        "obtained_at": r["obtained_at"].isoformat(), **_label(nm, snap, r["subject"], r["special_id"], specials),
    } for r in cp]

    pk = (await db.execute(text("""
        SELECT k.id::text AS id, k.player_id::text AS pid, k.source, k.opened_at,
               c.subject_player_id::text AS subject, c.special_id::text AS special_id
          FROM (SELECT id, player_id, source, opened_at FROM player_card_packs
                 WHERE organisation_id = CAST(:o AS UUID) AND opened_at IS NOT NULL ORDER BY opened_at DESC LIMIT :n) k
          LEFT JOIN player_card_copies c ON c.pack_id = k.id
         ORDER BY k.opened_at DESC
    """), {"o": org, "n": ACTIVITY_ROWS})).mappings().all()
    sp2 = await _specials(db, club.id, [r["special_id"] for r in pk])
    order = {"special": 0, "legendary": 1, "epic": 2, "rare": 3, "common": 4}
    openings: dict[str, dict] = {}
    for r in pk:
        o = openings.setdefault(r["id"], {"id": r["id"], "player": nm.get(r["pid"]), "player_id": r["pid"], "source": r["source"],
                                          "opened_at": r["opened_at"].isoformat(), "cards": []})
        if r["subject"]:
            o["cards"].append(_label(nm, snap, r["subject"], r["special_id"], sp2))
    for o in openings.values():
        o["cards"].sort(key=lambda c: order.get(c["tier"], 5))
        o["best"] = o["cards"][0]["tier"] if o["cards"] else None

    daily = (await db.execute(text(f"""
        SELECT d::date AS day,
               (SELECT COUNT(*) FROM player_special_cards sc WHERE sc.organisation_id = CAST(:o AS UUID) AND sc.created_at::date = d::date) AS specials,
               (SELECT COUNT(*) FROM player_card_packs k WHERE k.organisation_id = CAST(:o AS UUID) AND k.opened_at::date = d::date) AS packs,
               (SELECT COUNT(*) FROM player_card_swaps s WHERE s.organisation_id = CAST(:o AS UUID) AND s.status = 'accepted' AND s.resolved_at::date = d::date) AS swaps
          FROM generate_series(CURRENT_DATE - {DAYS - 1}, CURRENT_DATE, INTERVAL '1 day') d ORDER BY d
    """), {"o": org})).mappings().all()
    return {
        "recent_specials": recent_specials,
        "recent_cards": recent_cards,
        "recent_openings": list(openings.values()),
        "daily": [{"day": r["day"].isoformat(), "specials_added": int(r["specials"]), "packs_opened": int(r["packs"]), "swaps": int(r["swaps"])} for r in daily],
    }


# ── The set: every card that exists ───────────────────────────────────────────────────────────────────────────

async def catalogue(db: AsyncSession, club: Organisation, snap: dict, *, kind: str = "all", special_kind: Optional[str] = None,
                    q: str = "", sort: str = "rarity", limit: int = 60, offset: int = 0) -> dict:
    """Every card a pack can hold, with how many copies are out there and how many people have one."""
    limit = max(1, min(int(limit or 60), PAGE_MAX))
    offset = max(0, int(offset or 0))
    org = str(club.id)
    held_rows = (await db.execute(text("""
        SELECT subject_player_id::text AS subject, special_id::text AS special_id, COUNT(*) AS copies,
               COUNT(DISTINCT owner_player_id) AS owners, MAX(obtained_at) AS last_got,
               BOOL_OR(owner_player_id = subject_player_id) AS self_has
          FROM player_card_copies WHERE organisation_id = CAST(:o AS UUID) GROUP BY subject_player_id, special_id
    """), {"o": org})).mappings().all()
    held = {(r["subject"], r["special_id"]): (int(r["copies"]), int(r["owners"]), bool(r["self_has"])) for r in held_rows}

    items: list[dict] = []
    if kind in ("all", "player"):
        for pid, f in snap["figs"].items():
            if f["matches"] <= 0 or pid not in snap["people"]:
                continue
            c = cards.regular_card(snap, pid)
            copies, owners, self_has = held.get((pid, None), (0, 0, False))
            # Their own card is theirs without a row: one more copy, and one more owner unless they hold a pulled one too.
            items.append({**c, "held": copies + 1, "owners": owners + (0 if self_has else 1), "added_at": None})
    if kind in ("all", "special"):
        where = "WHERE sc.organisation_id = CAST(:o AS UUID)" + (" AND sc.kind = :sk" if special_kind else "")
        sp = (await db.execute(text(
            "SELECT sc.id, sc.player_id, sc.kind, sc.title, sc.occurred_on, sc.detail, sc.created_at FROM player_special_cards sc " + where
        ), {"o": org, **({"sk": special_kind} if special_kind else {})})).mappings().all()
        for r in sp:
            c = cards.special_card(snap, dict(r))
            if not c:
                continue
            copies, owners, _self = held.get((str(r["player_id"]), str(r["id"])), (0, 0, False))
            items.append({**c, "held": copies, "owners": owners, "added_at": r["created_at"].isoformat()})
    needle = (q or "").strip().lower()
    if needle:
        items = [i for i in items if needle in (i["name"] or "").lower() or needle in (i.get("title") or "").lower()]
    tier_rank = {"special": 5, "legendary": 4, "epic": 3, "rare": 2, "common": 1}
    if sort == "name":
        items.sort(key=lambda i: (i["name"] or "").lower())
    elif sort == "recent":
        items.sort(key=lambda i: i.get("added_at") or "", reverse=True)
    elif sort == "held":
        items.sort(key=lambda i: (i["held"], (i["name"] or "").lower()))
    else:
        items.sort(key=lambda i: (-tier_rank.get(i["tier"], 0), -(i.get("rarity") or 0), (i["name"] or "").lower()))
    return {
        "total": len(items),
        "counts": {"player": sum(1 for i in items if i["kind"] == "player"), "special": sum(1 for i in items if i["kind"] == "special")},
        "items": items[offset:offset + limit],
        "offset": offset, "limit": limit,
    }


# ── One player ────────────────────────────────────────────────────────────────────────────────────────────────

async def player_view(db: AsyncSession, club: Organisation, snap: dict, player: Player) -> dict:
    pid = str(player.id)
    nm = await names(db, club.id)
    coll = await cards.collection(db, club, player, snap)
    packs = (await db.execute(text("""
        SELECT id::text AS id, source, ref_key, granted_at, opened_at FROM player_card_packs
         WHERE player_id = CAST(:p AS UUID) ORDER BY COALESCE(opened_at, granted_at) DESC LIMIT 40
    """), {"p": pid})).mappings().all()
    by_source = (await db.execute(text("""
        SELECT source, COUNT(*) FILTER (WHERE opened_at IS NOT NULL) AS opened, COUNT(*) FILTER (WHERE opened_at IS NULL) AS waiting
          FROM player_card_packs WHERE player_id = CAST(:p AS UUID) GROUP BY source ORDER BY source
    """), {"p": pid})).mappings().all()
    got = (await db.execute(text("""
        SELECT c.subject_player_id::text AS subject, c.special_id::text AS special_id, c.source, c.obtained_at
          FROM player_card_copies c WHERE c.owner_player_id = CAST(:p AS UUID) ORDER BY c.obtained_at DESC LIMIT 25
    """), {"p": pid})).mappings().all()
    specials = await _specials(db, club.id, [r["special_id"] for r in got])
    sw = (await db.execute(text("""
        SELECT s.id::text AS id, s.from_player_id::text AS f, s.to_player_id::text AS t, s.status, s.created_at, s.resolved_at, NOW() AS now,
               s.note, s.parent_swap_id::text AS parent_id
          FROM player_card_swaps s WHERE s.from_player_id = CAST(:p AS UUID) OR s.to_player_id = CAST(:p AS UUID)
         ORDER BY s.created_at DESC LIMIT 25
    """), {"p": pid})).mappings().all()
    sw_items = await swaps._items_of(db, [r["id"] for r in sw])
    sp2 = await _specials(db, club.id, [c[1] for sides in sw_items.values() for side in sides.values() for c, _ in side if c[1]])
    return {
        "player": {"id": pid, "name": nm.get(pid), "in_pool": pid in snap["people"],
                   "rarity": (snap["rating"].get(pid) or {}).get("score"), "tier": (snap["rating"].get(pid) or {}).get("tier")},
        "totals": coll["totals"],
        "cards": coll["cards"],
        "packs": {
            "by_source": [{"source": r["source"], "opened": int(r["opened"]), "waiting": int(r["waiting"])} for r in by_source],
            "recent": [{"id": r["id"], "source": r["source"], "granted_at": r["granted_at"].isoformat(),
                        "opened_at": r["opened_at"].isoformat() if r["opened_at"] else None} for r in packs],
        },
        "recent_cards": [{"source": r["source"], "obtained_at": r["obtained_at"].isoformat(),
                          **_label(nm, snap, r["subject"], r["special_id"], specials)} for r in got],
        "swaps": [_swap_row(r, nm, snap, sp2, sw_items[r["id"]]) for r in sw],
    }


# ── The swap audit ────────────────────────────────────────────────────────────────────────────────────────────

def _swap_row(r, nm: dict, snap: dict, specials: dict, sides: dict) -> dict:
    """One request. `give` and `want` are lists of cards (each with `qty`), as lines of text."""
    status = r["status"]
    if status == "pending":
        if (r["now"] - r["created_at"]).days >= swaps.SWAP_DAYS:
            status = "expired"

    def side(items):
        return [{**_label(nm, snap, c[0], c[1], specials), "qty": qty} for c, qty in items]

    return {
        "id": r["id"], "status": status,
        "from": {"id": r["f"], "name": nm.get(r["f"])}, "to": {"id": r["t"], "name": nm.get(r["t"])},
        "give": side(sides["give"]), "want": side(sides["want"]), "note": r["note"], "parent_id": r["parent_id"],
        "created_at": r["created_at"].isoformat(), "resolved_at": r["resolved_at"].isoformat() if r["resolved_at"] else None,
    }


async def swap_audit(db: AsyncSession, club: Organisation, snap: dict, *, status: str = "all", q: str = "", limit: int = 50, offset: int = 0) -> dict:
    limit = max(1, min(int(limit or 50), PAGE_MAX))
    offset = max(0, int(offset or 0))
    nm = await names(db, club.id)
    cond = ""
    params: dict = {"o": str(club.id)}
    if status in ("accepted", "declined", "cancelled", "countered"):
        cond = " AND s.status = :st"
        params["st"] = status
    elif status == "pending":
        cond = f" AND s.status = 'pending' AND s.created_at > NOW() - INTERVAL '{swaps.SWAP_DAYS} days'"
    elif status == "expired":
        cond = f" AND s.status = 'pending' AND s.created_at <= NOW() - INTERVAL '{swaps.SWAP_DAYS} days'"
    rows = (await db.execute(text(f"""
        SELECT s.id::text AS id, s.from_player_id::text AS f, s.to_player_id::text AS t, s.status, s.created_at, s.resolved_at, NOW() AS now,
               s.note, s.parent_swap_id::text AS parent_id
          FROM player_card_swaps s WHERE s.organisation_id = CAST(:o AS UUID){cond} ORDER BY s.created_at DESC
    """), params)).mappings().all()
    items = await swaps._items_of(db, [r["id"] for r in rows])
    specials = await _specials(db, club.id, [c[1] for sides in items.values() for side in sides.values() for c, _ in side if c[1]])
    shaped = [_swap_row(r, nm, snap, specials, items[r["id"]]) for r in rows]
    needle = (q or "").strip().lower()
    if needle:
        shaped = [s for s in shaped if needle in (s["from"]["name"] or "").lower() or needle in (s["to"]["name"] or "").lower()
                  or any(needle in c["player"].lower() for c in s["give"] + s["want"])]
    counts = (await db.execute(text(f"""
        SELECT COUNT(*) FILTER (WHERE status = 'accepted') AS accepted, COUNT(*) FILTER (WHERE status = 'declined') AS declined,
               COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled, COUNT(*) FILTER (WHERE status = 'countered') AS countered,
               COUNT(*) FILTER (WHERE status = 'pending' AND created_at > NOW() - INTERVAL '{swaps.SWAP_DAYS} days') AS pending,
               COUNT(*) FILTER (WHERE status = 'pending' AND created_at <= NOW() - INTERVAL '{swaps.SWAP_DAYS} days') AS expired
          FROM player_card_swaps WHERE organisation_id = CAST(:o AS UUID)
    """), {"o": str(club.id)})).mappings().first()
    return {"total": len(shaped), "counts": {k: int(v) for k, v in counts.items()}, "swaps": shaped[offset:offset + limit], "offset": offset, "limit": limit}
