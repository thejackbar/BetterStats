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

Odds
----
Each card in a pack is a special card 5% of the time (when the club has any), otherwise a regular
card whose tier is drawn Common 60, Rare 28, Epic 10, Legendary 2. Every pack holds at least one
Rare or better, and the same card does not appear twice in one pack.
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
from app.services.game_status import NOT_PLAYED_SQL_LIST
from app.services.season_kind import season_key_sql

logger = logging.getLogger(__name__)

PACK_SIZE = 5
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
PACK_WEIGHTS = {"common": 60, "rare": 28, "epic": 10, "legendary": 2}
SPECIAL_CHANCE = 0.05
GAMES_MILESTONES = (10, 50, 100, 150, 200, 250, 300, 400, 500)

PACK_SOURCES = {
    "starter": "Starter pack",
    "weekly": "Weekly pack",
    "runs": "Runs pack",
    "wickets": "Wickets pack",
    "dismissals": "Dismissals pack",
    "duck": "Duck pack",
}

SPECIAL_KINDS = {
    "century": "Century",
    "fifty": "Half century",
    "five_for": "Five wicket haul",
    "hat_trick": "Hat-trick",
    "debut": "Debut",
    "games": "Games milestone",
    "award": "Club award",
}

_rng = secrets.SystemRandom()


# ── Settings ──────────────────────────────────────────────────────────────────

def default_settings() -> dict:
    return {
        "enabled": True,
        "include_juniors": False,
        "weekly_packs": DEFAULT_WEEKLY_PACKS,
        "timezone": None,
        "launched_at": None,
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
        "SELECT enabled, include_juniors, weekly_packs, timezone, launched_at "
        "FROM club_card_settings WHERE organisation_id = CAST(:o AS UUID)"
    ), {"o": str(org_id)})).mappings().first()
    if not row:
        return default_settings()
    out = dict(row)
    out["weekly_packs"] = max(0, min(int(out.get("weekly_packs") or 0), MAX_WEEKLY_PACKS))
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
        "settings": settings, "people": people, "figs": figs, "rating": rating, "pool": pool,
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
        "matches": f.get("matches", 0),
        "runs": f.get("runs", 0),
        "bat_avg": f.get("bat_avg"),
        "wickets": f.get("wickets", 0),
        "bowl_avg": f.get("bowl_avg"),
        "dismissals": f.get("dismissals", 0),
        "rarity": r["score"],
        "tier": r["tier"],
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
        "title": row["title"],
        "occurred_on": row["occurred_on"].isoformat() if row["occurred_on"] else None,
        "detail": row["detail"] or {},
        "tier": "special",
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


async def _insert_achievements(db, org: str, pids: list[str]) -> int:
    """Hat-tricks and club awards the club recorded against a player. One card per recorded row."""
    total = 0
    res = await db.execute(text(
        _INSERT_PREFIX + """
        SELECT CAST(:org AS UUID), pa.player_id, 'hat_trick', 'hat_trick:achievement:' || pa.id::text,
               NULL, NULL, 'Hat-trick',
               jsonb_build_object('season', pa.season, 'note', pa.detail)
          FROM player_achievements pa
         WHERE pa.org_id = CAST(:org AS UUID) AND pa.player_id = ANY(CAST(:pids AS uuid[]))
           AND (LOWER(COALESCE(pa.subcategory, '')) = 'hat tricks'
                OR LOWER(pa.achievement) = 'hat trick'
                OR LOWER(pa.achievement) LIKE 'hat-trick%' OR LOWER(pa.achievement) LIKE 'hat trick%')
        """ + _INSERT_SUFFIX), {"org": org, "pids": pids})
    total += res.rowcount or 0
    res = await db.execute(text(
        _INSERT_PREFIX + """
        SELECT CAST(:org AS UUID), pa.player_id, 'award', 'award:achievement:' || pa.id::text,
               NULL, NULL, LEFT(pa.achievement, 120),
               jsonb_build_object('season', pa.season, 'grade', pa.subcategory, 'note', pa.detail)
          FROM player_achievements pa
         WHERE pa.org_id = CAST(:org AS UUID) AND pa.player_id = ANY(CAST(:pids AS uuid[]))
           AND LOWER(pa.category) = 'club award'
        """ + _INSERT_SUFFIX), {"org": org, "pids": pids})
    return total + (res.rowcount or 0)


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


async def _gift_new_specials(db, org: str) -> int:
    """Everyone gets a copy of the special cards that commemorate them. Only adds."""
    res = await db.execute(text("""
        INSERT INTO player_card_copies (organisation_id, owner_player_id, subject_player_id, special_id, source)
        SELECT sc.organisation_id, sc.player_id, sc.player_id, sc.id, 'gift'
          FROM player_special_cards sc
         WHERE sc.organisation_id = CAST(:org AS UUID)
           AND NOT EXISTS (SELECT 1 FROM player_card_copies c
                            WHERE c.owner_player_id = sc.player_id AND c.special_id = sc.id AND c.source = 'gift')
        ON CONFLICT (owner_player_id, special_id) WHERE source = 'gift' DO NOTHING
    """), {"org": org})
    return res.rowcount or 0


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
        made["gifted"] = await _gift_new_specials(db, org)
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
    return {"ready": len(packs), "resets_at": week_ends_at(snap["settings"]).isoformat()}


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
    return added


async def available_packs(db: AsyncSession, pid: str, snap: dict) -> list[dict]:
    """Unopened packs the player can open now. A weekly pack is only good in the week it was granted."""
    wk = week_key(snap["settings"])
    rows = await db.execute(text("""
        SELECT id::text, source, ref_key, granted_at FROM player_card_packs
         WHERE player_id = CAST(:pid AS UUID) AND opened_at IS NULL
           AND (source <> 'weekly' OR ref_key LIKE :wk)
         ORDER BY CASE source WHEN 'starter' THEN 0 WHEN 'duck' THEN 2 WHEN 'weekly' THEN 1 ELSE 3 END, granted_at, ref_key
    """), {"pid": pid, "wk": f"{wk}:%"})
    return [{"id": r[0], "source": r[1], "label": PACK_SOURCES.get(r[1], "Pack")} for r in rows.fetchall()]


# ── Drawing a pack ────────────────────────────────────────────────────────────

def _draw_tier(pool: dict[str, list[str]], allowed: Iterable[str]) -> Optional[str]:
    """A tier by weight among those that have anyone in them; an empty tier falls to the next lower."""
    live = [t for t in allowed if pool.get(t)]
    if not live:
        return None
    total = sum(PACK_WEIGHTS[t] for t in live)
    pick = _rng.uniform(0, total)
    acc = 0.0
    for t in live:
        acc += PACK_WEIGHTS[t]
        if pick <= acc:
            return t
    return live[-1]


def draw_cards(pool: dict[str, list[str]], specials: list[str], size: int = PACK_SIZE) -> list[dict]:
    """The picks for one pack: `[{"kind": "player", "id": pid}, {"kind": "special", "id": special_id}]`.
    Pure and RNG-driven, so the odds can be checked without a database."""
    picks: list[dict] = []
    seen: set[tuple] = set()

    def take(kind: str, ident: str) -> bool:
        if (kind, ident) in seen:
            return False
        seen.add((kind, ident))
        picks.append({"kind": kind, "id": ident, "tier": None})
        return True

    def one(rare_plus: bool) -> Optional[dict]:
        for _ in range(12):
            if specials and _rng.random() < SPECIAL_CHANCE:
                ident = _rng.choice(specials)
                if (("special", ident)) not in seen:
                    seen.add(("special", ident))
                    return {"kind": "special", "id": ident, "tier": "special"}
            tier = _draw_tier(pool, ("rare", "epic", "legendary") if rare_plus else TIERS)
            if tier is None and rare_plus:
                tier = _draw_tier(pool, TIERS)
            if tier is None:
                return None
            ident = _rng.choice(pool[tier])
            if ("player", ident) not in seen:
                seen.add(("player", ident))
                return {"kind": "player", "id": ident, "tier": tier}
        return None

    for _ in range(size):
        pick = one(False)
        if pick:
            picks.append(pick)
    if picks and not any(p["tier"] != "common" for p in picks):
        # The guarantee: at least one Rare or better. The last slot is redrawn.
        replacement = one(True)
        if replacement:
            picks[-1] = replacement
    return picks


async def open_pack(db: AsyncSession, club: Organisation, player: Player, pack_id: str, snap: dict) -> Optional[list[dict]]:
    """Open one pack: lock it, draw, record the copies. Returns the cards, or None when the pack is not
    this player's, is already open, or was a weekly pack that has expired. The caller commits."""
    row = (await db.execute(text("""
        SELECT id::text, source, ref_key FROM player_card_packs
         WHERE id = CAST(:id AS UUID) AND player_id = CAST(:pid AS UUID) AND opened_at IS NULL
         FOR UPDATE
    """), {"id": pack_id, "pid": str(player.id)})).first()
    if not row:
        return None
    if row[1] == "weekly" and not str(row[2]).startswith(week_key(snap["settings"]) + ":"):
        return None
    specials = [sid for sid, owner in await _all_special_ids(db, club.id) if owner in snap["people"]]
    picks = draw_cards(snap["pool"], specials)
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
        "matches": 0, "runs": 0, "bat_avg": None, "wickets": 0, "bowl_avg": None, "dismissals": 0,
        "rarity": 1, "tier": "common",
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
