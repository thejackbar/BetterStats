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
import re
import statistics
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import OppositionDossier, async_session_maker
from app.services import grassroots_scores_client as gr
from app.services import iq_phrases
from app.services import rate_coverage as rc
from app.services.iq_filters import grade_canonical_label, grade_match_clause
from app.services.sync import _caught_by_keeper, _innings_keeper_names

logger = logging.getLogger(__name__)

# Payload schema version — bump whenever the dossier shape changes (new sections,
# new fields). A cached dossier from an older version is treated as stale and
# rebuilt on next view, so new analysis (game plan, how-they-win/lose, scouting
# notes, …) pulls through for EVERY cache key — whole-club AND each team — without
# waiting on the TTL or a manual refresh.
DOSSIER_VERSION = 10

# Squads change slowly and a rebuild is heavy; a week's freshness with a manual
# Refresh button is the right trade-off.
TTL = timedelta(days=7)
# A 'building' row whose task died (process restart) shouldn't wedge forever.
BUILD_STALE_AFTER = timedelta(minutes=5)
# Single-team mode: a full season of one grade → complete current-season form for
# that side (enough matches that every regular shows up).
MAX_OPP_SEASON_MATCHES = 18
# Whole-club mode: a club fields many teams (one per grade). Scan up to this many
# of their grades, a few recent matches each, capped overall — enough to surface
# every regular across every grade (the missing-players fix) without hammering the
# proxy. First build still lands in the ~10–40s window the UX expects.
MAX_TEAMS_SCOUTED = 8
MAX_MATCHES_PER_TEAM = 8
MAX_TOTAL_SEASON_MATCHES = 44
# Cap the grades touched during team discovery (a club season is well under this).
MAX_DISCOVERY_GRADES = 18
MAX_HEAD_TO_HEAD_GAMES = 25

# '1st XI' < '2nd XI' < … so a club's teams list reads top-down.
_TEAM_ORDINALS = {
    "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5, "6th": 6, "7th": 7, "8th": 8,
    "9th": 9, "10th": 10, "first": 1, "second": 2, "third": 3, "fourth": 4,
    "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
}

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


def _is_redacted_name(name: str | None) -> bool:
    """A CA-redacted junior renders as '********' (or blank). Such a player can
    still be counted in team totals, but must never be a named danger pick or a
    game-plan target — "Get ******** early" helps nobody."""
    n = (name or "").strip()
    return not n or bool(re.fullmatch(r"\*+", n))


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
    # cov_* are the halves of the strike rate. An opponent's card reaches us the
    # same way ours does — CA writes a missing ball count as nothing at all — so
    # the same rule applies: runs and balls from the same innings, never every
    # run over the balls somebody happened to type in. See rate_coverage.py.
    return {"name": name, "inns": 0, "runs": 0, "balls": 0, "outs": 0, "no": 0,
            "fours": 0, "sixes": 0, "hs": None, "hs_no": False,
            "cov_runs": 0, "cov_balls": 0, "cov_inns": 0,
            "dism": Counter(), "scores": [], "matches": set()}


def _new_bowl(name):
    return {"name": name, "balls": 0, "maidens": 0, "runs": 0, "wkts": 0, "spells": 0,
            "cov_runs": 0, "cov_balls": 0, "cov_wkts": 0, "cov_spells": 0,
            "five_fors": 0, "best_w": -1, "best_r": None, "spell_log": [], "matches": set()}


def _bat_coverage(b: dict, runs, balls) -> None:
    """Fold one innings into the covered halves, if it can answer a strike rate."""
    if rc.is_batting_covered(runs, balls):
        b["cov_runs"] += runs or 0
        b["cov_balls"] += balls or 0
        b["cov_inns"] += 1


def _bowl_coverage(bw: dict, runs, overs, balls, wkts) -> None:
    """The bowling twin. ``overs`` is the raw figure; ``balls`` its conversion."""
    if rc.is_bowling_covered(runs, overs):
        bw["cov_runs"] += runs or 0
        bw["cov_balls"] += balls or 0
        bw["cov_wkts"] += wkts or 0
        bw["cov_spells"] += 1


def _new_field(name):
    return {"name": name, "ct": 0, "ct_wk": 0, "ro": 0, "st": 0}


def _accumulate(scorecard: dict, match_id: str, opp_pids: dict[str, str], when: date | None,
                bat: dict, bowl: dict, field: dict, fow: dict | None = None) -> None:
    """Fold one scorecard's opponent rows into the accumulators (in place)."""
    when_s = when.isoformat() if when else None
    for inn in (scorecard.get("innings") or []):
        keeper_names = _innings_keeper_names(inn.get("fielding") or [])
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
            balls = row.get("ballsFaced")
            not_out = dt_id == 1
            b = bat.setdefault(pid, _new_bat(opp_pids[pid]))
            _bat_coverage(b, runs, balls)
            balls = balls or 0
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
                    short = _DISMISSAL_SHORT.get(dt_long, dt_long.lower())
                    if short == "caught" and _caught_by_keeper(row.get("dismissalText") or "", keeper_names):
                        short = "caught behind"
                    b["dism"][short] += 1
            if b["hs"] is None or runs > b["hs"]:
                b["hs"], b["hs_no"] = runs, not_out
            b["scores"].append({"date": when_s, "runs": runs, "balls": balls, "not_out": not_out})

        for row in (inn.get("bowling") or []):
            pid = row.get("participantId")
            if pid not in opp_pids:
                continue
            w = row.get("wicketsTaken") or 0
            r = row.get("runsConceded") or 0
            overs = row.get("oversBowled")
            balls = _overs_to_balls(overs)
            bw = bowl.setdefault(pid, _new_bowl(opp_pids[pid]))
            _bowl_coverage(bw, r, overs, balls, w)
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

        # Fall of wickets → partnership-by-wicket + collapse map. Gated to the
        # opponent's innings the same way (the falling batter is one of theirs);
        # a partnership for wicket k = score_at_fall(k) − score_at_fall(k−1).
        if fow is not None:
            opp_fow = []
            for fw in (inn.get("fallOfWickets") or []):
                if fw.get("participantId") not in opp_pids:
                    continue
                order, runs_at = fw.get("order"), fw.get("runs")
                if order is None or runs_at is None:
                    continue
                try:
                    opp_fow.append((int(order), int(runs_at)))
                except (TypeError, ValueError):
                    continue
            if opp_fow:
                opp_fow.sort(key=lambda x: x[0])
                prev = 0
                for order, runs_at in opp_fow:
                    e = fow.setdefault(order, {"runs": 0, "n": 0, "falls": []})
                    e["runs"] += max(runs_at - prev, 0)
                    e["n"] += 1
                    e["falls"].append(runs_at)
                    prev = runs_at


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
    # Form / "in form" flame. Judged in ABSOLUTE terms first (a batter making 30+
    # right now IS in form) and only then relative to their own baseline (a surge
    # for a modest average). The old purely-relative rule was the bug behind the
    # flame: it never lit up consistently good players (recent ≈ career, so never
    # 25% above) and over-lit weak ones (a single 30 dwarfs a low career average).
    form = None
    if recent_avg is not None and len(recent) >= 3:
        recent_best = max(recent_runs[:3]) if recent_runs else 0
        if (
            recent_avg >= 30
            or recent_best >= 50
            or (recent_avg >= 20 and avg is not None and recent_avg >= avg * 1.3)
        ):
            form = "hot"
        elif recent_avg < 12 and (avg is None or recent_avg < avg * 0.7):
            form = "cold"
        else:
            form = "steady"
    return {
        "player_id": pid,
        "name": b["name"],
        "matches": len(b["matches"]),
        "innings": inns,
        "runs": runs,
        "not_outs": b["no"],
        "high_score": (f"{b['hs']}*" if b["hs_no"] else str(b["hs"])) if b["hs"] is not None else None,
        "average": avg,
        "strike_rate": rc.strike_rate(b["cov_runs"], b["cov_balls"]),
        "strike_rate_coverage": rc.coverage(b["cov_inns"], max(inns, b["cov_inns"])),
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
        "economy": rc.economy(b["cov_runs"], b["cov_balls"]),
        "economy_coverage": rc.coverage(b["cov_spells"], max(b["spells"], b["cov_spells"])),
        "strike_rate": round(b["cov_balls"] / b["cov_wkts"], 2) if b["cov_wkts"] else None,
        "best": (f"{b['best_w']}/{b['best_r']}" if b["best_w"] >= 0 else None),
        "five_fors": b["five_fors"],
        "recent_wickets": [s["wkts"] for s in log[:5]],
    }


async def _synced_opponent_org(session: AsyncSession, opp_key: str) -> str | None:
    """Return the opponent's org id IF they are a synced BetterStats club holding
    game data, else None. ``opp_key`` is their org UUID when synced (the
    COALESCE(opp_org_id, opp_club_name) identity) — the DB-first gate.
    """
    if not _is_uuid(opp_key):
        return None
    hit = (await session.execute(
        text(
            """
            SELECT 1
            FROM seasons s
            JOIN grades gr ON gr.season_id = s.id
            JOIN games g ON g.grade_id = gr.id
            WHERE s.organisation_id = CAST(:org AS UUID)
            LIMIT 1
            """
        ),
        {"org": opp_key},
    )).first()
    return opp_key if hit else None


async def _db_season_accumulators(
    session: AsyncSession, opp_org_id: str,
    grade_filter: str | None = None, team_grade_id: str | None = None,
):
    """Build the dossier's ``season_bat/bowl/field/fow`` accumulators from the
    opponent's OWN stored data — identical in-memory shape to what
    ``_scout_grade`` builds from live Grassroots, so the rest of ``_assemble``
    runs unchanged (no duplicated synthesis).

    Scoped to their latest season **that holds game-level rows** — a stats-less
    season row (e.g. a freshly-seeded comp with no games synced yet) used to pin
    the whole dossier to an empty year, the "SQUAD (0)" symptom. ``pid`` = their
    players' raw participant GUID (``grassroots_id``) so the vs-us records
    (parsed from the GR head-to-head cards, whose participantId is that same
    GUID) key-align. ``grade_filter`` (canonical grade names, ``'||'``-joined)
    and ``team_grade_id`` narrow which of THEIR grades feed the pool — before
    these, a synced opponent's dossier was always whole-club regardless of the
    filter or the chosen team. Returns ``(bat, bowl, field, fow, dates, teams)``.
    """
    bat: dict = {}
    bowl: dict = {}
    field: dict = {}
    fow: dict = {}
    dates: list[date] = []
    teams: list[dict] = []

    yr = (await session.execute(
        text(
            """
            SELECT MAX(s.year) FROM seasons s
            WHERE s.organisation_id = CAST(:org AS UUID) AND s.year IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM grades gr JOIN games g ON g.grade_id = gr.id
                WHERE gr.season_id = s.id
              )
            """
        ),
        {"org": opp_org_id},
    )).scalar()
    if yr is None:
        return bat, bowl, field, fow, dates, teams
    p = {"org": opp_org_id, "yr": yr}
    # Grade narrowing shared by every data query below. Canonical-name matching
    # (merge- and sponsor-aware) so OUR filter bar's vocabulary matches THEIR
    # grade rows; team_grade_id matches either id form (raw CA GUID or PK).
    scope = ""
    if team_grade_id:
        scope += " AND (gr.grassroots_id = :tgid OR gr.id::text = :tgid)"
        p["tgid"] = team_grade_id
    if grade_filter:
        scope += f" AND {grade_match_clause(grade_canonical_label('gr', 'org'))}"
        p["grade"] = grade_filter

    grade_rows = await session.execute(
        text(
            f"""
            SELECT COALESCE(gr.grassroots_id, gr.id::text) AS grade_id,
                   {grade_canonical_label('gr', 'org')} AS grade_name,
                   COUNT(DISTINCT g.id) AS matches
            FROM grades gr
            JOIN seasons s ON s.id = gr.season_id
            LEFT JOIN games g ON g.grade_id = gr.id
            WHERE s.organisation_id = CAST(:org AS UUID) AND s.year = :yr
            GROUP BY 1, 2
            ORDER BY matches DESC NULLS LAST, grade_name
            """
        ),
        {"org": opp_org_id, "yr": yr},
    )
    for r in grade_rows:
        teams.append({"grade_id": r.grade_id, "grade_name": r.grade_name,
                      "team_name": r.grade_name, "matches": int(r.matches or 0)})

    bat_rows = await session.execute(
        text(
            f"""
            SELECT COALESCE(pl.grassroots_id, pl.id::text) AS pid,
                   COALESCE(pl.display_name_override, pl.name) AS name,
                   g.id::text AS match_id, g.played_at,
                   bi.runs, bi.balls, bi.fours, bi.sixes, bi.not_out,
                   bi.dismissal_type, bi.caught_behind
            FROM v_effective_batting_innings bi
            -- Their club's players only. These seasons are theirs, but a fixture
            -- between them and a THIRD synced club is a single `games` row holding
            -- both sides' rows, so scoping the season alone pulls that third club
            -- into the opponent's dossier.
            JOIN players pl ON pl.id = bi.player_id AND pl.organisation_id = CAST(:org AS UUID)
            JOIN v_effective_games g ON g.id = bi.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = CAST(:org AS UUID) AND s.year = :yr
              AND NOT COALESCE(bi.did_not_bat, FALSE)
              AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
              {scope}
            """
        ),
        p,
    )
    for r in bat_rows:
        b = bat.setdefault(r.pid, _new_bat(r.name))
        runs, balls = r.runs or 0, r.balls or 0
        _bat_coverage(b, r.runs, r.balls)
        when_s = r.played_at.isoformat() if r.played_at else None
        b["inns"] += 1
        b["runs"] += runs
        b["balls"] += balls
        b["fours"] += r.fours or 0
        b["sixes"] += r.sixes or 0
        b["matches"].add(r.match_id)
        if r.not_out:
            b["no"] += 1
        else:
            b["outs"] += 1
            if r.dismissal_type:
                # Normalise to the same keys the live path uses, and split out
                # caught-behind (kept off dismissal_type as a separate bool col).
                dt = r.dismissal_type.strip().lower()
                if dt in ("caught and bowled", "caught & bowled", "c & b", "c and b"):
                    dt = "c&b"
                elif dt == "caught" and r.caught_behind:
                    dt = "caught behind"
                b["dism"][dt] += 1
        if b["hs"] is None or runs > b["hs"]:
            b["hs"], b["hs_no"] = runs, bool(r.not_out)
        b["scores"].append({"date": when_s, "runs": runs, "balls": balls, "not_out": bool(r.not_out)})
        if r.played_at:
            dates.append(r.played_at)

    bowl_rows = await session.execute(
        text(
            f"""
            SELECT COALESCE(pl.grassroots_id, pl.id::text) AS pid,
                   COALESCE(pl.display_name_override, pl.name) AS name,
                   g.id::text AS match_id, g.played_at,
                   bs.overs, bs.maidens, bs.runs, bs.wickets
            FROM v_effective_bowling_spells bs
            JOIN players pl ON pl.id = bs.player_id AND pl.organisation_id = CAST(:org AS UUID)
            JOIN v_effective_games g ON g.id = bs.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = CAST(:org AS UUID) AND s.year = :yr
              {scope}
            """
        ),
        p,
    )
    for r in bowl_rows:
        bw = bowl.setdefault(r.pid, _new_bowl(r.name))
        w, runs = r.wickets or 0, r.runs or 0
        balls = _overs_to_balls(float(r.overs)) if r.overs is not None else 0
        _bowl_coverage(bw, runs, r.overs, balls, w)
        when_s = r.played_at.isoformat() if r.played_at else None
        bw["balls"] += balls
        bw["maidens"] += r.maidens or 0
        bw["runs"] += runs
        bw["wkts"] += w
        bw["spells"] += 1
        bw["matches"].add(r.match_id)
        if w >= 5:
            bw["five_fors"] += 1
        if w > bw["best_w"] or (w == bw["best_w"] and (bw["best_r"] is None or runs < bw["best_r"])):
            bw["best_w"], bw["best_r"] = w, runs
        bw["spell_log"].append({"date": when_s, "wkts": w, "runs": runs, "balls": balls})

    field_rows = await session.execute(
        text(
            f"""
            SELECT COALESCE(pl.grassroots_id, pl.id::text) AS pid,
                   COALESCE(pl.display_name_override, pl.name) AS name,
                   SUM(fs.catches) AS ct, SUM(fs.catches_wk) AS ct_wk,
                   SUM(fs.run_outs) AS ro, SUM(fs.stumpings) AS st
            FROM v_effective_fielding_stats fs
            JOIN players pl ON pl.id = fs.player_id AND pl.organisation_id = CAST(:org AS UUID)
            JOIN v_effective_games g ON g.id = fs.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = CAST(:org AS UUID) AND s.year = :yr
              {scope}
            GROUP BY 1, 2
            """
        ),
        p,
    )
    for r in field_rows:
        f = _new_field(r.name)
        f["ct"], f["ct_wk"], f["ro"], f["st"] = int(r.ct or 0), int(r.ct_wk or 0), int(r.ro or 0), int(r.st or 0)
        field[r.pid] = f

    # Partnership-by-wicket / collapse map from their stored partnerships.
    # `is_club_innings IS TRUE` is NOT a club filter on a shared fixture — a
    # match between the opponent and a THIRD synced club is one `games` row and
    # both clubs stamp their own innings TRUE — so one batter side must also
    # resolve to the opponent's own roster (both batters in a stand are from the
    # same innings, so scoping either side excludes the third club's stands).
    # Cumulative partnership runs within an innings == the score at each fall,
    # so we recover the live fow shape exactly.
    part_rows = await session.execute(
        text(
            f"""
            SELECT g.id::text AS match_id, pt.innings_number, pt.wicket_number, pt.runs
            FROM v_effective_partnerships pt
            JOIN v_effective_games g ON g.id = pt.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            LEFT JOIN players b1 ON b1.id = pt.batter1_id
            LEFT JOIN players b2 ON b2.id = pt.batter2_id
            WHERE s.organisation_id = CAST(:org AS UUID) AND s.year = :yr
              AND pt.is_club_innings IS TRUE
              AND (b1.organisation_id = CAST(:org AS UUID)
                   OR b2.organisation_id = CAST(:org AS UUID))
              {scope}
            ORDER BY g.id, pt.innings_number, pt.wicket_number
            """
        ),
        p,
    )
    cur_key = None
    cumulative = 0
    for r in part_rows:
        key = (r.match_id, r.innings_number)
        if key != cur_key:
            cur_key, cumulative = key, 0
        runs = r.runs or 0
        cumulative += runs
        e = fow.setdefault(r.wicket_number, {"runs": 0, "n": 0, "falls": []})
        e["runs"] += max(runs, 0)
        e["n"] += 1
        e["falls"].append(cumulative)

    return bat, bowl, field, fow, dates, teams


def _danger_index_bat(p: dict) -> float:
    """Rank batters by output, leaning on recent form. Explainable, not magic.

    The average is SHRUNK toward a modest club baseline (20) by three phantom
    dismissals before it counts — a raw average off one or two innings used to
    dominate this index, which is how a two-knock cameo topped the "remove
    early" tile over a 400-run regular. (runs + 3*20) / (outs + 3) reads as
    "what the average looks like after three more ordinary innings"."""
    runs = p.get("runs") or 0
    outs = (p.get("innings") or 0) - (p.get("not_outs") or 0)
    shrunk = (runs + 60) / (max(outs, 0) + 3)
    base = shrunk * 0.5 + runs * 0.05
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


def _cache_key(opp_key: str, team_grade_id: str | None, grade_filter: str | None = None) -> str:
    """Dossier cache key. A team-scoped dossier is cached separately from the
    whole-club one (and from other teams) by suffixing the chosen grade; a
    grade-FILTERED dossier likewise — a dossier built under one filter must
    never be served under another (the filter changes which of their grades
    feed the pool). Bare ``opp_key`` stays the unfiltered whole-club key, so
    prewarm and Ask IQ keep hitting the same rows they always did."""
    key = opp_key
    if team_grade_id:
        key += f"::team::{team_grade_id}"
    if grade_filter:
        # Deterministic + short: the filter is a '||'-joined name list.
        import hashlib
        key += "::gf::" + hashlib.sha1(grade_filter.encode("utf-8")).hexdigest()[:12]
    return key


async def get_or_start_dossier(
    session: AsyncSession,
    org_id: str,
    opp_key: str,
    *,
    opp_name: str | None = None,
    grade_id: str | None = None,
    team_grade_id: str | None = None,
    grade_filter: str | None = None,
    force: bool = False,
) -> dict:
    """Return a ready dossier, or kick off a background build and report status.

    The router polls this: ``{status: 'building'}`` until the task finishes, then
    ``{status: 'ready', ...payload}``. ``force`` (Refresh button) rebuilds even a
    fresh cache hit. ``team_grade_id`` narrows the squad+form scout to one of the
    opponent's teams (a grade); ``None`` scouts the whole club across all their
    grades. ``grade_id`` is the fixture's grade — a hint for which season to scout.
    ``grade_filter`` is the IQ filter bar's grade selection (canonical names,
    ``'||'``-joined) — it narrows which of THEIR grades are scouted, so a
    filtered page never headlines a player from a side outside the filter.
    """
    cache_key = _cache_key(opp_key, team_grade_id, grade_filter)
    row = await _load_row(session, org_id, cache_key)
    now = datetime.now(timezone.utc)

    def _fresh(r):
        return (r and r.status == "ready" and r.built_at and (now - r.built_at) < TTL
                and (r.payload or {}).get("schema_v") == DOSSIER_VERSION)

    if _fresh(row) and not force:
        return {"status": "ready", "cached": True, **(row.payload or {})}

    building = row and row.status == "building" and row.updated_at and (now - row.updated_at) < BUILD_STALE_AFTER
    if building and not force:
        return {
            "status": "building",
            "opponent": {"opp_key": opp_key, "name": row.opp_name or opp_name},
        }

    # Mark building and launch the detached build (its own session).
    await _upsert(session, org_id, cache_key, opp_name=opp_name, status="building", error=None)
    task = asyncio.create_task(_run_build(org_id, cache_key, opp_key, opp_name, grade_id, team_grade_id, grade_filter))
    _BUILD_TASKS.add(task)
    task.add_done_callback(_BUILD_TASKS.discard)
    return {"status": "building", "opponent": {"opp_key": opp_key, "name": opp_name}}


async def _run_build(org_id: str, cache_key: str, opp_key: str, opp_name: str | None,
                     grade_hint: str | None, team_grade_id: str | None,
                     grade_filter: str | None = None) -> None:
    async with async_session_maker() as session:
        try:
            payload = await _assemble(session, org_id, opp_key, opp_name, grade_hint, team_grade_id, grade_filter)
            await _upsert(
                session, org_id, cache_key,
                opp_name=payload.get("opponent", {}).get("name") or opp_name,
                status="ready", payload=payload, built_at=datetime.now(timezone.utc), error=None,
            )
            logger.info(f"BetterIQ: dossier built for org={org_id} opp={cache_key}")
        except Exception as e:  # never leave the row wedged at 'building'
            logger.exception(f"BetterIQ: dossier build failed for org={org_id} opp={cache_key}: {e}")
            try:
                await _upsert(session, org_id, cache_key, status="error", error=str(e)[:500])
            except Exception:
                pass


# ─── the build itself ────────────────────────────────────────────────────────

async def _our_games_vs(session: AsyncSession, org_id: str, opp_key: str,
                        grade_filter: str | None = None) -> list[dict]:
    # Org-scoped off the view's own organisation_id (migration 169) with grades
    # LEFT JOINed, so a grade-less manual game still lists (it has no GR
    # scorecard, so the fetch loop skips it harmlessly — but it must not error
    # out of the universe). With a grade filter, the vs-us pool narrows to games
    # in the filtered grade(s) so the head-to-head matches the page's header.
    extra = f"AND {grade_match_clause(grade_canonical_label('gr', 'org'))}" if grade_filter else ""
    params: dict = {"org": org_id, "opp_key": opp_key}
    if grade_filter:
        params["grade"] = grade_filter
    res = await session.execute(
        text(
            f"""
            SELECT g.id::text AS id, g.played_at,
                   COALESCE(gr.grassroots_id, g.grade_id::text) AS grade_id, g.venue
            FROM v_effective_games g
            LEFT JOIN grades gr ON gr.id = g.grade_id
            WHERE g.organisation_id = CAST(:org AS UUID)
              AND COALESCE(g.opp_org_id, g.opp_club_name) = :opp_key
              {extra}
            ORDER BY g.played_at DESC NULLS LAST
            """
        ),
        params,
    )
    return [dict(r) for r in res.mappings()]


# ─── opponent team / grade discovery ─────────────────────────────────────────

def _team_is_opponent(t: dict, *, opp_org_id: str | None, opp_name: str | None) -> bool:
    """Does this ``teams[]`` entry belong to the opponent (by org id or club name)?"""
    org = t.get("owningOrganisation") or {}
    if opp_org_id and _norm(org.get("id")) == _norm(opp_org_id):
        return True
    target = _club_norm(opp_name)
    if target and target in (
        _club_norm(org.get("name")), _club_norm(org.get("displayName")),
        _club_norm(t.get("displayName") or t.get("name")),
    ):
        return True
    return False


def _team_rank(name: str | None) -> int:
    """Sort key so '1st XI' precedes '2nd XI'; named/unknown sides fall to the back."""
    n = _norm(name)
    for word, rank in _TEAM_ORDINALS.items():
        if word in n:
            return rank
    m = re.search(r"\b(\d{1,2})\b", n)
    return int(m.group(1)) if m else 50


def _match_list_date(m: dict) -> date | None:
    """Best-effort match date from a grade-matches list entry (schema varies)."""
    for key in ("matchSchedule", "schedule"):
        for sched in (m.get(key) or []):
            iso = sched.get("startDateTime") or sched.get("startDate") or ""
            if iso:
                try:
                    return date.fromisoformat(iso[:10])
                except ValueError:
                    pass
    for key in ("startDateTime", "startDate", "date"):
        iso = m.get(key) or ""
        if iso:
            try:
                return date.fromisoformat(str(iso)[:10])
            except ValueError:
                pass
    return None


async def _grade_name(session: AsyncSession, grade_id: str) -> str | None:
    # grade_id in the opponent flow is the raw CA grade GUID (so it works against
    # the grassroots API), which for a per-club grade differs from our PK — match
    # on either form.
    res = await session.execute(
        text("SELECT name FROM grades WHERE id::text = :g OR grassroots_id = :g LIMIT 1"),
        {"g": grade_id},
    )
    row = res.mappings().first()
    return row["name"] if row else None


async def _target_season_id(session: AsyncSession, org_id: str, opp_key: str | None, grade_hint: str | None) -> str | None:
    """The season we should scout the opponent in.

    Precedence: the fixture's grade season → the season of our most recent
    meeting → our latest season. Exposed separately from the grade listing so
    ``_assemble`` can echo WHICH season the dossier was actually built against
    (a dossier keyed off an old meeting used to be labelled "this season").
    """
    if grade_hint:
        res = await session.execute(
            text("SELECT season_id::text AS sid FROM grades WHERE id = CAST(:g AS UUID)"),
            {"g": grade_hint},
        )
        row = res.mappings().first()
        if row:
            return row["sid"]
    if opp_key:
        res = await session.execute(
            text(
                """
                SELECT gr.season_id::text AS sid
                FROM v_effective_games g
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id
                WHERE s.organisation_id = CAST(:org AS UUID)
                  AND COALESCE(g.opp_org_id, g.opp_club_name) = :opp
                ORDER BY g.played_at DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"org": org_id, "opp": opp_key},
        )
        row = res.mappings().first()
        if row:
            return row["sid"]
    res = await session.execute(
        text(
            """
            SELECT id::text AS sid FROM seasons
            WHERE organisation_id = CAST(:org AS UUID)
            ORDER BY COALESCE(display_order, 999999) ASC, year DESC NULLS LAST
            LIMIT 1
            """
        ),
        {"org": org_id},
    )
    row = res.mappings().first()
    return row["sid"] if row else None


async def _target_season_grades(
    session: AsyncSession, org_id: str, season_id: str | None, grade_filter: str | None = None,
) -> list[tuple[str, str]]:
    """All (grade_id, grade_name) in the season we should scout the opponent in.

    A club fields one team per grade per season, so a season's grades are the
    universe of their 'teams' we can see. ``grade_filter`` (the IQ filter bar's
    ``'||'``-joined canonical grade names) narrows that universe — THE fix for a
    lower-grade opponent player headlining a filtered scout: without it, every
    grade our club fields a side in was scouted regardless of the filter.
    Returned names are the canonical (merge- and sponsor-aware) labels so the
    frontend's grade matching agrees with the filter bar's own vocabulary.
    """
    if not season_id:
        return []
    # gid feeds the grassroots /scores/grades/{id}/matches API, which is keyed on
    # the shared raw CA grade GUID — use grassroots_id (== id for legacy grades),
    # not the (possibly per-club uuid5) primary key.
    extra = f"AND {grade_match_clause(grade_canonical_label('grades', 'org'))}" if grade_filter else ""
    params: dict = {"sid": season_id, "org": org_id}
    if grade_filter:
        params["grade"] = grade_filter
    res = await session.execute(
        text(
            f"SELECT COALESCE(grassroots_id, id::text) AS gid, "
            f"{grade_canonical_label('grades', 'org')} AS gname "
            f"FROM grades WHERE season_id = CAST(:sid AS UUID) {extra}"
        ),
        params,
    )
    return [(r["gid"], r["gname"]) for r in res.mappings()]


async def _discover_opponent_teams(
    session: AsyncSession, org_id: str, opp_key: str | None, opp_name: str | None,
    grade_hint: str | None, grade_filter: str | None = None,
) -> tuple[list[dict], str | None, bool, bool]:
    """The opponent's teams this season = the grades they field a side in.

    Returns ``([{grade_id, grade_name, team_name, matches}], opp_org_id,
    external, grade_filter_matched)`` — each entry a selectable 'team'.
    ``opp_org_id`` is resolved opportunistically from the first matching team's
    owning org (handy when we only had a club name). ``external`` flags that the
    teams came from the club's OWN org endpoints rather than our grades (see
    below). When ``grade_filter`` narrows discovery to nothing (they field no
    side in the filtered grade), discovery retries unfiltered and
    ``grade_filter_matched`` comes back False so the UI can say so instead of
    silently showing the whole club as if it were the filtered view.
    """
    opp_org_id = opp_key if _is_uuid(opp_key) else None
    season_id = await _target_season_id(session, org_id, opp_key, grade_hint)
    season_grades = await _target_season_grades(session, org_id, season_id, grade_filter)
    grade_filter_matched = True
    if grade_filter and not season_grades:
        season_grades = await _target_season_grades(session, org_id, season_id, None)
        grade_filter_matched = False
    async def _teams_in(grades_list: list[tuple[str, str]]) -> list[dict]:
        nonlocal opp_org_id
        found: list[dict] = []
        for gid, gname in grades_list[:MAX_DISCOVERY_GRADES]:
            try:
                matches = await gr.get_grade_matches(gid)
            except Exception:
                matches = []
            team_name = None
            count = 0
            for m in matches:
                hit = next(
                    (t for t in (m.get("teams") or [])
                     if _team_is_opponent(t, opp_org_id=opp_org_id, opp_name=opp_name)),
                    None,
                )
                if not hit:
                    continue
                count += 1
                if not team_name:
                    team_name = hit.get("displayName") or hit.get("name")
                if not opp_org_id:
                    oid = (hit.get("owningOrganisation") or {}).get("id")
                    if oid:
                        opp_org_id = oid
            if count:
                found.append({"grade_id": gid, "grade_name": gname, "team_name": team_name or gname, "matches": count})
        found.sort(key=lambda d: (_team_rank(d["team_name"]), d["grade_name"] or ""))
        return found

    teams = await _teams_in(season_grades)
    if not teams and grade_filter and grade_filter_matched:
        # The grades matched the filter but the opponent fields no side in any of
        # them (e.g. filtered to our 1st-grade comp, they only play lower grades)
        # — retry unfiltered rather than shipping an empty scout, and say so.
        grade_filter_matched = False
        teams = await _teams_in(await _target_season_grades(session, org_id, season_id, None))

    external = False
    if not teams and opp_org_id:
        # The club fields no side in any grade we hold — a different association,
        # the division we've just been relegated into, or any club picked from
        # the CA-wide search. Enumerate THEIR seasons/teams from the public org
        # endpoints instead; the grade GUIDs feed _scout_grade unchanged.
        from app.services import iq_scout  # lazy: iq_scout imports our helpers
        try:
            teams = await iq_scout.external_club_teams(opp_org_id)
            external = bool(teams)
        except Exception as e:
            logger.warning(f"BetterIQ: external team discovery failed for {opp_org_id}: {e}")
    return teams, opp_org_id, external, grade_filter_matched


async def _scout_grade(
    grade_id: str, *, our_org_id: str, opp_org_id: str | None, opp_name: str | None, cap: int,
    bat: dict, bowl: dict, field: dict, dates: list, seen: set, fow: dict | None = None,
) -> int:
    """Fold up to ``cap`` of the opponent's most-recent matches in one grade into
    the accumulators (in place). Returns how many were scouted."""
    try:
        grade_matches = await gr.get_grade_matches(grade_id)
    except Exception as e:
        logger.warning(f"BetterIQ: grade {grade_id} matches failed: {e}")
        return 0
    opp_matches = [
        m for m in grade_matches
        if any(_team_is_opponent(t, opp_org_id=opp_org_id, opp_name=opp_name) for t in (m.get("teams") or []))
    ]
    opp_matches.sort(key=lambda m: (_match_list_date(m) or date.min), reverse=True)
    scouted = 0
    for m in opp_matches:
        if scouted >= cap:
            break
        mid = m.get("id")
        if not mid or mid in seen:
            continue
        seen.add(mid)
        sc = await gr.get_match_scorecard(mid)
        if not sc:
            continue
        opp_team = _find_opponent_team(sc, our_org_id=our_org_id, opp_org_id=opp_org_id, opp_name=opp_name)
        if not opp_team:
            continue
        roster = _team_roster(opp_team)
        if not roster:
            continue
        when = _match_date(sc)
        if when:
            dates.append(when)
        _accumulate(sc, mid, roster, when, bat, bowl, field, fow)
        scouted += 1
    return scouted


def _ordinal(n: int) -> str:
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")


# Wickets from here on are the tail — a low 9th/10th-wicket stand is expected,
# not an insight, so it's never flagged as a weakness anywhere.
_TAIL_WICKET = 8


def _partnership_insight(partnerships: list[dict]) -> str | None:
    """A one-line read on where their batting is strong vs *genuinely* fragile.

    Deliberately ignores the tail (8th wicket on): a cheap last-wicket stand is
    obvious, not actionable. We surface real tells instead — opener reliance, and
    a top/middle-order wicket that's weak relative to the stands around it."""
    qualified = [p for p in partnerships if p["samples"] >= 3 and p["avg_partnership"] is not None]
    if len(qualified) < 3:
        return None
    top_mid = [p for p in qualified if p["wicket"] < _TAIL_WICKET]
    if not top_mid:
        return None
    strongest = max(qualified, key=lambda p: p["avg_partnership"])
    bits: list[str] = []
    # Opener reliance — a genuine tell when the opening stand dwarfs the rest.
    openers = [p for p in qualified if p["wicket"] <= 2]
    rest = [p for p in qualified if 3 <= p["wicket"] < _TAIL_WICKET]
    if openers and rest:
        best_open = max(openers, key=lambda p: p["avg_partnership"])
        avg_rest = sum(p["avg_partnership"] for p in rest) / len(rest)
        if best_open["avg_partnership"] >= 30 and best_open["avg_partnership"] >= avg_rest * 1.8:
            bits.append(
                f"They lean on their openers — the {_ordinal(best_open['wicket'])}-wicket stand averages "
                f"{best_open['avg_partnership']:.2f} but the middle order is far thinner; break it early and the scoring stalls."
            )
    # A real soft spot in the top/middle order (never the tail).
    soft = min((p for p in top_mid if p["wicket"] >= 2), key=lambda p: p["avg_partnership"], default=None)
    if soft and soft["avg_partnership"] < strongest["avg_partnership"] * 0.5:
        bits.append(
            f"There's a soft spot at the {_ordinal(soft['wicket'])} wicket (just {soft['avg_partnership']}) — "
            "a strike there tends to trigger a slide."
        )
    if not bits:
        bits.append(f"Their strongest stand is the {_ordinal(strongest['wicket'])} wicket (avg {strongest['avg_partnership']}).")
    return " ".join(bits)


# ─── scouting synthesis (rule-based; the "digital analyst" layer) ─────────────
# Turns the assembled numbers into per-player key-notes, team tendencies and a
# game plan. Everything here is scorecard-derivable; sample-size drives a
# confidence flag (brief §19.5) so we never overstate a thin read.

def _confidence(samples: int) -> str:
    if (samples or 0) >= 8:
        return "high"
    if (samples or 0) >= 3:
        return "medium"
    return "low"


# Descriptive observation for a dominant dismissal mode (the NOTE). The matching
# tactical PLAN lives in iq_phrases. Cricket logic matters here — a batter who
# "holes out" (caught) is mishitting to fielders, so the plan pushes catchers OUT
# into the deep (NOT "keep catchers in", which was the old, wrong wording).
_DISMISSAL_NOTE = {
    "bowled": "Gets bowled more than most — beaten through the gate.",
    "lbw": "Falls lbw regularly — vulnerable playing across the line.",
    "caught": "Tends to hole out — he finds the fielder with the big shot.",
    "caught behind": "Nicks off more often than most — feels for the ball outside off.",
    "c&b": "Has a habit of driving it straight back to the bowler.",
    "stumped": "Can be drawn out of his crease and stumped.",
    "run out": "Has been run out a few times — suspect between the wickets.",
    "hit wicket": "Has been hit-wicket — gets cramped on the back foot.",
}


def _enrich_batter(b: dict, rank: int) -> None:
    outs = sum((b.get("dismissals") or {}).values())
    b["confidence"] = _confidence(b.get("innings"))
    avg = b.get("average")
    arch = iq_phrases.batter_archetype(b, rank)
    seed = b.get("player_id") or b.get("name") or ""
    # A rotating, archetype-aware scouting description (varied per player) plus a
    # concise factual line — so two danger bats never read the same.
    avg_s = f"{avg:.2f}" if avg is not None else "—"
    stat = f"{b['runs']:,} runs @ {avg_s} this season"
    if b.get("form") == "hot":
        stat += " and striking it well"
    elif b.get("form") == "cold":
        stat += ", though out of touch lately"
    bits = [iq_phrases.batter_note(arch, seed), stat + "."]

    # Dismissal pattern → a NOTE (how he gets out) + the matching tactical PLAN.
    dism = b.get("dismissals") or {}
    dominant = None
    if outs >= 3 and dism:
        top, cnt = max(dism.items(), key=lambda kv: kv[1])
        if cnt / outs >= 0.4:
            dominant = top
    if dominant and dominant in _DISMISSAL_NOTE:
        bits.append(_DISMISSAL_NOTE[dominant])
    # Caught behind is a high-value, specific tell — surface it even when it isn't
    # the single dominant mode (the user's ask: "nicks off more than usual").
    cb = dism.get("caught behind", 0)
    if outs >= 3 and cb >= 2 and cb / outs >= 0.25 and dominant != "caught behind":
        bits.append(_DISMISSAL_NOTE["caught behind"])
        if dominant is None:
            dominant = "caught behind"
    plan = iq_phrases.batter_plan(arch, dominant, seed)

    vs = b.get("vs_us")
    # A vs-us average needs a real sample behind it — one good knock used to
    # print "averages 68.00 against us" as if it were a career-long pattern.
    vs_sound = bool(vs and vs.get("average") and (vs.get("innings") or 0) >= 3)
    if vs_sound and (avg is None or vs["average"] >= avg):
        bits.append(f"Averages {vs['average']:.2f} against us ({vs['innings']} inns).")

    # Danger vs paper-tiger read (brief §16.2/16.3). Be inclusive about danger so
    # the *obvious* threats (top scorer, in form, high average, history vs us) all
    # light up — the old rule only fired on hot form / vs-us, so a quietly elite
    # accumulator went unflagged. "Paper tiger" is reserved for thin or flattering
    # profiles with no live danger signal.
    inns = b.get("innings") or 0
    hs_num = int(str(b.get("high_score") or "0").rstrip("*") or 0)
    flattered = inns >= 4 and (b.get("not_outs") or 0) / inns >= 0.4
    sound = b.get("confidence") != "low"  # enough innings to trust the average
    danger_reasons, caution_reasons = [], []
    if rank == 0:
        danger_reasons.append("their leading run-scorer")
    if b.get("form") == "hot":
        danger_reasons.append("in hot form")
    # A big average is only a *danger* signal off a sound, un-flattered sample —
    # otherwise it's a paper-tiger tell handled below.
    if avg is not None and avg >= 35 and sound and not flattered:
        danger_reasons.append(f"averages {avg:.2f}")
    if vs_sound and vs["average"] >= 30 and (avg is None or vs["average"] >= avg):
        danger_reasons.append(f"{vs['average']:.2f} vs us ({vs['innings']} inns)")
    if (b.get("fifties") or 0) + (b.get("hundreds") or 0) >= 3:
        danger_reasons.append("piles up big scores")
    if flattered and avg:
        caution_reasons.append("average flattered by not-outs")
    if inns >= 4 and b.get("runs") and hs_num / b["runs"] >= 0.45:
        caution_reasons.append("leans on one big score")
    if b.get("confidence") == "low":
        caution_reasons.append("small sample")
    if b.get("strike_rate") is not None and b["strike_rate"] < 55 and inns >= 5:
        caution_reasons.append("slow scorer, containable")
    level = "danger" if danger_reasons else ("caution" if caution_reasons else None)
    b["alert"] = {"level": level, "danger": danger_reasons, "caution": caution_reasons} if level else None
    b["risk"] = "high" if level == "danger" else ("low" if level == "caution" else "medium")
    b["key_note"], b["plan"] = " ".join(bits), plan


def _enrich_bowler(b: dict, rank: int) -> None:
    b["confidence"] = _confidence(b.get("matches"))
    avg = b.get("average")
    econ = b.get("economy")
    arch = iq_phrases.bowler_archetype(b, rank)
    seed = b.get("player_id") or b.get("name") or ""
    avg_s = f"{avg:.2f}" if avg is not None else "—"
    stat = f"{b['wickets']:,} wicket{'' if b['wickets'] == 1 else 's'} @ {avg_s}"
    if econ is not None:
        stat += f", economy {econ:.2f}"
    bits = [iq_phrases.bowler_note(arch, seed), stat + "."]
    tight = econ is not None and econ < 4.0
    vs = b.get("vs_us")
    if vs and vs.get("wickets"):
        bits.append(f"Has {vs['wickets']:,} wicket{'' if vs['wickets'] == 1 else 's'} against us before.")
    b["key_note"] = " ".join(bits)
    b["plan"] = iq_phrases.bowler_plan(arch, seed)

    danger_reasons, caution_reasons = [], []
    if rank == 0:
        danger_reasons.append("their leading wicket-taker")
    if (b.get("wickets") or 0) >= 5:
        danger_reasons.append("regular wickets")
    if tight:
        danger_reasons.append("very economical")
    if vs and vs.get("wickets") and vs["wickets"] >= 3:
        danger_reasons.append("has troubled us")
    if b.get("confidence") == "low":
        caution_reasons.append("small sample")
    if econ is not None and econ >= 6.0 and (b.get("wickets") or 0) < 5:
        caution_reasons.append("leaks runs — one to target")
    level = "danger" if danger_reasons else ("caution" if caution_reasons else None)
    b["alert"] = {"level": level, "danger": danger_reasons, "caution": caution_reasons} if level else None
    b["risk"] = "high" if level == "danger" else ("low" if level == "caution" else "medium")


def _how_they_win_lose(batters, bowlers, danger_bowlers, partnerships, mixed_grades: bool = False):
    win, lose = [], []
    total_runs = sum(b.get("runs") or 0 for b in batters)
    top3 = sum((b.get("runs") or 0) for b in sorted(batters, key=lambda x: x.get("runs") or 0, reverse=True)[:3])
    # The top-order concentration read only means something for ONE side: in a
    # whole-club (multi-grade) pool the "top three" are usually from three
    # different XIs, and a thin pool makes any share look concentrated.
    if not mixed_grades and total_runs >= 300 and len(batters) >= 6 and top3 / total_runs >= 0.5:
        pct = round(100 * top3 / total_runs)
        win.append(f"Top-order driven — {pct}% of their runs come from their top three.")
        lose.append(f"Early wickets choke them — {pct}% of their scoring rides on the top three.")
    qualified = [p for p in partnerships if p["samples"] >= 3 and p["avg_partnership"] is not None]
    if qualified:
        strong = max(qualified, key=lambda p: p["avg_partnership"])
        win.append(f"Build through the {_ordinal(strong['wicket'])} wicket — their strongest stand (avg {strong['avg_partnership']}).")
        # Only a TOP/MIDDLE-order soft spot counts — a cheap tail is obvious, not
        # a usable insight, so the 8th wicket on is never flagged here.
        top_mid = [p for p in qualified if 2 <= p["wicket"] < _TAIL_WICKET]
        if top_mid:
            weak = min(top_mid, key=lambda p: p["avg_partnership"])
            if weak["avg_partnership"] < strong["avg_partnership"] * 0.5:
                lose.append(f"Fragile at the {_ordinal(weak['wicket'])} wicket (avg {weak['avg_partnership']}) — get in there and the innings can unravel.")
    real_threats = [b for b in bowlers if (b.get("wickets") or 0) >= 4]
    if len(real_threats) <= 1 and danger_bowlers:
        lose.append(f"Thin attack — {danger_bowlers[0]['name']} is their one real threat; see him off and cash in on the rest.")
    elif len(real_threats) >= 3:
        win.append("Multiple wicket-taking options through the innings.")
    return win, lose


def _game_plan(danger_batters, danger_bowlers, bowlers):
    remove = danger_batters[0] if danger_batters else None
    see_off = danger_bowlers[0] if danger_bowlers else None
    frequent = [b for b in bowlers if (b.get("overs") or 0) >= 8 and b.get("economy") is not None]
    target = max(frequent, key=lambda b: b["economy"]) if frequent else None
    if target and target["economy"] < 5.0:
        target = None
    sn = lambda p: (p["name"].split(",")[0].strip() if p else "")
    parts = []
    if remove:
        parts.append(f"get {sn(remove)} early")
    if see_off:
        parts.append(f"see off {sn(see_off)}")
    if target:
        parts.append(f"cash in on {sn(target)}")
    one_liner = (parts[0][0].upper() + parts[0][1:] + (", then " + ", ".join(parts[1:]) if len(parts) > 1 else "") + ".") if parts else None
    warning = None
    if remove:
        vs = remove.get("vs_us")
        # The vs-us warning needs the same floor _enrich_batter applies: >= 3
        # innings, and a vs-us average that's actually at or above their season
        # form — a single 68 used to headline the whole plan as settled fact.
        if (vs and vs.get("average") and (vs.get("innings") or 0) >= 3
                and (remove.get("average") is None or vs["average"] >= remove["average"])):
            warning = f"{remove['name']} averages {vs['average']:.2f} against us ({vs['innings']} inns)."
        else:
            warning = f"{remove['name']} is their danger man."
    return {
        "remove_early": {"name": remove["name"], "why": remove.get("key_note")} if remove else None,
        "see_off": {"name": see_off["name"], "why": see_off.get("key_note")} if see_off else None,
        "target_bowler": {"name": target["name"], "economy": target.get("economy")} if target else None,
        "key_warning": warning,
        "one_liner": one_liner,
    }


async def _assemble(session: AsyncSession, org_id: str, opp_key: str, opp_name: str | None,
                    grade_hint: str | None, team_grade_id: str | None,
                    grade_filter: str | None = None) -> dict:
    opp_name = opp_name or (opp_key if not _is_uuid(opp_key) else None)
    our_games = await _our_games_vs(session, org_id, opp_key, grade_filter)
    if grade_filter and not our_games:
        # No meetings in the filtered grade — fall back to the club-wide history
        # for the vs-us layer (better than an empty head-to-head; the coverage
        # note says which scope was used).
        our_games = await _our_games_vs(session, org_id, opp_key)
        h2h_grade_filtered = False
    else:
        h2h_grade_filtered = bool(grade_filter)

    # Discover the opponent's teams (= the grades they field a side in this season).
    teams, opp_org_id, external_discovery, grade_filter_matched = await _discover_opponent_teams(
        session, org_id, opp_key, opp_name, grade_hint, grade_filter
    )
    if opp_name is None:
        opp_name = next((t["team_name"] for t in teams), None)
    season_id = await _target_season_id(session, org_id, opp_key, grade_hint)
    season_name = None
    if season_id:
        row = (await session.execute(
            text("SELECT name FROM seasons WHERE id = CAST(:sid AS UUID)"), {"sid": season_id}
        )).mappings().first()
        season_name = row["name"] if row else None

    season_bat: dict = {}
    season_bowl: dict = {}
    season_field: dict = {}
    season_fow: dict = {}
    season_dates: list[date] = []
    season_matches = 0
    teams_scouted = 0
    selected_team_name = None
    scout_grades: list[dict] = []

    # DB-first: when the opponent is itself a synced BetterStats club, build their
    # season form from our own stored data — no live Grassroots card scraping and
    # no re-storing their stats. Everything downstream (finalise, danger sorting,
    # enrichment, game plan, partnerships) is shape-identical, so it's unchanged.
    synced_org = await _synced_opponent_org(session, opp_key)
    db_built = False
    if synced_org:
        season_bat, season_bowl, season_field, season_fow, season_dates, db_teams = \
            await _db_season_accumulators(session, synced_org, grade_filter, team_grade_id)
        season_matches = len(
            {m for b in season_bat.values() for m in b["matches"]}
            | {m for b in season_bowl.values() for m in b["matches"]}
        )
        if not season_matches and (grade_filter or team_grade_id):
            # Narrowed to nothing (they hold no game-level rows in the filtered
            # grade) — retry whole-club rather than shipping an empty squad, and
            # flag it so the UI says the filter couldn't be applied.
            grade_filter_matched = False
            season_bat, season_bowl, season_field, season_fow, season_dates, db_teams = \
                await _db_season_accumulators(session, synced_org)
            season_matches = len(
                {m for b in season_bat.values() for m in b["matches"]}
                | {m for b in season_bowl.values() for m in b["matches"]}
            )
        if season_matches:
            db_built = True
            if not teams and db_teams:
                teams = db_teams
            scout_grades = teams
            if grade_filter and grade_filter_matched:
                # db_teams is the full picker list; the note's "across N teams"
                # should count only the grades the filter actually scoped to.
                wanted = set(grade_filter.split("||"))
                teams_scouted = len([t for t in db_teams if t["grade_name"] in wanted]) or 1
            else:
                teams_scouted = len(db_teams)
        else:
            # Synced club but no usable game-level rows (aggregate-only sync, a
            # failed sync, …) — fall through to the live scout rather than ship
            # an empty squad with full head-to-head (the Murdoch SQUAD (0) bug).
            season_bat, season_bowl, season_field, season_fow, season_dates = {}, {}, {}, {}, []
    if not db_built:
        # Live Grassroots scouting: one chosen team, or the whole club (default, so
        # no player is missed just because they play a different grade).
        if team_grade_id:
            scout_grades = [g for g in teams if g["grade_id"] == team_grade_id]
            if not scout_grades:  # selected a team discovery didn't list — scout it directly
                gn = await _grade_name(session, team_grade_id)
                scout_grades = [{"grade_id": team_grade_id, "grade_name": gn, "team_name": gn or "Selected team", "matches": None}]
            selected_team_name = scout_grades[0]["team_name"]
            per_team_cap, total_cap = MAX_OPP_SEASON_MATCHES, MAX_OPP_SEASON_MATCHES
        else:
            scout_grades = teams[:MAX_TEAMS_SCOUTED]
            if not scout_grades:  # discovery found nothing — fall back to the most-recent-meeting grade
                fb = next((g["grade_id"] for g in our_games if g.get("grade_id")), None)
                if fb:
                    gn = await _grade_name(session, fb)
                    scout_grades = [{"grade_id": fb, "grade_name": gn, "team_name": gn or (opp_name or ""), "matches": None}]
                per_team_cap, total_cap = MAX_OPP_SEASON_MATCHES, MAX_OPP_SEASON_MATCHES
            else:
                per_team_cap, total_cap = MAX_MATCHES_PER_TEAM, MAX_TOTAL_SEASON_MATCHES

        seen_match_ids: set[str] = set()
        for g in scout_grades:
            if season_matches >= total_cap:
                break
            cap = min(per_team_cap, total_cap - season_matches)
            n = await _scout_grade(
                g["grade_id"], our_org_id=org_id, opp_org_id=opp_org_id, opp_name=opp_name, cap=cap,
                bat=season_bat, bowl=season_bowl, field=season_field, dates=season_dates, seen=seen_match_ids,
                fow=season_fow,
            )
            season_matches += n
            if n:
                teams_scouted += 1

    # Head-to-head vs us — re-fetch our stored games against them (club-wide, all
    # seasons, capped, newest first) and parse the opponent's cards specifically
    # against us. Stays club-wide even in single-team mode: a player's record vs us
    # spans grades/seasons, and grade ids are per-season so can't scope it.
    h2h_bat: dict = {}
    h2h_bowl: dict = {}
    h2h_field: dict = {}
    h2h_games = 0
    for game in our_games[:MAX_HEAD_TO_HEAD_GAMES]:
        sc = await gr.get_match_scorecard(game["id"])
        if not sc:
            continue  # manual game / 204 — no CA scorecard
        opp_team = _find_opponent_team(sc, our_org_id=org_id, opp_org_id=opp_org_id, opp_name=opp_name)
        if not opp_team:
            continue
        roster = _team_roster(opp_team)
        if not roster:
            continue
        when = _match_date(sc) or (date.fromisoformat(game["played_at"]) if isinstance(game.get("played_at"), str) else game.get("played_at"))
        _accumulate(sc, game["id"], roster, when, h2h_bat, h2h_bowl, h2h_field)
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
        row["confidence"] = _confidence(row.get("innings"))
        row["redacted"] = _is_redacted_name(row.get("name"))
        batters.append(row)
    batters.sort(key=lambda p: (p["runs"] or 0), reverse=True)

    bowlers = []
    for pid, b in season_bowl.items():
        row = _finalise_bowl(pid, b)
        vs = h2h_bowl_final.get(pid)
        row["vs_us"] = {
            "wickets": vs["wickets"], "average": vs["average"], "economy": vs["economy"], "best": vs["best"],
        } if vs else None
        row["confidence"] = _confidence(row.get("matches"))
        row["redacted"] = _is_redacted_name(row.get("name"))
        bowlers.append(row)
    bowlers.sort(key=lambda p: (p["wickets"] or 0, -(p["average"] or 1e9)), reverse=True)

    keepers = [
        {"player_id": pid, "name": f["name"], "catches": f["ct"], "stumpings": f["st"], "run_outs": f["ro"]}
        for pid, f in season_field.items() if (f["ct_wk"] or f["st"])
    ]
    keepers.sort(key=lambda p: (p["catches"] + p["stumpings"]), reverse=True)

    # A redacted junior can't be a named danger pick or a game-plan target —
    # they stay in the full lists (flagged) so team totals still add up.
    danger_batters = sorted(
        [b for b in batters if not b["redacted"]], key=_danger_index_bat, reverse=True
    )[:5]
    danger_bowlers = sorted(
        [b for b in bowlers if b["wickets"] and not b["redacted"]],
        key=lambda p: (p["wickets"], -(p["average"] or 1e9)), reverse=True
    )[:5]

    # Players who've historically hurt us but aren't in the scouted squad — still
    # worth flagging ("watch for a recall").
    season_pids = set(season_bat) | set(season_bowl)
    threats_history = sorted(
        [r for pid, r in h2h_bat_final.items()
         if pid not in season_pids and (r["runs"] or 0) >= 50 and not _is_redacted_name(r.get("name"))],
        key=lambda p: (p["runs"] or 0), reverse=True,
    )[:5]

    # Team-wide dismissal breakdown — how their batters get out (catch-prone? lbw?).
    team_dism: Counter = Counter()
    for b in season_bat.values():
        team_dism.update(b["dism"])
    total_d = sum(team_dism.values())
    dismissal_breakdown = [
        {"type": k, "count": v, "pct": round(100 * v / total_d)} for k, v in team_dism.most_common()
    ] if total_d else []

    # Partnership / collapse map from their fall-of-wickets.
    partnerships = []
    for wk in sorted(season_fow):
        e = season_fow[wk]
        if not e["n"]:
            continue
        partnerships.append({
            "wicket": wk,
            "avg_partnership": round(e["runs"] / e["n"], 1),
            "samples": e["n"],
            "typical_score_at_fall": round(statistics.median(e["falls"])) if e["falls"] else None,
        })
    # Flag genuine top/middle-order soft spots for the UI; never redden the tail
    # (a low 9th/10th-wicket stand is expected, not a weakness).
    strongest_ps = max((p["avg_partnership"] for p in partnerships if p["samples"] >= 3), default=0)
    for p in partnerships:
        p["tail"] = p["wicket"] >= _TAIL_WICKET
        p["weak"] = bool(
            not p["tail"]
            and p["wicket"] >= 2
            and p["samples"] >= 3
            and strongest_ps > 0
            and p["avg_partnership"] < strongest_ps * 0.5
        )
    partnership_insight = _partnership_insight(partnerships)

    # ── Scouting synthesis: per-player key-notes + how they win/lose + game plan ──
    # Flag the keeper-batters from the real fielding data so they get keeper-aware
    # descriptions/plans (a danger bat who also keeps).
    keeper_ids = {k["player_id"] for k in keepers}
    for db in danger_batters:
        db["is_keeper"] = db.get("player_id") in keeper_ids
    for rank, db in enumerate(danger_batters):
        _enrich_batter(db, rank)
    for rank, db in enumerate(danger_bowlers):
        _enrich_bowler(db, rank)
    mixed_grades = teams_scouted > 1
    how_they_win, how_they_lose = _how_they_win_lose(
        batters, bowlers, danger_bowlers, partnerships, mixed_grades=mixed_grades
    )
    game_plan = _game_plan(danger_batters, danger_bowlers, bowlers)

    coverage = "rich" if season_matches else ("history_only" if h2h_games else "none")
    notes = []
    if db_built and season_matches:
        notes.append(
            f"Built from our own database — {opp_name or 'this opponent'} is a synced "
            f"BetterStats club ({season_matches} of their matches this season)."
        )
    elif team_grade_id and season_matches:
        notes.append(f"Focused on {selected_team_name or 'one team'} — {season_matches} recent matches in this grade.")
    elif external_discovery and season_matches:
        notes.append(
            f"{opp_name or 'This club'} plays outside our competitions — squad & form "
            f"scouted from Cricket Australia's public data ({season_matches} matches "
            f"across {teams_scouted} of their teams)."
        )
    elif season_matches:
        notes.append(
            f"Squad & form built live from {season_matches} matches across "
            f"{teams_scouted} of {opp_name or 'their'} team(s) this season."
        )
    else:
        notes.append("No current-season matches found — showing head-to-head history only.")
    if grade_filter and grade_filter_matched:
        gf_names = ", ".join(grade_filter.split("||"))
        notes.append(f"Scoped to {gf_names} per your filter.")
    elif grade_filter and not grade_filter_matched:
        gf_names = ", ".join(grade_filter.split("||"))
        notes.append(
            f"Your grade filter ({gf_names}) matched none of their sides — showing the whole club instead."
        )
    if season_name:
        notes.append(f"Season scouted: {season_name}.")
    if h2h_games:
        h2h_scope = "in the filtered grade(s)" if h2h_grade_filtered else "across every grade and season we hold"
        notes.append(f"Head-to-head built from {h2h_games} of our games against them, {h2h_scope}.")
    notes.append("Based on scorecards (no ball-by-ball), so no phase or ball-level matchup data.")

    return {
        # org_id = the opponent's CA organisation GUID when known — the key the
        # 5-year player career + deep-pass endpoints (iq_scout) are driven by.
        "opponent": {"opp_key": opp_key, "name": opp_name, "org_id": opp_org_id},
        "coverage": {"level": coverage, "notes": notes},
        "teams": teams,
        "selected_team": team_grade_id,
        "selected_team_name": selected_team_name,
        # The scope this dossier was actually built under — the UI badges it so
        # a filtered header can never sit over an unfiltered scout unremarked.
        "grade_filter": grade_filter.split("||") if grade_filter else None,
        "grade_filter_matched": grade_filter_matched if grade_filter else None,
        "mixed_grades": mixed_grades,
        "scouted": {
            "season_matches": season_matches,
            "teams_scouted": teams_scouted,
            "head_to_head_games": h2h_games,
            "h2h_grade_filtered": h2h_grade_filtered,
            "season_id": season_id,
            "season_name": season_name,
            "span": {
                "from": min(season_dates).isoformat() if season_dates else None,
                "to": max(season_dates).isoformat() if season_dates else None,
            },
            "grade_id": (scout_grades[0]["grade_id"] if scout_grades else None),
        },
        "danger_batters": danger_batters,
        "danger_bowlers": danger_bowlers,
        "batting": batters,
        "bowling": bowlers,
        "keepers": keepers,
        "historical_threats": threats_history,
        "dismissal_breakdown": dismissal_breakdown,
        "partnerships": partnerships,
        "partnership_insight": partnership_insight,
        "how_they_win": how_they_win,
        "how_they_lose": how_they_lose,
        "game_plan": game_plan,
        "schema_v": DOSSIER_VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
