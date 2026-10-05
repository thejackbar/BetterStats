"""BetterFantasyCricket engine — round generation, the priced pool, settlement.

The DB-bound half of the scoring/pricing core. It reads the club's real data
through the org-scoped ``v_effective_*`` views (so merges and manual adjustments
are respected) and writes the fantasy spine:

  - ``generate_rounds``  groups the season's games into weekly fantasy rounds
  - ``build_pool``       classifies each eligible player and prices them from
                         their recent record
  - ``settle_round``     computes per-player fantasy points for a round from the
                         scorecards, idempotently (safe to re-run after a re-sync)

Squad-level scoring (best 11, captain, transfer hit) and price movement live with
the salary-cap engine, which has the managers and squads. Pure points and role
maths come from ``fantasy_scoring``. Full design: docs/betterfantasycricket.md.

NOTE: not exercised in the build sandbox (no database). Verify on a deployed
environment after migration 087.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation
from app.services import fantasy_squad, fantasy_draft
from app.services import grassroots_scores_client as gr
from app.services import playhq_client
from app.services.club_match import club_match_keys
from app.services.club_grades import club_game_sql, club_grade_rows
from app.services.fantasy_scoring import (
    DEFAULT_RULES, DEFAULT_SCORING, classify_role, score_player_round,
)

logger = logging.getLogger(__name__)

# Recent window (in seasons, inclusive of the current year) used to price form.
PRICE_WINDOW_YEARS = 3
# Price band the baseline maps into; tuned so a balanced 12 fits a 100 budget but
# the premiums can't all be afforded. Heuristic — easy to retune once a club plays.
# A match longer than this many days between first and last day is treated as bad data.
MAX_MATCH_SPAN_DAYS = 10
PRICE_MIN, PRICE_MAX, PRICE_FLOOR, PRICE_K = 4.0, 15.0, 4.0, 0.12

# A round an admin has taken back out of settlement. It reads as not scored
# everywhere (public pages, ladders), but the automatic settlers skip it so the
# daily job doesn't put the points straight back; the admin's Settle button does.
ROUND_UNSETTLED = "unsettled"
AUTO_SETTLE_SKIP = ("scored", ROUND_UNSETTLED)


async def _grade_scope(session: AsyncSession, fs) -> list | None:
    """The grade ids a game may sit in to count, or None for every grade.

    ``included_grade_ids`` holds the club's OWN grade ids. A fixture between two
    clubs that both sync is one ``games`` row whose ``grade_id`` is whichever
    club's row it was first synced under, so matching on our ids alone would drop
    it the moment the other club had synced it first. Each included grade is
    widened to every grade row of the same name key the club's games sit in
    (``club_grade_rows``)."""
    ids = fs.included_grade_ids or None
    if not ids:
        return None
    want = {str(i) for i in ids}
    rows = await club_grade_rows(session, fs.organisation_id)
    keys = {c.key for c in rows if str(c.id) in want}
    return sorted({str(c.id) for c in rows if c.key in keys} | want)


def _grade_clause(included_grade_ids, alias: str = "g") -> str:
    """Optional ``AND <alias>.grade_id = ANY(:grades)`` when the season restricts
    which grades count. NULL/empty means every grade."""
    return f" AND {alias}.grade_id = ANY(:grades)" if included_grade_ids else ""


# ── Round generation ───────────────────────────────────────────────────────────

async def _discover_grade_guids(org_guid: str, year: int) -> list[str]:
    """Raw CA grade GUIDs the club fields in the season that starts in ``year``,
    straight from Grassroots: the club's season list (one call), then the teams
    of each matching season. Mirrors how ``sync.py`` seeds grades, without
    writing anything. ``sync`` stamps ``seasons.year`` from the season's start
    date, so the same rule picks the season here."""
    seasons = await playhq_client.get_seasons(org_guid)
    season_ids = [
        s["id"] for s in seasons
        if isinstance(s, dict) and s.get("id") and (s.get("startDate") or "")[:4] == str(year)
    ]
    found: list[str] = []
    for sid in season_ids:
        for t in await playhq_client.get_teams(org_guid, sid):
            grade_objs = list((t or {}).get("grades") or [])
            if (t or {}).get("grade"):
                grade_objs.append(t["grade"])
            for gd in grade_objs:
                gid = ((gd or {}).get("id") or "").strip()
                if gid and gid not in found:
                    found.append(gid)
    return found


async def _live_calendar_spans(session: AsyncSession, fs, refresh: bool) -> tuple[list[tuple[date, date]], int]:
    """Spans (first day, last day) of the club's matches in the fantasy season-year, read straight from the
    Play-Cricket (Grassroots) season calendar: every match in each of the
    season's grades that involves the club, whatever its status.

    This is why generating rounds needs no BetterSelect fixture sync and no
    played games: before a ball is bowled the stored ``games`` table is empty
    for the new season and upcoming fixtures are never persisted there.

    A match is a SPAN, not a date: a two-day match carries one ``matchSchedule``
    entry per day (``matchDay`` 1 and 2, a week apart) and the entries are not
    reliably in day order. Reading only the first one split one match across two
    rounds, or put it on day 2 in one grade and day 1 in another. Returns
    ``(spans, grades_checked)``. A grade whose fetch fails contributes nothing
    (the client already swallows and logs), so a Play-Cricket blip degrades to
    "fewer dates", never an error. ``refresh`` bypasses the in-process cache so
    an admin pressing the button sees a newly published draw."""
    grades = fs.included_grade_ids or None
    params = {"org": str(fs.organisation_id), "year": fs.season_year}
    if grades:
        params["grades"] = grades
    rows = (await session.execute(
        text(f"""
            SELECT DISTINCT COALESCE(g.grassroots_id, g.id::text) AS guid
            FROM grades g
            JOIN seasons s ON s.id = g.season_id
            WHERE s.organisation_id = CAST(:org AS UUID) AND s.year = :year
              {"AND g.id = ANY(:grades)" if grades else ""}
        """),
        params,
    )).all()
    guids = [r[0] for r in rows if r[0]]
    if not grades:
        # Always add the grades Play-Cricket lists for the year to the ones on
        # file, never only when none are. A club can have SOME of its grades
        # synced (Leederville had its women's grade but not its men's), and the
        # rounds then silently covered one program. Discovery is read-only and
        # mirrors how sync seeds grades: the season list, then each season's
        # teams carry the grade ids. Skipped when the admin restricted the
        # season to chosen grades: those are our own ids, so already on file.
        try:
            for g in await _discover_grade_guids(str(fs.organisation_id), fs.season_year):
                if g not in guids:
                    guids.append(g)
        except Exception:
            logger.exception("fantasy: grade discovery failed for season %s", fs.id)
    if not guids:
        return [], 0

    org = await session.get(Organisation, fs.organisation_id)
    keys = club_match_keys(org) if org is not None else []
    org_id = str(fs.organisation_id).lower()
    batches = await asyncio.gather(
        *[gr.get_grade_matches(g, force=refresh) for g in guids], return_exceptions=True,
    )
    spans: list[tuple[date, date]] = []
    for matches in batches:
        if not isinstance(matches, list):
            continue
        for m in matches:
            teams = m.get("teams") or []
            ours = any(
                str((t.get("owningOrganisation") or {}).get("id") or "").lower() == org_id
                or (keys and any(k in (t.get("displayName") or "").lower() for k in keys))
                for t in teams
            )
            if not ours:
                continue
            days: list[date] = []
            for entry in m.get("matchSchedule") or []:
                try:
                    days.append(date.fromisoformat(((entry or {}).get("startDateTime") or "")[:10]))
                except ValueError:
                    continue   # a bye has no schedule at all
            if days:
                spans.append((min(days), max(days)))
    return spans, len(guids)


def _group_rounds(spans: list[tuple[date, date]]) -> list[tuple[date, date]]:
    """Turn match spans into fantasy rounds: ``[(first_day, last_day)]`` in order.

    A round is a club weekend (one ISO week). A match that runs across weeks (a
    two-day game, a week apart) bridges them, so the weeks it touches are ONE
    round and its scorecard stays in one round. Weeks are joined transitively.
    The window runs from the earliest to the latest actual match day in the
    round, which also covers a stored game whose ``played_at`` is either day.
    A span longer than ``MAX_MATCH_SPAN_DAYS`` is bad data, so only its end days
    count as single days rather than gluing a stretch of the season together."""
    def monday(d: date) -> date:
        return d - timedelta(days=d.weekday())

    parent: dict[date, date] = {}

    def find(x: date) -> date:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    days_by_root: dict[date, set[date]] = defaultdict(set)
    clean: list[tuple[date, date]] = []
    for a, b in spans:
        if b < a:
            a, b = b, a
        if (b - a).days > MAX_MATCH_SPAN_DAYS:
            clean += [(a, a), (b, b)]
        else:
            clean.append((a, b))
    for a, b in clean:
        w, last = monday(a), monday(b)
        find(w)
        while w < last:
            w += timedelta(days=7)
            parent[find(w)] = find(monday(a))
    for a, b in clean:
        days_by_root[find(monday(a))].update((a, b))
    rounds = [(min(d), max(d)) for d in days_by_root.values()]
    rounds.sort()
    return rounds


async def generate_rounds(session: AsyncSession, fs, refresh: bool = False) -> dict:
    """Group the season-year's matches into rounds (a club weekend = one ISO
    week; a two-day match spanning two weeks is ONE round, see ``_group_rounds``)
    and upsert ``fantasy_rounds``. Idempotent on round_number; never rewrites a
    round already marked ``scored``. Rounds beyond the new count that nobody has
    scored, picked for or drawn against are removed, so a regenerate that merges
    weeks does not leave stale rounds behind.

    Dates come from two places, merged: games already stored (played, synced,
    manual) and the live Play-Cricket calendar for the season's grades (upcoming
    and just-played matches not synced yet). Returns ``{rounds, from_games,
    from_calendar, grades_checked, detail}``; ``detail`` is a plain sentence the
    admin screen shows, and explains a zero."""
    grades = await _grade_scope(session, fs)
    rows = await session.execute(
        text(f"""
            SELECT g.played_at
            FROM v_effective_games g
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE {club_game_sql("g", "org")} AND s.year = :year
              AND g.played_at IS NOT NULL{_grade_clause(grades)}
            ORDER BY g.played_at
        """),
        {"org": str(fs.organisation_id), "year": fs.season_year, "grades": grades},
    )
    game_dates = {r[0] for r in rows.all()}
    try:
        cal_spans, grades_checked = await _live_calendar_spans(session, fs, refresh)
    except Exception:
        logger.exception("fantasy: live calendar read failed for season %s", fs.id)
        cal_spans, grades_checked = [], 0

    cal_days = {d for a, b in cal_spans for d in (a, b)}
    windows = _group_rounds(cal_spans + [(d, d) for d in game_dates])
    result = {
        "rounds": len(windows), "from_games": len(game_dates),
        "from_calendar": len(cal_days), "grades_checked": grades_checked,
    }
    if not windows:
        if grades_checked:
            result["detail"] = (
                f"No rounds yet: Play-Cricket has no matches published for the club in "
                f"the {fs.season_year}/{(fs.season_year + 1) % 100:02d} grades. Try again once the draw is out."
            )
        else:
            result["detail"] = (
                f"No rounds yet: Play-Cricket lists no {fs.season_year}/{(fs.season_year + 1) % 100:02d} "
                f"season or grades for the club, so there is no draw to read. Check the season year "
                f"matches the one the competition runs under."
            )
        return result

    existing = await session.execute(
        text("SELECT round_number, status FROM fantasy_rounds WHERE fantasy_season_id = CAST(:fs AS UUID)"),
        {"fs": str(fs.id)},
    )
    scored = {r["round_number"] for r in existing.mappings() if r["status"] == "scored"}

    for n, (first, last) in enumerate(windows, start=1):
        if n in scored:
            continue  # leave settled rounds untouched
        # games.played_at is a DATE, so the round window is date-keyed. We don't
        # hold kick-off times, so the lock is the start of the round's first day.
        await session.execute(
            text("""
                INSERT INTO fantasy_rounds
                    (fantasy_season_id, organisation_id, round_number, name, lock_at, start_date, end_date, status)
                VALUES (CAST(:fs AS UUID), CAST(:org AS UUID), :n, :name, :lock_at, :start, :end, 'upcoming')
                ON CONFLICT (fantasy_season_id, round_number) DO UPDATE
                SET name = EXCLUDED.name, lock_at = EXCLUDED.lock_at,
                    start_date = EXCLUDED.start_date, end_date = EXCLUDED.end_date,
                    updated_at = NOW()
            """),
            {
                "fs": str(fs.id), "org": str(fs.organisation_id), "n": n,
                "name": f"Round {n}", "lock_at": datetime.combine(first, time()),
                "start": first, "end": last,
            },
        )
    # Merging weeks can leave fewer rounds than an earlier run made. Drop the
    # surplus only when nothing at all hangs off it (no scores, squad lineups or
    # chips, draws or transfers): those rows record what somebody did.
    await session.execute(
        text("""
            DELETE FROM fantasy_rounds r
            WHERE r.fantasy_season_id = CAST(:fs AS UUID) AND r.round_number > :n
              AND r.status <> 'scored'
              AND NOT EXISTS (SELECT 1 FROM fantasy_player_round_scores x WHERE x.round_id = r.id)
              AND NOT EXISTS (SELECT 1 FROM fantasy_squad_round_scores x WHERE x.round_id = r.id)
              AND NOT EXISTS (SELECT 1 FROM fantasy_transactions x WHERE x.round_id = r.id)
              AND NOT EXISTS (SELECT 1 FROM fantasy_h2h_fixtures x WHERE x.round_id = r.id)
        """),
        {"fs": str(fs.id), "n": len(windows)},
    )
    result["detail"] = f"Generated {len(windows)} round{'' if len(windows) == 1 else 's'} from the {fs.season_year}/{(fs.season_year + 1) % 100:02d} draw."
    return result


# ── Pool build (role + price) ──────────────────────────────────────────────────

async def build_pool(session: AsyncSession, fs, reset: bool | None = None) -> int:
    """Classify and price every eligible player and upsert ``fantasy_pool_players``.

    Eligible = an active player who has turned out in the recent window (this
    season-year or the prior ``PRICE_WINDOW_YEARS - 1``). The recent window
    matters: a fantasy season is usually set up BEFORE the games begin, so a
    current-year-only gate would leave the pool empty pre-season; seeding from
    the last couple of seasons gives the squad you'd expect, and a rebuild once
    the season is underway naturally picks up anyone new. An admin role override
    (role_source = 'admin') is preserved on rebuild; the live ``current_price`` is
    kept once the season is live, but reset to the new baseline while the season
    is still in setup, so changing the pricing window updates the visible prices.
    ``reset`` overrides that default: the admin's explicit "recalculate prices"
    passes ``reset=True`` so a window change moves prices even mid-season.
    Returns the pool size."""
    window = max(1, int((fs.rules or {}).get("price_window_years", PRICE_WINDOW_YEARS)))
    recent_from = fs.season_year - (window - 1)
    reset_price = (fs.status in ("setup", "open")) if reset is None else bool(reset)
    rows = await session.execute(
        text("""
            SELECT p.id AS player_id, p.player_role, p.skill_positions,
                   COALESCE(SUM(pss.batting_innings), 0) AS bat_inns,
                   COALESCE(SUM(pss.bowling_innings), 0) AS bowl_inns,
                   COALESCE(SUM(pss.wickets), 0) AS wickets,
                   COALESCE(SUM(pss.catches_wk), 0) + COALESCE(SUM(pss.stumpings), 0) AS keeper_dis,
                   -- recent (form) window for pricing
                   COALESCE(SUM(pss.matches) FILTER (WHERE s.year >= :rfrom), 0) AS r_matches,
                   COALESCE(SUM(pss.runs) FILTER (WHERE s.year >= :rfrom), 0) AS r_runs,
                   COALESCE(SUM(pss.fours) FILTER (WHERE s.year >= :rfrom), 0) AS r_fours,
                   COALESCE(SUM(pss.sixes) FILTER (WHERE s.year >= :rfrom), 0) AS r_sixes,
                   COALESCE(SUM(pss.fifties) FILTER (WHERE s.year >= :rfrom), 0) AS r_fifties,
                   COALESCE(SUM(pss.hundreds) FILTER (WHERE s.year >= :rfrom), 0) AS r_hundreds,
                   COALESCE(SUM(pss.wickets) FILTER (WHERE s.year >= :rfrom), 0) AS r_wickets,
                   COALESCE(SUM(pss.maidens) FILTER (WHERE s.year >= :rfrom), 0) AS r_maidens,
                   COALESCE(SUM(pss.five_wicket_innings) FILTER (WHERE s.year >= :rfrom), 0) AS r_fivefor,
                   COALESCE(SUM(pss.catches) FILTER (WHERE s.year >= :rfrom), 0) AS r_catches,
                   COALESCE(SUM(pss.catches_wk) FILTER (WHERE s.year >= :rfrom), 0) AS r_catches_wk,
                   COALESCE(SUM(pss.stumpings) FILTER (WHERE s.year >= :rfrom), 0) AS r_stumpings,
                   COALESCE(SUM(pss.run_outs) FILTER (WHERE s.year >= :rfrom), 0) AS r_run_outs
            FROM players p
            JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
            JOIN seasons s ON s.id = pss.season_id AND s.organisation_id = CAST(:org AS UUID)
            WHERE p.organisation_id = CAST(:org AS UUID)
              AND p.status = 'active' AND COALESCE(p.is_player, true)
            GROUP BY p.id, p.player_role, p.skill_positions
            HAVING BOOL_OR(s.year >= :rfrom)
        """),
        {"org": str(fs.organisation_id), "year": fs.season_year, "rfrom": recent_from},
    )

    count = 0
    for r in rows.mappings():
        role, source = classify_role(
            player_role=r["player_role"], skill_positions=r["skill_positions"],
            bat_innings=int(r["bat_inns"]), wickets=int(r["wickets"]),
            bowl_innings=int(r["bowl_inns"]), keeper_dismissals=int(r["keeper_dis"]),
        )
        price = _baseline_price(r, role)
        await session.execute(
            text("""
                INSERT INTO fantasy_pool_players
                    (fantasy_season_id, organisation_id, player_id, role, role_source,
                     base_price, current_price)
                VALUES (CAST(:fs AS UUID), CAST(:org AS UUID), CAST(:pid AS UUID), :role, :source,
                        :price, :price)
                ON CONFLICT (fantasy_season_id, player_id) DO UPDATE SET
                    base_price = EXCLUDED.base_price,
                    current_price = CASE WHEN :reset THEN EXCLUDED.base_price
                                ELSE fantasy_pool_players.current_price END,
                    role = CASE WHEN fantasy_pool_players.role_source = 'admin'
                                THEN fantasy_pool_players.role ELSE EXCLUDED.role END,
                    role_source = CASE WHEN fantasy_pool_players.role_source = 'admin'
                                THEN 'admin' ELSE EXCLUDED.role_source END,
                    updated_at = NOW()
            """),
            {
                "fs": str(fs.id), "org": str(fs.organisation_id), "pid": str(r["player_id"]),
                "role": role, "source": source, "price": price, "reset": reset_price,
            },
        )
        count += 1
    return count


def _baseline_price(r, role: str) -> float:
    """Map a player's recent record to a starting price. Approximate fantasy
    points per game from season aggregates (per-innings milestones aren't in the
    aggregates, so fifties/hundreds/five-fors stand in), role-weighted, then
    scaled into the price band."""
    s = DEFAULT_SCORING
    m = float(s["off_role_multiplier"])
    bat_mult, bowl_mult, keep_mult = (
        (m, 1.0, 1.0) if role == "bowler" else
        (m, 1.0, m) if role == "keeper" else
        (1.0, 1.0, 1.0) if role == "allrounder" else
        (1.0, m, 1.0)
    )
    bat = (r["r_runs"] * s["run"] + r["r_fours"] * s["four"] + r["r_sixes"] * s["six"]
           + r["r_fifties"] * s["fifty"] + r["r_hundreds"] * s["hundred"])
    bowl = r["r_wickets"] * s["wicket"] + r["r_maidens"] * s["maiden"] + r["r_fivefor"] * s["five_wickets"]
    keep = r["r_catches_wk"] * s["catch"] + r["r_stumpings"] * s["stumping"]
    field = (r["r_catches"] - r["r_catches_wk"]) * s["catch"] + r["r_run_outs"] * s["run_out"]
    matches = max(int(r["r_matches"]), 1)
    weighted = bat * bat_mult + bowl * bowl_mult + keep * keep_mult + field + matches * s["appearance"]
    ppg = weighted / matches
    return round(min(max(PRICE_FLOOR + ppg * PRICE_K, PRICE_MIN), PRICE_MAX), 1)


async def classify_and_price_one(session: AsyncSession, fs, player_id) -> tuple[str, float]:
    """Role + baseline price for a single player, used when an admin adds a
    returning player to the pool by hand. Falls back to a batter at the floor
    price when there's no usable history."""
    window = max(1, int((fs.rules or {}).get("price_window_years", PRICE_WINDOW_YEARS)))
    recent_from = fs.season_year - (window - 1)
    row = (await session.execute(
        text("""
            SELECT p.player_role, p.skill_positions,
                   COALESCE(SUM(pss.batting_innings), 0) AS bat_inns,
                   COALESCE(SUM(pss.bowling_innings), 0) AS bowl_inns,
                   COALESCE(SUM(pss.wickets), 0) AS wickets,
                   COALESCE(SUM(pss.catches_wk), 0) + COALESCE(SUM(pss.stumpings), 0) AS keeper_dis,
                   COALESCE(SUM(pss.matches) FILTER (WHERE s.year >= :rfrom), 0) AS r_matches,
                   COALESCE(SUM(pss.runs) FILTER (WHERE s.year >= :rfrom), 0) AS r_runs,
                   COALESCE(SUM(pss.fours) FILTER (WHERE s.year >= :rfrom), 0) AS r_fours,
                   COALESCE(SUM(pss.sixes) FILTER (WHERE s.year >= :rfrom), 0) AS r_sixes,
                   COALESCE(SUM(pss.fifties) FILTER (WHERE s.year >= :rfrom), 0) AS r_fifties,
                   COALESCE(SUM(pss.hundreds) FILTER (WHERE s.year >= :rfrom), 0) AS r_hundreds,
                   COALESCE(SUM(pss.wickets) FILTER (WHERE s.year >= :rfrom), 0) AS r_wickets,
                   COALESCE(SUM(pss.maidens) FILTER (WHERE s.year >= :rfrom), 0) AS r_maidens,
                   COALESCE(SUM(pss.five_wicket_innings) FILTER (WHERE s.year >= :rfrom), 0) AS r_fivefor,
                   COALESCE(SUM(pss.catches) FILTER (WHERE s.year >= :rfrom), 0) AS r_catches,
                   COALESCE(SUM(pss.catches_wk) FILTER (WHERE s.year >= :rfrom), 0) AS r_catches_wk,
                   COALESCE(SUM(pss.stumpings) FILTER (WHERE s.year >= :rfrom), 0) AS r_stumpings,
                   COALESCE(SUM(pss.run_outs) FILTER (WHERE s.year >= :rfrom), 0) AS r_run_outs
            FROM players p
            LEFT JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
            LEFT JOIN seasons s ON s.id = pss.season_id AND s.organisation_id = CAST(:org AS UUID)
            WHERE p.id = CAST(:pid AS UUID)
            GROUP BY p.id, p.player_role, p.skill_positions
        """),
        {"org": str(fs.organisation_id), "pid": str(player_id), "rfrom": recent_from},
    )).mappings().first()
    if not row:
        return "batter", PRICE_MIN
    role, _src = classify_role(
        player_role=row["player_role"], skill_positions=row["skill_positions"],
        bat_innings=int(row["bat_inns"]), wickets=int(row["wickets"]),
        bowl_innings=int(row["bowl_inns"]), keeper_dismissals=int(row["keeper_dis"]),
    )
    return role, _baseline_price(row, role)


# ── Round settlement (player points) ───────────────────────────────────────────

async def _round_player_scores(session: AsyncSession, fs, rnd) -> dict[str, dict]:
    """Read-only: compute each player's fantasy points for a round's window from
    the scorecards, with no writes. Returns ``{player_id: {base, total,
    breakdown, games}}``. Shared by round settlement (which then persists) and the
    live preview (which doesn't), so the two can never disagree."""
    grades = await _grade_scope(session, fs)
    base = {"org": str(fs.organisation_id), "year": fs.season_year,
            "start": rnd.start_date, "end": rnd.end_date, "grades": grades}

    # A game is the club's when it is its own fixture or it is one of the two
    # sides; never decided by who owns the season row it happens to hang off.
    games = await session.execute(
        text(f"""
            SELECT g.id
            FROM v_effective_games g
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE {club_game_sql("g", "org")} AND s.year = :year
              AND g.played_at::date BETWEEN :start AND :end{_grade_clause(grades)}
        """),
        base,
    )
    game_ids = [row[0] for row in games.all()]
    if not game_ids:
        return {}
    # A shared fixture carries BOTH clubs' rows, so only our own players count.
    gp = {"gids": game_ids, "org": str(fs.organisation_id)}

    batting = await session.execute(
        text("""
            SELECT bi.player_id, bi.game_id, bi.runs,
                   COALESCE(bi.fours, 0) AS fours, COALESCE(bi.sixes, 0) AS sixes,
                   (bi.did_not_bat IS NOT TRUE AND NOT bi.not_out AND bi.dismissal_type IS NOT NULL) AS out
            FROM v_effective_batting_innings bi
            JOIN players pl ON pl.id = bi.player_id AND pl.organisation_id = CAST(:org AS UUID)
            WHERE bi.game_id = ANY(:gids) AND bi.did_not_bat IS NOT TRUE
        """), gp,
    )
    bowling = await session.execute(
        text("""
            SELECT bs.player_id, bs.game_id, bs.wickets, COALESCE(bs.maidens, 0) AS maidens
            FROM v_effective_bowling_spells bs
            JOIN players pl ON pl.id = bs.player_id AND pl.organisation_id = CAST(:org AS UUID)
            WHERE bs.game_id = ANY(:gids)
        """), gp,
    )
    fielding = await session.execute(
        text("""
            SELECT fs.player_id, fs.game_id,
                   COALESCE(fs.catches, 0) AS catches, COALESCE(fs.catches_wk, 0) AS catches_wk,
                   COALESCE(fs.run_outs, 0) AS run_outs, COALESCE(fs.stumpings, 0) AS stumpings
            FROM v_effective_fielding_stats fs
            JOIN players pl ON pl.id = fs.player_id AND pl.organisation_id = CAST(:org AS UUID)
            WHERE fs.game_id = ANY(:gids)
        """), gp,
    )
    appearances = await session.execute(
        text("""SELECT ga.player_id, ga.game_id FROM game_appearances ga
                JOIN players pl ON pl.id = ga.player_id AND pl.organisation_id = CAST(:org AS UUID)
                WHERE ga.game_id = ANY(:gids)"""), gp,
    )
    roles = await session.execute(
        text("SELECT player_id, role FROM fantasy_pool_players WHERE fantasy_season_id = CAST(:fs AS UUID)"),
        {"fs": str(fs.id)},
    )
    role_by_player = {str(r["player_id"]): r["role"] for r in roles.mappings()}

    # Assemble per (player, game): batting innings list, bowling list, fielding, played.
    games_by_player: dict[str, dict] = defaultdict(dict)

    def _cell(pid: str, gid) -> dict:
        g = games_by_player[pid].setdefault(gid, {
            "batting": [], "bowling": [], "catches_wk": 0, "stumpings": 0,
            "catches_nonwk": 0, "run_outs": 0, "played": True,
        })
        return g

    for b in batting.mappings():
        _cell(str(b["player_id"]), b["game_id"])["batting"].append(
            {"runs": b["runs"] or 0, "fours": b["fours"], "sixes": b["sixes"], "out": bool(b["out"])}
        )
    for w in bowling.mappings():
        _cell(str(w["player_id"]), w["game_id"])["bowling"].append(
            {"wickets": w["wickets"] or 0, "maidens": w["maidens"]}
        )
    for f in fielding.mappings():
        c = _cell(str(f["player_id"]), f["game_id"])
        c["catches_wk"] = f["catches_wk"]
        c["stumpings"] = f["stumpings"]
        c["catches_nonwk"] = max((f["catches"] or 0) - (f["catches_wk"] or 0), 0)
        c["run_outs"] = f["run_outs"]
    for a in appearances.mappings():
        _cell(str(a["player_id"]), a["game_id"])  # ensures the appearance point

    out: dict[str, dict] = {}
    for pid, by_game in games_by_player.items():
        role = role_by_player.get(pid, "batter")
        base_pts, total_pts, breakdown = score_player_round(list(by_game.values()), role, fs.scoring or DEFAULT_SCORING)
        out[pid] = {"base": base_pts, "total": total_pts, "breakdown": breakdown, "games": len(by_game)}
    return out


async def _write_player_scores(session: AsyncSession, fs, rnd, by_player: dict[str, dict]) -> int:
    """Upsert each player's round score. Idempotent on (round, player). A score an
    admin typed in by hand (``breakdown.manual``) is theirs and is left as it is."""
    scored = 0
    for pid, sc in by_player.items():
        await session.execute(
            text("""
                INSERT INTO fantasy_player_round_scores
                    (fantasy_season_id, round_id, player_id, base_points, total_points, breakdown, games_counted, computed_at)
                VALUES (CAST(:fs AS UUID), CAST(:rid AS UUID), CAST(:pid AS UUID), :base, :total, CAST(:bd AS JSONB), :games, NOW())
                ON CONFLICT (round_id, player_id) DO UPDATE SET
                    base_points = EXCLUDED.base_points, total_points = EXCLUDED.total_points,
                    breakdown = EXCLUDED.breakdown, games_counted = EXCLUDED.games_counted,
                    computed_at = NOW()
                WHERE fantasy_player_round_scores.breakdown->>'manual' IS NULL
            """),
            {
                "fs": str(fs.id), "rid": str(rnd.id), "pid": pid,
                "base": sc["base"], "total": sc["total"],
                "bd": json.dumps(sc["breakdown"]), "games": sc["games"],
            },
        )
        scored += 1
    return scored


async def refresh_live_round(session: AsyncSession, fs, rnd) -> int:
    """Provisional scoring for a round that has started but isn't over, so points
    show on the ladder and the player list while a long round is still running
    (a two-week round otherwise shows nothing until the end).

    Writes the same player, squad and ladder rows settlement does, from the games
    in the window so far, but leaves the round unscored, grants no free transfer
    and fills no head-to-head result; settlement later recomputes it all and does
    those. A no-op unless the round has started and is not scored. Returns the
    number of players with points."""
    if rnd.status == "scored" or not rnd.start_date or rnd.start_date > date.today():
        return 0
    by_player = await _round_player_scores(session, fs, rnd)
    # Provisional rows are ours to replace, so a corrected scorecard that no
    # longer scores a player drops them rather than leaving a stale figure.
    await session.execute(
        text("""DELETE FROM fantasy_player_round_scores
                WHERE round_id = CAST(:rid AS UUID) AND player_id <> ALL(CAST(:pids AS UUID[]))
                  AND breakdown->>'manual' IS NULL"""),
        {"rid": str(rnd.id), "pids": list(by_player)},
    )
    n = await _write_player_scores(session, fs, rnd, by_player)
    await _refresh_pool_totals(session, fs, rnd)
    await fantasy_squad.score_squads_for_round(session, fs, rnd, rollover=False)
    return n


async def settle_round(session: AsyncSession, fs, rnd, live_picks: bool = False) -> int:
    """Compute each player's fantasy points for a round from the scorecards of the
    games in the round window, and upsert ``fantasy_player_round_scores``.
    Idempotent on (round, player). Marks the round ``scored`` and refreshes the
    pool's season totals. Returns the number of players scored.

    Settling a round that is already scored (a late scorecard, a corrected one, a
    scoring change) scores each squad with the lineup it was settled with, so a
    transfer made since does not rewrite the round. ``live_picks=True`` is for an
    admin edit of the picks themselves, which is meant to change history."""
    by_player = await _round_player_scores(session, fs, rnd)
    has_manual = bool((await session.execute(
        text("SELECT 1 FROM fantasy_player_round_scores WHERE round_id = CAST(:rid AS UUID) "
             "AND breakdown->>'manual' IS NOT NULL LIMIT 1"), {"rid": str(rnd.id)},
    )).scalar())
    if not by_player and not has_manual:
        await _mark_scored(session, rnd, 0)
        return 0
    # Settling a round that is already scored (to pick up a corrected scorecard or
    # an admin edit) must not bank another free transfer; only the first does.
    first_settle = rnd.status != "scored"
    from_snapshot = (not first_settle) and not live_picks

    scored = await _write_player_scores(session, fs, rnd, by_player)

    await _refresh_pool_totals(session, fs, rnd)
    # Roll the per-player points up into each squad's best-11 round score + ladder.
    await fantasy_squad.score_squads_for_round(session, fs, rnd, rollover=first_settle, from_snapshot=from_snapshot)
    # Fill any head-to-head draft fixtures for this round.
    await fantasy_draft.settle_h2h(session, fs, rnd)
    # The season is live once the first round settles — squad changes now go
    # through transfers, not a full rebuild.
    if fs.status in ("setup", "open"):
        await session.execute(
            text("UPDATE fantasy_seasons SET status = 'active', updated_at = NOW() WHERE id = CAST(:fs AS UUID)"),
            {"fs": str(fs.id)},
        )
        fs.status = "active"
    await _mark_scored(session, rnd, scored)
    return scored


async def set_manual_score(session: AsyncSession, fs, rnd, player_id, points: float, note: str | None, by) -> None:
    """Type in a player's fantasy points for a round, for someone whose games are
    not in the data (a new player, an unsynced match). Settlement and the live
    refresh leave it alone; ``clear_manual_score`` hands the round back to the
    scorecards. ``points`` is the final figure, after any role multiplier."""
    await session.execute(
        text("""
            INSERT INTO fantasy_player_round_scores
                (fantasy_season_id, round_id, player_id, base_points, total_points, breakdown, games_counted, computed_at)
            VALUES (CAST(:fs AS UUID), CAST(:rid AS UUID), CAST(:pid AS UUID), :pts, :pts,
                    CAST(:bd AS JSONB), 1, NOW())
            ON CONFLICT (round_id, player_id) DO UPDATE SET
                base_points = EXCLUDED.base_points, total_points = EXCLUDED.total_points,
                breakdown = EXCLUDED.breakdown, games_counted = EXCLUDED.games_counted,
                computed_at = NOW()
        """),
        {"fs": str(fs.id), "rid": str(rnd.id), "pid": str(player_id), "pts": round(float(points), 2),
         "bd": json.dumps({"manual": True, "note": note or None, "by": str(by) if by else None,
                           "at": datetime.utcnow().isoformat()})},
    )


async def clear_manual_score(session: AsyncSession, rnd, player_id) -> bool:
    """Remove a hand-typed score. Returns whether there was one. The next settle
    of the round computes the player from the scorecards again."""
    res = await session.execute(
        text("DELETE FROM fantasy_player_round_scores WHERE round_id = CAST(:rid AS UUID) "
             "AND player_id = CAST(:pid AS UUID) AND breakdown->>'manual' IS NOT NULL"),
        {"rid": str(rnd.id), "pid": str(player_id)},
    )
    return bool(res.rowcount)


async def rescore_round(session: AsyncSession, fs, rnd, live_picks: bool = False) -> str:
    """Bring one round's points in line with the data and picks as they now stand.
    A scored round is settled again (no second free transfer); a round still being
    played gets its provisional points; anything else is left for its own settle.
    Returns what was done."""
    if rnd.status == "scored":
        await settle_round(session, fs, rnd, live_picks=live_picks)
        return "settled"
    if rnd.status != ROUND_UNSETTLED and rnd.start_date and rnd.start_date <= date.today():
        await refresh_live_round(session, fs, rnd)
        return "refreshed"
    return "skipped"


async def rescore_from_round(session: AsyncSession, fs, from_round: int = 1, live_picks: bool = False) -> dict:
    """``rescore_round`` for every round from ``from_round`` on, in order.
    ``live_picks`` is for edits to the picks themselves (see ``settle_round``)."""
    rows = (await session.execute(
        text("SELECT id FROM fantasy_rounds WHERE fantasy_season_id = CAST(:fs AS UUID) "
             "AND round_number >= :n ORDER BY round_number"),
        {"fs": str(fs.id), "n": int(from_round)},
    )).scalars().all()
    done = {"settled": 0, "refreshed": 0, "skipped": 0}
    from app.models.db import FantasyRound
    for rid in rows:
        rnd = await session.get(FantasyRound, rid)
        done[await rescore_round(session, fs, rnd, live_picks=live_picks)] += 1
    return done


async def round_drift(session: AsyncSession, fs, rnd) -> list[dict]:
    """Players whose stored points for a scored round no longer match the scorecards.

    A round is settled once its window has ended, but scorers finish and correct
    scorecards afterwards and a sync can land a game late, so a player who played
    can be sitting on 0 (or a stale figure) in a round that is already scored.
    Read only. A hand-typed score is never reported: it is the club's own."""
    now = await _round_player_scores(session, fs, rnd)
    stored = {str(r["player_id"]): float(r["total_points"]) for r in (await session.execute(
        text("""SELECT player_id, total_points FROM fantasy_player_round_scores
                WHERE round_id = CAST(:rid AS UUID) AND breakdown->>'manual' IS NULL"""),
        {"rid": str(rnd.id)})).mappings().all()}
    manual = {str(r[0]) for r in (await session.execute(
        text("""SELECT player_id FROM fantasy_player_round_scores
                WHERE round_id = CAST(:rid AS UUID) AND breakdown->>'manual' IS NOT NULL"""),
        {"rid": str(rnd.id)})).all()}
    out = []
    for pid in sorted(set(now) | set(stored)):
        if pid in manual:
            continue
        a, b = stored.get(pid, 0.0), float(now[pid]["total"]) if pid in now else 0.0
        if abs(a - b) > 1e-6:
            out.append({"player_id": pid, "stored": a, "now": b})
    if out:
        names = {str(r[0]): r[1] for r in (await session.execute(
            text("SELECT id, name FROM players WHERE id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": [d["player_id"] for d in out]})).all()}
        for d in out:
            d["name"] = names.get(d["player_id"], "?")
    return out


RECENT_ROUND_DAYS = 14


async def refresh_recent_rounds(session: AsyncSession, fs, days: int = RECENT_ROUND_DAYS) -> int:
    """Settle again any round scored within the last ``days`` days whose points no
    longer match the scorecards (a late or corrected scorecard). Squads keep the
    lineup they were settled with, and no free transfer is banked. Returns how many
    rounds were refreshed."""
    cutoff = date.today() - timedelta(days=days)
    rows = (await session.execute(
        text("SELECT id FROM fantasy_rounds WHERE fantasy_season_id = CAST(:fs AS UUID) "
             "AND status = 'scored' AND end_date >= :c ORDER BY round_number"),
        {"fs": str(fs.id), "c": cutoff},
    )).scalars().all()
    from app.models.db import FantasyRound
    n = 0
    for rid in rows:
        rnd = await session.get(FantasyRound, rid)
        if await round_drift(session, fs, rnd):
            await settle_round(session, fs, rnd)
            n += 1
    return n


async def unsettle_round(session: AsyncSession, fs, rnd) -> int:
    """Undo ``settle_round`` for a round that was settled by mistake. Returns the
    number of player scores removed (0 when the round wasn't scored).

    Only what settlement wrote is touched: a score an admin typed in by hand stays.
    Each squad's round row also carries
    what its manager did before the round locked (chip played, transfers made,
    points hit), so a row with any of that is kept and just has its scoring
    cleared, and a row with none of it is removed. The round goes to
    ``unsettled``, which the automatic settlers skip, until it is settled again.
    A round still inside its window goes back to ``upcoming`` instead, so it
    carries on as an in-progress round (provisional points, settled when it ends)."""
    if rnd.status != "scored":
        return 0
    p = {"rid": str(rnd.id), "fs": str(fs.id)}

    removed = (await session.execute(
        text("DELETE FROM fantasy_player_round_scores WHERE round_id = CAST(:rid AS UUID) "
             "AND breakdown->>'manual' IS NULL"), p,
    )).rowcount or 0
    await session.execute(
        text("""DELETE FROM fantasy_squad_round_scores
                WHERE round_id = CAST(:rid AS UUID)
                  AND chip_used IS NULL AND transfers_made = 0 AND transfer_hit = 0"""), p,
    )
    await session.execute(
        text("""UPDATE fantasy_squad_round_scores
                SET points = 0, raw_points = 0, captain_player_id = NULL,
                    dropped_player_id = NULL, lineup = '[]'::jsonb
                WHERE round_id = CAST(:rid AS UUID)"""), p,
    )
    await session.execute(
        text("""UPDATE fantasy_h2h_fixtures
                SET home_points = NULL, away_points = NULL, result = NULL
                WHERE round_id = CAST(:rid AS UUID)"""), p,
    )
    in_progress = bool(rnd.end_date and rnd.end_date >= date.today())
    new_status = "upcoming" if in_progress else ROUND_UNSETTLED
    await session.execute(
        text("""UPDATE fantasy_rounds SET status = :st, scored_at = NULL, updated_at = NOW()
                WHERE id = CAST(:rid AS UUID)"""),
        {**p, "st": new_status},
    )
    rnd.status, rnd.scored_at = new_status, None

    # Totals follow the rows that are left. Last-round points show the latest
    # round that is still scored.
    await session.execute(
        text("""
            UPDATE fantasy_pool_players pp SET
                total_points = COALESCE((
                    SELECT SUM(prs.total_points) FROM fantasy_player_round_scores prs
                    WHERE prs.fantasy_season_id = CAST(:fs AS UUID) AND prs.player_id = pp.player_id
                ), 0),
                last_round_points = COALESCE((
                    SELECT prs.total_points FROM fantasy_player_round_scores prs
                    WHERE prs.player_id = pp.player_id AND prs.round_id = (
                        SELECT r.id FROM fantasy_rounds r
                        WHERE r.fantasy_season_id = CAST(:fs AS UUID) AND r.status = 'scored'
                        ORDER BY r.round_number DESC LIMIT 1)
                ), 0),
                updated_at = NOW()
            WHERE pp.fantasy_season_id = CAST(:fs AS UUID)
        """), p,
    )
    await fantasy_squad.recompute_squad_totals(session, fs)

    # Take back the free transfer settlement banked. A squad with a wildcard or
    # free hit armed (a huge bank) is left alone.
    per = int((fs.rules or DEFAULT_RULES).get("free_transfers_per_round", 1))
    await session.execute(
        text("""UPDATE fantasy_squads SET free_transfers = GREATEST(free_transfers - :per, 0)
                WHERE fantasy_season_id = CAST(:fs AS UUID) AND free_transfers < 100"""),
        {"per": per, "fs": p["fs"]},
    )
    if in_progress:
        await refresh_live_round(session, fs, rnd)
    return removed


async def _refresh_pool_totals(session: AsyncSession, fs, rnd) -> None:
    """Recompute each pool player's season total and this-round points from the
    per-round scores (so re-settling a corrected round self-heals the totals)."""
    await session.execute(
        text("""
            UPDATE fantasy_pool_players pp SET
                total_points = COALESCE(t.total, 0),
                last_round_points = COALESCE(lr.pts, 0),
                updated_at = NOW()
            FROM (SELECT player_id, SUM(total_points) AS total
                  FROM fantasy_player_round_scores
                  WHERE fantasy_season_id = CAST(:fs AS UUID) GROUP BY player_id) t
            LEFT JOIN (SELECT player_id, total_points AS pts
                       FROM fantasy_player_round_scores
                       WHERE round_id = CAST(:rid AS UUID)) lr ON lr.player_id = t.player_id
            WHERE pp.fantasy_season_id = CAST(:fs AS UUID) AND pp.player_id = t.player_id
        """),
        {"fs": str(fs.id), "rid": str(rnd.id)},
    )


async def _mark_scored(session: AsyncSession, rnd, _count: int) -> None:
    await session.execute(
        text("UPDATE fantasy_rounds SET status = 'scored', scored_at = NOW(), updated_at = NOW() WHERE id = CAST(:rid AS UUID)"),
        {"rid": str(rnd.id)},
    )
    rnd.status = "scored"   # keep the loaded row in step, so a second settle in this session isn't "first"
