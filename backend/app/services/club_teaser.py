"""Club teaser snapshots: a marketing-sized picture of a club that has not
registered, built from a handful of cheap Cricket Australia calls.

WHY IT IS NOT THE SYNC. The onboarding sync pulls every scorecard a club has
ever played (thousands of calls). A teaser dashboard needs one season's totals,
and CA already serves those pre-computed:

    seasons                      1 call
    batting / bowling / fielding 1-3 pages each, for ONE season
    teams                        1 call, gives the season's grades
    ladder per senior grade      ~5-10 calls, gives played / won / lost

That is ~15-30 calls a club against thousands. Nothing here writes an
``organisations`` / ``players`` / ``games`` row: an unclaimed club must not
appear on the public site, in the sync scheduler or in the duplicate checks.
When a club claims, the normal sync runs and the snapshot is left as history.

THREE DESIGN CALLS

* **Juniors are left out, and it is decided per grade, not per player.** The
  season aggregate has no grade on a row, so a club with junior grades has its
  stats fetched grade by grade for the SENIOR grades only. A club with nothing
  but junior grades is skipped (``junior_only``): a marketing page must not
  name children, and CA redacts many of their names anyway.
* **A snapshot's version moves only when its CONTENT does** (``data_hash``).
  The rendered email image lives on the HDD and costs a Chromium render, so a
  weekly re-pull that found nothing new must not invalidate it.
* **When to look again is decided when the pull is WRITTEN** (``next_pull_at``),
  from what the pull found, so "who is due" is one indexed comparison rather
  than a per-club calculation over the whole directory.

The preview token is generated once and never rotated by a refresh: a link that
has already gone out in an email has to keep working.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import secrets
import time
import zlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 2: draws removed (played - won - lost is abandoned/tied/no-result, not draws),
#    a club is built on the last season with a real number of matches, ladder
#    rows carry a short grade name, and the club carries CA's own org id.
SCHEMA_VERSION = 2
MIN_SEASON_MATCHES = 6

# Seasons probed newest-first for one that actually has stats. In September the
# newest season usually exists with teams and no scorecards yet.
MAX_SEASON_PROBES = 4
MAX_LADDER_GRADES = 12
TOP_N = 5

# Re-pull cadence, in days. In play = the snapshot's season started within the
# last IN_PLAY_DAYS; a newer season that has been listed but has no stats yet
# is checked on the in-play cadence too, so a new season is noticed within a week.
IN_PLAY_DAYS = 300
REFRESH_IN_PLAY = 7
REFRESH_OFF_SEASON = 45
REFRESH_EMPTY = 14
REFRESH_JUNIOR_ONLY = 90
ERROR_BACKOFF = (1, 3, 7, 14, 30)

_REDACTED = re.compile(r"\*{2,}")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


# ---------------------------------------------------------------------------
# The live API, behind one small interface so the builder can be driven by
# fixtures. Every call is counted: the whole point of this module is a call
# budget, so the figure is stored beside each snapshot.
# ---------------------------------------------------------------------------
class LiveAPI:
    """``pacer`` is shared by every club a crawl is working on, so the crawl has
    ONE rate however many clubs run at once. Each club still gets its own
    instance (and its own ``calls`` counter), which is what the work report and
    ``club_teaser_snapshots.api_calls`` read.

    A "call" here is one method below. A stats call can page (100 rows a page),
    so the requests on the wire can exceed the calls paced by a little; the
    ``calls`` figures quoted in this module's notes count the same way."""

    _pacer = None  # class default: an instance built without __init__ is simply unpaced

    def __init__(self, concurrency: int = 4, pacer=None):
        from app.services import grassroots_scores_client as gr, playhq_client as ph
        self._ph, self._gr = ph, gr
        self._sem = asyncio.Semaphore(concurrency)
        self._pacer = pacer
        self.calls = 0

    async def _run(self, coro_fn, *a, **kw):
        async with self._sem:
            if self._pacer is not None:
                await self._pacer.wait()
            self.calls += 1
            return await coro_fn(*a, **kw)

    async def resolve_org(self, club: dict, directory_guid: str) -> Optional[str]:
        """The Cricket Australia ``organisationGuid`` for a directory club.

        ``marketing_clubs.grassroots_guid`` holds PlayHQ's own search guid (the
        ``playHQId`` namespace), and the fixturesladders / participants APIs
        answer 204 for it: the first live sample read 20 of 20 clubs as empty
        for exactly that reason. The name search returns both ids side by side,
        so the club is found by its own name and confirmed on the id the
        directory already holds; a name alone is never trusted."""
        want = (directory_guid or "").lower()
        for o in await self._run(self._ph.search_organisations, club.get("name") or ""):
            ca = o.get("organisationGuid") or o.get("id")
            if ca and want in {str(o.get("playHQId") or "").lower(), str(ca).lower()}:
                return str(ca)
        return None

    async def seasons(self, org: str) -> list:
        return await self._run(self._ph.get_seasons, org)

    async def teams(self, org: str, season: str) -> list:
        return await self._run(self._ph.get_teams, org, season)

    async def batting(self, org: str, season: str, grade: Optional[str] = None) -> list:
        return await self._run(self._ph.get_batting_stats, org, season, grade)

    async def bowling(self, org: str, season: str, grade: Optional[str] = None) -> list:
        return await self._run(self._ph.get_bowling_stats, org, season, grade)

    async def fielding(self, org: str, season: str, grade: Optional[str] = None) -> list:
        return await self._run(self._ph.get_fielding_stats, org, season, grade)

    async def ladder(self, grade: str) -> Optional[dict]:
        return await self._run(self._gr.get_grade_ladder, grade)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def _num(v, default=0):
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _int(v) -> int:
    return int(_num(v))


def season_start(s: dict) -> Optional[date]:
    raw = (s or {}).get("startDate") or ""
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def season_year(s: dict) -> Optional[int]:
    d = season_start(s)
    if d:
        return d.year
    m = re.search(r"(19|20)\d{2}", (s or {}).get("name") or "")
    return int(m.group(0)) if m else None


def order_seasons(seasons: list) -> list:
    """Newest first. A season with no readable date sorts by its name's year,
    then last, rather than being dropped."""
    def key(s):
        d = season_start(s)
        return (d.toordinal() if d else (season_year(s) or 0) * 366, s.get("name") or "")
    return sorted([s for s in seasons if isinstance(s, dict) and s.get("id")], key=key, reverse=True)


def is_redacted(name) -> bool:
    n = (name or "").strip()
    return not n or bool(_REDACTED.search(n))


def display_name(name: str) -> str:
    """'Smith, John' or 'John Smith' -> 'J. Smith'. A single token is kept."""
    n = (name or "").strip()
    if "," in n:
        last, _, first = n.partition(",")
        n = f"{first.strip()} {last.strip()}".strip()
    parts = n.split()
    if len(parts) < 2:
        return n
    return f"{parts[0][0].upper()}. {' '.join(parts[1:])}"


def is_junior_grade(name: str) -> bool:
    from app.services.grade_labels import suggest_categories
    return "junior" in suggest_categories(name)


def grades_from_teams(teams: list) -> list[dict]:
    """Distinct grades a club fielded a team in, in first-seen order. A team
    carries its grade under ``grade`` and/or ``grades`` (the sync reads both)."""
    seen: dict[str, dict] = {}
    for t in teams or []:
        objs = list((t or {}).get("grades") or [])
        if (t or {}).get("grade"):
            objs.append(t["grade"])
        for g in objs:
            gid = ((g or {}).get("id") or "").strip()
            if gid and gid not in seen:
                seen[gid] = {"id": gid, "name": (g or {}).get("name") or "Grade"}
    return list(seen.values())


def _stat(row: dict) -> dict:
    return (row or {}).get("statistics") or {}


def merge_rows(lists: list[list]) -> list[dict]:
    """Merge one stat feed fetched grade by grade back into one row per player.
    Counts add; a best figure is kept as the best; the row keeps the first
    name seen. Averages are recomputed by the caller from the summed counts."""
    out: dict[str, dict] = {}
    for rows in lists:
        for r in rows or []:
            pid = r.get("id")
            if not pid:
                continue
            cur = out.get(pid)
            if cur is None:
                out[pid] = {"id": pid, "name": r.get("name") or r.get("shortName"),
                            "statistics": dict(_stat(r))}
                continue
            a, b = cur["statistics"], _stat(r)
            for k, v in b.items():
                if k in ("battingHighScore",):
                    if _num(v, -1) > _num(a.get(k), -1):
                        a[k] = v
                        a["isBattingHSNotOut"] = b.get("isBattingHSNotOut")
                elif k == "bowlingBestInnings":
                    if _better_bowling(v, a.get(k)):
                        a[k] = v
                elif k in ("isBattingHSNotOut",):
                    continue
                elif isinstance(v, (int, float)) and not isinstance(v, bool):
                    a[k] = _num(a.get(k)) + v
                else:
                    a.setdefault(k, v)
    return list(out.values())


def _bowling_key(fig) -> Optional[tuple]:
    m = re.match(r"^\s*(\d+)\s*[-/]\s*(\d+)\s*$", str(fig or ""))
    return (-int(m.group(1)), int(m.group(2))) if m else None


def _better_bowling(new, old) -> bool:
    kn, ko = _bowling_key(new), _bowling_key(old)
    if kn is None:
        return False
    return ko is None or kn < ko


def top_batting(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        s = _stat(r)
        runs, inns, no = _int(s.get("battingAggregate")), _int(s.get("battingInnings")), _int(s.get("battingNotOuts"))
        if runs <= 0 or is_redacted(r.get("name")):
            continue
        dismissals = inns - no
        avg = round(runs / dismissals, 2) if dismissals > 0 else None
        out.append({
            "name": display_name(r.get("name")), "runs": runs, "innings": inns,
            "average": avg, "high_score": s.get("battingHighScore"),
            "hs_not_out": bool(s.get("isBattingHSNotOut")),
            "fifties": _int(s.get("batting50s")), "hundreds": _int(s.get("batting100s")),
        })
    out.sort(key=lambda p: (-p["runs"], p["name"]))
    return out[:TOP_N]


def top_bowling(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        s = _stat(r)
        wk, runs, balls = _int(s.get("bowlingWickets")), _int(s.get("bowlingRuns")), _int(s.get("bowlingBalls"))
        if wk <= 0 or is_redacted(r.get("name")):
            continue
        out.append({
            "name": display_name(r.get("name")), "wickets": wk,
            "best": s.get("bowlingBestInnings") or None,
            "average": round(runs / wk, 2),
            "economy": round(runs / (balls / 6), 2) if balls > 0 else None,
        })
    out.sort(key=lambda p: (-p["wickets"], p["average"], p["name"]))
    return out[:TOP_N]


def top_fielding(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        s = _stat(r)
        catches = _int(s.get("fieldingTotalCatches") or s.get("fieldingCatches"))
        ro, st = _int(s.get("fieldingRunOuts")), _int(s.get("fieldingStumpings"))
        if catches + ro + st <= 0 or is_redacted(r.get("name")):
            continue
        out.append({"name": display_name(r.get("name")), "catches": catches,
                    "run_outs": ro, "stumpings": st})
    out.sort(key=lambda p: (-(p["catches"] + p["run_outs"] + p["stumpings"]), p["name"]))
    return out[:TOP_N]


def season_records(bat_rows: list[dict], bowl_rows: list[dict]) -> list[dict]:
    recs = []
    best_hs = None
    for r in bat_rows:
        s = _stat(r)
        hs = _num(s.get("battingHighScore"), -1)
        if hs > 0 and not is_redacted(r.get("name")) and (best_hs is None or hs > best_hs[0]):
            best_hs = (hs, r, s)
    if best_hs:
        _, r, s = best_hs
        recs.append({"label": "Most Individual Runs",
                     "value": f"{int(best_hs[0])}{'*' if s.get('isBattingHSNotOut') else ''}",
                     "player": display_name(r.get("name"))})
    best_bb = None
    for r in bowl_rows:
        k = _bowling_key(_stat(r).get("bowlingBestInnings"))
        if k and not is_redacted(r.get("name")) and (best_bb is None or k < best_bb[0]):
            best_bb = (k, r)
    if best_bb:
        recs.append({"label": "Best Bowling Figures", "value": _stat(best_bb[1]).get("bowlingBestInnings"),
                     "player": display_name(best_bb[1].get("name"))})
    return recs


def our_ladder_row(raw_ladder, org_guid: str) -> Optional[dict]:
    """Our club's row in a grade ladder, matched on the OWNING ORGANISATION id,
    which is exact where a team name is not. Returns None when there is no
    ladder or the club is not on it."""
    from app.services.iq import _ladder_rows
    rows, _ = _ladder_rows(raw_ladder)
    want = (org_guid or "").lower()
    for r in rows:
        if str((r.get("org") or {}).get("id") or "").lower() == want:
            return {"rank": r.get("rank"), "teams": len(rows), "played": _int(r.get("played")),
                    "won": _int(r.get("won")), "lost": _int(r.get("lost")),
                    "points": r.get("points")}
    return None


def ladder_totals(entries: list[dict]) -> dict:
    played = sum(e["played"] for e in entries)
    won = sum(e["won"] for e in entries)
    lost = sum(e["lost"] for e in entries)
    # No "draws": played minus won minus lost is also abandoned, tied and
    # no-result games (Flemington's 10 "drawn" were mostly washouts), and a
    # piece of marketing must not state a figure the data cannot back.
    return {"matches": played, "wins": won, "losses": lost,
            "win_rate": round(100 * won / played) if played else None}


def content_hash(snapshot: dict) -> str:
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def next_pull_delay(status: str, *, attempts: int = 0, guid: str = "",
                    season_start_: Optional[date] = None, season_pending: bool = False,
                    today: Optional[date] = None) -> timedelta:
    """How long until this club is looked at again, decided from what the pull
    just found. A small stable per-club jitter (up to +20%) stops every club
    seeded on one night from coming due on the same night for ever."""
    today = today or datetime.now(timezone.utc).date()
    if status == "error":
        days = ERROR_BACKOFF[min(max(attempts, 1), len(ERROR_BACKOFF)) - 1]
    elif status == "empty":
        days = REFRESH_EMPTY
    elif status == "junior_only":
        days = REFRESH_JUNIOR_ONLY
    else:
        in_play = bool(season_start_) and (today - season_start_).days <= IN_PLAY_DAYS
        days = REFRESH_IN_PLAY if (in_play or season_pending) else REFRESH_OFF_SEASON
    jitter = (zlib.crc32((guid or "").encode()) % 1000) / 1000 * 0.2
    return timedelta(days=days * (1 + jitter))


# ---------------------------------------------------------------------------
# The pull
# ---------------------------------------------------------------------------
async def _stats_for(api, org: str, season: str, grades: Optional[list[str]]):
    """(batting, bowling, fielding) rows for a season. ``grades`` None = the
    whole club in one call each; a list = those grades only, merged."""
    if grades is None:
        return await asyncio.gather(api.batting(org, season), api.bowling(org, season),
                                    api.fielding(org, season))
    out = []
    for kind in ("batting", "bowling", "fielding"):
        got = await asyncio.gather(*[getattr(api, kind)(org, season, g) for g in grades])
        out.append(merge_rows(list(got)))
    return tuple(out)


_DIVISIONISH = re.compile(r"\d|grade|div|reserve|colts|open|social|women|men|u\d", re.I)


def short_grade(name: str, limit: int = 40) -> str:
    """A grade name a card can hold. "O60 Div 1 - Geoff Dymock Shield" becomes
    "O60 Div 1" (the part before the dash names the division); a name whose
    leading part says nothing ("North East - Georgie McElligott Shield
    Women's Social T20") is kept whole and clipped."""
    name = re.sub(r"\s+", " ", (name or "").strip())
    head, sep, _ = name.partition(" - ")
    if sep and head and _DIVISIONISH.search(head):
        name = head.strip()
    return name if len(name) <= limit else name[: limit - 1].rstrip() + "…"


async def _season_ladders(api, org: str, season_id: str, grades: list[dict]) -> list[dict]:
    got = await asyncio.gather(*[api.ladder(g["id"]) for g in grades[:MAX_LADDER_GRADES]])
    out = []
    for g, raw in zip(grades, got):
        row = our_ladder_row(raw, org)
        if row:
            out.append({"grade": g["name"], "grade_short": short_grade(g["name"]), **row})
    return out


async def _build_season(api, org_guid: str, season: dict) -> dict:
    """Everything one season contributes: its grades, the season's stats and
    our ladder rows, or ``kind='junior_only'`` when every grade is junior."""
    teams = await api.teams(org_guid, season["id"])
    grades = grades_from_teams(teams)
    junior = [g for g in grades if is_junior_grade(g["name"])]
    senior = [g for g in grades if g not in junior]
    if junior and not senior:
        return {"kind": "junior_only"}
    bat, bowl, field = await _stats_for(api, org_guid, season["id"],
                                        [g["id"] for g in senior] if junior else None)
    ladders = await _season_ladders(api, org_guid, season["id"], senior or grades)
    return {"kind": "ok", "grades": grades, "bat": bat, "bowl": bowl, "field": field,
            "ladders": ladders, "totals": ladder_totals(ladders)}


async def pull_club(api, org_guid: str, club: Optional[dict] = None, *,
                    today: Optional[date] = None) -> dict:
    """Pull and build one club's snapshot. Never raises: a failure is a result
    with ``status='error'`` so the caller records it and backs off.

    Returns ``{status, snapshot, season_year, season_start, season_pending,
    calls, error}`` where status is ok | empty | junior_only | error.
    """
    club = club or {}
    result: dict[str, Any] = {"status": "error", "snapshot": None, "season_year": None,
                              "season_start": None, "season_pending": False, "error": None}
    try:
        # A live API maps the directory's guid onto the one CA answers to. A
        # club CA's search cannot place is reported as empty (re-looked-at on
        # the empty cadence), never guessed by name.
        resolve = getattr(api, "resolve_org", None)
        if resolve:
            org_guid = await resolve(club, org_guid)
            if not org_guid:
                result["status"] = "empty"
                return result
        seasons = order_seasons(await api.seasons(org_guid))
        if not seasons:
            result["status"] = "empty"
            return result

        chosen, chosen_idx = None, None
        for i, s in enumerate(seasons[:MAX_SEASON_PROBES]):
            if await api.batting(org_guid, s["id"]):
                chosen, chosen_idx = s, i
                break
        if chosen is None:
            result["status"] = "empty"
            return result

        built = await _build_season(api, org_guid, chosen)
        # A season that has only just started has a batting row or two and one
        # ladder game, which reads as "1 match played" in a piece about the
        # club. Use the next older season with stats instead when this one is
        # that thin; the club then reads as season_pending, so the newer one is
        # noticed within a week. Only ONE older season is tried, and only when
        # it really is fuller.
        if built["kind"] == "ok" and built["totals"]["matches"] < MIN_SEASON_MATCHES:
            for j in range(chosen_idx + 1, min(len(seasons), MAX_SEASON_PROBES)):
                older = seasons[j]
                if await api.batting(org_guid, older["id"]):
                    b2 = await _build_season(api, org_guid, older)
                    if b2["kind"] == "ok" and b2["totals"]["matches"] >= MIN_SEASON_MATCHES:
                        chosen, chosen_idx, built = older, j, b2
                    break
        if built["kind"] == "junior_only":
            result["status"] = "junior_only"
            result["season_year"] = season_year(chosen)
            result["season_start"] = season_start(chosen)
            return result
        grades, bat, bowl, field = built["grades"], built["bat"], built["bowl"], built["field"]
        ladders, totals = built["ladders"], built["totals"]

        prev = None
        for s in seasons[chosen_idx + 1: chosen_idx + 3]:
            p_grades = [g for g in grades_from_teams(await api.teams(org_guid, s["id"]))
                        if not is_junior_grade(g["name"])]
            p_ladders = await _season_ladders(api, org_guid, s["id"], p_grades) if p_grades else []
            if p_ladders:
                prev = {"season": s.get("name"), **ladder_totals(p_ladders)}
                break
        if prev and totals["matches"] and prev["matches"]:
            totals["matches_vs_prev_pct"] = round(100 * (totals["matches"] - prev["matches"]) / prev["matches"])
        totals["prev"] = prev

        starts = [d for d in (season_start(s) for s in seasons) if d]
        snapshot = {
            "schema": SCHEMA_VERSION,
            "club": {**{k: club.get(k) for k in ("name", "short_name", "suburb", "state",
                                                 "association", "logo_url")},
                     # CA's own organisation id (the one the trial wizard's club
                     # search returns), so a claim can open on the right club.
                     # The directory's guid is a different namespace.
                     "ca_org_id": org_guid},
            "season": {"id": chosen["id"], "name": chosen.get("name"),
                       "year": season_year(chosen),
                       "start": season_start(chosen).isoformat() if season_start(chosen) else None},
            "history": {"seasons_listed": len(seasons),
                        "first_year": min(starts).year if starts else None},
            "totals": totals,
            "ladders": ladders,
            "batting": top_batting(bat),
            "bowling": top_bowling(bowl),
            "fielding": top_fielding(field),
            "records": season_records(bat, bowl),
        }
        result.update(status="ok", snapshot=snapshot, season_year=season_year(chosen),
                      season_start=season_start(chosen), season_pending=chosen_idx > 0)
        return result
    except Exception as exc:  # noqa: BLE001 - a pull must never take a batch down
        logger.warning("teaser pull failed for %s: %s", org_guid, exc)
        result["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return result
    finally:
        result["calls"] = getattr(api, "calls", 0)


# ---------------------------------------------------------------------------
# Persistence and scheduling
# ---------------------------------------------------------------------------
_CLUB_COLS = """mc.id, mc.grassroots_guid AS guid, mc.name, mc.short_name, mc.suburb, mc.state,
                mc.association_name AS association, mc.logo_url"""

# Not a customer, not excluded, not asked to be left alone, real CA guid. A
# club already trialling through the sales pipeline has done a trial, so it is
# left out unless asked for.
_TARGET_WHERE = """mc.kind = 'club' AND NOT mc.excluded AND NOT mc.not_interested
                   AND mc.existing_org_id IS NULL
                   AND mc.grassroots_guid ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'"""


# The Club Directory's own type filters, applied as the default for who gets a
# snapshot: juniors, carnivals, schools, rep teams and governing-body orgs are
# not who the campaign is for. Same keys and same definitions as the Directory
# (club_directory.filter_mode_conditions), so "Juniors" means one thing on both.
# Each value is 'exclude' or 'include'; a key left out is not filtered on.
DEFAULT_TYPE_MODES = {"junior": "exclude", "carnival": "exclude", "school": "exclude",
                      "rep": "exclude", "cricket_au": "exclude"}


def clean_type_modes(modes: Optional[dict]) -> dict:
    """Only known directory filter keys with a valid mode survive."""
    from app.services.club_directory import FILTER_MODE_KEYS
    out = {}
    for k, v in (modes or {}).items():
        k, v = str(k).strip().lower(), str(v or "").strip().lower()
        if k in FILTER_MODE_KEYS and v in ("include", "exclude"):
            out[k] = v
    return out


async def type_filtered_ids(session: AsyncSession, modes: Optional[dict]) -> Optional[list[str]]:
    """Ids of the directory clubs that pass the type filters, or None when no
    filter is on. Resolved through the Directory's own conditions and bound as
    an array (about 7,000 ids at most), never pasted into the SQL."""
    from sqlalchemy import select, func, true, false
    from app.models.db import MarketingClub
    from app.services.club_directory import _filter_conditions
    # A NULL test result (a club with no generic email has nothing for the
    # Cricket Australia domain test to read) must count as "does not match":
    # kept by an exclude, dropped by an include. Left as NULL it would drop the
    # club from BOTH, which for an exclude quietly removes every club with a
    # blank field from the campaign.
    conds = []
    for key, mode in clean_type_modes(modes).items():
        exclude_cond, include_cond = _filter_conditions(key)
        conds.append(func.coalesce(exclude_cond, true()) if mode == "exclude"
                     else func.coalesce(include_cond, false()))
    if not conds:
        return None
    rows = (await session.execute(select(MarketingClub.id).where(*conds))).scalars().all()
    return [str(r) for r in rows]


async def due_clubs(session: AsyncSession, limit: int, *, now: Optional[datetime] = None,
                    include_trialists: bool = False, club_id: Optional[str] = None,
                    type_modes: Optional[dict] = None) -> list[dict]:
    """Clubs whose snapshot is missing or due, never-pulled first, then clubs
    with an emailable contact (the ones a campaign will actually reach), then
    the longest overdue. ``type_modes`` is the Directory type filter."""
    now = now or datetime.now(timezone.utc)
    trial = "" if include_trialists else "AND jsonb_array_length(COALESCE(mc.trial_modules, '[]'::jsonb)) = 0"
    only = "AND mc.id = CAST(:club AS uuid)" if club_id else ""
    allowed = await type_filtered_ids(session, type_modes)
    if allowed is not None:
        only += " AND mc.id = ANY(CAST(:allowed AS uuid[]))"
    rows = (await session.execute(text(f"""
        SELECT {_CLUB_COLS}
        FROM marketing_clubs mc
        LEFT JOIN club_teaser_snapshots t ON t.marketing_club_id = mc.id
        WHERE {_TARGET_WHERE} {trial} {only}
          AND (t.id IS NULL OR t.next_pull_at IS NULL OR t.next_pull_at <= :now
               OR (t.status = 'ok' AND COALESCE((t.snapshot->>'schema')::int, 0) < :schema))
        ORDER BY (t.id IS NULL) DESC,
                 EXISTS (SELECT 1 FROM marketing_club_contacts c
                          WHERE c.marketing_club_id = mc.id AND c.subscribed
                            AND COALESCE(c.email, '') <> '') DESC,
                 t.next_pull_at ASC NULLS FIRST
        LIMIT :limit
    """), {"now": now, "limit": limit, "schema": SCHEMA_VERSION, **({"club": club_id} if club_id else {}),
           **({"allowed": allowed} if allowed is not None else {})})).mappings().all()
    return [dict(r) for r in rows]


def crawl_estimate(due: int, avg_calls: float, rate: float, start_hour: int, end_hour: int) -> Optional[dict]:
    """How long the clubs still due take at ``rate`` calls a second, in hours
    of crawling and in days of the daily window. None when there is nothing to
    say: crawl off, nothing due, or no pulled club yet to read a calls-a-club
    figure off (a guess there would be quoted back at us)."""
    if rate <= 0 or due <= 0 or avg_calls <= 0:
        return None
    window = max(end_hour - start_hour, 0)
    if window <= 0:
        return None
    calls = due * avg_calls
    hours = calls / rate / 3600.0
    return {"calls": round(calls), "hours": round(hours, 1),
            "window_hours": window, "days": round(hours / window, 1),
            "rate_to_finish_in_one_window": round(calls / (window * 3600.0), 2)}


async def teaser_progress(session: AsyncSession, *, now: Optional[datetime] = None,
                          type_modes: Optional[dict] = None) -> dict:
    """What the crawl has done and what is left, for the Club Directory panel.
    ``due`` is the same test ``due_clubs`` applies (asserted equal by the
    suite), so the number on screen is the number the worker will work through.
    One aggregate over the target set, plus the last hour's calls, which is the
    rate actually being achieved rather than the one that was asked for."""
    now = now or datetime.now(timezone.utc)
    allowed = await type_filtered_ids(session, type_modes)
    only = " AND mc.id = ANY(CAST(:allowed AS uuid[]))" if allowed is not None else ""
    params: dict = {"now": now, "hour_ago": now - timedelta(hours=1), "schema": SCHEMA_VERSION}
    if allowed is not None:
        params["allowed"] = allowed
    row = (await session.execute(text(f"""
        SELECT COUNT(*) AS targets,
               COUNT(t.id) AS with_snapshot,
               COUNT(*) FILTER (WHERE t.id IS NULL) AS never_pulled,
               COUNT(*) FILTER (WHERE t.id IS NULL OR t.next_pull_at IS NULL
                                   OR t.next_pull_at <= :now
                                   OR (t.status = 'ok' AND COALESCE((t.snapshot->>'schema')::int, 0) < :schema)) AS due,
               COUNT(*) FILTER (WHERE t.status = 'ok') AS ok,
               COUNT(*) FILTER (WHERE t.status = 'empty') AS empty,
               COUNT(*) FILTER (WHERE t.status = 'junior_only') AS junior_only,
               COUNT(*) FILTER (WHERE t.status = 'error') AS error,
               AVG(t.api_calls) FILTER (WHERE t.status IN ('ok', 'empty', 'junior_only')
                                          AND t.api_calls > 0) AS avg_calls,
               MAX(t.pulled_at) AS last_pulled_at,
               COUNT(*) FILTER (WHERE t.pulled_at > :hour_ago) AS clubs_last_hour,
               COALESCE(SUM(t.api_calls) FILTER (WHERE t.pulled_at > :hour_ago), 0) AS calls_last_hour
        FROM marketing_clubs mc
        LEFT JOIN club_teaser_snapshots t ON t.marketing_club_id = mc.id
        WHERE {_TARGET_WHERE} AND jsonb_array_length(COALESCE(mc.trial_modules, '[]'::jsonb)) = 0
              {only}
    """), params)).mappings().one()
    out = {k: int(row[k] or 0) for k in ("targets", "with_snapshot", "never_pulled", "due", "ok",
                                         "empty", "junior_only", "error", "clubs_last_hour",
                                         "calls_last_hour")}
    out["avg_calls"] = round(float(row["avg_calls"] or 0), 1)
    out["last_pulled_at"] = row["last_pulled_at"].isoformat() if row["last_pulled_at"] else None
    return out


# ---------------------------------------------------------------------------
# What a page or an image leads with
# ---------------------------------------------------------------------------
# Derived on read, never stored: the rules below can change tomorrow and every
# existing snapshot then reads the new way with no re-pull. The snapshot stays
# plain data.
#
# The lead is an INDIVIDUAL fact (a batter's runs, a bowler's wickets) because
# that is always something to be proud of, whatever the club's ladder looks
# like: a prospect at the foot of the ladder is not shown the foot of the
# ladder as the hook. The season record and the ladder are shown only where
# they flatter (a win rate near half or better; a grade in the top half of its
# ladder), so nothing on the page reads as a slight.
FLATTERING_WIN_RATE = 45
HERO_RUNS_PER_POINT = 15      # 15 runs weighs the same as 1 wicket when picking the lead
MAX_LADDERS_SHOWN = 4


def ordinal(n) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "-"
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def _hero(snap: dict) -> Optional[dict]:
    bat, bowl = snap.get("batting") or [], snap.get("bowling") or []
    b = bat[0] if bat else None
    w = bowl[0] if bowl else None
    if not b and not w:
        return None
    bat_score = (b["runs"] / HERO_RUNS_PER_POINT) if b else -1
    bowl_score = w["wickets"] if w else -1
    if b and bat_score >= bowl_score:
        hs = f"{b.get('high_score')}{'*' if b.get('hs_not_out') else ''}" if b.get("high_score") is not None else None
        bits = [f"average {b['average']}"] if b.get("average") is not None else []
        if hs:
            bits.append(f"highest score {hs}")
        if b.get("hundreds"):
            bits.append(f"{b['hundreds']} hundred{'s' if b['hundreds'] != 1 else ''}")
        elif b.get("fifties"):
            bits.append(f"{b['fifties']} fifties")
        return {"kind": "runs", "player": b["name"], "value": b["runs"], "unit": "runs",
                "detail": ", ".join(bits)}
    bits = [f"average {w['average']}"] if w.get("average") is not None else []
    if w.get("best"):
        bits.append(f"best {w['best']}")
    if w.get("economy") is not None:
        bits.append(f"economy {w['economy']}")
    return {"kind": "wickets", "player": w["name"], "value": w["wickets"], "unit": "wickets",
            "detail": ", ".join(bits)}


def presentation(snap: dict) -> dict:
    """The parts of a snapshot a page or image is built from, chosen by the
    rules above. ``lead`` is the grade the club plays the most games in (its
    main side); ``ladders_shown`` only the ones in the top half."""
    club = snap.get("club") or {}
    totals = snap.get("totals") or {}
    ladders = [l for l in (snap.get("ladders") or []) if l.get("rank")]
    lead = None
    if ladders:
        lead_row = sorted(ladders, key=lambda l: (-(l.get("played") or 0), l.get("rank") or 99))[0]
        lead = {"grade": lead_row.get("grade_short") or lead_row.get("grade"),
                "rank": lead_row.get("rank"), "teams": lead_row.get("teams"),
                "played": lead_row.get("played"), "won": lead_row.get("won"),
                "lost": lead_row.get("lost"), "points": lead_row.get("points")}
    shown = [
        {"grade": l.get("grade_short") or l.get("grade"), "rank": l["rank"], "teams": l.get("teams"),
         "place": ordinal(l["rank"]), "played": l.get("played"), "won": l.get("won"),
         "lost": l.get("lost"), "points": l.get("points")}
        for l in ladders
        if l.get("teams") and int(l["rank"]) <= (int(l["teams"]) + 1) // 2
    ]
    shown.sort(key=lambda l: (l["rank"], -(l.get("played") or 0)))
    matches = totals.get("matches") or 0
    return {
        "club": {"name": club.get("name"), "suburb": club.get("suburb"), "state": club.get("state"),
                 "association": club.get("association"), "logo_url": club.get("logo_url")},
        "season": {"name": (snap.get("season") or {}).get("name"), "year": (snap.get("season") or {}).get("year")},
        "hero": _hero(snap),
        "lead": lead,
        "teams": len(ladders),
        "matches": matches,
        "record": ({"played": matches, "won": totals.get("wins"), "lost": totals.get("losses"),
                    "win_rate": totals.get("win_rate")}
                   if matches >= MIN_SEASON_MATCHES and (totals.get("win_rate") or 0) >= FLATTERING_WIN_RATE
                   else None),
        "ladders_shown": shown[:MAX_LADDERS_SHOWN],
        "history": snap.get("history") or {},
    }


async def save_result(session: AsyncSession, club: dict, result: dict, *,
                      now: Optional[datetime] = None) -> dict:
    """Write one pull. A snapshot's ``version`` moves only when its content
    does; a failed pull keeps the last good snapshot and only records the
    error and when to try again. Commits. Returns what changed."""
    now = now or datetime.now(timezone.utc)
    cid, guid = str(club["id"]), club["guid"]
    prior = (await session.execute(text(
        "SELECT id, data_hash, version, attempts, snapshot FROM club_teaser_snapshots "
        "WHERE marketing_club_id = CAST(:c AS uuid)"), {"c": cid})).mappings().first()
    status = result["status"]
    attempts = ((prior or {}).get("attempts") or 0) + 1 if status == "error" else 0
    delay = next_pull_delay(status, attempts=attempts, guid=guid,
                            season_start_=result.get("season_start"),
                            season_pending=bool(result.get("season_pending")), today=now.date())
    snap = result.get("snapshot") if status == "ok" else None
    new_hash = content_hash(snap) if snap else None
    changed = bool(snap) and (prior is None or prior["data_hash"] != new_hash)
    version = (prior["version"] if prior else 0) + (1 if changed else 0)

    if prior is None:
        await session.execute(text("""
            INSERT INTO club_teaser_snapshots (marketing_club_id, org_guid, token, status, snapshot,
                data_hash, version, season_year, season_start, api_calls, attempts, last_error,
                pulled_at, changed_at, next_pull_at)
            VALUES (CAST(:c AS uuid), :g, :tok, :st, CAST(:snap AS jsonb), :h, :v, :sy, :ss, :calls,
                    :att, :err, :now, :chg, :nxt)"""),
            {"c": cid, "g": guid, "tok": secrets.token_urlsafe(16), "st": status,
             "snap": json.dumps(snap, default=str) if snap else None, "h": new_hash, "v": version,
             "sy": result.get("season_year"), "ss": result.get("season_start"),
             "calls": result.get("calls", 0), "att": attempts, "err": result.get("error"),
             "now": now, "chg": now if changed else None, "nxt": now + delay})
    elif status == "error":
        # Keep the last good snapshot and its status; only the bookkeeping moves.
        await session.execute(text("""
            UPDATE club_teaser_snapshots SET attempts = :att, last_error = :err, pulled_at = :now,
                   next_pull_at = :nxt, api_calls = :calls, updated_at = :now WHERE id = :id"""),
            {"att": attempts, "err": result.get("error"), "now": now, "nxt": now + delay,
             "calls": result.get("calls", 0), "id": prior["id"]})
    else:
        await session.execute(text("""
            UPDATE club_teaser_snapshots SET status = :st,
                   snapshot = CASE WHEN :chg OR :st <> 'ok' THEN CAST(:snap AS jsonb) ELSE snapshot END,
                   data_hash = CASE WHEN :chg OR :st <> 'ok' THEN :h ELSE data_hash END,
                   version = :v, season_year = :sy, season_start = :ss, api_calls = :calls,
                   attempts = 0, last_error = NULL, pulled_at = :now,
                   changed_at = CASE WHEN :chg THEN :now ELSE changed_at END,
                   next_pull_at = :nxt, updated_at = :now
            WHERE id = :id"""),
            {"st": status, "chg": changed, "snap": json.dumps(snap, default=str) if snap else None,
             "h": new_hash, "v": version, "sy": result.get("season_year"),
             "ss": result.get("season_start"), "calls": result.get("calls", 0),
             "now": now, "nxt": now + delay, "id": prior["id"]})
    await session.commit()
    return {"status": status, "changed": changed, "version": version,
            "next_pull_at": now + delay, "calls": result.get("calls", 0)}


async def run_batch(limit: int, *, session_maker=None, api_factory: Callable[[], Any] = LiveAPI,
                    should_stop: Optional[Callable[[AsyncSession], Awaitable[bool]]] = None,
                    club_concurrency: int = 2, pause_seconds: float = 0.0,
                    include_trialists: bool = False, club_id: Optional[str] = None,
                    dry_run: bool = False, type_modes: Optional[dict] = None) -> dict:
    """Pull every due club up to ``limit``. Each club runs on its own session
    with its own call counter, so one failure or stall touches nobody else, and
    ``should_stop`` is asked between clubs so the operator's Stop switch halts
    the traffic within one club's worth of calls."""
    from app.models.db import async_session_maker
    session_maker = session_maker or async_session_maker
    async with session_maker() as s:
        todo = await due_clubs(s, limit, include_trialists=include_trialists, club_id=club_id,
                               type_modes=type_modes)
    summary = {"due": len(todo), "ok": 0, "empty": 0, "junior_only": 0, "error": 0,
               "changed": 0, "calls": 0, "stopped": False, "dry_run": dry_run,
               "detail": [{"name": c["name"], "state": c["state"], "status": None, "calls": 0,
                           "secs": 0.0}
                          for c in todo]}
    by_id = {str(c["id"]): d for c, d in zip(todo, summary["detail"])}
    if dry_run or not todo:
        return summary
    sem = asyncio.Semaphore(club_concurrency)

    async def one(club: dict):
        async with sem:
            if summary["stopped"]:
                return
            if should_stop:
                async with session_maker() as s:
                    if await should_stop(s):
                        summary["stopped"] = True
                        return
            api = api_factory()
            started = time.monotonic()
            result = await pull_club(api, club["guid"], club)
            async with session_maker() as s:
                saved = await save_result(s, club, result)
            secs = time.monotonic() - started
            summary[saved["status"]] = summary.get(saved["status"], 0) + 1
            summary["changed"] += 1 if saved["changed"] else 0
            summary["calls"] += saved["calls"]
            row = by_id.get(str(club["id"]))
            if row is not None:
                row.update(status=saved["status"], calls=saved["calls"], secs=round(secs, 3),
                           error=result.get("error"))
            if pause_seconds:
                await asyncio.sleep(pause_seconds)

    await asyncio.gather(*[one(c) for c in todo])
    return summary


# ---------------------------------------------------------------------------
# The paced crawl: one long-running worker, one rate
# ---------------------------------------------------------------------------
# This replaced a cron job that fired a small batch every 5 or 10 minutes: a
# burst, then nothing, then another burst. The worker below never stops
# looking for work; what it limits is HOW FAST it calls out. Every call, from
# every club being worked, goes through one ``CallPacer``, so the upstream sees
# a steady trickle that wobbles a little (services/call_pacer.py) at the rate
# the operator set, inside the hours the operator set (Perth time).
#
# It is OFF UNTIL A SUPER ADMIN SETS ``club_teaser_calls_per_second``: this is
# outbound traffic at scale to a third party, so nobody gets it by deploying.
# The operator's Stop switch (``marketing_crawl_control``) halts it between
# clubs, as it does every other unattended crawl. It assumes ONE API process:
# like every job in this app it runs in-process, and a second process would
# run a second crawl at the same rate.
PERTH = ZoneInfo("Australia/Perth")
CYCLE_BATCH = 10               # clubs per cycle: a setting change lands within a couple of minutes
CYCLE_CLUB_CONCURRENCY = 2     # clubs in flight at once; the rate is the pacer's, not this
IDLE_SECONDS = 300             # nothing is due: look again in five minutes
OFF_SECONDS = 60               # switched off or stopped: read the settings again in a minute
OUTSIDE_POLL_SECONDS = 300     # outside the hours: never sleep longer, so a widened window is noticed
ERROR_SECONDS = 60             # a cycle raised: try again in a minute, never hot-loop
TROUBLE_SECONDS = 900          # a whole cycle of errors: leave the upstream alone for a quarter hour
TROUBLE_MIN_CLUBS = 3


@dataclass(frozen=True)
class PacedConfig:
    rate: float          # calls a second on average; 0 = off
    start_hour: int      # Perth, inclusive
    end_hour: int        # Perth, exclusive (24 = midnight)
    type_modes: dict


def in_window(now: datetime, start_hour: int, end_hour: int) -> bool:
    return start_hour <= now.astimezone(PERTH).hour < end_hour


def seconds_until_open(now: datetime, start_hour: int, end_hour: int) -> float:
    """0 inside the hours, else the wait until they next open (Perth)."""
    if in_window(now, start_hour, end_hour):
        return 0.0
    local = now.astimezone(PERTH)
    opens = local.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    if local >= opens:
        opens += timedelta(days=1)
    return (opens - local).total_seconds()


async def load_config(session_maker=None) -> PacedConfig:
    from app.models.db import async_session_maker
    from app.services import platform_settings as ps
    session_maker = session_maker or async_session_maker
    async with session_maker() as s:
        rate = await ps.get_club_teaser_rate(s)
        start, end = await ps.get_club_teaser_window(s)
        modes = await ps.get_club_teaser_type_modes(s)
    return PacedConfig(rate, start, end, modes)


async def paced_cycle(pacer, *, session_maker=None, config_fn=None, api_factory=None,
                      is_paused=None, now_fn=None, batch: int = CYCLE_BATCH,
                      club_concurrency: int = CYCLE_CLUB_CONCURRENCY) -> dict:
    """One pass of the crawl: read the settings, and if the crawl is on and
    inside its hours pull the next few due clubs through ``pacer``.

    Returns ``{status, wait, summary?}``. ``status`` is off | outside_window |
    stopped | idle | trouble | worked, and ``wait`` is how long the caller
    should sleep before the next pass (0 = straight away, which is how it stays
    continuous while there is work)."""
    from app.models.db import async_session_maker
    session_maker = session_maker or async_session_maker
    if is_paused is None:
        from app.services import club_directory
        is_paused = club_directory.is_crawl_paused
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    cfg = await (config_fn() if config_fn else load_config(session_maker))
    if cfg.rate <= 0:
        return {"status": "off", "wait": OFF_SECONDS}

    def closed_wait() -> float:
        return max(1.0, min(seconds_until_open(now_fn(), cfg.start_hour, cfg.end_hour),
                            OUTSIDE_POLL_SECONDS))

    if not in_window(now_fn(), cfg.start_hour, cfg.end_hour):
        return {"status": "outside_window", "wait": closed_wait()}
    async with session_maker() as s:
        if await is_paused(s):
            return {"status": "stopped", "wait": OFF_SECONDS}

    pacer.set_rate(cfg.rate)
    closed = {"hit": False}

    async def guard(session) -> bool:
        # Asked between clubs. A club in flight finishes (about half a minute
        # of calls), so the hours are honoured to within that.
        if not in_window(now_fn(), cfg.start_hour, cfg.end_hour):
            closed["hit"] = True
            return True
        return bool(await is_paused(session))

    summary = await run_batch(
        batch, session_maker=session_maker, api_factory=api_factory or (lambda: LiveAPI(pacer=pacer)),
        should_stop=guard, club_concurrency=club_concurrency, type_modes=cfg.type_modes)
    summary.pop("detail", None)
    if summary["due"] == 0:
        return {"status": "idle", "wait": IDLE_SECONDS, "summary": summary}
    if summary["stopped"]:
        if closed["hit"]:
            return {"status": "outside_window", "wait": closed_wait(), "summary": summary}
        return {"status": "stopped", "wait": OFF_SECONDS, "summary": summary}
    if (summary["error"] >= TROUBLE_MIN_CLUBS
            and summary["ok"] + summary["empty"] + summary["junior_only"] == 0):
        return {"status": "trouble", "wait": TROUBLE_SECONDS, "summary": summary}
    return {"status": "worked", "wait": 0, "summary": summary}


async def run_forever(*, pacer=None, session_maker=None, config_fn=None, api_factory=None,
                      is_paused=None, now_fn=None, sleep=asyncio.sleep,
                      batch: int = CYCLE_BATCH, club_concurrency: int = CYCLE_CLUB_CONCURRENCY,
                      max_cycles: Optional[int] = None) -> None:
    """The crawl. Runs for the life of the process (``max_cycles`` is for the
    tests). A cycle that raises is logged and retried after a pause, never
    allowed to end the loop or spin."""
    from app.services.call_pacer import CallPacer
    pacer = pacer or CallPacer(1.0)
    last, cycles = None, 0
    while max_cycles is None or cycles < max_cycles:
        cycles += 1
        try:
            out = await paced_cycle(pacer, session_maker=session_maker, config_fn=config_fn,
                                    api_factory=api_factory, is_paused=is_paused, now_fn=now_fn,
                                    batch=batch, club_concurrency=club_concurrency)
        except Exception:  # noqa: BLE001 - a marketing crawl must never take the app down
            logger.exception("Club teaser crawl cycle failed")
            out = {"status": "error", "wait": ERROR_SECONDS}
        if out["status"] != last:
            logger.info("Club teaser crawl: %s", out["status"])
            last = out["status"]
        s = out.get("summary")
        if s and out["status"] in ("worked", "trouble"):
            logger.info("Club teaser crawl: %d club(s), %d call(s): %d ok, %d empty, %d junior_only, %d error",
                        s["due"], s["calls"], s["ok"], s["empty"], s["junior_only"], s["error"])
        if out["wait"]:
            await sleep(out["wait"])
