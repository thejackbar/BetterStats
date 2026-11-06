"""Upcoming milestones for the players on a BetterSocials lineup post.

The lineup layouts print a gold badge beside a player who is about to reach a
club milestone and a "MILESTONE WATCH" strip above the foot. This is the one
place that decides who gets one. It adds no milestone definition of its own:

* **THE FIGURES ARE THE MILESTONES PAGE'S.** Career runs, wickets and matches
  come from ``milestone_totals.profile_totals`` (the figure each player's
  profile opens on) and the thresholds and the "in reach" windows from
  ``milestone_rules`` read through the club's own ``Scheme``. A club that has set
  runs to every 250 or matches to every 25 on the Milestones page gets those
  rungs here with nothing else to set. The window is the tracker's
  (``reach_window``): 50 runs below 1,000 and 100 above, 5 wickets below 100 and
  10 above.
* **GAMES ARE THE ONE CERTAIN ONE.** A lineup names who plays, so the match
  itself is known: a player on 99 club games who is in the XI plays their 100th
  tonight. Runs and wickets are only ever "in reach", never promised.
* **ONE PER PLAYER, THREE PER POST, CERTAIN FIRST.** A player's best candidate
  stands for them, then the post takes the top three. After "certain" the order
  is how far through its own window a candidate is (needed / window), so 4
  wickets from 100 and 40 runs from 1,000 are compared on how close each is to
  landing, not on raw counts that always favour wickets. Ties go to the smaller
  raw gap, then the name.
* **A PLAYER ALREADY COUNTED IS NOT COUNTED TWICE.** When the match has been
  played and scored (a late repost), the career figures already include it, so
  the player's games before the match are one fewer. Otherwise a repost would
  call the 100th game the 101st.
* **AS OF THE LAST COMPLETED ROUND, AND SAYS WHEN IT CANNOT BE.** The figures are
  only as good as the last sync. The answer carries ``freshness``: ``stale``
  when a club game in the last round is still UPCOMING or LIVE after its date, or
  no successful sync has finished since the day of the last scored game;
  ``unknown`` when the club has nothing to judge by (no scored game, or no sync
  history, which is every club that works from imports alone); ``fresh``
  otherwise. Only ``stale`` blocks a post; ``unknown`` says so and does not
  refuse (a club may legitimately lack the means to prove freshness).

Players are scoped by ``players.organisation_id``, so a fill-in or another
club's player is never read. An id this club cannot answer for is left out of
``known`` and gets no badge.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import milestone_totals
from app.services.club_grades import club_game_sql
from app.services.game_status import NOT_PLAYED_SQL_LIST
from app.services.milestone_rules import (
    Scheme, load_scheme, next_threshold, reach_window,
)
from app.services.social_debuts import MAX_PLAYERS, parse_ids  # noqa: F401  (re-exported)

#: Most milestones a post carries.
MAX_ITEMS = 3

#: How far back "the last round" is looked for. A fixture still UPCOMING or LIVE
#: after its date inside this window means the round has not been pulled yet.
ROUND_WINDOW_DAYS = 10

#: (kind on the post, milestone type in ``milestone_rules``, unit word).
_STATS = (
    ("runs", "runs", "club runs"),
    ("wickets", "wickets", "club wickets"),
)


def _fmt(n: int) -> str:
    return f"{n:,}"


def _short_target(n: int) -> str:
    """1000 -> '1K', 2500 -> '2.5K', 100 -> '100'. For a badge with little room."""
    if n >= 1000:
        k = n / 1000
        return f"{k:g}K"
    return str(n)


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def candidates_for(player: dict, scheme: Scheme | None) -> list[dict]:
    """Every milestone this player is close to, certain or in reach.

    ``player`` carries ``player_id``, ``player_name`` and the career figures
    ``matches``, ``runs``, ``wickets`` as they stand BEFORE the lineup's match.
    """
    out: list[dict] = []
    base = {"player_id": player["player_id"], "player_name": player.get("player_name") or ""}
    games = int(player.get("matches") or 0)
    # This match is their next game. A threshold that is exactly the next game
    # is the one certain milestone a lineup can announce.
    target = next_threshold("matches", games, scheme)
    if target is not None and target == games + 1:
        out.append({
            **base, "kind": "games", "certain": True, "current": games,
            "target": target, "needed": 1, "window": 1,
            "label": f"{_ordinal(target)} club game",
            "badge": f"{_ordinal(target).upper()} GAME", "short": _ordinal(target).upper(),
        })
    for kind, mtype, unit in _STATS:
        current = int(player.get(kind) or 0)
        target = next_threshold(mtype, current, scheme)
        if target is None:
            continue
        needed = target - current
        window = reach_window(mtype, target, scheme)
        if needed > window or needed <= 0:
            continue
        noun = "run" if kind == "runs" else "wicket"
        word = noun if needed == 1 else noun + "s"
        out.append({
            **base, "kind": kind, "certain": False, "current": current,
            "target": target, "needed": needed, "window": window,
            "label": f"{_fmt(needed)} {word} to {_fmt(target)} {unit}",
            "badge": f"{_short_target(target)} {'RUNS' if kind == 'runs' else 'WKTS'}",
            "short": _short_target(target),
        })
    return out


def rank_key(c: dict) -> tuple:
    """Certain first, then closest to landing inside its own window, then smallest gap."""
    return (0 if c["certain"] else 1, c["needed"] / max(1, c["window"]), c["needed"],
            c["player_name"].lower(), c["kind"])


def pick_watch(players: list[dict], scheme: Scheme | None, limit: int = MAX_ITEMS) -> list[dict]:
    """The post's milestones: each player's best candidate, then the top ``limit``."""
    best: dict[str, dict] = {}
    for p in players:
        cands = candidates_for(p, scheme)
        if cands:
            best[p["player_id"]] = min(cands, key=rank_key)
    return sorted(best.values(), key=rank_key)[:limit]


def badges_for(players: list[dict], scheme: Scheme | None) -> dict[str, dict]:
    """One badge per player who has any candidate, for the gold mark beside their name.

    The strip is capped at three, but a badge is per player, so a squad of eleven
    may carry more badges than the strip lists. The strip is the shortlist; the
    badge is "this one is close".
    """
    out: dict[str, dict] = {}
    for p in players:
        cands = candidates_for(p, scheme)
        if cands:
            out[p["player_id"]] = min(cands, key=rank_key)
    return out


# ─── Freshness ────────────────────────────────────────────────────────────────

_ROUND_SQL = text(f"""
    SELECT
        MAX(g.played_at) FILTER (
            WHERE UPPER(COALESCE(g.status, '')) NOT IN ('UPCOMING', 'LIVE')
              AND UPPER(COALESCE(g.status, '')) NOT IN ({NOT_PLAYED_SQL_LIST})
        ) AS last_scored,
        COUNT(*) FILTER (
            WHERE UPPER(COALESCE(g.status, '')) IN ('UPCOMING', 'LIVE')
        ) AS unscored
    FROM v_effective_games g
    WHERE {club_game_sql('g', 'club_org')}
      AND g.played_at >= :floor
      AND g.played_at < :ceiling
""")

_PLAYED_ON_SQL = text("""
    SELECT DISTINCT ga.player_id::text AS player_id
    FROM game_appearances ga
    JOIN v_effective_games g ON g.id = ga.game_id
    WHERE ga.player_id = ANY(CAST(:ids AS uuid[]))
      AND g.played_at = :on
      AND UPPER(COALESCE(g.status, '')) NOT IN ('UPCOMING', 'LIVE')
      AND UPPER(COALESCE(g.status, '')) NOT IN (""" + NOT_PLAYED_SQL_LIST + """)
""")

_PLAYERS_SQL = text("""
    SELECT p.id::text AS player_id,
           COALESCE(p.display_name_override, p.name) AS player_name
    FROM players p
    WHERE p.organisation_id = CAST(:org AS uuid)
      AND p.id = ANY(CAST(:ids AS uuid[]))
""")


def judge_freshness(*, last_scored: date | None, unscored: int,
                    synced_at: datetime | None) -> tuple[str, str | None]:
    """``(freshness, reason)`` for a club whose last round is ``last_scored``.

    Pure, so the rule can be proved without a database. A game still UPCOMING or
    LIVE after its date is the sharpest sign (the round was never pulled); a last
    successful sync dated before the last scored game's day is the other (the
    round was scored on CA's side after we last looked).
    """
    if unscored:
        n = "game is" if unscored == 1 else "games are"
        return "stale", (f"{unscored} {n} from the last round still not scored here. "
                         "Run a sync, then make the post again.")
    if last_scored is None or synced_at is None:
        return "unknown", None
    synced_day = synced_at.astimezone(timezone.utc).date() if synced_at.tzinfo else synced_at.date()
    if synced_day < last_scored:
        return "stale", (f"The last sync finished before the {last_scored.strftime('%-d %b')} round was played. "
                         "Run a sync, then make the post again.")
    return "fresh", None


async def _freshness(db: AsyncSession, org_id, on: date, today: date) -> dict:
    from app.services.auto_sync import last_sync_at
    ceiling = min(on, today)
    floor = ceiling - timedelta(days=ROUND_WINDOW_DAYS)
    row = (await db.execute(_ROUND_SQL, {
        "club_org": str(org_id), "floor": floor, "ceiling": ceiling,
    })).mappings().first() or {}
    synced = await last_sync_at(db, org_id)
    state, reason = judge_freshness(
        last_scored=row.get("last_scored"), unscored=int(row.get("unscored") or 0),
        synced_at=synced,
    )
    return {
        "freshness": state,
        "stale": state == "stale",
        "stale_reason": reason,
        "as_of": row["last_scored"].isoformat() if row.get("last_scored") else None,
        "synced_at": synced.isoformat() if synced else None,
    }


async def social_milestones(
    db: AsyncSession, org, player_ids: list[str], on: date | None = None,
    *, today: date | None = None,
) -> dict:
    """``{items, badges, known, freshness, stale, stale_reason, as_of, synced_at, match_date}``.

    ``items`` is the strip (at most three), ``badges`` maps a player id to the
    badge text for the gold mark beside their name. ``on`` is the match day.
    """
    day = on or date.today()
    now = today or date.today()
    out = {"items": [], "badges": {}, "known": [], "match_date": day.isoformat()}
    fresh = await _freshness(db, org.id, day, now)
    out.update(fresh)
    if not player_ids:
        return out
    people = [dict(r) for r in (await db.execute(
        _PLAYERS_SQL, {"org": str(org.id), "ids": player_ids})).mappings()]
    if not people:
        return out
    out["known"] = [p["player_id"] for p in people]
    scheme = await load_scheme(db, org.id)
    totals = await milestone_totals.profile_totals(db, org.id, [p["player_id"] for p in people])
    # A match already scored is already inside the career figure.
    counted = {r[0] for r in (await db.execute(
        _PLAYED_ON_SQL, {"ids": out["known"], "on": day})).all()}
    rows = []
    for p in people:
        t = (totals.get(p["player_id"]) or {}).get("totals") or {}
        matches = int(t.get("matches") or 0)
        if p["player_id"] in counted:
            matches = max(0, matches - 1)
        rows.append({
            "player_id": p["player_id"], "player_name": p["player_name"],
            "matches": matches, "runs": int(t.get("runs") or 0), "wickets": int(t.get("wickets") or 0),
        })
    out["items"] = pick_watch(rows, scheme)
    out["badges"] = badges_for(rows, scheme)
    return out
