"""Player Cards sets: groups of cards a player can work towards completing ("every century at the club", "2015/16 awards").

Sets are defined in code and measured against what is in the club now, so nothing is stored: a new century card makes the
century set one bigger, and a player's progress is the number of its cards they hold. Finishing a set earns a banner and nothing
else (there are no bonus or paid packs). A set needs at least `MIN_SET` cards to be offered.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation
from app.services import player_card_swaps as swaps, player_cards as cards

MIN_SET = 3
AWARD_SEASON_MIN = 3  # a season's awards become a set once the club holds this many of them

KIND_TITLES = {
    "century": ("Every century at the club", "Each hundred a club player has made."),
    "fifty": ("Every half century", "Each fifty a club player has made."),
    "five_for": ("Every five wicket haul", "Five wickets or more in an innings."),
    "hat_trick": ("Every hat-trick", "Three in three balls."),
    "debut": ("Every debut", "A card for each player's first game."),
    "games": ("Every games milestone", "10, 50, 100 and on."),
    "runs_milestone": ("Every runs milestone", "Each 1,000 career runs."),
    "wickets_milestone": ("Every wickets milestone", "Each 200 career wickets."),
    "dismissals_milestone": ("Every dismissals milestone", "Each 50 career dismissals."),
    "award": ("Every club award", "All the awards the club has recorded."),
}
TIER_TITLES = {
    "legendary": ("Every Legendary", "The club's rarest players."),
    "epic": ("Every Epic", "The players just below the very best."),
    "rare": ("Every Rare", "Solid club players, well worth having."),
}


def _season_label(raw) -> str:
    return (raw or "").strip()


async def _special_rows(db: AsyncSession, club: Organisation, snap: dict) -> list[dict]:
    rows = (await db.execute(text(
        "SELECT id::text AS id, player_id::text AS player_id, kind, detail FROM player_special_cards "
        "WHERE organisation_id = CAST(:o AS UUID)"), {"o": str(club.id)})).mappings().all()
    return [dict(r) for r in rows if r["player_id"] in snap["people"]]


async def definitions(db: AsyncSession, club: Organisation, snap: dict) -> list[dict]:
    """Every set the club has, with the keys of its cards: `{key, group, title, blurb, players: set, specials: set}`."""
    out: list[dict] = []
    drawable = [pid for pid, f in snap["figs"].items() if f["matches"] > 0 and pid in snap["people"]]
    for tier, (title, blurb) in TIER_TITLES.items():
        members = {pid for pid in drawable if (snap["rating"].get(pid) or {}).get("tier") == tier}
        if len(members) >= MIN_SET:
            out.append({"key": f"tier:{tier}", "group": "Players", "title": title, "blurb": blurb, "players": members, "specials": set()})
    rows = await _special_rows(db, club, snap)
    by_kind: dict[str, set] = {}
    by_season: dict[str, set] = {}
    for r in rows:
        by_kind.setdefault(r["kind"], set()).add(r["id"])
        if r["kind"] == "award":
            season = _season_label((r["detail"] or {}).get("season"))
            if season:
                by_season.setdefault(season, set()).add(r["id"])
    for kind, (title, blurb) in KIND_TITLES.items():
        members = by_kind.get(kind, set())
        if len(members) >= MIN_SET:
            out.append({"key": f"kind:{kind}", "group": "Special cards", "title": title, "blurb": blurb, "players": set(), "specials": members})
    for season, members in sorted(by_season.items(), reverse=True):
        if len(members) >= AWARD_SEASON_MIN:
            out.append({"key": f"season:{season}", "group": "Awards", "title": f"{season} awards", "blurb": f"The club's awards for {season}.", "players": set(), "specials": members})
    return out


def card_keys(defn: dict) -> set[str]:
    return {f"p:{p}" for p in defn["players"]} | {f"s:{s}" for s in defn["specials"]}


async def held_keys(db: AsyncSession, club: Organisation, me: str) -> set[str]:
    """Every card the player holds, by key; their own card counts without a row."""
    held = (await swaps._rows_by_card(db, club.id, me)).get(me, {})
    keys = {swaps.key_of(*c) for c, n in held.items() if n > 0}
    keys.add(f"p:{me}")
    return keys


async def overview(db: AsyncSession, club: Organisation, snap: dict, me: str) -> dict:
    defs = await definitions(db, club, snap)
    mine = await held_keys(db, club, me)
    sets = []
    for d in defs:
        keys = card_keys(d)
        owned = len(keys & mine)
        sets.append({"key": d["key"], "group": d["group"], "title": d["title"], "blurb": d["blurb"], "total": len(keys), "owned": owned,
                     "percent": round(100 * owned / len(keys)) if keys else 0, "complete": owned >= len(keys)})
    return {"sets": sets, "complete": sum(1 for s in sets if s["complete"])}


async def members(db: AsyncSession, club: Organisation, snap: dict, key: str) -> Optional[tuple[set, set, dict]]:
    """The player ids and special card ids in one set, and its heading, or None when the set does not exist."""
    for d in await definitions(db, club, snap):
        if d["key"] == key:
            return d["players"], d["specials"], {"key": d["key"], "title": d["title"], "blurb": d["blurb"], "group": d["group"]}
    return None
