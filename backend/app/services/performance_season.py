"""Performance Tracker: season leaderboards, season milestones and career milestones
for a tracked round, from Cricket Australia's own published totals.

Three sources, all public play.cricket.com.au data:

  grade season totals   ``/participants/grades/{grade}/{batting|bowling|fielding}-statistics``:
                        every player in the grade, this season, with their club.
                        One quick read per competition, kept in process for
                        ``SEASON_TTL``.
  the round's cards     the scorecards of the round's finished matches (the same
                        cached reads as the pull), for what each player did THIS
                        round.
  club career totals    ``/participants/organisations/{club}/...-statistics`` with
                        no season: every player the club has ever had, all grades.
                        Thousands of rows a club, a hundred a page, so it is read
                        in the background, paced, and kept in ``ca_club_careers``
                        for ``CAREER_MAX_AGE``.

A milestone is a mark crossed THIS round: the total before the round (the total
now, less this round's figures) is under it and the total now reaches it. That
subtraction is only true when nothing has been played since the round, so a
round that is not the grade's latest gets leaderboards ("as at today") and no
milestones, and says why. A career total read before the round finished cannot
show it, so that club's career milestones wait for its next read.

Career totals are the club's own record on play.cricket.com.au: complete where a
competition has always been scored there (PSWL), short where a club's older
seasons never were. The page names that lens.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import grassroots_scores_client as gr
from app.services import playhq_client as ph
from app.services.social_competition import short_club
from app.services.social_rounds import _DNB_TYPES

log = logging.getLogger(__name__)

SEASON_TTL = 15 * 60
CAREER_MAX_AGE = timedelta(days=7)
CAREER_STALE_FETCH = timedelta(minutes=30)   # a 'fetching' row older than this was abandoned
CAREER_PAGE_PAUSE = 0.25                     # seconds between career pages: polite, bounded
CAREER_MAX_PAGES = 80                        # 8,000 players a club, a hard stop
CAREER_MAX_CLUBS_PER_RUN = 16
LEADERS = 10

SEASON_MARKS = {
    "runs": [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
    "wickets": [10, 15, 20, 25, 30, 35, 40, 50],
    "catches": [10, 15, 20],
}
CAREER_MARKS = {
    "matches": [50, 100, 150, 200, 250, 300, 350, 400, 450, 500],
    "runs": [1000 * n for n in range(1, 21)],
    "wickets": [50 * n for n in range(1, 21)],
    "catches": [50, 100, 150, 200, 250, 300],
}

_season_cache: dict[str, tuple[float, dict]] = {}
_inflight: set[str] = set()


# ── Reading Cricket Australia ─────────────────────────────────────────────────

def _person(name: str) -> str:
    """'Wijesinghe, Isuri' -> 'Isuri Wijesinghe'; all lower case reads title case."""
    n = (name or "").strip()
    if "," in n:
        last, first = (x.strip() for x in n.split(",", 1))
        n = f"{first} {last}".strip()
    return n.title() if n and n == n.lower() else n


async def _stats_pages(client: httpx.AsyncClient, url: str, max_pages: int, pause: float = 0.0) -> list[dict]:
    """Every row of a stats list, a hundred a page. Both shapes Cricket Australia
    serves are read: a bare list (grade lists) and ``{participants: [...]}``
    (club lists). Ends on a short page and never trusts a full one to mean more
    (playhq_client.get_seasons has the same trap); rows are deduped on id."""
    out: dict[str, dict] = {}
    offset = 1
    for _ in range(max_pages):
        r = await client.get(url, params=ph._base_params({"limit": 100, "offset": offset}), timeout=30)
        if r.status_code == 204 or not r.content:
            break
        r.raise_for_status()
        data = r.json()
        items = data if isinstance(data, list) else (data.get("participants") or data.get("data") or [])
        before = len(out)
        for it in items:
            pid = str(it.get("id") or "").lower()
            if pid:
                out.setdefault(pid, it)
        if len(items) < 100 or len(out) == before:
            break
        offset += 100
        if pause:
            await asyncio.sleep(pause)
    return list(out.values())


async def grade_season(grade_id: str) -> dict[str, dict]:
    """participant id -> this season's totals in the grade, with their club."""
    hit = _season_cache.get(grade_id)
    if hit and time.time() - hit[0] < SEASON_TTL:
        return hit[1]
    base = f"{ph.BASE_URL}/participants/grades/{grade_id}"
    async with httpx.AsyncClient() as client:
        bat, bowl, fld = await asyncio.gather(
            _stats_pages(client, f"{base}/batting-statistics", 20),
            _stats_pages(client, f"{base}/bowling-statistics", 20),
            _stats_pages(client, f"{base}/fielding-statistics", 20),
        )
    players: dict[str, dict] = {}

    def slot(row):
        pid = str(row.get("id") or "").lower()
        org = row.get("organisation") or {}
        p = players.setdefault(pid, {
            "pid": pid, "name": _person(row.get("name")), "club_id": (org.get("id") or "").lower() or None,
            "club": short_club(org.get("name") or ""), "matches": 0, "inns": 0, "runs": 0, "not_outs": 0,
            "hs": 0, "hs_not_out": False, "fifties": 0, "hundreds": 0, "wickets": 0, "bowl_runs": 0,
            "best": None, "five_fors": 0, "catches": 0, "stumpings": 0, "run_outs": 0,
        })
        p["matches"] = max(p["matches"], int((row.get("statistics") or {}).get("matches") or 0))
        return p, row.get("statistics") or {}

    for row in bat:
        p, s = slot(row)
        p.update(inns=int(s.get("battingInnings") or 0), runs=int(s.get("battingAggregate") or 0),
                 not_outs=int(s.get("battingNotOuts") or 0), hs=int(s.get("battingHighScore") or 0),
                 hs_not_out=bool(s.get("isBattingHSNotOut")), fifties=int(s.get("batting50s") or 0),
                 hundreds=int(s.get("batting100s") or 0))
    for row in bowl:
        p, s = slot(row)
        best = str(s.get("bowlingBestInnings") or "")
        bw = None
        if "-" in best:
            a, b = best.split("-", 1)
            if a.strip().isdigit() and b.strip().isdigit():
                bw = (int(a), int(b))
        p.update(wickets=int(s.get("bowlingWickets") or 0), bowl_runs=int(s.get("bowlingRuns") or 0),
                 best=bw, five_fors=int(s.get("bowling5WIs") or 0))
    for row in fld:
        p, s = slot(row)
        p.update(catches=int(s.get("fieldingTotalCatches") or 0), stumpings=int(s.get("fieldingStumpings") or 0),
                 run_outs=int(s.get("fieldingRunOuts") or 0))
    players.pop("", None)
    if players:
        _season_cache[grade_id] = (time.time(), players)
    return players


async def round_figures(match_ids: list[str]) -> dict[str, dict]:
    """participant id -> what they did in these matches: ``{matches, runs,
    wickets, catches}``. A player named on a team sheet played (one match each),
    as did anyone with a row on the card; absent and did-not-bat rows add no
    runs but the player still played if the sheet names them."""
    cards = await asyncio.gather(*[gr.get_match_scorecard(m) for m in match_ids if m], return_exceptions=True)
    out: dict[str, dict] = {}

    def slot(pid):
        return out.setdefault(pid, {"matches": 0, "runs": 0, "wickets": 0, "catches": 0, "_m": set()})

    for mid, sc in zip([m for m in match_ids if m], cards):
        if not isinstance(sc, dict):
            continue
        for team in sc.get("teams") or []:
            for p in team.get("players") or []:
                pid = (p.get("participantId") or "").lower()
                if pid:
                    slot(pid)["_m"].add(mid)
        for inn in sc.get("innings") or []:
            for b in inn.get("batting") or []:
                pid = (b.get("participantId") or "").lower()
                if not pid:
                    continue
                s = slot(pid)
                s["_m"].add(mid)
                if (b.get("dismissalType") or "").strip().lower() not in _DNB_TYPES:
                    s["runs"] += int(b.get("runsScored") or 0)
            for bw in inn.get("bowling") or []:
                pid = (bw.get("participantId") or "").lower()
                if pid:
                    s = slot(pid)
                    s["_m"].add(mid)
                    s["wickets"] += int(bw.get("wicketsTaken") or 0)
            for f in inn.get("fielding") or []:
                pid = (f.get("participantId") or "").lower()
                if pid:
                    total = f.get("totalCatches")
                    if total is None:
                        total = int(f.get("catches") or 0) + int(f.get("wicketKeeperCatches") or 0)
                    slot(pid)["catches"] += int(total or 0)
    for s in out.values():
        s["matches"] = len(s.pop("_m"))
    return out


# ── Career cache ──────────────────────────────────────────────────────────────

async def _careers(db: AsyncSession, club_ids: list[str]) -> dict[str, dict]:
    if not club_ids:
        return {}
    rows = (await db.execute(text(
        "SELECT ca_org_id, name, data, status, started_at, fetched_at FROM ca_club_careers "
        "WHERE ca_org_id = ANY(CAST(:ids AS text[]))"), {"ids": club_ids})).mappings().all()
    return {r["ca_org_id"]: dict(r) for r in rows}


def _needs_fetch(row: dict | None, last_day: date | None, now: datetime) -> bool:
    if row is None or row.get("fetched_at") is None:
        fetching = row and row.get("status") == "fetching" and row.get("started_at") \
            and now - row["started_at"] < CAREER_STALE_FETCH
        return not fetching
    if row.get("status") == "fetching" and row.get("started_at") and now - row["started_at"] < CAREER_STALE_FETCH:
        return False
    if now - row["fetched_at"] > CAREER_MAX_AGE:
        return True
    # Read on or before the round's last day: it may not hold the round yet.
    return bool(last_day and row["fetched_at"].date() <= last_day and now.date() > last_day)


async def _crawl_stopped(db: AsyncSession) -> bool:
    try:
        from app.services.club_directory import is_crawl_paused
        return await is_crawl_paused(db)
    except Exception:  # noqa: BLE001 - no switch table: not stopped
        await db.rollback()
        return False


async def _fetch_club_career(club_id: str) -> dict[str, list]:
    """pid -> [matches, runs, wickets, catches, name] for every player the club has."""
    base = f"{ph.BASE_URL}/participants/organisations/{club_id}"
    out: dict[str, list] = {}
    async with httpx.AsyncClient() as client:
        for kind in ("batting", "bowling", "fielding"):
            rows = await _stats_pages(client, f"{base}/{kind}-statistics", CAREER_MAX_PAGES, CAREER_PAGE_PAUSE)
            for row in rows:
                pid = str(row.get("id") or "").lower()
                s = row.get("statistics") or {}
                e = out.setdefault(pid, [0, 0, 0, 0, _person(row.get("name"))])
                e[0] = max(e[0], int(s.get("matches") or 0))
                if kind == "batting":
                    e[1] = int(s.get("battingAggregate") or 0)
                elif kind == "bowling":
                    e[2] = int(s.get("bowlingWickets") or 0)
                else:
                    e[3] = int(s.get("fieldingTotalCatches") or 0)
            await asyncio.sleep(CAREER_PAGE_PAUSE)
    out.pop("", None)
    return out


async def refresh_careers(clubs: list[tuple[str, str]]) -> None:
    """Read each club's career totals into ``ca_club_careers``, one club at a
    time, on its own session (it runs after the request has answered). Stops
    between clubs when the operator's crawl Stop switch is on. Never raises."""
    from app.models.db import async_session_maker
    try:
        async with async_session_maker() as db:
            for club_id, name in clubs[:CAREER_MAX_CLUBS_PER_RUN]:
                if await _crawl_stopped(db):
                    await db.execute(text(
                        "UPDATE ca_club_careers SET status = 'stopped' WHERE ca_org_id = :id AND status = 'fetching'"),
                        {"id": club_id})
                    await db.commit()
                    continue
                try:
                    data = await _fetch_club_career(club_id)
                    await db.execute(text(
                        "UPDATE ca_club_careers SET data = CAST(:d AS jsonb), players = :n, status = 'ready', "
                        "error = NULL, fetched_at = NOW(), name = :name WHERE ca_org_id = :id"),
                        {"d": json.dumps(data), "n": len(data), "name": name, "id": club_id})
                    await db.commit()
                except Exception as exc:  # noqa: BLE001 - one club must not stop the rest
                    log.warning("career read failed for club %s: %s", club_id, exc)
                    await db.rollback()
                    await db.execute(text(
                        "UPDATE ca_club_careers SET status = 'error', error = :e WHERE ca_org_id = :id"),
                        {"e": str(exc)[:300], "id": club_id})
                    await db.commit()
                finally:
                    _inflight.discard(club_id)
    except Exception:  # noqa: BLE001
        log.exception("career refresh run failed")
    finally:
        for club_id, _ in clubs:
            _inflight.discard(club_id)


async def ensure_careers(db: AsyncSession, clubs: dict[str, str], last_day: date | None) -> dict[str, dict]:
    """The career rows for these clubs (id -> name), and a background read
    started for any missing, old, or read before the round ended."""
    ids = sorted(c for c in clubs if c)
    held = await _careers(db, ids)
    now = datetime.now(timezone.utc)
    want = [c for c in ids if c not in _inflight and _needs_fetch(held.get(c), last_day, now)]
    if want:
        for c in want:
            await db.execute(text(
                "INSERT INTO ca_club_careers (ca_org_id, name, status, started_at) VALUES (:id, :n, 'fetching', NOW()) "
                "ON CONFLICT (ca_org_id) DO UPDATE SET status = 'fetching', started_at = NOW()"),
                {"id": c, "n": clubs[c]})
            _inflight.add(c)
        await db.commit()
        asyncio.create_task(refresh_careers([(c, clubs[c]) for c in want]))
        held = await _careers(db, ids)
    return held


# ── Leaderboards and milestones ───────────────────────────────────────────────

def _crossed(before: int, after: int, marks: list[int]) -> int | None:
    hit = [m for m in marks if before < m <= after]
    return hit[-1] if hit else None


def leaderboards(players: list[dict]) -> dict:
    def row(p, value, sub=""):
        return {"pid": p["pid"], "name": p["name"], "club": p["club"], "club_id": p["club_id"], "value": value, "sub": sub}
    bat = [p for p in players if p["runs"] or p["inns"]]
    bowl = [p for p in players if p["wickets"]]
    return {
        "runs": [row(p, p["runs"], f"{p['inns']} inns" + (f", avg {p['runs'] / (p['inns'] - p['not_outs']):.1f}" if p["inns"] > p["not_outs"] else ""))
                 for p in sorted(bat, key=lambda p: (-p["runs"], p["inns"], p["name"]))[:LEADERS]],
        "wickets": [row(p, p["wickets"], f"{p['bowl_runs']} runs" + (f", avg {p['bowl_runs'] / p['wickets']:.1f}" if p["wickets"] else ""))
                    for p in sorted(bowl, key=lambda p: (-p["wickets"], p["bowl_runs"], p["name"]))[:LEADERS]],
        "catches": [row(p, p["catches"], f"{p['stumpings']} st" if p["stumpings"] else "")
                    for p in sorted([p for p in players if p["catches"]], key=lambda p: (-p["catches"], p["name"]))[:LEADERS]],
        "high_score": [row(p, f"{p['hs']}{'*' if p['hs_not_out'] else ''}")
                       for p in sorted([p for p in bat if p["hs"]], key=lambda p: (-p["hs"], not p["hs_not_out"], p["name"]))[:LEADERS]],
        "best_bowling": [row(p, f"{p['best'][0]}/{p['best'][1]}")
                         for p in sorted([p for p in bowl if p["best"]], key=lambda p: (-p["best"][0], p["best"][1], p["name"]))[:LEADERS]],
    }


def _merge(players_by_comp: list[dict[str, dict]]) -> list[dict]:
    """One row a player across competitions: totals added, bests the best."""
    out: dict[str, dict] = {}
    for comp in players_by_comp:
        for pid, p in comp.items():
            held = out.get(pid)
            if held is None:
                out[pid] = dict(p)
                continue
            for k in ("matches", "inns", "runs", "not_outs", "fifties", "hundreds", "wickets", "bowl_runs",
                      "five_fors", "catches", "stumpings", "run_outs"):
                held[k] += p[k]
            if (p["hs"], p["hs_not_out"]) > (held["hs"], held["hs_not_out"]):
                held["hs"], held["hs_not_out"] = p["hs"], p["hs_not_out"]
            if p["best"] and (not held["best"] or (-p["best"][0], p["best"][1]) < (-held["best"][0], held["best"][1])):
                held["best"] = p["best"]
    return list(out.values())


def season_milestones(season: dict[str, dict], figs: dict[str, dict]) -> list[dict]:
    out = []
    for pid, f in figs.items():
        p = season.get(pid)
        if not p:
            continue
        for key, word in (("runs", "runs"), ("wickets", "wickets"), ("catches", "catches")):
            now = p[key]
            mark = _crossed(now - f[key], now, SEASON_MARKS[key])
            if mark:
                out.append({"pid": pid, "name": p["name"], "club": p["club"], "kind": f"season_{key}", "mark": mark,
                            "text": f"{p['name']} ({p['club']}) passed {mark} {word} for the season ({now})"})
    out.sort(key=lambda m: (m["kind"], -m["mark"], m["name"]))
    return out


def career_milestones(careers: dict[str, dict], season: dict[str, dict], figs: dict[str, dict]) -> list[dict]:
    out = []
    for pid, f in figs.items():
        p = season.get(pid)
        if not p or not p.get("club_id"):
            continue
        row = careers.get(p["club_id"])
        data = (row or {}).get("data") or {}
        if isinstance(data, str):
            data = json.loads(data)
        e = data.get(pid)
        if not e:
            continue
        matches, runs, wkts, catches = e[0], e[1], e[2], e[3]
        club = p["club"]
        for key, now, text_of in (
            ("matches", matches, lambda m: f"{p['name']} played game {m} for {club}"),
            ("runs", runs, lambda m: f"{p['name']} passed {m:,} career runs for {club} ({runs:,})"),
            ("wickets", wkts, lambda m: f"{p['name']} passed {m} career wickets for {club} ({wkts})"),
            ("catches", catches, lambda m: f"{p['name']} passed {m} career catches for {club} ({catches})"),
        ):
            mark = _crossed(now - f[key], now, CAREER_MARKS[key])
            if mark:
                out.append({"pid": pid, "name": p["name"], "club": club, "kind": f"career_{key}", "mark": mark, "text": text_of(mark)})
    out.sort(key=lambda m: (m["kind"], -m["mark"], m["name"]))
    return out


def _latest(all_matches: list[dict], round_id: str, last_day: str) -> bool:
    """Is the round the grade's latest played? No finished match in another
    round starts after the round's last day."""
    for m in all_matches:
        if str(m.get("statusId")) != "3":
            continue
        rid = str(((m.get("round") or {}).get("id")) or "").lower()
        if rid == (round_id or "").lower():
            continue
        day = ""
        for s in m.get("matchSchedule") or []:
            day = (s.get("startDateTime") or "")[:10] or day
            break
        if day and last_day and day > last_day:
            return False
    return True


async def round_season(db: AsyncSession, round_data: dict) -> dict:
    """Leaderboards and milestones for a tracked round (its stored pulls)."""
    comps = [c for c in (round_data.get("competitions") or [])
             if isinstance(c, dict) and isinstance(c.get("pull"), dict) and c["pull"].get("kind") == "round"]
    blocks, seasons = [], []
    clubs: dict[str, str] = {}
    prepared = []
    for c in comps:
        pull = c["pull"]
        grade_id = pull.get("grade_id")
        match_ids = [r.get("match_id") for r in pull.get("results") or []]
        last_day = max((r.get("date") or "" for r in pull.get("results") or []), default="")
        try:
            season, figs, all_matches = await asyncio.gather(
                grade_season(grade_id), round_figures(match_ids), gr.get_grade_matches(grade_id))
        except Exception as exc:  # noqa: BLE001 - one competition must not blank the rest
            log.warning("season read failed for grade %s: %s", grade_id, exc)
            blocks.append({"key": c.get("key"), "name": c.get("name"), "grade": pull.get("grade"),
                           "error": "Cricket Australia's season totals could not be read. Try again shortly."})
            continue
        latest = _latest(all_matches or [], pull.get("round_id"), last_day)
        for p in season.values():
            if p.get("club_id") and p["pid"] in figs:
                clubs.setdefault(p["club_id"], p["club"])
        seasons.append(season)
        prepared.append((c, pull, season, figs, latest, last_day))

    last_days = [ld for *_, ld in prepared if ld]
    last = date.fromisoformat(max(last_days)) if last_days else None
    careers = await ensure_careers(db, clubs, last)
    status = {"ready": [], "pending": [], "failed": []}
    for cid, name in sorted(clubs.items(), key=lambda kv: kv[1]):
        row = careers.get(cid) or {}
        usable = row.get("fetched_at") is not None and (not last or row["fetched_at"].date() > last)
        (status["ready"] if usable else status["failed"] if row.get("status") in ("error", "stopped") else status["pending"]).append(name)

    for c, pull, season, figs, latest, last_day in prepared:
        usable = {cid: r for cid, r in careers.items()
                  if r.get("fetched_at") is not None and (not last or r["fetched_at"].date() > last)}
        blocks.append({
            "key": c.get("key"), "name": c.get("name"), "grade": pull.get("grade"), "round": pull.get("round"),
            "latest": latest,
            "players": len(season),
            "leaders": leaderboards(list(season.values())),
            "season_milestones": season_milestones(season, figs) if latest else [],
            "career_milestones": career_milestones(usable, season, figs) if latest else [],
        })
    return {
        "competitions": blocks,
        "all": {"leaders": leaderboards(_merge(seasons))} if len(seasons) > 1 else None,
        "career": status,
        "as_at": datetime.now(timezone.utc).isoformat(),
    }
