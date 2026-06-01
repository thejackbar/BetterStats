"""BetterIQ — live opponent scouting dossier.

Builds a deep report on an opponent we DON'T sync, by reading the same
Grassroots ``/scores/*`` scorecards the Core sync reads and keeping the
*opponent* half (sync keeps only ours — ``if pid not in our_team_pids:
continue``). Two sources combine:

* **Current-season squad + form** — every match in the (fixture's) grade is
  listed; we keep the opponent's matches and aggregate their batting / bowling /
  fielding per ``participantId``. The grade is league-wide, so this is the
  opponent's real form against the whole competition, not just us.
* **Head-to-head vs us** — our stored games against this opponent are re-fetched
  (capped, newest first) and the opponent's cards parsed, giving each of their
  players a record specifically against us.

The result is assembled and cached in ``opposition_dossiers`` (built on demand
in a background task; the router polls ``status``). We hold scorecards, not
ball-by-ball, so analytics stop at the scorecard ceiling: form, averages, SR,
conversion, dismissal patterns, vs-us records, venue — no phase/matchup ball
logs.

Opponent identity follows sync: the opponent ``teams[]`` entry is the one whose
``owningOrganisation.id`` is NOT ours (or, in a grade full of other clubs, the
one matching the opponent's org id / club name). Every row is then gated by that
team's roster ``participantId`` set — the mirror image of sync's ``our_team_pids``
gate.
"""
from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import OppositionDossier, async_session_maker
from app.services import grassroots_scores_client as gr

logger = logging.getLogger(__name__)

# Squads change slowly and a rebuild is heavy; a week's freshness with a manual
# Refresh button is the right trade-off.
TTL = timedelta(days=7)
# A 'building' row whose task died (process restart) shouldn't wedge forever.
BUILD_STALE_AFTER = timedelta(minutes=5)
# Bound the work so a first build stays in the ~10–40s window the UX expects.
MAX_OPP_SEASON_MATCHES = 18
MAX_HEAD_TO_HEAD_GAMES = 25

# Hold references to in-flight build tasks so the event loop doesn't GC a
# fire-and-forget task mid-build (asyncio only keeps a weak ref otherwise).
_BUILD_TASKS: set = set()

_DISMISSAL_SHORT = {
    "Caught": "caught", "Bowled": "bowled", "Leg Before Wicket": "lbw",
    "Run Out": "run out", "Stumped": "stumped", "Hit Wicket": "hit wicket",
    "Caught & Bowled": "c&b", "Caught and Bowled": "c&b",
}
_NOT_AN_INNINGS = {"absent", "did not bat", "dnb"}
_TEAM_SUFFIXES = (
    "1st xi", "2nd xi", "3rd xi", "4th xi", "5th xi", "6th xi", "7th xi", "8th xi",
    "1st grade", "2nd grade", "3rd grade", "4th grade", "colts", "mens", "womens",
)


# ─── small pure helpers ──────────────────────────────────────────────────────

def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _club_norm(name: str | None) -> str:
    """Normalise a team displayName down to a club name for fuzzy matching."""
    n = _norm(name)
    for suf in _TEAM_SUFFIXES:
        if n.endswith(" " + suf):
            n = n[: -(len(suf) + 1)]
            break
    return n.strip()


def _is_uuid(s: str | None) -> bool:
    if not s or len(s) < 32:
        return False
    try:
        import uuid as _u
        _u.UUID(s)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _overs_to_balls(ov) -> int:
    """CA overs like 10.2 → 10 overs + 2 balls = 62 balls."""
    try:
        ov = float(ov or 0)
    except (TypeError, ValueError):
        return 0
    whole = int(ov)
    frac = round((ov - whole) * 10)
    return whole * 6 + min(max(frac, 0), 5)


def _balls_to_overs(balls: int) -> float:
    return round(balls // 6 + (balls % 6) / 10, 1)


def _match_date(scorecard: dict) -> date | None:
    for sched in (scorecard.get("matchSchedule") or []):
        iso = sched.get("startDateTime") or ""
        if iso:
            try:
                return date.fromisoformat(iso[:10])
            except ValueError:
                pass
    return None


def _find_opponent_team(scorecard: dict, *, our_org_id: str | None, opp_org_id: str | None, opp_name: str | None) -> dict | None:
    """The opponent's ``teams[]`` entry in a scorecard.

    Prefers an org-id match, then a club-name match, then (for our own games)
    "the team that isn't ours".
    """
    teams = scorecard.get("teams") or []
    if opp_org_id:
        for t in teams:
            if _norm((t.get("owningOrganisation") or {}).get("id")) == _norm(opp_org_id):
                return t
    if opp_name:
        target = _club_norm(opp_name)
        for t in teams:
            org = t.get("owningOrganisation") or {}
            if target and target in (_club_norm(org.get("name")), _club_norm(org.get("displayName")), _club_norm(t.get("displayName") or t.get("name"))):
                return t
    if our_org_id:
        others = [t for t in teams if _norm((t.get("owningOrganisation") or {}).get("id")) != _norm(our_org_id)]
        if len(others) == 1:
            return others[0]
    return None


def _team_roster(team: dict) -> dict[str, str]:
    """participantId → display name for everyone on a team sheet."""
    out: dict[str, str] = {}
    for pl in ((team.get("players") or []) + (team.get("nonPlayingMembers") or [])):
        pid = pl.get("participantId") or pl.get("id")
        if not pid:
            continue
        out[pid] = pl.get("displayName") or pl.get("name") or pl.get("playerShortName") or pid
    return out


def _new_bat(name):
    return {"name": name, "inns": 0, "runs": 0, "balls": 0, "outs": 0, "no": 0,
            "fours": 0, "sixes": 0, "hs": None, "hs_no": False,
            "dism": Counter(), "scores": [], "matches": set()}


def _new_bowl(name):
    return {"name": name, "balls": 0, "maidens": 0, "runs": 0, "wkts": 0, "spells": 0,
            "five_fors": 0, "best_w": -1, "best_r": None, "spell_log": [], "matches": set()}


def _new_field(name):
    return {"name": name, "ct": 0, "ct_wk": 0, "ro": 0, "st": 0}


def _accumulate(scorecard: dict, match_id: str, opp_pids: dict[str, str], when: date | None,
                bat: dict, bowl: dict, field: dict) -> None:
    """Fold one scorecard's opponent rows into the accumulators (in place)."""
    when_s = when.isoformat() if when else None
    for inn in (scorecard.get("innings") or []):
        for row in (inn.get("batting") or []):
            pid = row.get("participantId")
            if pid not in opp_pids:
                continue
            dt_id = row.get("dismissalTypeId") or 0
            if dt_id == 0:  # DNB / absent — not a real innings (matches sync + CA aggregate)
                continue
            if _norm(row.get("dismissalType")) in _NOT_AN_INNINGS:
                continue
            runs = row.get("runsScored") or 0
            balls = row.get("ballsFaced") or 0
            not_out = dt_id == 1
            b = bat.setdefault(pid, _new_bat(opp_pids[pid]))
            b["inns"] += 1
            b["runs"] += runs
            b["balls"] += balls
            b["fours"] += row.get("foursScored") or 0
            b["sixes"] += row.get("sixesScored") or 0
            b["matches"].add(match_id)
            if not_out:
                b["no"] += 1
            else:
                b["outs"] += 1
                dt_long = row.get("dismissalType") or ""
                if dt_long:
                    b["dism"][_DISMISSAL_SHORT.get(dt_long, dt_long.lower())] += 1
            if b["hs"] is None or runs > b["hs"]:
                b["hs"], b["hs_no"] = runs, not_out
            b["scores"].append({"date": when_s, "runs": runs, "balls": balls, "not_out": not_out})

        for row in (inn.get("bowling") or []):
            pid = row.get("participantId")
            if pid not in opp_pids:
                continue
            w = row.get("wicketsTaken") or 0
            r = row.get("runsConceded") or 0
            balls = _overs_to_balls(row.get("oversBowled"))
            bw = bowl.setdefault(pid, _new_bowl(opp_pids[pid]))
            bw["balls"] += balls
            bw["maidens"] += row.get("maidensBowled") or 0
            bw["runs"] += r
            bw["wkts"] += w
            bw["spells"] += 1
            bw["matches"].add(match_id)
            if w >= 5:
                bw["five_fors"] += 1
            if w > bw["best_w"] or (w == bw["best_w"] and (bw["best_r"] is None or r < bw["best_r"])):
                bw["best_w"], bw["best_r"] = w, r
            bw["spell_log"].append({"date": when_s, "wkts": w, "runs": r, "balls": balls})

        for row in (inn.get("fielding") or []):
            pid = row.get("participantId")
            if pid not in opp_pids:
                continue
            f = field.setdefault(pid, _new_field(opp_pids[pid]))
            ct_wk = row.get("wicketKeeperCatches") or 0
            ct = row.get("totalCatches")
            if ct is None:
                ct = (row.get("catches") or 0) + ct_wk
            f["ct"] += ct or 0
            f["ct_wk"] += ct_wk
            f["ro"] += row.get("runOuts") or 0
            f["st"] += row.get("stumpings") or 0


# ─── finalisers (accumulator → analytics-ready dict) ─────────────────────────

def _finalise_bat(pid: str, b: dict) -> dict:
    inns, runs, outs, balls = b["inns"], b["runs"], b["outs"], b["balls"]
    scores = sorted(b["scores"], key=lambda s: s["date"] or "", reverse=True)
    fifties = sum(1 for s in scores if 50 <= s["runs"] < 100)
    hundreds = sum(1 for s in scores if s["runs"] >= 100)
    recent = scores[:5]
    recent_runs = [s["runs"] for s in recent]
    avg = round(runs / outs, 2) if outs else None
    recent_avg = round(sum(recent_runs) / max(len([s for s in recent if not s["not_out"]]), 1), 2) if recent else None
    # "Hot" when recent scoring clearly outpaces the career-vs-field average.
    form = None
    if avg is not None and recent_avg is not None and len(recent) >= 3:
        form = "hot" if recent_avg >= avg * 1.25 else ("cold" if recent_avg <= avg * 0.6 else "steady")
    return {
        "player_id": pid,
        "name": b["name"],
        "matches": len(b["matches"]),
        "innings": inns,
        "runs": runs,
        "not_outs": b["no"],
        "high_score": (f"{b['hs']}*" if b["hs_no"] else str(b["hs"])) if b["hs"] is not None else None,
        "average": avg,
        "strike_rate": round(100 * runs / balls, 1) if balls else None,
        "fifties": fifties,
        "hundreds": hundreds,
        "fours": b["fours"],
        "sixes": b["sixes"],
        "boundary_pct": round(100 * (4 * b["fours"] + 6 * b["sixes"]) / runs, 1) if runs else None,
        "dismissals": dict(b["dism"]),
        "recent_scores": [
            (f"{s['runs']}*" if s["not_out"] else str(s["runs"])) for s in recent
        ],
        "recent_avg": recent_avg,
        "form": form,
    }


def _finalise_bowl(pid: str, b: dict) -> dict:
    wkts, runs, balls = b["wkts"], b["runs"], b["balls"]
    log = sorted(b["spell_log"], key=lambda s: s["date"] or "", reverse=True)
    return {
        "player_id": pid,
        "name": b["name"],
        "matches": len(b["matches"]),
        "overs": _balls_to_overs(balls),
        "maidens": b["maidens"],
        "runs": runs,
        "wickets": wkts,
        "average": round(runs / wkts, 2) if wkts else None,
        "economy": round(runs / (balls / 6), 2) if balls else None,
        "strike_rate": round(balls / wkts, 1) if wkts else None,
        "best": (f"{b['best_w']}/{b['best_r']}" if b["best_w"] >= 0 else None),
        "five_fors": b["five_fors"],
        "recent_wickets": [s["wkts"] for s in log[:5]],
    }


def _danger_index_bat(p: dict) -> float:
    """Rank batters by output, leaning on recent form. Explainable, not magic."""
    base = (p["average"] or 0) * 0.5 + (p["runs"] or 0) * 0.05
    if p["form"] == "hot":
        base *= 1.3
    elif p["form"] == "cold":
        base *= 0.7
    return base


# ─── cache plumbing ──────────────────────────────────────────────────────────

async def _load_row(session: AsyncSession, org_id: str, opp_key: str) -> OppositionDossier | None:
    res = await session.execute(
        select(OppositionDossier).where(
            OppositionDossier.organisation_id == org_id,
            OppositionDossier.opp_key == opp_key,
        )
    )
    return res.scalar_one_or_none()


async def _upsert(session: AsyncSession, org_id: str, opp_key: str, **fields) -> None:
    row = await _load_row(session, org_id, opp_key)
    now = datetime.now(timezone.utc)
    if row is None:
        row = OppositionDossier(organisation_id=org_id, opp_key=opp_key)
        session.add(row)
    for k, v in fields.items():
        setattr(row, k, v)
    row.updated_at = now
    await session.commit()


async def get_or_start_dossier(
    session: AsyncSession,
    org_id: str,
    opp_key: str,
    *,
    opp_name: str | None = None,
    grade_id: str | None = None,
    force: bool = False,
) -> dict:
    """Return a ready dossier, or kick off a background build and report status.

    The router polls this: ``{status: 'building'}`` until the task finishes, then
    ``{status: 'ready', ...payload}``. ``force`` (Refresh button) rebuilds even a
    fresh cache hit.
    """
    row = await _load_row(session, org_id, opp_key)
    now = datetime.now(timezone.utc)

    def _fresh(r):
        return r and r.status == "ready" and r.built_at and (now - r.built_at) < TTL

    if _fresh(row) and not force:
        return {"status": "ready", "cached": True, **(row.payload or {})}

    building = row and row.status == "building" and row.updated_at and (now - row.updated_at) < BUILD_STALE_AFTER
    if building and not force:
        return {
            "status": "building",
            "opponent": {"opp_key": opp_key, "name": row.opp_name or opp_name},
        }

    # Mark building and launch the detached build (its own session).
    await _upsert(session, org_id, opp_key, opp_name=opp_name, status="building", error=None)
    task = asyncio.create_task(_run_build(org_id, opp_key, opp_name, grade_id))
    _BUILD_TASKS.add(task)
    task.add_done_callback(_BUILD_TASKS.discard)
    return {"status": "building", "opponent": {"opp_key": opp_key, "name": opp_name}}


async def _run_build(org_id: str, opp_key: str, opp_name: str | None, grade_id: str | None) -> None:
    async with async_session_maker() as session:
        try:
            payload = await _assemble(session, org_id, opp_key, opp_name, grade_id)
            await _upsert(
                session, org_id, opp_key,
                opp_name=payload.get("opponent", {}).get("name") or opp_name,
                status="ready", payload=payload, built_at=datetime.now(timezone.utc), error=None,
            )
            logger.info(f"BetterIQ: dossier built for org={org_id} opp={opp_key}")
        except Exception as e:  # never leave the row wedged at 'building'
            logger.exception(f"BetterIQ: dossier build failed for org={org_id} opp={opp_key}: {e}")
            try:
                await _upsert(session, org_id, opp_key, status="error", error=str(e)[:500])
            except Exception:
                pass


# ─── the build itself ────────────────────────────────────────────────────────

async def _our_games_vs(session: AsyncSession, org_id: str, opp_key: str) -> list[dict]:
    res = await session.execute(
        text(
            """
            SELECT g.id::text AS id, g.played_at, g.grade_id::text AS grade_id, g.venue
            FROM v_effective_games g
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = CAST(:org AS UUID)
              AND COALESCE(g.opp_org_id, g.opp_club_name) = :opp_key
            ORDER BY g.played_at DESC NULLS LAST
            """
        ),
        {"org": org_id, "opp_key": opp_key},
    )
    return [dict(r) for r in res.mappings()]


async def _assemble(session: AsyncSession, org_id: str, opp_key: str, opp_name: str | None, grade_id: str | None) -> dict:
    opp_org_id = opp_key if _is_uuid(opp_key) else None
    our_games = await _our_games_vs(session, org_id, opp_key)

    # Resolve the grade to scout for current-season form: the fixture's grade if
    # given, else the grade of our most recent meeting (same league-wide grade).
    scout_grade = grade_id
    if not scout_grade:
        for g in our_games:
            if g.get("grade_id"):
                scout_grade = g["grade_id"]
                break

    resolved_name = opp_name
    season_bat: dict = {}
    season_bowl: dict = {}
    season_field: dict = {}
    season_matches = 0
    season_dates: list[date] = []

    if scout_grade:
        try:
            grade_matches = await gr.get_grade_matches(scout_grade)
        except Exception as e:
            logger.warning(f"BetterIQ: grade {scout_grade} matches failed: {e}")
            grade_matches = []

        # Keep only matches the opponent is in — by org id, else by club name.
        opp_match_ids: list[str] = []
        for m in grade_matches:
            mid = m.get("id")
            if not mid:
                continue
            for t in (m.get("teams") or []):
                org = t.get("owningOrganisation") or {}
                if opp_org_id and _norm(org.get("id")) == _norm(opp_org_id):
                    opp_match_ids.append(mid)
                    if not resolved_name:
                        resolved_name = org.get("name") or org.get("displayName")
                    break
                if opp_name and _club_norm(opp_name) and _club_norm(opp_name) in (
                    _club_norm(org.get("name")), _club_norm(org.get("displayName")), _club_norm(t.get("displayName"))
                ):
                    opp_match_ids.append(mid)
                    if not opp_org_id:
                        opp_org_id = org.get("id")
                    break
        opp_match_ids = opp_match_ids[:MAX_OPP_SEASON_MATCHES]

        for mid in opp_match_ids:
            sc = await gr.get_match_scorecard(mid)
            if not sc:
                continue
            opp_team = _find_opponent_team(sc, our_org_id=org_id, opp_org_id=opp_org_id, opp_name=opp_name or resolved_name)
            if not opp_team:
                continue
            roster = _team_roster(opp_team)
            if not roster:
                continue
            when = _match_date(sc)
            if when:
                season_dates.append(when)
            _accumulate(sc, mid, roster, when, season_bat, season_bowl, season_field)
            season_matches += 1

    # Head-to-head vs us — re-fetch our stored games against them (capped, newest
    # first) and parse the opponent's cards specifically against Applecross.
    h2h_bat: dict = {}
    h2h_bowl: dict = {}
    h2h_field: dict = {}
    h2h_games = 0
    for g in our_games[:MAX_HEAD_TO_HEAD_GAMES]:
        sc = await gr.get_match_scorecard(g["id"])
        if not sc:
            continue  # manual game / 204 — no CA scorecard
        opp_team = _find_opponent_team(sc, our_org_id=org_id, opp_org_id=opp_org_id, opp_name=opp_name or resolved_name)
        if not opp_team:
            continue
        roster = _team_roster(opp_team)
        if not roster:
            continue
        when = _match_date(sc) or (date.fromisoformat(g["played_at"]) if isinstance(g.get("played_at"), str) else g.get("played_at"))
        _accumulate(sc, g["id"], roster, when, h2h_bat, h2h_bowl, h2h_field)
        h2h_games += 1

    # ── assemble squad: season form, annotated with vs-us records ────────────
    h2h_bat_final = {pid: _finalise_bat(pid, b) for pid, b in h2h_bat.items()}
    h2h_bowl_final = {pid: _finalise_bowl(pid, b) for pid, b in h2h_bowl.items()}

    batters = []
    for pid, b in season_bat.items():
        row = _finalise_bat(pid, b)
        vs = h2h_bat_final.get(pid)
        row["vs_us"] = {
            "innings": vs["innings"], "runs": vs["runs"], "average": vs["average"],
            "high_score": vs["high_score"], "fifties": vs["fifties"], "hundreds": vs["hundreds"],
        } if vs else None
        batters.append(row)
    batters.sort(key=lambda p: (p["runs"] or 0), reverse=True)

    bowlers = []
    for pid, b in season_bowl.items():
        row = _finalise_bowl(pid, b)
        vs = h2h_bowl_final.get(pid)
        row["vs_us"] = {
            "wickets": vs["wickets"], "average": vs["average"], "economy": vs["economy"], "best": vs["best"],
        } if vs else None
        bowlers.append(row)
    bowlers.sort(key=lambda p: (p["wickets"] or 0, -(p["average"] or 1e9)), reverse=True)

    keepers = [
        {"player_id": pid, "name": f["name"], "catches": f["ct"], "stumpings": f["st"], "run_outs": f["ro"]}
        for pid, f in season_field.items() if (f["ct_wk"] or f["st"])
    ]
    keepers.sort(key=lambda p: (p["catches"] + p["stumpings"]), reverse=True)

    danger_batters = sorted(batters, key=_danger_index_bat, reverse=True)[:5]
    danger_bowlers = sorted(
        [b for b in bowlers if b["wickets"]], key=lambda p: (p["wickets"], -(p["average"] or 1e9)), reverse=True
    )[:5]

    # Players who've historically hurt us but aren't in the scouted squad — still
    # worth flagging ("watch for a recall").
    season_pids = set(season_bat) | set(season_bowl)
    threats_history = sorted(
        [r for pid, r in h2h_bat_final.items() if pid not in season_pids and (r["runs"] or 0) >= 50],
        key=lambda p: (p["runs"] or 0), reverse=True,
    )[:5]

    coverage = "rich" if season_matches else ("history_only" if h2h_games else "none")
    notes = []
    if season_matches:
        notes.append(f"Squad & form built live from {season_matches} of {(opp_name or resolved_name) or 'their'} matches in this grade.")
    else:
        notes.append("No current-season matches found in this grade — showing head-to-head history only.")
    if h2h_games:
        notes.append(f"Head-to-head built from {h2h_games} of our games against them.")
    notes.append("Based on scorecards (no ball-by-ball), so no phase or ball-level matchup data.")

    return {
        "opponent": {"opp_key": opp_key, "name": (opp_name or resolved_name)},
        "coverage": {"level": coverage, "notes": notes},
        "scouted": {
            "season_matches": season_matches,
            "head_to_head_games": h2h_games,
            "span": {
                "from": min(season_dates).isoformat() if season_dates else None,
                "to": max(season_dates).isoformat() if season_dates else None,
            },
            "grade_id": scout_grade,
        },
        "danger_batters": danger_batters,
        "danger_bowlers": danger_bowlers,
        "batting": batters,
        "bowling": bowlers,
        "keepers": keepers,
        "historical_threats": threats_history,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
