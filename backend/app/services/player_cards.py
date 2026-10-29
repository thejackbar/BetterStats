"""Player Cards: a collectable card for every player at a club, and the packs that hand them out.

What a card is
--------------
A REGULAR card is a player's six career figures (matches, runs, batting average, wickets, bowling
average, dismissals) plus a RARITY rating from 1 to 99. Nothing about it is stored: figures and
rarity are derived on read from the club's own numbers (`club_snapshot`, cached for a few minutes),
so a corrected scorecard is wrong nowhere. A SPECIAL card commemorates one event (a century, a
five-for, a 100th game) and is frozen at that moment; the event is a row in `player_special_cards`.
What a person OWNS is a row in `player_card_copies`, one row per copy. Their own card is always
theirs and is never a row.

Which players are in the pool
-----------------------------
The club's real players, minus anyone hidden from the public site (`players.is_public` false, which
is also how a removal request is honoured), minus anyone the club took out of the card pool, minus
players whose only cricket is junior unless the club switched juniors on, and minus players with no
match played yet (they have a card, but nobody can pull it). A card someone already owns of a player
who later leaves the pool is not shown.

Figures are the unfiltered career block (every grade, `v_effective_player_season_stats`), the same
source the profile reads before any grade lens. It is not raised to the scorecards the club holds, so
a profile can read a game or two higher for a player Cricket Australia undercounted.

How packs are earned
--------------------
Grants only ever ADD a row (`player_card_packs`, unique on player, source and ref_key), so a figure
corrected downwards never takes a pack back and a re-run grants nothing twice:

* starter: two, once, when a player first opens their cards.
* weekly: the club's weekly count, per Monday-to-Sunday week in the club's timezone. A week's pack
  expires when the week ends; every other pack banks.
* milestone: one per 25 runs, per 2 wickets and per 2 dismissals (catches, run outs, stumpings) in the
  club's current season, all grades. The first look backfills the whole season.
* duck: one per duck scored since the club first used cards (the "better luck next time" pack).
* achievement: one for each century, five-for, hat-trick, fifty and landmark (a games, runs, wickets or dismissals
  milestone card) dated on or after the club first used cards. Nothing is backfilled from history.
* a day: Match Day (the player is in a team sheet or played a game today), a holiday (Halloween, the Melbourne Cup,
  Christmas, Boxing Day, New Year, Australia Day, Anzac Day), a birthday, a surprise drop on random days, and any day
  the club schedules itself (a Test match). Granted when the player opens their page that day, then banked.

Odds
----
Standard packs: each card is a special card 5% of the time (when the club has any), otherwise a regular card whose
tier is drawn Common 60, Rare 28, Epic 10, Legendary 2. Every pack holds at least one Rare or better, and the same card
does not appear twice in one pack. Day packs and achievement packs have their own odds, a bigger guaranteed Rare-or-better
count and a better special chance; all of that lives in `player_card_pack_kinds`.
"""
from __future__ import annotations

import logging
import secrets
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation, Player
from app.services import player_card_designs as pack_designs, player_card_pack_kinds as kinds
from app.services.game_status import NOT_PLAYED_SQL_LIST
from app.services.season_kind import season_key_sql

logger = logging.getLogger(__name__)

PACK_SIZE = 5
MIN_PACK_SIZE = 1
MAX_PACK_SIZE = 12
STARTER_PACKS = 2
DEFAULT_TIMEZONE = "Australia/Perth"
DEFAULT_WEEKLY_PACKS = 1
MAX_WEEKLY_PACKS = 10
RUNS_PER_PACK = 25
WICKETS_PER_PACK = 2
DISMISSALS_PER_PACK = 2
OPEN_ALL_LIMIT = 500

TIERS = ("common", "rare", "epic", "legendary")
# Lowest rarity rating that earns each tier.
TIER_FROM = (("legendary", 90), ("epic", 75), ("rare", 55), ("common", 0))
PACK_WEIGHTS = kinds.STANDARD
SPECIAL_CHANCE = 0.05
GAMES_MILESTONES = (10, 50, 100, 150, 200, 250, 300, 400, 500)

PACK_SOURCES = {key: k.label for key, k in kinds.KINDS.items()}

SPECIAL_KINDS = {
    "century": "Century",
    "fifty": "Half century",
    "five_for": "Five wicket haul",
    "hat_trick": "Hat-trick",
    "debut": "Debut",
    "games": "Games milestone",
    "runs_milestone": "Runs milestone",
    "wickets_milestone": "Wickets milestone",
    "dismissals_milestone": "Dismissals milestone",
    "award": "Club award",
}

# A card for every step of a career figure: 1,000 runs, 2,000 runs and so on. (kind, figure in `figs`, step, the most
# cards one player can get for it). The cap keeps a bad imported total from making dozens of cards.
STAT_MILESTONES = (
    ("runs_milestone", "runs", 1000, 30),
    ("wickets_milestone", "wickets", 200, 10),
    ("dismissals_milestone", "dismissals", 50, 20),
)

# Which cards get a full-card photo (club setting `big_photos`), and which of the player's shots a card uses.
PHOTO_MODES = ("top", "specials", "all")
BIG_PHOTO_TIERS = ("epic", "legendary")

# What a player is given when a card is made about them: their debut and their latest landmark, or every one.
GIFT_MODES = ("minimal", "all")
LANDMARK_KINDS = ("games", "runs_milestone", "wickets_milestone", "dismissals_milestone")

_rng = secrets.SystemRandom()


# ── Settings ──────────────────────────────────────────────────────────────────

def default_settings() -> dict:
    return {
        "enabled": True,
        "include_juniors": False,
        "weekly_packs": DEFAULT_WEEKLY_PACKS,
        "timezone": None,
        "launched_at": None,
        "alerts_enabled": True,
        "sets_enabled": True,
        "showcase_enabled": True,
        "board_enabled": True,
        "feed_enabled": True,
        "event_packs_enabled": True,
        "starter_gifts": "minimal",
        "big_photos": "all",
    }


def club_zone(settings: dict) -> ZoneInfo:
    """The club's own timezone for the weekly reset. A stored name that no longer resolves falls
    back to the platform default rather than failing the page."""
    for name in (settings.get("timezone"), DEFAULT_TIMEZONE):
        if not name:
            continue
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            continue
    return ZoneInfo("UTC")


def week_key(settings: dict, now: Optional[datetime] = None) -> str:
    """ISO year and week of the club's local date. Monday 00:00 starts a new key."""
    local = (now or datetime.now(timezone.utc)).astimezone(club_zone(settings))
    iso = local.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def week_ends_at(settings: dict, now: Optional[datetime] = None) -> datetime:
    """The next Monday 00:00 in the club's timezone, as an aware datetime."""
    zone = club_zone(settings)
    local = (now or datetime.now(timezone.utc)).astimezone(zone)
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday + timedelta(days=7)


async def load_settings(db: AsyncSession, org_id) -> dict:
    row = (await db.execute(text(
        "SELECT enabled, include_juniors, weekly_packs, timezone, launched_at, alerts_enabled, "
        "sets_enabled, showcase_enabled, board_enabled, feed_enabled, event_packs_enabled, starter_gifts, big_photos "
        "FROM club_card_settings WHERE organisation_id = CAST(:o AS UUID)"
    ), {"o": str(org_id)})).mappings().first()
    if not row:
        return default_settings()
    out = dict(row)
    out["weekly_packs"] = max(0, min(int(out.get("weekly_packs") or 0), MAX_WEEKLY_PACKS))
    if out.get("starter_gifts") not in GIFT_MODES:
        out["starter_gifts"] = "minimal"
    if out.get("big_photos") not in PHOTO_MODES:
        out["big_photos"] = "all"
    return out


async def ensure_launched(db: AsyncSession, org_id) -> dict:
    """The settings, with the club's launch time stamped on first use. Duck packs count from it."""
    await db.execute(text(
        "INSERT INTO club_card_settings (organisation_id, launched_at) "
        "VALUES (CAST(:o AS UUID), NOW()) "
        "ON CONFLICT (organisation_id) DO UPDATE SET launched_at = NOW() "
        "WHERE club_card_settings.launched_at IS NULL"
    ), {"o": str(org_id)})
    return await load_settings(db, org_id)


async def save_settings(db: AsyncSession, org_id, patch: dict) -> dict:
    """Apply only the keys that were sent: an absent key leaves the field alone."""
    await ensure_launched(db, org_id)
    sets, params = [], {"o": str(org_id)}
    if "enabled" in patch and patch["enabled"] is not None:
        sets.append("enabled = :enabled")
        params["enabled"] = bool(patch["enabled"])
    if "include_juniors" in patch and patch["include_juniors"] is not None:
        sets.append("include_juniors = :include_juniors")
        params["include_juniors"] = bool(patch["include_juniors"])
    if "weekly_packs" in patch and patch["weekly_packs"] is not None:
        sets.append("weekly_packs = :weekly_packs")
        params["weekly_packs"] = max(0, min(int(patch["weekly_packs"]), MAX_WEEKLY_PACKS))
    for flag in ("alerts_enabled", "sets_enabled", "showcase_enabled", "board_enabled", "feed_enabled",
                 "event_packs_enabled"):
        if flag in patch and patch[flag] is not None:
            sets.append(f"{flag} = :{flag}")
            params[flag] = bool(patch[flag])
    if "starter_gifts" in patch and patch["starter_gifts"] is not None:
        if patch["starter_gifts"] not in GIFT_MODES:
            raise ValueError("Starting cards are either minimal or all.")
        sets.append("starter_gifts = :starter_gifts")
        params["starter_gifts"] = patch["starter_gifts"]
    if "big_photos" in patch and patch["big_photos"] is not None:
        if patch["big_photos"] not in PHOTO_MODES:
            raise ValueError("Pick which cards get the big photo: top, specials or all.")
        sets.append("big_photos = :big_photos")
        params["big_photos"] = patch["big_photos"]
    if "timezone" in patch:
        tz = (patch["timezone"] or "").strip() or None
        if tz:
            try:
                ZoneInfo(tz)
            except (ZoneInfoNotFoundError, ValueError, OSError):
                raise ValueError("That is not a timezone we know.")
        sets.append("timezone = :timezone")
        params["timezone"] = tz
    if sets:
        sets.append("updated_at = NOW()")
        await db.execute(text(
            f"UPDATE club_card_settings SET {', '.join(sets)} WHERE organisation_id = CAST(:o AS UUID)"
        ), params)
    forget(org_id)
    return await load_settings(db, org_id)


async def hidden_ids(db: AsyncSession, org_id) -> set[str]:
    rows = await db.execute(text(
        "SELECT player_id::text FROM player_card_hidden WHERE organisation_id = CAST(:o AS UUID)"
    ), {"o": str(org_id)})
    return {r[0] for r in rows.fetchall()}


async def set_hidden(db: AsyncSession, org_id, player_id, hidden: bool, by: Optional[str]) -> None:
    if hidden:
        await db.execute(text(
            "INSERT INTO player_card_hidden (organisation_id, player_id, hidden_by) "
            "VALUES (CAST(:o AS UUID), CAST(:p AS UUID), :by) "
            "ON CONFLICT (organisation_id, player_id) DO NOTHING"
        ), {"o": str(org_id), "p": str(player_id), "by": by})
    else:
        await db.execute(text(
            "DELETE FROM player_card_hidden WHERE organisation_id = CAST(:o AS UUID) "
            "AND player_id = CAST(:p AS UUID)"
        ), {"o": str(org_id), "p": str(player_id)})
    forget(org_id)


# ── Rarity ────────────────────────────────────────────────────────────────────

def tier_for(score: int) -> str:
    for tier, floor in TIER_FROM:
        if score >= floor:
            return tier
    return "common"


def _pct(sorted_vals: list[float], v: float) -> float:
    """Where `v` sits among `sorted_vals`, 0 to 100 (ties share the midpoint)."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    lo = sum(1 for x in sorted_vals if x < v)
    eq = sum(1 for x in sorted_vals if x == v)
    return 100.0 * (lo + 0.5 * eq) / n


def _avg(runs, innings, not_outs) -> Optional[float]:
    outs = (innings or 0) - (not_outs or 0)
    return round(runs / outs, 2) if outs > 0 else None


def _bowl_avg(conceded, wickets) -> Optional[float]:
    return round(conceded / wickets, 2) if wickets and wickets > 0 else None


def _rank_bonus(rank: Optional[int]) -> int:
    if rank is None:
        return 0
    if rank == 1:
        return 6
    if rank <= 3:
        return 4
    if rank <= 10:
        return 2
    return 0


def rate_pool(figs: dict[str, dict]) -> dict[str, dict]:
    """`{pid: {"score": 1..99, "tier": ...}}` for every player in `figs`.

    The score blends where a player sits in the club (percentiles, so a small club's best is still
    its best), weighted to the stronger of batting and bowling, then adds a bonus for standing on the
    club's all-time boards (runs, wickets, dismissals, matches). Players with no matches get 1."""
    played = {p: f for p, f in figs.items() if f["matches"] > 0}
    out = {p: {"score": 1, "tier": "common"} for p in figs}
    if not played:
        return out

    def col(key):
        return sorted(f[key] for f in played.values())

    runs_s, wk_s, dis_s, mat_s = col("runs"), col("wickets"), col("dismissals"), col("matches")
    bat_avgs = sorted(f["bat_avg"] for f in played.values() if f["bat_avg"] is not None and f["innings"] >= 10)
    bowl_avgs = sorted(f["bowl_avg"] for f in played.values() if f["bowl_avg"] is not None and f["wickets"] >= 10)

    ranks = {}
    for key in ("runs", "wickets", "dismissals", "matches"):
        order = sorted(played.values(), key=lambda f: -f[key])
        for f in order:
            if f[key] <= 0:
                continue
            ranks.setdefault(f["pid"], {})[key] = 1 + sum(1 for g in played.values() if g[key] > f[key])

    for pid, f in played.items():
        bat = _pct(runs_s, f["runs"]) if f["runs"] > 0 else 0.0
        if f["bat_avg"] is not None and f["innings"] >= 10 and bat_avgs:
            bat = 0.65 * bat + 0.35 * _pct(bat_avgs, f["bat_avg"])
        bowl = _pct(wk_s, f["wickets"]) if f["wickets"] > 0 else 0.0
        if f["bowl_avg"] is not None and f["wickets"] >= 10 and bowl_avgs:
            bowl = 0.65 * bowl + 0.35 * (100.0 - _pct(bowl_avgs, f["bowl_avg"]))
        field = _pct(dis_s, f["dismissals"]) if f["dismissals"] > 0 else 0.0
        longevity = _pct(mat_s, f["matches"])
        base = 0.40 * max(bat, bowl) + 0.15 * min(bat, bowl) + 0.15 * field + 0.30 * longevity
        bonuses = sorted((_rank_bonus(r) for r in ranks.get(pid, {}).values()), reverse=True)
        bonus = min(sum(bonuses[:2]), 10)
        score = max(1, min(99, int(round(base + bonus))))
        out[pid] = {"score": score, "tier": tier_for(score)}
    return out


# ── The club snapshot ─────────────────────────────────────────────────────────

_FIGURES_SQL = """
    SELECT pss.player_id::text AS pid,
           COALESCE(SUM(pss.matches), 0)         AS matches,
           COALESCE(SUM(pss.runs), 0)            AS runs,
           COALESCE(SUM(pss.batting_innings), 0) AS innings,
           COALESCE(SUM(pss.not_outs), 0)        AS not_outs,
           COALESCE(SUM(pss.wickets), 0)         AS wickets,
           COALESCE(SUM(pss.runs_conceded), 0)   AS conceded,
           COALESCE(SUM(pss.catches), 0)         AS catches,
           COALESCE(SUM(pss.run_outs), 0)        AS run_outs,
           COALESCE(SUM(pss.stumpings), 0)       AS stumpings
      FROM v_effective_player_season_stats pss
     WHERE pss.player_id = ANY(CAST(:pids AS uuid[]))
     GROUP BY pss.player_id
"""

_SNAP_TTL = 300.0
_SNAP_MAX = 60
_SNAP: dict[str, tuple[float, dict]] = {}
_SPECIAL_REFRESH: dict[str, float] = {}
SPECIAL_REFRESH_TTL = 600.0


def forget(org_id=None) -> None:
    """Drop the cached snapshot (settings, a hidden player or a merge changed who is in the pool)."""
    if org_id is None:
        _SNAP.clear()
        _SPECIAL_REFRESH.clear()
        return
    _SNAP.pop(str(org_id), None)


def _int(v) -> int:
    return int(v or 0)


async def _club_players(db: AsyncSession, org_id) -> list[Player]:
    from sqlalchemy import select
    res = await db.execute(select(Player).where(Player.organisation_id == org_id, Player.is_player.is_(True)))
    return list(res.scalars().all())


async def _junior_only(db: AsyncSession, org_id) -> set[str]:
    from app.services import junior_hiding
    try:
        grades = await junior_hiding.junior_grade_ids(db, org_id)
        return await junior_hiding.junior_only_player_ids(db, org_id, grades)
    except Exception:  # noqa: BLE001 - a failure here must not take the cards down; fail towards hiding nobody extra
        logger.exception("player cards: junior lookup failed for %s", org_id)
        from app.services.session_safety import rollback_keeping
        await rollback_keeping(db)
        return set()


async def club_snapshot(db: AsyncSession, club: Organisation, *, fresh: bool = False) -> dict:
    """The club's card pool, cached for a few minutes.

    ``{"settings", "people": {pid: person}, "figs": {pid: figures}, "rating": {pid: rarity},
    "pool": {tier: [pid]}, "current_season_ids": [...], "season_label"}``. `people` holds every
    eligible player (their own card always works); `pool` holds only those with a match played."""
    key = str(club.id)
    hit = _SNAP.get(key)
    now = time.monotonic()
    if hit and not fresh and now - hit[0] < _SNAP_TTL:
        return hit[1]

    settings = await load_settings(db, club.id)
    players = await _club_players(db, club.id)
    hidden = await hidden_ids(db, club.id)
    juniors = set() if settings["include_juniors"] else await _junior_only(db, club.id)

    people: dict[str, dict] = {}
    for p in players:
        pid = str(p.id)
        if p.is_public is False or pid in hidden or pid.lower() in juniors:
            continue
        people[pid] = {
            "id": pid,
            "display_name": p.display_name,
            "photo_url": p.photo_url,
            "hero_photo_url": getattr(p, "hero_photo_url", None),
            "action_photo_url": getattr(p, "action_photo_url", None),
            "hero_source": getattr(p, "hero_source", None),
        }

    figs: dict[str, dict] = {}
    if people:
        rows = await db.execute(text(_FIGURES_SQL), {"pids": list(people)})
        for r in rows.mappings():
            innings, not_outs = _int(r["innings"]), _int(r["not_outs"])
            runs, wickets, conceded = _int(r["runs"]), _int(r["wickets"]), _int(r["conceded"])
            figs[r["pid"]] = {
                "pid": r["pid"],
                "matches": _int(r["matches"]),
                "runs": runs,
                "innings": innings,
                "bat_avg": _avg(runs, innings, not_outs),
                "wickets": wickets,
                "bowl_avg": _bowl_avg(conceded, wickets),
                "dismissals": _int(r["catches"]) + _int(r["run_outs"]) + _int(r["stumpings"]),
            }
    for pid in people:
        figs.setdefault(pid, {"pid": pid, "matches": 0, "runs": 0, "innings": 0, "bat_avg": None,
                              "wickets": 0, "bowl_avg": None, "dismissals": 0})

    rating = rate_pool(figs)
    pool: dict[str, list[str]] = {t: [] for t in TIERS}
    for pid, f in figs.items():
        if f["matches"] > 0:
            pool[rating[pid]["tier"]].append(pid)

    season_ids, season_label = await _current_season(db, club.id, list(people))
    snap = {
        "org_id": key, "settings": settings, "people": people, "figs": figs, "rating": rating, "pool": pool,
        "current_season_ids": season_ids, "season_label": season_label,
    }
    if len(_SNAP) >= _SNAP_MAX:
        _SNAP.clear()
    _SNAP[key] = (now, snap)
    return snap


async def _current_season(db: AsyncSession, org_id, pids: list[str]) -> tuple[list[str], Optional[str]]:
    """The club's own season ids for the season of its newest played game, as (year, kind), plus its
    name. Never `ORDER BY year DESC, name DESC` (Winter sorts after Summer)."""
    if not pids:
        return [], None
    try:
        latest = (await db.execute(text("""
            SELECT g.season_id
              FROM (SELECT game_id FROM game_appearances WHERE player_id = ANY(CAST(:pids AS uuid[]))
                    UNION
                    SELECT game_id FROM v_effective_batting_innings WHERE player_id = ANY(CAST(:pids AS uuid[]))) pg
              JOIN v_effective_games g ON g.id = pg.game_id
             WHERE g.played_at IS NOT NULL AND g.played_at <= CURRENT_DATE AND g.season_id IS NOT NULL
               AND (g.status IS NULL OR g.status NOT IN (""" + NOT_PLAYED_SQL_LIST + """))
             ORDER BY g.played_at DESC
             LIMIT 1
        """), {"pids": pids})).scalar()
        if not latest:
            return [], None
        key_sql = season_key_sql("s.year", "s.name")
        rows = (await db.execute(text(f"""
            SELECT s.id::text, s.name FROM seasons s
             WHERE s.organisation_id = CAST(:org AS UUID)
               AND {key_sql} = (SELECT {season_key_sql('s2.year', 's2.name')} FROM seasons s2 WHERE s2.id = :sid)
        """), {"org": str(org_id), "sid": latest})).fetchall()
        # The newest game may sit in a shared fixture filed under another club's season; then the club
        # has no season of that (year, kind) and the current season is simply the one it has.
        if not rows:
            return [], None
        return [r[0] for r in rows], rows[0][1]
    except Exception:  # noqa: BLE001 - milestone packs wait; nothing else depends on it
        logger.exception("player cards: current season lookup failed for %s", org_id)
        from app.services.session_safety import rollback_keeping
        await rollback_keeping(db)
        return [], None


# ── Card payloads ─────────────────────────────────────────────────────────────

def card_shot(person: dict, tier: str, special_kind: Optional[str], mode: str) -> str:
    """Which of the player's photos a card shows: `hero`, `action` (both fill the card) or `profile` (the circle).

    By default every card fills with the player's HERO photo when they have one, and every special card (a century, a five-for, a
    debut, a milestone, an award) with their ACTION shot. A club can narrow that with `big_photos` (`top`: special, Epic and
    Legendary cards; `specials`: special cards only), and the cards left out show the profile photo in a circle. A club's per-player pin
    (`hero_source`) beats the card's own choice, because somebody decided it for this player.

    Nothing is left blank: a special card without an action shot falls to the hero photo, then the profile photo; a regular card
    without a hero photo keeps its circle (it does not borrow the action shot) unless the player has no profile photo, when the action
    shot is used rather than the club logo."""
    shots = {"hero": person.get("hero_photo_url"), "action": person.get("action_photo_url")}
    special = special_kind is not None
    big = special or mode == "all" or (mode == "top" and tier in BIG_PHOTO_TIERS)
    if not big and person.get("photo_url"):
        return "profile"
    pin = person.get("hero_source")
    if pin in shots:
        want = pin
    elif special:
        want = "action"
    else:
        want = "hero"
    for k in (want, "hero" if want == "action" else "action"):
        if not shots[k]:
            continue
        if k != want and not special and pin not in shots and person.get("photo_url"):
            continue
        return k
    return "profile"


def regular_card(snap: dict, pid: str) -> Optional[dict]:
    person = snap["people"].get(pid)
    if not person:
        return None
    f = snap["figs"].get(pid) or {}
    r = snap["rating"].get(pid) or {"score": 1, "tier": "common"}
    return {
        "kind": "player",
        "key": f"p:{pid}",
        "player_id": pid,
        "name": person["display_name"],
        "photo_url": person["photo_url"],
        "hero_photo_url": person["hero_photo_url"],
        "action_photo_url": person["action_photo_url"],
        "hero_source": person["hero_source"],
        "matches": f.get("matches", 0),
        "runs": f.get("runs", 0),
        "bat_avg": f.get("bat_avg"),
        "wickets": f.get("wickets", 0),
        "bowl_avg": f.get("bowl_avg"),
        "dismissals": f.get("dismissals", 0),
        "rarity": r["score"],
        "tier": r["tier"],
        "shot": card_shot(person, r["tier"], None, snap["settings"].get("big_photos") or "all"),
    }


def special_card(snap: dict, row: dict) -> Optional[dict]:
    person = snap["people"].get(str(row["player_id"]))
    if not person:
        return None
    return {
        "kind": "special",
        "key": f"s:{row['id']}",
        "special_id": str(row["id"]),
        "special_kind": row["kind"],
        "player_id": str(row["player_id"]),
        "name": person["display_name"],
        "photo_url": person["photo_url"],
        "hero_photo_url": person["hero_photo_url"],
        "action_photo_url": person["action_photo_url"],
        "hero_source": person["hero_source"],
        "title": row["title"],
        "occurred_on": row["occurred_on"].isoformat() if row["occurred_on"] else None,
        "detail": row["detail"] or {},
        "tier": "special",
        "shot": card_shot(person, "special", row["kind"], snap["settings"].get("big_photos") or "all"),
    }


async def _specials_by_id(db: AsyncSession, org_id, ids: Iterable) -> dict[str, dict]:
    ids = [str(i) for i in ids]
    if not ids:
        return {}
    rows = await db.execute(text(
        "SELECT id, player_id, kind, title, occurred_on, detail FROM player_special_cards "
        "WHERE organisation_id = CAST(:o AS UUID) AND id = ANY(CAST(:ids AS uuid[]))"
    ), {"o": str(org_id), "ids": ids})
    return {str(r["id"]): dict(r) for r in rows.mappings()}


async def _all_special_ids(db: AsyncSession, org_id) -> list[tuple[str, str]]:
    rows = await db.execute(text(
        "SELECT id::text, player_id::text FROM player_special_cards WHERE organisation_id = CAST(:o AS UUID)"
    ), {"o": str(org_id)})
    return [(r[0], r[1]) for r in rows.fetchall()]


# ── Special cards (events) ────────────────────────────────────────────────────

# Opposition: the side of the game our player was not on (by the appearance's team), else CA's own
# field, which a shared fixture only gets right from one side.
_OPP = ("COALESCE(CASE WHEN ga.team_name = g.home_team THEN g.away_team "
        "WHEN ga.team_name = g.away_team THEN g.home_team END, g.opp_club_name)")

_INSERT_PREFIX = ("INSERT INTO player_special_cards (organisation_id, player_id, kind, event_key, game_id, "
                  "occurred_on, title, detail) ")
_INSERT_SUFFIX = " ON CONFLICT (organisation_id, event_key) DO NOTHING"


async def _insert_batting(db, org: str, pids: list[str], kind: str, lo: int, hi: Optional[int], title: str) -> int:
    upper = f" AND bi.runs <= {int(hi)}" if hi is not None else ""
    res = await db.execute(text(
        _INSERT_PREFIX + f"""
        SELECT CAST(:org AS UUID), bi.player_id, '{kind}',
               '{kind}:' || bi.player_id::text || ':' || COALESCE(g.played_at::text, bi.game_id::text) || ':' || COALESCE(bi.innings_number, 1)::text,
               bi.game_id, g.played_at, '{title}',
               jsonb_build_object('runs', bi.runs, 'not_out', COALESCE(bi.not_out, FALSE), 'balls', bi.balls,
                                  'fours', bi.fours, 'sixes', bi.sixes, 'opposition', {_OPP})
          FROM v_effective_batting_innings bi
          JOIN v_effective_games g ON g.id = bi.game_id
          LEFT JOIN game_appearances ga ON ga.game_id = bi.game_id AND ga.player_id = bi.player_id
         WHERE bi.player_id = ANY(CAST(:pids AS uuid[]))
           AND COALESCE(bi.did_not_bat, FALSE) = FALSE
           AND bi.runs >= {int(lo)}{upper}
        """ + _INSERT_SUFFIX), {"org": org, "pids": pids})
    return res.rowcount or 0


async def _insert_five_fors(db, org: str, pids: list[str]) -> int:
    res = await db.execute(text(
        _INSERT_PREFIX + f"""
        SELECT CAST(:org AS UUID), bs.player_id, 'five_for',
               'five_for:' || bs.player_id::text || ':' || COALESCE(g.played_at::text, bs.game_id::text) || ':' || COALESCE(bs.innings_number, 1)::text,
               bs.game_id, g.played_at, 'Five wicket haul',
               jsonb_build_object('wickets', bs.wickets, 'runs', bs.runs, 'overs', bs.overs, 'maidens', bs.maidens,
                                  'opposition', {_OPP})
          FROM v_effective_bowling_spells bs
          JOIN v_effective_games g ON g.id = bs.game_id
          LEFT JOIN game_appearances ga ON ga.game_id = bs.game_id AND ga.player_id = bs.player_id
         WHERE bs.player_id = ANY(CAST(:pids AS uuid[])) AND bs.wickets >= 5
        """ + _INSERT_SUFFIX), {"org": org, "pids": pids})
    return res.rowcount or 0


# A club types its award's name and its season in more than one way: `player_achievements.season` holds a
# seasons id (what the Awards screen writes) or a plain label like "2015_16" (what an import writes), and the
# club may have given the award a display name under Award definitions. A card reads both the way the honour
# board does (`services/honours.py`): the seasons row's name, "_" read as "/", and the club's own name for the
# award. The definition is picked with a scalar subquery so two definitions under one name cannot fan a row out.
_AWARD_SEASON_JOIN = """
          LEFT JOIN seasons se ON se.organisation_id = pa.org_id AND se.id = CASE
               WHEN pa.season ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
               THEN CAST(pa.season AS UUID) ELSE NULL END"""
_AWARD_SEASON = ("NULLIF(REGEXP_REPLACE(BTRIM(COALESCE(se.name, pa.season, '')), "
                 "'^([0-9]{4})_([0-9]{2}|[0-9]{4})$', '\\1/\\2'), '')")
_AWARD_TITLE = """LEFT(COALESCE(
                 (SELECT NULLIF(BTRIM(d.display_name), '') FROM org_award_definitions d
                   WHERE d.org_id = pa.org_id AND d.category = pa.category
                     AND COALESCE(d.subcategory, '') = COALESCE(pa.subcategory, '') AND d.achievement = pa.achievement
                     AND NULLIF(BTRIM(d.display_name), '') IS NOT NULL
                   ORDER BY d.sort_order, d.id LIMIT 1),
                 pa.achievement), 120)"""


async def _insert_achievements(db, org: str, pids: list[str]) -> int:
    """Hat-tricks and club awards the club recorded against a player. One card per recorded row, titled with the
    club's own name for the award and dated with the season as the club writes it. A card made earlier is brought
    in line (title and detail only; the card, its copies and its date stay), so a rename or a corrected season
    reaches it."""
    total = 0
    res = await db.execute(text(
        _INSERT_PREFIX + f"""
        SELECT CAST(:org AS UUID), pa.player_id, 'hat_trick', 'hat_trick:achievement:' || pa.id::text,
               NULL, NULL, 'Hat-trick',
               jsonb_build_object('season', {_AWARD_SEASON}, 'note', pa.detail)
          FROM player_achievements pa {_AWARD_SEASON_JOIN}
         WHERE pa.org_id = CAST(:org AS UUID) AND pa.player_id = ANY(CAST(:pids AS uuid[]))
           AND (LOWER(COALESCE(pa.subcategory, '')) = 'hat tricks'
                OR LOWER(pa.achievement) = 'hat trick'
                OR LOWER(pa.achievement) LIKE 'hat-trick%' OR LOWER(pa.achievement) LIKE 'hat trick%')
        """ + _INSERT_SUFFIX), {"org": org, "pids": pids})
    total += res.rowcount or 0
    res = await db.execute(text(
        _INSERT_PREFIX + f"""
        SELECT CAST(:org AS UUID), pa.player_id, 'award', 'award:achievement:' || pa.id::text,
               NULL, NULL, {_AWARD_TITLE},
               jsonb_build_object('season', {_AWARD_SEASON}, 'grade', pa.subcategory, 'note', pa.detail)
          FROM player_achievements pa {_AWARD_SEASON_JOIN}
         WHERE pa.org_id = CAST(:org AS UUID) AND pa.player_id = ANY(CAST(:pids AS uuid[]))
           AND LOWER(pa.category) = 'club award'
        """ + _INSERT_SUFFIX), {"org": org, "pids": pids})
    total += res.rowcount or 0
    # Existing award and hat-trick cards read the same way. Only a row that still exists is touched, and only
    # where the wording differs, so a refresh with nothing changed writes nothing.
    await db.execute(text(f"""
        UPDATE player_special_cards c
           SET title = x.title, detail = x.detail
          FROM (SELECT 'award:achievement:' || pa.id::text AS event_key, {_AWARD_TITLE} AS title,
                       jsonb_build_object('season', {_AWARD_SEASON}, 'grade', pa.subcategory, 'note', pa.detail) AS detail
                  FROM player_achievements pa {_AWARD_SEASON_JOIN}
                 WHERE pa.org_id = CAST(:org AS UUID) AND pa.player_id = ANY(CAST(:pids AS uuid[]))
                   AND LOWER(pa.category) = 'club award') x
         WHERE c.organisation_id = CAST(:org AS UUID) AND c.kind = 'award' AND c.event_key = x.event_key
           AND (c.title IS DISTINCT FROM x.title OR c.detail IS DISTINCT FROM x.detail)
    """), {"org": org, "pids": pids})
    await db.execute(text(f"""
        UPDATE player_special_cards c
           SET detail = x.detail
          FROM (SELECT 'hat_trick:achievement:' || pa.id::text AS event_key,
                       jsonb_build_object('season', {_AWARD_SEASON}, 'note', pa.detail) AS detail
                  FROM player_achievements pa {_AWARD_SEASON_JOIN}
                 WHERE pa.org_id = CAST(:org AS UUID) AND pa.player_id = ANY(CAST(:pids AS uuid[]))) x
         WHERE c.organisation_id = CAST(:org AS UUID) AND c.kind = 'hat_trick' AND c.event_key = x.event_key
           AND c.detail IS DISTINCT FROM x.detail
    """), {"org": org, "pids": pids})
    return total


async def _insert_game_milestones(db, org: str, snap: dict) -> int:
    """A debut and a card at each games milestone a player has reached. Reached is the profile's own
    matches figure, so a career held only as a season total still earns them; the date is the date
    of that numbered game when we hold it, else blank."""
    figs = snap["figs"]
    pids = [p for p, f in figs.items() if f["matches"] > 0]
    if not pids:
        return 0
    rows = await db.execute(text("""
        WITH played AS (
            SELECT player_id, game_id FROM game_appearances
             WHERE player_id = ANY(CAST(:pids AS uuid[])) AND is_reserve IS NOT TRUE
            UNION
            SELECT player_id, game_id FROM v_effective_batting_innings
             WHERE player_id = ANY(CAST(:pids AS uuid[])) AND COALESCE(did_not_bat, FALSE) = FALSE
            UNION
            SELECT player_id, game_id FROM v_effective_bowling_spells
             WHERE player_id = ANY(CAST(:pids AS uuid[]))
        ), dated AS (
            SELECT p.player_id, g.played_at, g.id AS game_id,
                   ROW_NUMBER() OVER (PARTITION BY p.player_id ORDER BY g.played_at, g.id) AS n
              FROM played p JOIN v_effective_games g ON g.id = p.game_id
             WHERE g.played_at IS NOT NULL AND (g.status IS NULL OR g.status NOT IN (""" + NOT_PLAYED_SQL_LIST + """))
        )
        SELECT player_id::text AS pid, n, played_at, game_id::text AS game_id
          FROM dated WHERE n = 1 OR n = ANY(CAST(:marks AS int[]))
    """), {"pids": pids, "marks": list(GAMES_MILESTONES)})
    dates: dict[tuple[str, int], tuple] = {(r["pid"], int(r["n"])): (r["played_at"], r["game_id"]) for r in rows.mappings()}

    batch: list[dict] = []
    for pid in pids:
        m = figs[pid]["matches"]
        wanted = [("debut", 1, "Debut")] + [("games", t, f"{t} games") for t in GAMES_MILESTONES if m >= t]
        for kind, n, title in wanted:
            played_at, game_id = dates.get((pid, n), (None, None))
            batch.append({"org": org, "pid": pid, "kind": kind, "key": f"{kind}:{pid}:{n}", "gid": game_id,
                          "on": played_at, "title": title, "detail": f'{{"games": {n}}}'})
    if batch:
        await db.execute(text(
            _INSERT_PREFIX + "VALUES (CAST(:org AS UUID), CAST(:pid AS UUID), :kind, :key, "
            "CAST(:gid AS UUID), :on, :title, CAST(:detail AS JSONB))" + _INSERT_SUFFIX
        ), batch)
    return len(batch)


# Where a career figure grew, game by game, so a milestone card can say when it was reached. Each kind reads one
# per-game view and says how much a row adds.
_MILESTONE_SOURCES = {
    "runs_milestone": ("v_effective_batting_innings", "x.runs", "x.runs IS NOT NULL AND COALESCE(x.did_not_bat, FALSE) = FALSE", "x.innings_number"),
    "wickets_milestone": ("v_effective_bowling_spells", "COALESCE(x.wickets, 0)", "TRUE", "x.innings_number"),
    "dismissals_milestone": ("v_effective_fielding_stats", "COALESCE(x.catches, 0) + COALESCE(x.run_outs, 0) + COALESCE(x.stumpings, 0)", "TRUE", "x.id"),
}
_NOUN = {"runs_milestone": "runs", "wickets_milestone": "wickets", "dismissals_milestone": "dismissals"}


async def _insert_stat_milestones(db, org: str, snap: dict) -> int:
    """A card for each step of a player's career runs, wickets and dismissals (see `STAT_MILESTONES`).

    Reached is the profile's own career figure, so a career held only as season totals still earns its cards.
    The date is the game the figure crossed the step in, worked out from the scorecards we hold and offset by
    whatever part of the career they do not cover (the older, season-total part is assumed to come first). A
    step the held scorecards cannot place is left without a date rather than given a wrong one."""
    total = 0
    figs = snap["figs"]
    for kind, key, step, cap in STAT_MILESTONES:
        reached = [(pid, int(f[key])) for pid, f in figs.items() if f.get(key, 0) >= step]
        if not reached:
            continue
        table, add, where, order = _MILESTONE_SOURCES[kind]
        res = await db.execute(text(f"""
            WITH career AS (
                SELECT c.pid, c.total FROM unnest(CAST(:pids AS uuid[]), CAST(:totals AS int[])) AS c(pid, total)
            ), inn AS (
                SELECT x.player_id AS pid, g.id AS game_id, g.played_at,
                       SUM({add}) OVER w AS cum
                  FROM {table} x JOIN v_effective_games g ON g.id = x.game_id
                 WHERE x.player_id = ANY(CAST(:pids AS uuid[])) AND g.played_at IS NOT NULL AND {where}
                WINDOW w AS (PARTITION BY x.player_id ORDER BY g.played_at, g.id, {order})
            ), base AS (
                SELECT c.pid, c.total, GREATEST(c.total - COALESCE((SELECT MAX(i.cum) FROM inn i WHERE i.pid = c.pid), 0), 0) AS base
                  FROM career c
            )
            {_INSERT_PREFIX}
            SELECT CAST(:org AS UUID), b.pid, :kind, :kind || ':' || b.pid::text || ':' || t.t::text,
                   ev.game_id, ev.played_at, to_char(t.t, 'FM999,999,999') || ' ' || :noun,
                   jsonb_build_object('threshold', t.t, 'total', b.total)
              FROM base b
              CROSS JOIN LATERAL generate_series(CAST(:step AS int), LEAST(b.total, CAST(:step AS int) * CAST(:cap AS int)), CAST(:step AS int)) AS t(t)
              LEFT JOIN LATERAL (
                  SELECT i.game_id, i.played_at FROM inn i
                   WHERE i.pid = b.pid AND t.t > b.base AND b.base + i.cum >= t.t
                   ORDER BY i.cum LIMIT 1
              ) ev ON TRUE
            {_INSERT_SUFFIX}
        """), {"org": org, "kind": kind, "noun": _NOUN[kind], "step": step, "cap": cap,
               "pids": [p for p, _ in reached], "totals": [v for _, v in reached]})
        total += res.rowcount or 0
    return total


_GIFT_INSERT = """
    INSERT INTO player_card_copies (organisation_id, owner_player_id, subject_player_id, special_id, source)
    SELECT sc.organisation_id, sc.player_id, sc.player_id, sc.id, 'gift'
      FROM player_special_cards sc
     WHERE sc.organisation_id = CAST(:org AS UUID)
       AND {keep}
       AND NOT EXISTS (SELECT 1 FROM player_card_copies c
                        WHERE c.owner_player_id = sc.player_id AND c.special_id = sc.id AND c.source = 'gift')
    ON CONFLICT (owner_player_id, special_id) WHERE source = 'gift' DO NOTHING
"""

# The one landmark card per player that a minimal club gifts: the latest by date, then the biggest.
_LATEST_LANDMARK = """sc.kind = ANY(CAST(:landmarks AS text[])) AND sc.id = (
        SELECT l.id FROM player_special_cards l
         WHERE l.organisation_id = sc.organisation_id AND l.player_id = sc.player_id AND l.kind = ANY(CAST(:landmarks AS text[]))
         ORDER BY l.occurred_on DESC NULLS LAST, l.created_at DESC NULLS LAST, l.id DESC LIMIT 1)"""
_DEBUT_OR_LANDMARK = f"(sc.kind = 'debut' OR ({_LATEST_LANDMARK}))"


async def _gift_new_specials(db, org: str, mode: str = "minimal") -> int:
    """A player is given a copy of the special cards that commemorate them. A minimal club (the default) gives
    their debut card and their latest landmark card; `all` gives every one. Only adds: a landmark that is later
    superseded by a newer one keeps the copy the player already holds."""
    keep = "TRUE" if mode == "all" else _DEBUT_OR_LANDMARK
    res = await db.execute(text(_GIFT_INSERT.format(keep=keep)), {"org": org, "landmarks": list(LANDMARK_KINDS)})
    return res.rowcount or 0


async def trim_gifts(db, org: str, *, apply: bool = False) -> dict:
    """Take a club's starting gifts back to the minimal set: remove the gifted copies that are not the player's
    debut or latest landmark. Only a copy still marked `gift` and held by the player it commemorates is touched (a swap re-marks the
    copy `swap`, so a card that has moved is never taken back), and a pack pull is never a gift. Dry run unless
    `apply`; returns what it would remove or removed."""
    where = f"""
        FROM player_card_copies c JOIN player_special_cards sc ON sc.id = c.special_id
         WHERE c.organisation_id = CAST(:org AS UUID) AND c.source = 'gift' AND c.owner_player_id = sc.player_id
           AND NOT {_DEBUT_OR_LANDMARK}"""
    params = {"org": org, "landmarks": list(LANDMARK_KINDS)}
    counted = (await db.execute(text(f"SELECT COUNT(*) AS n, COUNT(DISTINCT c.owner_player_id) AS players {where}"), params)).mappings().first()
    out = {"cards": int(counted["n"] or 0), "players": int(counted["players"] or 0), "applied": False}
    if apply and out["cards"]:
        await db.execute(text(f"DELETE FROM player_card_copies WHERE id IN (SELECT c.id {where})"), params)
        out["applied"] = True
        forget(org)
    return out


async def refresh_specials(db: AsyncSession, club: Organisation, *, force: bool = False) -> dict:
    """Make sure every event in the club's history has its special card, and that each player holds the
    cards that commemorate them. Idempotent and add-only: a card is never removed because a figure
    was later corrected. Throttled per club unless `force`."""
    key = str(club.id)
    now = time.monotonic()
    if not force and now - _SPECIAL_REFRESH.get(key, -1e9) < SPECIAL_REFRESH_TTL:
        return {"skipped": True}
    snap = await club_snapshot(db, club)
    # Every player the club holds a card for, whether or not they are in the pool today: switching
    # juniors on later must find the cards already made.
    pids = [str(p.id) for p in await _club_players(db, club.id) if p.is_public is not False]
    made: dict[str, int] = {}
    if pids:
        org = str(club.id)
        made["century"] = await _insert_batting(db, org, pids, "century", 100, None, "Century")
        made["fifty"] = await _insert_batting(db, org, pids, "fifty", 50, 99, "Half century")
        made["five_for"] = await _insert_five_fors(db, org, pids)
        made["achievements"] = await _insert_achievements(db, org, pids)
        made["games"] = await _insert_game_milestones(db, org, snap)
        made["stat_milestones"] = await _insert_stat_milestones(db, org, snap)
        made["gifted"] = await _gift_new_specials(db, org, snap["settings"].get("starter_gifts") or "minimal")
    _SPECIAL_REFRESH[key] = now
    return made


# ── The dashboard's one-line view ─────────────────────────────────────────────

async def dashboard_summary(db: AsyncSession, club: Organisation, player: Player) -> Optional[dict]:
    """What the page's header needs: how many packs are ready. Grants anything newly earned first.
    None when the club has cards off or the player is not in the card pool (hidden, or a junior
    while juniors are off), so the module simply does not show. The caller commits."""
    snap = await club_snapshot(db, club)
    if not snap["settings"]["enabled"]:
        return None
    if snap["settings"].get("launched_at") is None:
        await ensure_launched(db, club.id)
        forget(club.id)
        snap = await club_snapshot(db, club, fresh=True)
    pid = str(player.id)
    if pid not in snap["people"]:
        return None
    await ensure_grants(db, club, pid, snap)
    packs = await available_packs(db, pid, snap)
    from app.services import player_card_swaps  # imported here: that module imports this one
    return {
        "ready": len(packs),
        "swaps_waiting": await player_card_swaps.waiting_count(db, pid),
        "resets_at": week_ends_at(snap["settings"]).isoformat(),
    }


# ── Pack grants ───────────────────────────────────────────────────────────────

async def _insert_packs(db, org: str, pid: str, source: str, refs: list[str]) -> int:
    if not refs:
        return 0
    res = await db.execute(text("""
        INSERT INTO player_card_packs (organisation_id, player_id, source, ref_key)
        SELECT CAST(:org AS UUID), CAST(:pid AS UUID), :source, r FROM unnest(CAST(:refs AS text[])) AS r
        ON CONFLICT (player_id, source, ref_key) DO NOTHING
    """), {"org": org, "pid": pid, "source": source, "refs": refs})
    return res.rowcount or 0


async def _season_figures(db, pid: str, season_ids: list[str]) -> dict:
    row = (await db.execute(text("""
        SELECT COALESCE(SUM(pss.runs), 0) AS runs, COALESCE(SUM(pss.wickets), 0) AS wickets,
               COALESCE(SUM(pss.catches + pss.run_outs + pss.stumpings), 0) AS dismissals
          FROM v_effective_player_season_stats pss
         WHERE pss.player_id = CAST(:pid AS UUID) AND pss.season_id = ANY(CAST(:sids AS uuid[]))
    """), {"pid": pid, "sids": season_ids})).mappings().first()
    return {k: _int(row[k]) for k in ("runs", "wickets", "dismissals")} if row else {"runs": 0, "wickets": 0, "dismissals": 0}


async def _duck_refs(db, pid: str, since: Optional[date]) -> list[str]:
    if since is None:
        return []
    rows = await db.execute(text("""
        SELECT bi.game_id::text || ':' || COALESCE(bi.innings_number, 1)::text
          FROM v_effective_batting_innings bi JOIN v_effective_games g ON g.id = bi.game_id
         WHERE bi.player_id = CAST(:pid AS UUID) AND bi.runs = 0
           AND COALESCE(bi.not_out, FALSE) = FALSE AND COALESCE(bi.did_not_bat, FALSE) = FALSE
           AND g.played_at >= :since
    """), {"pid": pid, "since": since})
    return [r[0] for r in rows.fetchall()]


def club_today(settings: dict, now: Optional[datetime] = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(club_zone(settings)).date()


async def _playing_today(db, org: str, pid: str, today: date) -> bool:
    """On a team sheet for a fixture played TODAY, or in a scorecard dated today. A fixture is played on its own days only: a two day
    game is its first day and its last (`played_on` and `end_on`, a week apart for a weekend game played over two Saturdays), never the
    days between."""
    hit = (await db.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM fixture_lineups fl JOIN fixtures f ON f.id = fl.fixture_id
             WHERE fl.player_id = CAST(:pid AS UUID) AND f.organisation_id = CAST(:org AS UUID)
               AND f.status NOT IN ('CANCELLED', 'BYE')
               AND (f.played_on = :today OR f.end_on = :today)
        ) OR EXISTS (
            SELECT 1 FROM game_appearances ga JOIN v_effective_games g ON g.id = ga.game_id
             WHERE ga.player_id = CAST(:pid AS UUID) AND g.played_at = :today AND COALESCE(ga.is_reserve, FALSE) = FALSE
        )
    """), {"org": org, "pid": pid, "today": today})).scalar()
    return bool(hit)


_STRAY_MATCH_DAY = """
    FROM player_card_packs pk
   WHERE pk.organisation_id = CAST(:org AS UUID) AND pk.source = 'match_day' AND pk.opened_at IS NULL
     AND pk.ref_key ~ '^match_day:[0-9]{4}-[0-9]{2}-[0-9]{2}$'
     AND NOT EXISTS (
        SELECT 1 FROM fixture_lineups fl JOIN fixtures f ON f.id = fl.fixture_id
         WHERE fl.player_id = pk.player_id AND f.organisation_id = pk.organisation_id AND f.status NOT IN ('CANCELLED', 'BYE')
           AND (f.played_on = split_part(pk.ref_key, ':', 2)::date OR f.end_on = split_part(pk.ref_key, ':', 2)::date))
     AND NOT EXISTS (
        SELECT 1 FROM game_appearances ga JOIN v_effective_games g ON g.id = ga.game_id
         WHERE ga.player_id = pk.player_id AND g.played_at = split_part(pk.ref_key, ':', 2)::date AND COALESCE(ga.is_reserve, FALSE) = FALSE)
"""


async def unwind_stray_match_day_packs(db, org: str, *, apply: bool = False) -> dict:
    """Match Day packs were once granted on every day between a two day game's first and last day. Take back the UNOPENED ones whose
    player was not playing on the day the pack is for (by the rule in `_playing_today`). A pack that has been opened stays: the cards
    are in the player's book. Dry run unless `apply`."""
    counted = (await db.execute(text(f"SELECT COUNT(*) AS n, COUNT(DISTINCT pk.player_id) AS players {_STRAY_MATCH_DAY}"), {"org": org})).mappings().first()
    out = {"packs": int(counted["n"] or 0), "players": int(counted["players"] or 0), "applied": False}
    if apply and out["packs"]:
        await db.execute(text(f"DELETE FROM player_card_packs WHERE id IN (SELECT pk.id {_STRAY_MATCH_DAY})"), {"org": org})
        out["applied"] = True
    return out


async def _insert_labelled(db, org: str, pid: str, source: str, ref: str, label: Optional[str], quality: Optional[str] = None) -> int:
    res = await db.execute(text("""
        INSERT INTO player_card_packs (organisation_id, player_id, source, ref_key, label, quality)
        VALUES (CAST(:org AS UUID), CAST(:pid AS UUID), :source, :ref, :label, :quality)
        ON CONFLICT (player_id, source, ref_key) DO NOTHING
    """), {"org": org, "pid": pid, "source": source, "ref": ref, "label": label, "quality": quality})
    return res.rowcount or 0


async def _scheduled_events(db, org: str, today: date) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT id::text AS id, title, starts_on, ends_on, per_day, quality FROM club_card_event_packs
         WHERE organisation_id = CAST(:org AS UUID) AND starts_on <= :today AND :today <= ends_on
    """), {"org": org, "today": today})).mappings().all()
    return [dict(r) for r in rows]


MAX_EVENT_DAYS = 31
MAX_EVENTS = 60


async def list_events(db, org_id) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT id::text AS id, title, starts_on, ends_on, per_day, quality FROM club_card_event_packs
         WHERE organisation_id = CAST(:org AS UUID) AND ends_on >= (CURRENT_DATE - 30) ORDER BY starts_on, created_at
    """), {"org": str(org_id)})).mappings().all()
    return [{"id": r["id"], "title": r["title"], "starts_on": r["starts_on"].isoformat(), "ends_on": r["ends_on"].isoformat(),
             "per_day": bool(r["per_day"]), "quality": r["quality"] or kinds.DEFAULT_QUALITY} for r in rows]


async def add_event(db, org_id, title: str, starts_on: date, ends_on: Optional[date], per_day: bool = True,
                    quality: str = kinds.DEFAULT_QUALITY) -> dict:
    """Schedule a pack for a day or a run of days (a Test match). Rejects a run that ends before it starts or is longer
    than a month, so one slip of a year does not hand out a pack a day for twelve months."""
    title = (title or "").strip()[:80]
    if not title:
        raise ValueError("Give the pack a name.")
    if quality not in kinds.QUALITIES:
        raise ValueError("Pick one of the pack qualities.")
    ends_on = ends_on or starts_on
    if ends_on < starts_on:
        raise ValueError("The last day cannot be before the first.")
    if (ends_on - starts_on).days + 1 > MAX_EVENT_DAYS:
        raise ValueError(f"A scheduled pack can run at most {MAX_EVENT_DAYS} days.")
    n = (await db.execute(text("SELECT COUNT(*) FROM club_card_event_packs WHERE organisation_id = CAST(:org AS UUID)"),
                          {"org": str(org_id)})).scalar()
    if int(n or 0) >= MAX_EVENTS:
        raise ValueError("That is plenty of scheduled packs. Delete an old one first.")
    row = (await db.execute(text("""
        INSERT INTO club_card_event_packs (organisation_id, title, starts_on, ends_on, per_day, quality)
        VALUES (CAST(:org AS UUID), :title, :s, :e, :pd, :q) RETURNING id::text
    """), {"org": str(org_id), "title": title, "s": starts_on, "e": ends_on, "pd": bool(per_day), "q": quality})).first()
    return {"id": row[0], "title": title, "starts_on": starts_on.isoformat(), "ends_on": ends_on.isoformat(), "per_day": bool(per_day), "quality": quality}


async def delete_event(db, org_id, event_id: str) -> bool:
    """Remove a scheduled pack. Packs already granted from it stay with the players: they were earned."""
    res = await db.execute(text(
        "DELETE FROM club_card_event_packs WHERE id = CAST(:id AS UUID) AND organisation_id = CAST(:org AS UUID)"
    ), {"id": event_id, "org": str(org_id)})
    return bool(res.rowcount)


async def _grant_day_packs(db, club: Organisation, pid: str, settings: dict) -> dict[str, int]:
    """Packs for today: holidays, a birthday, a surprise drop, Match Day and any day the club scheduled. A day pack can
    only be earned on its day (the page has to be opened), then it banks until opened."""
    org, today = str(club.id), club_today(settings)
    added: dict[str, int] = {}
    if settings.get("event_packs_enabled") is not False:
        for source, ref in kinds.annual_events(today):
            added[source] = await _insert_packs(db, org, pid, source, [ref])
        if kinds.is_mystery_day(org, today):
            added["mystery"] = await _insert_packs(db, org, pid, "mystery", [f"mystery:{today.isoformat()}"])
        dob = (await db.execute(text("SELECT date_of_birth FROM players WHERE id = CAST(:pid AS UUID)"), {"pid": pid})).scalar()
        if kinds.is_birthday(dob, today):
            added["birthday"] = await _insert_packs(db, org, pid, "birthday", [f"birthday:{today.year}"])
        if await _playing_today(db, org, pid, today):
            added["match_day"] = await _insert_packs(db, org, pid, "match_day", [f"match_day:{today.isoformat()}"])
    for ev in await _scheduled_events(db, org, today):
        ref = f"{ev['id']}:{today.isoformat()}" if ev["per_day"] else ev["id"]
        added["event"] = added.get("event", 0) + await _insert_labelled(db, org, pid, "event", ref, ev["title"], ev["quality"])
    return added


async def _grant_achievement_packs(db, org: str, pid: str, launched: Optional[datetime]) -> dict[str, int]:
    """One pack for each century, five-for, hat-trick, fifty and landmark the player has had since the club began using
    cards. Never from before: a club's whole history does not turn into a flood of high packs on launch."""
    if launched is None:
        return {}
    rows = (await db.execute(text("""
        SELECT id::text, kind FROM player_special_cards
         WHERE organisation_id = CAST(:org AS UUID) AND player_id = CAST(:pid AS UUID)
           AND kind = ANY(CAST(:kinds AS text[])) AND occurred_on >= :since
    """), {"org": org, "pid": pid, "kinds": list(kinds.ACHIEVEMENT_PACKS), "since": launched.date()})).fetchall()
    by_source: dict[str, list[str]] = {}
    for sid, kind in rows:
        by_source.setdefault(kinds.ACHIEVEMENT_PACKS[kind], []).append(sid)
    return {src: await _insert_packs(db, org, pid, src, refs) for src, refs in by_source.items()}


async def ensure_grants(db: AsyncSession, club: Organisation, pid: str, snap: dict) -> dict:
    """Add every pack this player has earned and not yet been granted. Safe to call on every visit."""
    settings, org = snap["settings"], str(club.id)
    added: dict[str, int] = {}
    added["starter"] = await _insert_packs(db, org, pid, "starter", [str(i) for i in range(1, STARTER_PACKS + 1)])
    wk = week_key(settings)
    added["weekly"] = await _insert_packs(db, org, pid, "weekly", [f"{wk}:{i}" for i in range(1, settings["weekly_packs"] + 1)])
    if snap["current_season_ids"]:
        fig = await _season_figures(db, pid, snap["current_season_ids"])
        season = snap["current_season_ids"][0]
        for source, total, per in (("runs", fig["runs"], RUNS_PER_PACK), ("wickets", fig["wickets"], WICKETS_PER_PACK),
                                   ("dismissals", fig["dismissals"], DISMISSALS_PER_PACK)):
            # One ref per rung, keyed by the club's season so a new season starts counting again.
            added[source] = await _insert_packs(db, org, pid, source, [f"{season}:{i}" for i in range(1, total // per + 1)])
    launched = settings.get("launched_at")
    added["duck"] = await _insert_packs(db, org, pid, "duck", await _duck_refs(db, pid, launched.date() if launched else None))
    added.update(await _grant_achievement_packs(db, org, pid, launched))
    added.update(await _grant_day_packs(db, club, pid, settings))
    return added


# Where each kind of pack sits in the list: what is special or time-limited first, bulk packs last.
_PACK_ORDER = {"starter": 0, **{k: 1 for k in ("century", "five_for", "hat_trick", "fifty", "milestone")},
               **{k: 2 for k in kinds.DAY_SOURCES}, "custom": 2, "reward": 2, "weekly": 3, "duck": 5}


async def available_packs(db: AsyncSession, pid: str, snap: dict) -> list[dict]:
    """Unopened packs the player can open now. A weekly pack is only good in the week it was granted."""
    wk = week_key(snap["settings"])
    rows = await db.execute(text("""
        SELECT id::text, source, ref_key, granted_at, label, quality, size FROM player_card_packs
         WHERE player_id = CAST(:pid AS UUID) AND opened_at IS NULL
           AND (source <> 'weekly' OR ref_key LIKE :wk)
    """), {"pid": pid, "wk": f"{wk}:%"})
    packs = sorted(rows.fetchall(), key=lambda r: (_PACK_ORDER.get(r[1], 4), r[3], r[2]))
    designs = await pack_designs.load_all(db, snap["org_id"]) if snap.get("org_id") else {}
    out = []
    for r in packs:
        ev = pack_designs.event_id_of(r[1], r[2])
        design = pack_designs.resolve(designs, r[1], ev, pack_designs.gift_id_of(r[1], r[2]))
        # A pack with a name of its own (a scheduled event) keeps it; otherwise the club's name for that kind of pack, then ours.
        own = (design or {}).get("title") if design and design["target"] != pack_designs.DEFAULT_TARGET else None
        out.append({"id": r[0], "source": r[1], "label": r[4] or own or kinds.label_for(r[1]), "quality": r[5], "size": r[6] or PACK_SIZE, "design": design})
    return out


# ── Packs an admin creates by hand ───────────────────────────────────────────

MAX_GIFT_QTY = 10
MAX_GIFT_TITLE = 40
RECENT_GIFTS = 12


def quality_options() -> list[dict]:
    """The quality ladder as the admin screen shows it: what each step guarantees and how the tiers are weighted."""
    out = []
    for key, k in kinds.QUALITIES.items():
        total = sum(k.weights.values())
        out.append({"key": key, "label": k.label, "line": k.line, "rare_plus": k.rare_plus, "special_pct": round(k.special * 100),
                    "odds": {t: round(100 * k.weights[t] / total) for t in TIERS}})
    return out


async def create_gift(db, club: Organisation, snap: dict, *, title: str, quality: str, qty: int = 1, audience: str = "all",
                      player_ids: Optional[list[str]] = None, request_id: Optional[str] = None, by: Optional[str] = None,
                      size: int = PACK_SIZE) -> dict:
    """Hand out packs now: `qty` packs of `quality`, named `title`, to everyone with a card or to the players chosen. They arrive as
    ordinary unopened packs (opened from the player's page, banked until opened, never expiring). `request_id` is the screen's own
    id for this click: sending the same one twice grants once. Raises ValueError with a message the admin can read."""
    title = " ".join((title or "").split())[:MAX_GIFT_TITLE]
    if not title:
        raise ValueError("Give the pack a name.")
    if quality not in kinds.QUALITIES:
        raise ValueError("Pick one of the pack qualities.")
    if not isinstance(qty, int) or isinstance(qty, bool) or not 1 <= qty <= MAX_GIFT_QTY:
        raise ValueError(f"Each player can be given from 1 to {MAX_GIFT_QTY} packs.")
    if not isinstance(size, int) or isinstance(size, bool) or not MIN_PACK_SIZE <= size <= MAX_PACK_SIZE:
        raise ValueError(f"A pack holds from {MIN_PACK_SIZE} to {MAX_PACK_SIZE} cards.")
    if audience == "all":
        pids = sorted(snap["people"])
    elif audience == "players":
        pids = sorted({str(p) for p in (player_ids or []) if str(p) in snap["people"]})
        if not pids:
            raise ValueError("Pick at least one player who is in the card pool.")
    else:
        raise ValueError("Pick everyone, or choose the players.")
    if not pids:
        raise ValueError("Nobody is in the card pool yet.")
    try:
        gift_id = str(uuid.UUID(str(request_id))) if request_id else str(uuid.uuid4())
    except ValueError:
        gift_id = str(uuid.uuid4())
    org = str(club.id)
    made = (await db.execute(text("""
        INSERT INTO club_card_pack_gifts (id, organisation_id, title, quality, qty, audience, players, created_by, size)
        VALUES (CAST(:id AS UUID), CAST(:org AS UUID), :title, :quality, :qty, :audience, :players, :by, :size)
        ON CONFLICT (id) DO NOTHING RETURNING id::text
    """), {"id": gift_id, "org": org, "title": title, "quality": quality, "qty": qty, "audience": audience, "players": len(pids), "by": by, "size": size})).first()
    if not made:
        existing = (await db.execute(text(
            "SELECT title, quality, qty, players, size FROM club_card_pack_gifts WHERE id = CAST(:id AS UUID) AND organisation_id = CAST(:org AS UUID)"),
            {"id": gift_id, "org": org})).mappings().first()
        if not existing:
            raise ValueError("That request belongs to another club.")
        return {"id": gift_id, "title": existing["title"], "quality": existing["quality"], "qty": existing["qty"],
                "players": existing["players"], "packs": existing["players"] * existing["qty"], "size": existing["size"], "repeat": True}
    await db.execute(text("""
        INSERT INTO player_card_packs (organisation_id, player_id, source, ref_key, label, quality, size)
        SELECT CAST(:org AS UUID), CAST(p AS UUID), 'custom', :gid || ':' || n::text, :title, :quality, CAST(:size AS INT)
          FROM unnest(CAST(:pids AS text[])) AS p, generate_series(1, CAST(:qty AS INT)) AS n
        ON CONFLICT (player_id, source, ref_key) DO NOTHING
    """), {"org": org, "gid": gift_id, "title": title, "quality": quality, "pids": pids, "qty": qty, "size": size})
    return {"id": gift_id, "title": title, "quality": quality, "qty": qty, "players": len(pids), "packs": len(pids) * qty, "size": size, "repeat": False}


async def list_gifts(db, org_id) -> list[dict]:
    """The packs the club has handed out lately, with how many have been opened."""
    rows = (await db.execute(text("""
        SELECT g.id::text AS id, g.title, g.quality, g.qty, g.audience, g.players, g.created_at, g.size,
               (SELECT COUNT(*) FROM player_card_packs p WHERE p.organisation_id = g.organisation_id AND p.source = 'custom'
                   AND p.ref_key LIKE g.id::text || ':%' AND p.opened_at IS NOT NULL) AS opened
          FROM club_card_pack_gifts g WHERE g.organisation_id = CAST(:org AS UUID)
         ORDER BY g.created_at DESC LIMIT :n
    """), {"org": str(org_id), "n": RECENT_GIFTS})).mappings().all()
    return [{"id": r["id"], "title": r["title"], "quality": r["quality"], "qty": r["qty"], "audience": r["audience"], "players": r["players"],
             "packs": r["players"] * r["qty"], "size": r["size"] or PACK_SIZE, "opened": int(r["opened"] or 0), "created_at": r["created_at"].isoformat()} for r in rows]


# ── Drawing a pack ────────────────────────────────────────────────────────────

def _draw_tier(pool: dict[str, list[str]], allowed: Iterable[str], weights: Optional[dict] = None) -> Optional[str]:
    """A tier by weight among those that have anyone in them; an empty tier falls to the next lower."""
    weights = weights or PACK_WEIGHTS
    live = [t for t in allowed if pool.get(t)]
    if not live:
        return None
    total = sum(weights[t] for t in live)
    pick = _rng.uniform(0, total)
    acc = 0.0
    for t in live:
        acc += weights[t]
        if pick <= acc:
            return t
    return live[-1]


def draw_cards(pool: dict[str, list[str]], specials: list[str], size: int = PACK_SIZE,
               kind: Optional[kinds.Kind] = None) -> list[dict]:
    """The picks for one pack: `[{"kind": "player", "id": pid}, {"kind": "special", "id": special_id}]`.
    `kind` sets the odds, the special chance and how many cards are guaranteed Rare or better (the standard
    pack when omitted). Pure and RNG-driven, so the odds can be checked without a database."""
    kind = kind or kinds.DEFAULT_KIND
    weights, special_chance = kind.weights, kind.special
    picks: list[dict] = []
    seen: set[tuple] = set()

    def one(rare_plus: bool) -> Optional[dict]:
        for _ in range(12):
            if specials and _rng.random() < special_chance:
                ident = _rng.choice(specials)
                if (("special", ident)) not in seen:
                    seen.add(("special", ident))
                    return {"kind": "special", "id": ident, "tier": "special"}
            tier = _draw_tier(pool, ("rare", "epic", "legendary") if rare_plus else TIERS, weights)
            if tier is None and rare_plus:
                tier = _draw_tier(pool, TIERS, weights)
            if tier is None:
                return None
            ident = _rng.choice(pool[tier])
            if ("player", ident) not in seen:
                seen.add(("player", ident))
                return {"kind": "player", "id": ident, "tier": tier}
        # Twelve random tries all landed on cards already in the pack (a small club, a big pack): take any card still unseen, the
        # best tiers first when a Rare or better is wanted, so a pack is never short of cards the club actually has.
        order = ("legendary", "epic", "rare") if rare_plus else TIERS
        left = [(t, i) for t in order for i in pool.get(t, []) if ("player", i) not in seen]
        if left:
            t, ident = _rng.choice(left)
            seen.add(("player", ident))
            return {"kind": "player", "id": ident, "tier": t}
        if not rare_plus:
            unseen = [sp for sp in specials if ("special", sp) not in seen]
            if unseen:
                ident = _rng.choice(unseen)
                seen.add(("special", ident))
                return {"kind": "special", "id": ident, "tier": "special"}
        return None

    for _ in range(size):
        pick = one(False)
        if pick:
            picks.append(pick)
    # The guarantee: at least `rare_plus` cards are Rare or better (a special card counts). Weakest slots are redrawn.
    # (The guarantee is written for five cards; a bigger or smaller pack scales it, never below one.)
    scaled = max(1, -(-kind.rare_plus * size // PACK_SIZE)) if kind.rare_plus else 0
    want = min(scaled, len(picks))
    for _ in range(want):
        good = sum(1 for p in picks if p["tier"] != "common")
        if good >= want:
            break
        slot = next((i for i in range(len(picks) - 1, -1, -1) if picks[i]["tier"] == "common"), None)
        if slot is None:
            break
        replacement = one(True)
        if not replacement:
            break
        picks[slot] = replacement
    return picks


async def open_pack(db: AsyncSession, club: Organisation, player: Player, pack_id: str, snap: dict) -> Optional[list[dict]]:
    """Open one pack: lock it, draw, record the copies. Returns the cards, or None when the pack is not
    this player's, is already open, or was a weekly pack that has expired. The caller commits."""
    row = (await db.execute(text("""
        SELECT id::text, source, ref_key, quality, size FROM player_card_packs
         WHERE id = CAST(:id AS UUID) AND player_id = CAST(:pid AS UUID) AND opened_at IS NULL
         FOR UPDATE
    """), {"id": pack_id, "pid": str(player.id)})).first()
    if not row:
        return None
    if row[1] == "weekly" and not str(row[2]).startswith(week_key(snap["settings"]) + ":"):
        return None
    specials = [sid for sid, owner in await _all_special_ids(db, club.id) if owner in snap["people"]]
    picks = draw_cards(snap["pool"], specials, size=max(MIN_PACK_SIZE, min(int(row[4] or PACK_SIZE), MAX_PACK_SIZE)), kind=kinds.quality_kind(row[3], row[1]))
    await db.execute(text("UPDATE player_card_packs SET opened_at = NOW() WHERE id = CAST(:id AS UUID)"), {"id": pack_id})
    special_rows = await _specials_by_id(db, club.id, [p["id"] for p in picks if p["kind"] == "special"])
    cards: list[dict] = []
    for pick in picks:
        if pick["kind"] == "special":
            srow = special_rows.get(pick["id"])
            card = special_card(snap, srow) if srow else None
            subject, special_id = (str(srow["player_id"]), pick["id"]) if srow else (None, None)
        else:
            card = regular_card(snap, pick["id"])
            subject, special_id = pick["id"], None
        if card is None:
            continue
        await db.execute(text("""
            INSERT INTO player_card_copies (organisation_id, owner_player_id, subject_player_id, special_id, pack_id, source)
            VALUES (CAST(:org AS UUID), CAST(:owner AS UUID), CAST(:subject AS UUID), CAST(:sid AS UUID), CAST(:pack AS UUID), 'pack')
        """), {"org": str(club.id), "owner": str(player.id), "subject": subject, "sid": special_id, "pack": pack_id})
        cards.append(card)
    return cards


# ── The collection ────────────────────────────────────────────────────────────

async def collection(db: AsyncSession, club: Organisation, player: Player, snap: dict) -> dict:
    """The player's cards, one entry per distinct card with a copy count, plus how much of the club's
    set they hold. Their own card is always there."""
    pid = str(player.id)
    rows = (await db.execute(text("""
        SELECT subject_player_id::text AS subject, special_id::text AS special_id,
               COUNT(*) AS copies, MAX(obtained_at) AS latest, MIN(obtained_at) AS first
          FROM player_card_copies WHERE owner_player_id = CAST(:pid AS UUID)
         GROUP BY subject_player_id, special_id
    """), {"pid": pid})).mappings().all()

    owned: dict[str, dict] = {}
    for r in rows:
        k = f"s:{r['special_id']}" if r["special_id"] else f"p:{r['subject']}"
        owned[k] = {"copies": int(r["copies"]), "latest": r["latest"], "first": r["first"],
                    "special_id": r["special_id"], "subject": r["subject"]}
    own_key = f"p:{pid}"
    if own_key in owned:
        owned[own_key]["copies"] += 1
    else:
        owned[own_key] = {"copies": 1, "latest": None, "first": None, "special_id": None, "subject": pid}

    special_rows = await _specials_by_id(db, club.id, [v["special_id"] for v in owned.values() if v["special_id"]])
    cards: list[dict] = []
    for k, v in owned.items():
        if v["special_id"]:
            srow = special_rows.get(v["special_id"])
            card = special_card(snap, srow) if srow else None
        else:
            card = regular_card(snap, v["subject"])
            if card is None and v["subject"] == pid:
                # Their own card still works if they are out of the pool (hidden, junior) for others.
                card = _own_card_outside_pool(player, snap)
        if card is None:
            continue
        card["copies"] = v["copies"]
        card["obtained_at"] = (v["latest"] or v["first"]).isoformat() if (v["latest"] or v["first"]) else None
        card["mine"] = (v["subject"] == pid and not v["special_id"])
        cards.append(card)

    pool_total = sum(1 for f in snap["figs"].values() if f["matches"] > 0)
    specials_total = len([1 for _sid, owner in await _all_special_ids(db, club.id) if owner in snap["people"]])
    owned_regular = len([c for c in cards if c["kind"] == "player" and snap["figs"].get(c["player_id"], {}).get("matches", 0) > 0])
    owned_special = len([c for c in cards if c["kind"] == "special"])
    return {
        "cards": cards,
        "totals": {
            "regular_owned": owned_regular, "regular_total": pool_total,
            "special_owned": owned_special, "special_total": specials_total,
            "copies": sum(c["copies"] for c in cards),
        },
    }


def _own_card_outside_pool(player: Player, snap: dict) -> dict:
    return {
        "kind": "player", "key": f"p:{player.id}", "player_id": str(player.id), "name": player.display_name,
        "photo_url": player.photo_url, "hero_photo_url": getattr(player, "hero_photo_url", None),
        "action_photo_url": getattr(player, "action_photo_url", None), "hero_source": getattr(player, "hero_source", None),
        "matches": 0, "runs": 0, "bat_avg": None, "wickets": 0, "bowl_avg": None, "dismissals": 0,
        "rarity": 1, "tier": "common",
        "shot": card_shot({"photo_url": player.photo_url, "hero_photo_url": getattr(player, "hero_photo_url", None),
                           "action_photo_url": getattr(player, "action_photo_url", None), "hero_source": getattr(player, "hero_source", None)},
                          "common", None, snap["settings"].get("big_photos") or "all"),
    }


def summarise(cards: list[dict]) -> dict:
    """What a bulk open reports instead of listing hundreds of cards."""
    by_tier = {t: 0 for t in (*TIERS, "special")}
    for c in cards:
        by_tier[c["tier"]] = by_tier.get(c["tier"], 0) + 1
    order = {"special": 0, "legendary": 1, "epic": 2, "rare": 3, "common": 4}
    best = sorted(cards, key=lambda c: (order.get(c["tier"], 5), -(c.get("rarity") or 0)))[:12]
    seen, top = set(), []
    for c in best:
        if c["key"] in seen:
            continue
        seen.add(c["key"])
        top.append(c)
    return {"total": len(cards), "by_tier": by_tier, "best": top}


async def open_many(db: AsyncSession, club: Organisation, player: Player, snap: dict, limit: int = OPEN_ALL_LIMIT) -> dict:
    """Open every pack the player can open now (up to `limit`). Returns a summary and the packs opened."""
    packs = (await available_packs(db, str(player.id), snap))[:limit]
    all_cards: list[dict] = []
    opened = 0
    for pack in packs:
        got = await open_pack(db, club, player, pack["id"], snap)
        if got is None:
            continue
        opened += 1
        all_cards.extend(got)
    return {"opened": opened, **summarise(all_cards)}


def new_id() -> str:  # pragma: no cover - tiny helper kept for tests
    return str(uuid.uuid4())
