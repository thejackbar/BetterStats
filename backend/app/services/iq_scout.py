"""BetterIQ — scout ANY club, not just opponents in our own grades.

The live dossier (iq_opponent) discovers an opponent's teams by scanning the
grades OUR club plays in, which breaks the moment the target club sits outside
our competitions — a newly-relegated club's next opposition, a side from a
different association, or simply any club picked from the CA-wide search. The
public Grassroots endpoints are all keyed by the org GUID alone, so we can
enumerate ANY club's seasons/teams/stats the same way our own sync does:

* ``external_club_teams`` — the club's current teams (grades) from
  ``/fixturesladders/organisations/{org}/seasons`` + ``/teams``, used by
  ``iq_opponent._discover_opponent_teams`` as the fallback when the club fields
  no side in any grade we hold. The grade GUIDs feed the existing
  ``_scout_grade`` pipeline unchanged.
* **Player career (last 5 years)** — CA's season-aggregate statistics endpoints
  return every player at a club per season in a few light calls, so a 5-year
  career view (per-season matches/runs/avg/SR/wickets/econ/catches) is
  near-instant. Built per club, cached, sliced per player on read.
* **Player deep pass** — scorecard-level detail (dismissal patterns, batting
  position, conversion) across the same window. Aggregates can't carry these,
  so we locate the grades the player actually appeared in (per-grade aggregate
  calls), then scan only those grades' scorecards — roughly 60–100 cards, a
  minute or two on first build, instead of the thousands a whole-club scan
  would cost.

Everything lands in the existing ``opposition_dossiers`` JSON cache (namespaced
``career::…`` / ``pdeep::…`` keys, org-scoped to OUR club) — external club data
is never normalised into the player/stats tables, same data-rights posture as
the dossier.
"""
from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import async_session_maker
from app.services import grassroots_scores_client as gr
from app.services import playhq_client
from app.services.iq_opponent import (
    BUILD_STALE_AFTER,
    TTL,
    _BUILD_TASKS,
    _DISMISSAL_SHORT,
    _NOT_AN_INNINGS,
    _balls_to_overs,
    _find_opponent_team,
    _is_uuid,
    _load_row,
    _match_date,
    _norm,
    _overs_to_balls,
    _team_is_opponent,
    _team_rank,
    _team_roster,
    _upsert,
)
from app.services.sync import _caught_by_keeper, _innings_keeper_names

logger = logging.getLogger(__name__)

# Payload schema versions — bump on shape changes so stale caches rebuild.
CAREER_VERSION = 1
DEEP_VERSION = 1

CAREER_YEARS = 5
# A club year can span several CA season rows (summer comp, T20 comp, juniors…).
MAX_CAREER_SEASON_ROWS = 16
# Aggregate-stats calls in flight at once (the gr scorecard client has its own).
_AGG_SEMAPHORE = asyncio.Semaphore(4)

# Deep-pass bounds (CA-proxy politeness + first-build latency).
MAX_DEEP_SEASONS = 6            # season rows the player appears in, newest first
MAX_LOCATE_CALLS = 90           # per-grade aggregate calls spent finding their grades
MAX_DEEP_GRADE_SEASONS = 10     # grade-seasons actually scanned
MAX_DEEP_MATCHES_PER_GRADE = 16
MAX_DEEP_SCORECARDS = 100


def _season_year(season: dict) -> int | None:
    """Year of a CA season row — startDate first, name ("Summer 2010/11") as the
    fallback (mirrors the sync's Season.year derivation)."""
    sd = (season.get("startDate") or "")[:4]
    if sd.isdigit():
        return int(sd)
    m = re.search(r"(19|20)\d{2}", season.get("name") or "")
    return int(m.group(0)) if m else None


async def _dated_seasons(org_guid: str) -> list[tuple[int, str, str]]:
    """The club's CA season rows as (year, season_guid, name), undated rows dropped."""
    seasons = await playhq_client.get_seasons(org_guid)
    out = []
    for s in seasons:
        sid = (s.get("id") or "").strip()
        yr = _season_year(s)
        if sid and yr:
            out.append((yr, sid, s.get("name") or ""))
    return out


async def external_club_teams(org_guid: str) -> list[dict]:
    """A club's current teams (grades), discovered from THEIR org — no dependency
    on our own grades. Shape matches ``_discover_opponent_teams`` entries so the
    dossier pipeline consumes them unchanged. Uses the newest year that actually
    fields sides (falling back one year covers the pre-season window)."""
    dated = await _dated_seasons(org_guid)
    if not dated:
        return []
    years = sorted({y for y, _, _ in dated}, reverse=True)
    teams: list[dict] = []
    seen: set[str] = set()
    for y in years[:2]:
        for yr, sid, _name in dated:
            if yr != y:
                continue
            for t in await playhq_client.get_teams(org_guid, sid):
                team_name = t.get("name") or t.get("displayName")
                grade_objs = list(t.get("grades") or [])
                if t.get("grade"):
                    grade_objs.append(t["grade"])
                for gd in grade_objs:
                    gid = ((gd or {}).get("id") or "").strip()
                    if not gid or gid in seen:
                        continue
                    seen.add(gid)
                    gname = gd.get("name")
                    teams.append({
                        "grade_id": gid,
                        "grade_name": gname,
                        "team_name": team_name or gname or "",
                        "matches": None,
                    })
        if teams:
            break
    teams.sort(key=lambda d: (_team_rank(d["team_name"]), d["grade_name"] or ""))
    return teams


# ─── cache plumbing (shared by career + deep; reuses opposition_dossiers) ─────

def _career_key(org_guid: str) -> str:
    return f"career::{org_guid.lower()}"


def _deep_key(org_guid: str, player_id: str) -> str:
    return f"pdeep::{org_guid.lower()}::{player_id.lower()}"


async def _get_or_start(
    session: AsyncSession, our_org_id: str, cache_key: str, version: int,
    build, *, name: str | None = None, force: bool = False,
):
    """The dossier's build/poll contract for the scout caches: a fresh ready row
    returns the payload; otherwise mark building, launch the detached task and
    report ``{status:'building'}`` for the frontend to poll."""
    row = await _load_row(session, our_org_id, cache_key)
    now = datetime.now(timezone.utc)
    fresh = (
        row and row.status == "ready" and row.built_at and (now - row.built_at) < TTL
        and (row.payload or {}).get("schema_v") == version
    )
    if fresh and not force:
        return {"status": "ready", "cached": True, **(row.payload or {})}
    building = row and row.status == "building" and row.updated_at and (now - row.updated_at) < BUILD_STALE_AFTER
    if building and not force:
        return {"status": "building"}
    await _upsert(session, our_org_id, cache_key, opp_name=name, status="building", error=None)
    task = asyncio.create_task(_run_build(our_org_id, cache_key, build, name))
    _BUILD_TASKS.add(task)
    task.add_done_callback(_BUILD_TASKS.discard)
    return {"status": "building"}


async def _run_build(our_org_id: str, cache_key: str, build, name: str | None) -> None:
    async with async_session_maker() as session:
        try:
            payload = await build()
            await _upsert(
                session, our_org_id, cache_key,
                opp_name=(payload.get("org") or {}).get("name") or name,
                status="ready", payload=payload,
                built_at=datetime.now(timezone.utc), error=None,
            )
            logger.info(f"BetterIQ scout: built {cache_key} for org={our_org_id}")
        except Exception as e:  # never leave the row wedged at 'building'
            logger.exception(f"BetterIQ scout: build failed for org={our_org_id} key={cache_key}: {e}")
            try:
                await _upsert(session, our_org_id, cache_key, status="error", error=str(e)[:500])
            except Exception:
                pass


# ─── 5-year career from CA's season aggregates ────────────────────────────────

def _best_figures(s) -> tuple[int, int] | None:
    """Parse CA's "4-13" best-bowling string."""
    s = str(s or "")
    if "-" not in s:
        return None
    try:
        w, r = s.split("-", 1)
        return int(w), int(r)
    except ValueError:
        return None


def _rollup(rows: list[dict]) -> dict:
    """Fold per-season-row aggregate stats into one summary (a year, or a career).
    Counting stats sum; averages/rates are recomputed from the summed raw fields
    rather than averaged (matches how sync derives them)."""
    m = inns = no = runs = balls = f50 = f100 = ducks = 0
    hs = None
    hs_no = False
    w = bballs = bruns = maid = fiw = 0
    best: tuple[int, int] | None = None
    ct = ctwk = st = ro = 0
    for r in rows:
        bat = r.get("bat") or {}
        bowl = r.get("bowl") or {}
        fld = r.get("field") or {}
        m += bat.get("matches") or bowl.get("matches") or fld.get("matches") or 0
        inns += bat.get("battingInnings") or 0
        runs += bat.get("battingAggregate") or 0
        no += bat.get("battingNotOuts") or 0
        balls += bat.get("battingBallsFaced") or 0
        f50 += bat.get("batting50s") or 0
        f100 += bat.get("batting100s") or 0
        ducks += bat.get("batting0s") or 0
        h = bat.get("battingHighScore")
        if h is not None and (hs is None or h > hs):
            hs, hs_no = h, bool(bat.get("isBattingHSNotOut"))
        w += bowl.get("bowlingWickets") or 0
        bballs += bowl.get("bowlingBalls") or 0
        bruns += bowl.get("bowlingRuns") or 0
        maid += bowl.get("bowlingMaidens") or 0
        fiw += bowl.get("bowling5WIs") or 0
        bp = _best_figures(bowl.get("bowlingBestInnings"))
        if bp and (best is None or bp[0] > best[0] or (bp[0] == best[0] and bp[1] < best[1])):
            best = bp
        ct += fld.get("fieldingTotalCatches") or 0
        ctwk += fld.get("fieldingCatchesWK") or 0
        st += fld.get("fieldingStumpings") or 0
        ro += fld.get("fieldingRunOuts") or 0
    outs = max(inns - no, 0)
    return {
        "matches": m,
        "innings": inns,
        "runs": runs,
        "not_outs": no,
        "average": round(runs / outs, 2) if outs else None,
        "strike_rate": round(100 * runs / balls, 2) if balls else None,
        "high_score": (f"{hs}*" if hs_no else str(hs)) if hs is not None else None,
        "fifties": f50,
        "hundreds": f100,
        "ducks": ducks,
        "wickets": w,
        "overs": _balls_to_overs(bballs),
        "runs_conceded": bruns,
        "maidens": maid,
        "five_fors": fiw,
        "bowling_average": round(bruns / w, 2) if w else None,
        "economy": round(bruns / (bballs / 6), 2) if bballs else None,
        "best": f"{best[0]}/{best[1]}" if best else None,
        "catches": ct,
        "catches_wk": ctwk,
        "stumpings": st,
        "run_outs": ro,
    }


def _has_activity(t: dict) -> bool:
    return bool(t["matches"] or t["innings"] or t["runs"] or t["wickets"] or t["catches"])


async def _build_career(org_guid: str, club_name: str | None = None) -> dict:
    """One club's last-CAREER_YEARS player aggregates, every player, keyed for a
    per-player slice on read. ~3 light calls per season row, all public."""
    dated = await _dated_seasons(org_guid)
    built_at = datetime.now(timezone.utc).isoformat()
    if not dated:
        return {
            "org": {"id": org_guid, "name": club_name},
            "window": None, "players": [],
            "schema_v": CAREER_VERSION, "built_at": built_at,
        }
    cur = max(y for y, _, _ in dated)
    window = sorted(
        [d for d in dated if d[0] >= cur - (CAREER_YEARS - 1)], reverse=True
    )[:MAX_CAREER_SEASON_ROWS]

    async def fetch(kind: str, fn, sid: str):
        async with _AGG_SEMAPHORE:
            try:
                return kind, sid, await fn(org_guid, sid)
            except Exception as e:
                logger.warning(f"BetterIQ scout: {kind} stats failed for {org_guid}/{sid}: {e}")
                return kind, sid, []

    tasks = []
    year_of: dict[str, int] = {}
    for yr, sid, _name in window:
        year_of[sid] = yr
        tasks.append(fetch("bat", playhq_client.get_batting_stats, sid))
        tasks.append(fetch("bowl", playhq_client.get_bowling_stats, sid))
        tasks.append(fetch("field", playhq_client.get_fielding_stats, sid))
    results = await asyncio.gather(*tasks)

    # pid → {name, rows: {season_guid: {year, bat, bowl, field}}}
    acc: dict[str, dict] = {}
    for kind, sid, rows in results:
        for p in rows or []:
            pid = (p.get("id") or "").strip()
            if not pid:
                continue
            e = acc.setdefault(pid, {"name": p.get("name") or p.get("shortName") or "Unknown", "rows": {}})
            r = e["rows"].setdefault(sid, {"year": year_of[sid]})
            r[kind] = p.get("statistics") or {}

    players = []
    for pid, e in acc.items():
        by_year: dict[int, list[dict]] = {}
        for sid, r in e["rows"].items():
            by_year.setdefault(r["year"], []).append(r)
        seasons = []
        for yr in sorted(by_year, reverse=True):
            seasons.append({"year": yr, **_rollup(by_year[yr])})
        totals = _rollup(list(e["rows"].values()))
        if not _has_activity(totals):
            continue
        players.append({
            "player_id": pid,
            "name": e["name"],
            # Raw CA season ids the player appears in — the deep pass uses these
            # to locate their grades without rescanning the whole club.
            "season_refs": [
                {"id": sid, "year": r["year"]}
                for sid, r in sorted(e["rows"].items(), key=lambda kv: kv[1]["year"], reverse=True)
            ],
            "seasons": seasons,
            "totals": totals,
        })
    players.sort(key=lambda p: (p["totals"]["runs"] or 0, p["totals"]["wickets"] or 0), reverse=True)

    return {
        "org": {"id": org_guid, "name": club_name},
        "window": {"from_year": cur - (CAREER_YEARS - 1), "to_year": cur},
        "season_rows_scanned": len(window),
        "players": players,
        "schema_v": CAREER_VERSION,
        "built_at": built_at,
    }


async def get_player_career(
    session: AsyncSession, our_org_id: str, org_guid: str, player_id: str,
    *, club_name: str | None = None, force: bool = False,
) -> dict:
    """One player's last-5-years season-by-season aggregates. The whole club is
    built (and cached) once; this slices the one player out, so flicking through
    a squad costs nothing after the first build."""
    if not _is_uuid(org_guid):
        return {"status": "unavailable", "message": "No Cricket Australia organisation id for this club."}
    d = await _get_or_start(
        session, our_org_id, _career_key(org_guid), CAREER_VERSION,
        lambda: _build_career(org_guid, club_name), name=club_name, force=force,
    )
    if d.get("status") != "ready":
        return d
    pid = (player_id or "").lower()
    player = next((p for p in d.get("players") or [] if (p.get("player_id") or "").lower() == pid), None)
    return {
        "status": "ready",
        "org": d.get("org"),
        "window": d.get("window"),
        "built_at": d.get("built_at"),
        "player": player,
    }


async def get_club_players(
    session: AsyncSession, our_org_id: str, org_guid: str,
    *, club_name: str | None = None, force: bool = False,
) -> dict:
    """Every player at a club across the career window — a light list for the
    scout pages' search/selection. The dossier squad only covers players seen in
    the current-season scan, which silently hid anyone who hasn't played this
    season (the "found him in search, gone on the club page" bug); this list is
    the career blob's full roster, so a 5-year veteran is always selectable."""
    if not _is_uuid(org_guid):
        return {"status": "unavailable", "message": "No Cricket Australia organisation id for this club."}
    d = await _get_or_start(
        session, our_org_id, _career_key(org_guid), CAREER_VERSION,
        lambda: _build_career(org_guid, club_name), name=club_name, force=force,
    )
    if d.get("status") != "ready":
        return d
    players = []
    for p in d.get("players") or []:
        t = p.get("totals") or {}
        seasons = p.get("seasons") or []
        players.append({
            "player_id": p.get("player_id"),
            "name": p.get("name"),
            "matches": t.get("matches"),
            "runs": t.get("runs"),
            "average": t.get("average"),
            "wickets": t.get("wickets"),
            "catches": t.get("catches"),
            "last_year": seasons[0]["year"] if seasons else None,
        })
    return {
        "status": "ready",
        "org": d.get("org"),
        "window": d.get("window"),
        "built_at": d.get("built_at"),
        "players": players,
    }


# ─── per-player deep pass (scorecards across the window) ─────────────────────

_POSITION_BUCKETS = ["Opening", "First drop", "Middle order", "Lower order", "Tail"]


def _pos_bucket(pos) -> str | None:
    try:
        pos = int(pos)
    except (TypeError, ValueError):
        return None
    if pos <= 2:
        return "Opening"
    if pos == 3:
        return "First drop"
    if pos <= 6:
        return "Middle order"
    if pos <= 8:
        return "Lower order"
    return "Tail"


_BANDS = [("0-9", 0, 9), ("10-24", 10, 24), ("25-49", 25, 49), ("50-99", 50, 99), ("100+", 100, 10 ** 9)]

_DEEP_DISMISSAL_NOTE = {
    "bowled": "gets bowled more than most, so attack the stumps",
    "lbw": "falls lbw regularly, so bowl straight and appeal hard",
    "caught": "tends to hole out, so push catchers into the deep",
    "caught behind": "nicks off more often than most, so stack the cordon",
    "c&b": "has a habit of chipping it back to the bowler",
    "stumped": "can be drawn out of the crease",
    "run out": "is suspect between the wickets",
}


def _other_team_name(scorecard: dict, club_team: dict) -> str | None:
    for t in scorecard.get("teams") or []:
        if t is not club_team and t.get("id") != club_team.get("id"):
            return t.get("displayName") or t.get("name")
    return None


async def _locate_player_grades(org_guid: str, pid_l: str, season_refs: list[dict]) -> list[dict]:
    """Which grades the player appeared in, per season — one light per-grade
    aggregate call per (season, grade), bounded by MAX_LOCATE_CALLS."""
    located: list[dict] = []
    calls = 0
    for ref in season_refs[:MAX_DEEP_SEASONS]:
        sid, yr = ref["id"], ref["year"]
        try:
            teams = await playhq_client.get_teams(org_guid, sid)
        except Exception:
            continue
        grades: list[tuple[str, str | None]] = []
        seen: set[str] = set()
        for t in teams:
            grade_objs = list(t.get("grades") or [])
            if t.get("grade"):
                grade_objs.append(t["grade"])
            for gd in grade_objs:
                gid = ((gd or {}).get("id") or "").strip()
                if gid and gid not in seen:
                    seen.add(gid)
                    grades.append((gid, gd.get("name")))
        found_this_season = 0
        for gid, gname in grades:
            if calls >= MAX_LOCATE_CALLS or found_this_season >= 2:
                # Players rarely turn out in more than two grades a season, so
                # stop probing once two are found — keeps the locate budget from
                # being burned on a club fielding 15+ sides.
                break
            hit = False
            try:
                calls += 1
                rows = await playhq_client.get_batting_stats(org_guid, sid, grade_id=gid)
                hit = any((r.get("id") or "").lower() == pid_l for r in rows)
                if not hit:
                    calls += 1
                    rows = await playhq_client.get_bowling_stats(org_guid, sid, grade_id=gid)
                    hit = any((r.get("id") or "").lower() == pid_l for r in rows)
            except Exception:
                continue
            if hit:
                found_this_season += 1
                located.append({"season_id": sid, "year": yr, "grade_id": gid, "grade_name": gname})
    return located[:MAX_DEEP_GRADE_SEASONS]


async def _build_player_deep(
    our_org_id: str, org_guid: str, player_id: str,
    player_name: str | None = None, club_name: str | None = None,
) -> dict:
    # The career blob tells us which seasons the player appears in (and warms the
    # career cache as a side effect if it wasn't built yet).
    career = None
    async with async_session_maker() as session:
        row = await _load_row(session, our_org_id, _career_key(org_guid))
        if row and row.status == "ready" and (row.payload or {}).get("schema_v") == CAREER_VERSION:
            career = row.payload
    if career is None:
        career = await _build_career(org_guid, club_name)
        async with async_session_maker() as session:
            await _upsert(
                session, our_org_id, _career_key(org_guid),
                opp_name=club_name, status="ready", payload=career,
                built_at=datetime.now(timezone.utc), error=None,
            )
    return await _scan_player_deep(org_guid, player_id, career, player_name=player_name, club_name=club_name)


async def _scan_player_deep(
    org_guid: str, player_id: str, career: dict,
    *, player_name: str | None = None, club_name: str | None = None,
) -> dict:
    """The network half of the deep pass — locate the player's grades, scan those
    scorecards, assemble. Pure CA-proxy reads, no DB."""
    pid = (player_id or "").strip()
    pid_l = pid.lower()
    club_name = club_name or (career.get("org") or {}).get("name")
    entry = next((p for p in career.get("players") or [] if (p.get("player_id") or "").lower() == pid_l), None)
    player_name = (entry or {}).get("name") or player_name
    season_refs = (entry or {}).get("season_refs") or []

    located = await _locate_player_grades(org_guid, pid_l, season_refs) if season_refs else []

    # Scan the located grades' scorecards, newest first, keeping only this
    # player's rows. Caps keep the proxy load and first-build latency sane.
    bat_inns: list[dict] = []
    bowl_spells: list[dict] = []
    field_tot = {"catches": 0, "catches_wk": 0, "run_outs": 0, "stumpings": 0}
    scanned = 0
    played = 0
    dates: list[date] = []
    for loc in located:
        if scanned >= MAX_DEEP_SCORECARDS:
            break
        try:
            matches = await gr.get_grade_matches(loc["grade_id"])
        except Exception:
            continue
        club_matches = [
            m for m in matches
            if any(_team_is_opponent(t, opp_org_id=org_guid, opp_name=club_name) for t in (m.get("teams") or []))
        ]
        club_matches.sort(key=lambda m: ((m.get("matchSchedule") or [{}])[0].get("startDateTime") or ""), reverse=True)
        for m in club_matches[:MAX_DEEP_MATCHES_PER_GRADE]:
            if scanned >= MAX_DEEP_SCORECARDS:
                break
            mid = m.get("id")
            if not mid:
                continue
            sc = await gr.get_match_scorecard(mid)
            scanned += 1
            if not sc:
                continue
            team = _find_opponent_team(sc, our_org_id=None, opp_org_id=org_guid, opp_name=club_name)
            if not team:
                continue
            roster = _team_roster(team)
            if pid not in roster and pid_l not in {k.lower() for k in roster}:
                continue  # the player sat this one out
            played += 1
            when = _match_date(sc)
            if when:
                dates.append(when)
            when_s = when.isoformat() if when else None
            vs = _other_team_name(sc, team)
            for inn in sc.get("innings") or []:
                keeper_names = _innings_keeper_names(inn.get("fielding") or [])
                for r in inn.get("batting") or []:
                    if (r.get("participantId") or "").lower() != pid_l:
                        continue
                    dt_id = r.get("dismissalTypeId") or 0
                    if dt_id == 0 or _norm(r.get("dismissalType")) in _NOT_AN_INNINGS:
                        continue
                    not_out = dt_id == 1
                    dism = None
                    if not not_out:
                        dt_long = r.get("dismissalType") or ""
                        dism = _DISMISSAL_SHORT.get(dt_long, dt_long.lower()) if dt_long else "unknown"
                        if dism == "caught" and _caught_by_keeper(r.get("dismissalText") or "", keeper_names):
                            dism = "caught behind"
                    bat_inns.append({
                        "date": when_s, "year": loc["year"], "grade": loc["grade_name"], "vs": vs,
                        "runs": r.get("runsScored") or 0, "balls": r.get("ballsFaced") or 0,
                        "fours": r.get("foursScored") or 0, "sixes": r.get("sixesScored") or 0,
                        "not_out": not_out, "dismissal": dism, "position": r.get("batOrder"),
                    })
                for r in inn.get("bowling") or []:
                    if (r.get("participantId") or "").lower() != pid_l:
                        continue
                    bowl_spells.append({
                        "date": when_s, "year": loc["year"], "grade": loc["grade_name"], "vs": vs,
                        "balls": _overs_to_balls(r.get("oversBowled")),
                        "maidens": r.get("maidensBowled") or 0,
                        "runs": r.get("runsConceded") or 0,
                        "wickets": r.get("wicketsTaken") or 0,
                    })
                for r in inn.get("fielding") or []:
                    if (r.get("participantId") or "").lower() != pid_l:
                        continue
                    ct_wk = r.get("wicketKeeperCatches") or 0
                    ct = r.get("totalCatches")
                    if ct is None:
                        ct = (r.get("catches") or 0) + ct_wk
                    field_tot["catches"] += ct or 0
                    field_tot["catches_wk"] += ct_wk
                    field_tot["run_outs"] += r.get("runOuts") or 0
                    field_tot["stumpings"] += r.get("stumpings") or 0

    return _assemble_deep(
        org_guid, club_name, pid, player_name, located,
        bat_inns, bowl_spells, field_tot, scanned, played, dates,
    )


def _assemble_deep(
    org_guid, club_name, pid, player_name, located,
    bat_inns, bowl_spells, field_tot, scanned, played, dates,
) -> dict:
    bat_inns.sort(key=lambda i: i["date"] or "", reverse=True)
    bowl_spells.sort(key=lambda s: s["date"] or "", reverse=True)

    # ── batting ──
    inns = len(bat_inns)
    runs = sum(i["runs"] for i in bat_inns)
    balls = sum(i["balls"] for i in bat_inns)
    outs = sum(1 for i in bat_inns if not i["not_out"])
    hs_row = max(bat_inns, key=lambda i: i["runs"], default=None)
    boundary_runs = sum(4 * i["fours"] + 6 * i["sixes"] for i in bat_inns)

    dism_counter: Counter = Counter(i["dismissal"] for i in bat_inns if i["dismissal"])
    dismissals = [
        {"type": k, "count": v, "pct": round(100 * v / outs)} for k, v in dism_counter.most_common()
    ] if outs else []

    bands = [
        {"band": label, "count": sum(1 for i in bat_inns if lo <= i["runs"] <= hi)}
        for label, lo, hi in _BANDS
    ]

    reached25 = sum(1 for i in bat_inns if i["runs"] >= 25)
    reached50 = sum(1 for i in bat_inns if i["runs"] >= 50)
    reached100 = sum(1 for i in bat_inns if i["runs"] >= 100)
    conversion = {
        "start_pct": round(100 * reached25 / inns) if inns else None,
        "fifty_conv_pct": round(100 * reached50 / reached25) if reached25 else None,
        "hundred_conv_pct": round(100 * reached100 / reached50) if reached50 else None,
    }

    pos_acc: dict[str, dict] = {}
    for i in bat_inns:
        b = _pos_bucket(i["position"])
        if not b:
            continue
        e = pos_acc.setdefault(b, {"innings": 0, "runs": 0, "outs": 0})
        e["innings"] += 1
        e["runs"] += i["runs"]
        e["outs"] += 0 if i["not_out"] else 1
    by_position = [
        {"bucket": b, "innings": e["innings"], "runs": e["runs"],
         "average": round(e["runs"] / e["outs"], 2) if e["outs"] else None}
        for b in _POSITION_BUCKETS if (e := pos_acc.get(b))
    ]

    def _bat_year(items):
        yi = len(items)
        yr_runs = sum(i["runs"] for i in items)
        yr_outs = sum(1 for i in items if not i["not_out"])
        yr_balls = sum(i["balls"] for i in items)
        return {
            "innings": yi, "runs": yr_runs,
            "average": round(yr_runs / yr_outs, 2) if yr_outs else None,
            "strike_rate": round(100 * yr_runs / yr_balls, 2) if yr_balls else None,
        }

    bat_years: dict[int, list] = {}
    for i in bat_inns:
        bat_years.setdefault(i["year"], []).append(i)
    bat_by_year = [{"year": y, **_bat_year(items)} for y, items in sorted(bat_years.items(), reverse=True)]

    batting = {
        "innings_count": inns,
        "runs": runs,
        "average": round(runs / outs, 2) if outs else None,
        "strike_rate": round(100 * runs / balls, 2) if balls else None,
        "high_score": (f"{hs_row['runs']}{'*' if hs_row['not_out'] else ''}" if hs_row else None),
        "boundary_pct": round(100 * boundary_runs / runs, 1) if runs else None,
        "dismissals": dismissals,
        "bands": bands,
        "conversion": conversion,
        "by_position": by_position,
        "by_year": bat_by_year,
        "recent": bat_inns[:12],
    } if inns else None

    # ── bowling ──
    wkts = sum(s["wickets"] for s in bowl_spells)
    bruns = sum(s["runs"] for s in bowl_spells)
    bballs = sum(s["balls"] for s in bowl_spells)
    best = max(bowl_spells, key=lambda s: (s["wickets"], -s["runs"]), default=None)

    def _bowl_year(items):
        yw = sum(s["wickets"] for s in items)
        yr_ = sum(s["runs"] for s in items)
        yb = sum(s["balls"] for s in items)
        return {
            "spells": len(items), "wickets": yw, "overs": _balls_to_overs(yb),
            "average": round(yr_ / yw, 2) if yw else None,
            "economy": round(yr_ / (yb / 6), 2) if yb else None,
        }

    bowl_years: dict[int, list] = {}
    for s in bowl_spells:
        bowl_years.setdefault(s["year"], []).append(s)
    bowl_by_year = [{"year": y, **_bowl_year(items)} for y, items in sorted(bowl_years.items(), reverse=True)]

    bowling = {
        "spells": len(bowl_spells),
        "wickets": wkts,
        "overs": _balls_to_overs(bballs),
        "average": round(bruns / wkts, 2) if wkts else None,
        "economy": round(bruns / (bballs / 6), 2) if bballs else None,
        "strike_rate": round(bballs / wkts, 2) if wkts else None,
        "best": f"{best['wickets']}/{best['runs']}" if best and best["wickets"] else None,
        "by_year": bowl_by_year,
        "recent": [{**s, "overs": _balls_to_overs(s["balls"])} for s in bowl_spells[:12]],
    } if bowl_spells else None

    # ── rule-based read ──
    bits: list[str] = []
    if batting:
        avg_s = f"{batting['average']:.2f}" if batting["average"] is not None else "n/a"
        bits.append(f"{runs:,} runs @ {avg_s} across {inns} scanned innings.")
        if outs >= 3 and dismissals:
            top = dismissals[0]
            if top["count"] / outs >= 0.4 and top["type"] in _DEEP_DISMISSAL_NOTE:
                bits.append(f"He {_DEEP_DISMISSAL_NOTE[top['type']]}.")
        c = conversion
        if c["start_pct"] is not None and c["start_pct"] >= 40 and (c["fifty_conv_pct"] or 0) < 35 and reached25 >= 4:
            bits.append("Gets a start more often than not but rarely converts it, so stay patient once he's in.")
        if by_position:
            best_pos = max((p for p in by_position if p["innings"] >= 3 and p["average"] is not None),
                           key=lambda p: p["average"], default=None)
            if best_pos:
                bits.append(f"Most dangerous batting {best_pos['bucket'].lower()} ({best_pos['average']:.2f} from {best_pos['innings']} innings).")
    if bowling and wkts:
        bavg = f"{bowling['average']:.2f}" if bowling["average"] is not None else "n/a"
        bits.append(f"{wkts} wickets @ {bavg} with the ball in the same window.")

    notes = [
        f"Scanned {scanned} scorecards across {len(located)} of their team-seasons; he appeared in {played} of those games.",
        "Career numbers above come from CA's season totals; these per-innings reads come only from the scorecards we scanned, so they can undercount a long career.",
    ]

    return {
        "org": {"id": org_guid, "name": club_name},
        "player": {"player_id": pid, "name": player_name},
        "coverage": {
            "scorecards": scanned,
            "games_played": played,
            "grade_seasons": [
                {"year": loc["year"], "grade": loc["grade_name"]} for loc in located
            ],
            "span": {
                "from": min(dates).isoformat() if dates else None,
                "to": max(dates).isoformat() if dates else None,
            },
            "notes": notes,
        },
        "batting": batting,
        "bowling": bowling,
        "fielding": field_tot if any(field_tot.values()) else None,
        "summary": " ".join(bits) if bits else None,
        "schema_v": DEEP_VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }


async def get_or_start_player_deep(
    session: AsyncSession, our_org_id: str, org_guid: str, player_id: str,
    *, player_name: str | None = None, club_name: str | None = None, force: bool = False,
) -> dict:
    """Scorecard-level deep dive on one external player (dismissals, positions,
    conversion across the career window). Background build + poll, cached 7 days."""
    if not _is_uuid(org_guid) or not player_id:
        return {"status": "unavailable", "message": "No Cricket Australia ids to scout this player with."}
    return await _get_or_start(
        session, our_org_id, _deep_key(org_guid, player_id), DEEP_VERSION,
        lambda: _build_player_deep(our_org_id, org_guid, player_id, player_name, club_name),
        name=player_name, force=force,
    )
