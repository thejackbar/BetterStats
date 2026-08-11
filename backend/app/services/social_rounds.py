"""BetterSocials — round-level fixtures & results sourced from Play.cricket.

The single-scorecard import (admin.get_social_scorecard) pulls one match by id;
these build a whole round across every grade the club plays, shaped for the
Fixtures / Results roundup posts in the Post Designer.

  - Fixtures  : reuses fixtures_source.org_grassroots_fixtures (upcoming/live
                from /scores/grades/{id}/matches, status 0/2), grouped by date.
  - Results   : discovers COMPLETED club matches (status 3) for the org's
                current-season grades, then fetches each match's scorecard
                (same endpoint as the scorecard import) to read team totals and
                win/loss, grouped by date (most-recent first).

Both return ``{season, dates: [{date, label, round, fixtures|results: [...]}]}``;
the frontend lets the operator pick a match-day and fills the editor + Match Info.

Two more builds sit alongside them:

  - *_for_reference : the same round shapes anchored on ONE pasted match link
                      (any status, any date), for the off-season / past-round
                      case where the default pulls come back empty.
  - social_potm     : our side's performances in one match ranked into a
                      player-of-the-match shortlist.
"""
from __future__ import annotations

import asyncio
import re
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import grassroots_scores_client as gr
from app.services.club_match import club_match_keys
from app.services.fixtures_source import _current_grade_rows, org_grassroots_fixtures
from app.services.social_match_lookup import parse_reference
from app.services.sync import strip_team_suffix

# Bound the results scorecard fan-out: at most a few recent match-days / matches.
_RESULT_WINDOW_DAYS = 90
_RESULT_MAX_DATES = 3
_RESULT_MAX_MATCHES = 24

# A pasted match link anchors a whole round: club matches within this many days
# either side of the anchor count as the same round (a Saturday one-dayer and a
# Sunday junior game are one weekend), on top of an exact round-name match
# (which catches the second day of a two-day round).
_ROUND_WINDOW_DAYS = 3

# Player-of-the-match points, from the scorecard's own counting stats. Keeper
# catches score lower than outfield dismissals on purpose (chances come to the
# gloves), maidens are a small bowling tiebreaker.
_POTM_RUN = 1
_POTM_WICKET = 20
_POTM_FIELD_DISMISSAL = 8   # outfield catch, stumping, run out
_POTM_WK_CATCH = 4
_POTM_MAIDEN = 2

# Same dismissal-type semantics as admin.py's single-scorecard import.
_DNB_TYPES = {"did not bat", "dnb", "absent", "absent hurt"}
_NOT_OUT_ID = 1  # dismissalTypeId == 1 means "not out" in GR API


def _label(day: str) -> str:
    """'2026-06-14' -> 'SAT 14 JUN' (no leading zero, uppercase)."""
    try:
        d = date.fromisoformat(day)
    except (ValueError, TypeError):
        return (day or "").upper()
    return f"{d.strftime('%a').upper()} {d.day} {d.strftime('%b').upper()}"


def _mono(name: str) -> str:
    words = [w for w in re.split(r"[^A-Za-z0-9]+", strip_team_suffix(name or "")) if w]
    if not words:
        return "OPP"
    if len(words) == 1:
        return words[0][:3].upper()
    code = "".join(w[0] for w in words[:3]).upper()
    return code if len(code) >= 2 else words[0][:3].upper()


def _to_12h(t: str | None) -> str:
    if not t:
        return ""
    try:
        hh, mm = t.split(":")[:2]
        h, m = int(hh), int(mm)
    except (ValueError, TypeError):
        return t or ""
    ap = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {ap}"


def _round_label(raw: str | None) -> str:
    r = (raw or "").strip()
    if not r:
        return ""
    return r if re.search(r"\d", r) and not r.isdigit() else (f"ROUND {r}" if r.isdigit() else r.upper())


def _team_id_from_inn(inn: dict) -> str | None:
    for k in ("battingTeamId", "teamId"):
        v = inn.get(k)
        if v:
            return str(v).lower()
    for k in ("battingTeam", "team"):
        obj = inn.get(k)
        if isinstance(obj, dict) and obj.get("id"):
            return str(obj["id"]).lower()
    return None


def _score_str(inn: dict | None) -> str | None:
    """'6/188' (AU wickets/runs) or '188' if all out, from an innings dict."""
    if not inn:
        return None
    rs = inn.get("runsScored")
    if rs is None:
        return None
    runs = int(rs)
    wk_raw = inn.get("numberOfWicketsFallen")
    wk = int(wk_raw) if wk_raw is not None else None
    return f"{wk}/{runs}" if (wk is not None and wk < 10) else str(runs)


def _margin_from_text(text: str | None) -> str:
    if not text:
        return ""
    m = re.search(r"\bby\b(.+)$", text, re.IGNORECASE)
    frag = (m.group(1) if m else "").strip()
    if not frag:
        return ""
    frag = frag.upper().replace("WKTS", "WICKETS").replace("WKT", "WICKET")
    return f"BY {frag}".strip()


def _overs_str(overs_raw) -> str:
    """Convert oversBowled string/float to 'X.Y' cricket-notation display string."""
    if overs_raw is None:
        return "0"
    if isinstance(overs_raw, str) and "." in overs_raw:
        return overs_raw
    try:
        balls = int(float(str(overs_raw)) * 6) if "." not in str(overs_raw) else None
        return f"{balls // 6}.{balls % 6}" if balls is not None else str(overs_raw)
    except (TypeError, ValueError):
        return str(overs_raw)


def _perf_name(raw: str | None) -> str:
    """'Surname, First' or 'First Surname' -> 'F. SURNAME' performer label."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    if "," in raw:
        last, first = (x.strip() for x in raw.split(",", 1))
    else:
        parts = raw.split()
        if len(parts) == 1:
            return parts[0].upper().rstrip(".,;:")
        first, last = parts[0], " ".join(parts[1:])
    fi = first[:1].upper()
    last = last.strip().upper().rstrip(".,;:")
    return f"{fi}. {last}" if fi and last else (last or first.upper())


def _top_batters(bat_rows: list) -> list[dict]:
    """Our club's top 2 run scorers from one innings (most runs, fewer balls breaks ties)."""
    cands = [
        b for b in (bat_rows or [])
        if (b.get("dismissalType") or "").lower() not in _DNB_TYPES
        and (int(b.get("runsScored") or 0) > 0 or int(b.get("ballsFaced") or 0) > 0)
    ]
    cands.sort(key=lambda b: (-int(b.get("runsScored") or 0), int(b.get("ballsFaced") or 0)))
    out = []
    for b in cands[:2]:
        name = _perf_name(b.get("playerShortName"))
        if not name:
            continue
        runs = int(b.get("runsScored") or 0)
        balls = int(b.get("ballsFaced") or 0)
        dt_id = b.get("dismissalTypeId") or 0
        dt = (b.get("dismissalType") or "").lower()
        not_out = dt_id == _NOT_OUT_ID or dt == "not out"
        out.append({"name": name, "line": f"{runs}{'*' if not_out else ''} ({balls})"})
    return out


def _top_bowlers(bowl_rows: list) -> list[dict]:
    """Our club's top 2 wicket takers from one innings (most wickets, fewest runs breaks ties)."""
    def overs_val(o):
        try:
            return float(str(o or 0).replace(",", "."))
        except (TypeError, ValueError):
            return 0.0

    cands = [b for b in (bowl_rows or []) if overs_val(b.get("oversBowled")) > 0 or int(b.get("wicketsTaken") or 0) > 0]
    cands.sort(key=lambda b: (-int(b.get("wicketsTaken") or 0), int(b.get("runsConceded") or 0)))
    out = []
    for b in cands[:2]:
        name = _perf_name(b.get("playerShortName"))
        if not name:
            continue
        w = int(b.get("wicketsTaken") or 0)
        r = int(b.get("runsConceded") or 0)
        out.append({"name": name, "line": f"{w}/{r} ({_overs_str(b.get('oversBowled'))})"})
    return out


def _club_dict(org) -> dict:
    name = (org.name or "CLUB")
    logo = org.logo_url or (f"/api/images/organisations/{org.id}/logo" if getattr(org, "logo_data", None) else None)
    return {"name": name.upper(), "full": name.upper(), "mono": _mono(name), "logo": logo}


def _result_row(sc: dict, org, keys: list[str], grade_name: str) -> dict | None:
    """One results-roundup row from a raw Grassroots scorecard, from the club's
    perspective (us / them / W·L·T / margin)."""
    ms = sc.get("matchSummary") or {}
    summary_teams = ms.get("teams") or []
    teams_raw = sc.get("teams") or []
    innings = sc.get("innings") or []
    org_id = str(org.id).lower()

    def is_ours(t: dict) -> bool:
        if ((t.get("owningOrganisation") or {}).get("id") or "").lower() == org_id:
            return True
        dn = (t.get("displayName") or "").lower()
        return any(k in dn for k in keys)

    our_team = next((t for t in teams_raw if is_ours(t)), None)
    if not our_team:
        return None
    our_id = (our_team.get("id") or "").lower()
    opp_team = next((t for t in teams_raw if (t.get("id") or "").lower() != our_id), None)
    opp_id = (opp_team.get("id") or "").lower() if opp_team else None

    inn_by_team = {}
    for i in innings:
        tid = _team_id_from_inn(i)
        if tid and tid not in inn_by_team:
            inn_by_team[tid] = i
    us = _score_str(inn_by_team.get(our_id))
    them = _score_str(inn_by_team.get(opp_id))
    if us is None or them is None:
        return None

    our_inn = inn_by_team.get(our_id) or {}
    top_bat = _top_batters(our_inn.get("batting") or [])
    top_bowl = _top_bowlers(our_inn.get("bowling") or [])

    outcome = "T"
    for st in summary_teams:
        if (st.get("id") or "").lower() != our_id:
            continue
        rt = (st.get("resultType") or "").upper()
        if st.get("isWinner") or rt.startswith("WON"):
            outcome = "W"
        elif rt.startswith("LOST"):
            outcome = "L"
        else:
            outcome = "T"
        break

    opp_name = (opp_team.get("displayName") if opp_team else None) \
        or ((opp_team or {}).get("owningOrganisation") or {}).get("name") or "OPPONENT"
    return {
        "grade": (grade_name or "").upper(),
        "opp": strip_team_suffix(opp_name).upper(),
        "oppMono": _mono(opp_name),
        "us": us,
        "them": them,
        "outcome": outcome,
        "margin": _margin_from_text(ms.get("result") or ms.get("statusText")),
        "topBat": top_bat,
        "topBowl": top_bowl,
    }


async def social_fixtures(db: AsyncSession, org) -> dict:
    """Upcoming/live fixtures for the org, grouped by match-day, shaped for the
    Fixtures roundup posts."""
    fixtures = await org_grassroots_fixtures(db, org)
    keys = club_match_keys(org)
    season = next((fx.get("season_name") for fx in fixtures if fx.get("season_name")), None)
    by_date: dict[str, dict] = {}
    for fx in fixtures:
        home = fx.get("home_team") or ""
        away = fx.get("away_team") or ""
        hl, al = home.lower(), away.lower()
        if any(k in al for k in keys) and not any(k in hl for k in keys):
            ha, opp = "A", home
        else:
            ha, opp = "H", away
        day = fx.get("played_at") or ""
        bucket = by_date.setdefault(day, {"date": day, "label": _label(day), "round": "", "fixtures": []})
        if not bucket["round"]:
            bucket["round"] = _round_label(fx.get("round"))
        bucket["fixtures"].append({
            "grade": (fx.get("grade_name") or "").upper(),
            "opp": strip_team_suffix(opp).upper(),
            "oppMono": _mono(opp),
            "ha": ha,
            "time": _to_12h(fx.get("time")),
            "venue": (fx.get("venue") or "").upper(),
        })
    dates = sorted(by_date.values(), key=lambda d: d["date"])
    return {"season": season, "club": _club_dict(org), "dates": dates}


async def social_results(db: AsyncSession, org) -> dict:
    """Recent completed results for the org, grouped by match-day (most-recent
    first), shaped for the Results roundup posts. Scores/result come from each
    match's scorecard — the same source as the single-scorecard import."""
    rows = await _current_grade_rows(db, org.id)
    if not rows:
        return {"season": None, "club": _club_dict(org), "dates": []}
    keys = club_match_keys(org)
    # Keyed on the raw CA grade guid, which is what a discovered match carries,
    # NOT our own grades.id (the second column). See _current_grade_rows.
    grade_name_by_guid = {guid: gname for guid, _, gname, _ in rows}
    season = next((sname for *_, sname in rows if sname), None)
    since = (date.today() - timedelta(days=_RESULT_WINDOW_DAYS)).isoformat()

    discovered = await asyncio.gather(
        *[gr.get_grade_results(guid, since=since) for guid, *_ in rows],
        return_exceptions=True,
    )
    club_matches: list[dict] = []
    for lst in discovered:
        if not isinstance(lst, list):
            continue
        for m in lst:
            home = (m.get("home_team") or "").lower()
            away = (m.get("away_team") or "").lower()
            if any(k in home or k in away for k in keys):
                club_matches.append(m)

    # De-dup by match id, newest first, then keep only the most-recent few
    # match-days (bounded scorecard fan-out).
    seen: set = set()
    ordered: list[dict] = []
    for m in sorted(club_matches, key=lambda x: x.get("played_at") or "", reverse=True):
        mid = m.get("id")
        if not mid or mid in seen:
            continue
        seen.add(mid)
        ordered.append(m)
    kept: list[dict] = []
    kept_dates: list[str] = []
    for m in ordered:
        day = m.get("played_at") or ""
        if day not in kept_dates:
            if len(kept_dates) >= _RESULT_MAX_DATES:
                break
            kept_dates.append(day)
        kept.append(m)
        if len(kept) >= _RESULT_MAX_MATCHES:
            break

    cards = await asyncio.gather(*[gr.get_match_scorecard(m["id"]) for m in kept], return_exceptions=True)
    by_date: dict[str, dict] = {}
    for m, sc in zip(kept, cards):
        if not isinstance(sc, dict):
            continue
        row = _result_row(sc, org, keys, grade_name_by_guid.get(m.get("grade_id")) or "")
        if not row:
            continue
        day = m.get("played_at") or ""
        bucket = by_date.setdefault(day, {"date": day, "label": _label(day), "round": "", "results": []})
        if not bucket["round"]:
            bucket["round"] = _round_label(m.get("round"))
        bucket["results"].append(row)
    dates = sorted(by_date.values(), key=lambda d: d["date"], reverse=True)
    return {"season": season, "club": _club_dict(org), "dates": dates}


# ── Round anchored on a pasted match link ────────────────────────────────────
# Off-season (or for a past round) the no-argument fixtures/results pulls come
# back empty, so a club pastes any ONE match link from the round and we find
# every grade's match that weekend from the full grade match lists.

_INVALID_REF_MESSAGE = "Paste a match link from play.cricket.com.au, or a match ID"
_PLAYHQ_REF_MESSAGE = (
    "That's a playhq.com link. BetterPosts pulls match data from play.cricket.com.au, "
    "which uses a different match ID. Find the same match on play.cricket.com.au "
    "and paste that link instead."
)
_NOT_FOUND_MESSAGE = (
    "We couldn't match that to one of your club's matches. Check the link is "
    "for a game your club played."
)


def _match_day_time(m: dict) -> tuple[str, str]:
    """('YYYY-MM-DD', 'HH:MM') from a raw grade-match item's schedule."""
    sched = m.get("matchSchedule") or [{}]
    dt = (sched[0].get("startDateTime") if sched else "") or ""
    return dt[:10], (dt[11:16] if len(dt) >= 16 else "")


def _match_home_away(m: dict) -> tuple[str, str]:
    """Prefers ``matchSummary.teams`` (the plain ``/scores/matches/{id}``
    detail carries ``displayName``/``isHome`` only there — its top-level
    ``teams`` is the roster/team-list shape, no names at all) and falls back
    to the top-level array, which is where a grade-matches LIST item (from
    ``/scores/grades/{id}/matches``) carries them instead. One function reads
    both shapes this module deals with."""
    ms_teams = (m.get("matchSummary") or {}).get("teams") or []
    teams = ms_teams or (m.get("teams") or [])
    home = next((t.get("displayName") for t in teams if t.get("isHome")), None) or ""
    away = next((t.get("displayName") for t in teams if not t.get("isHome")), None) or ""
    return home, away


def _match_round_name(m: dict) -> str:
    return ((m.get("round") or {}).get("name") or "").strip()


async def _grade_season(db: AsyncSession, org_id, grade_guid: str):
    """``(season_id, season_name)`` for the org's own season owning a grade
    guid — searched across the org's WHOLE grade history, not just the
    latest-by-year season. Returns ``None`` when the guid isn't one of this
    org's grades at all."""
    res = await db.execute(
        text(
            """
            SELECT s.id, s.name
            FROM grades g
            JOIN seasons s ON s.id = g.season_id
            WHERE s.organisation_id = CAST(:org AS UUID)
              AND COALESCE(g.grassroots_id, g.id::text) = :guid
            LIMIT 1
            """
        ),
        {"org": str(org_id), "guid": grade_guid},
    )
    row = res.first()
    return (row.id, row.name) if row else None


async def _grade_rows_for_season(db: AsyncSession, org_id, season_id) -> list[tuple]:
    """``[(grade_guid, grade_id, grade_name, season_name)]`` for one EXPLICIT
    season — the round-anchored sibling of ``_current_grade_rows``, which
    always means "the org's latest season by year". A pasted link may anchor
    an older season (that's the whole point of the link path — the no-link
    pulls already cover "latest"), so this looks the season up by id
    instead of assuming it's the newest one."""
    res = await db.execute(
        text(
            """
            SELECT DISTINCT COALESCE(g.grassroots_id, g.id::text) AS guid,
                   g.id AS grade_id,
                   COALESCE(g.display_name_override, g.name) AS grade_name,
                   s.name AS season_name
            FROM grades g
            JOIN seasons s ON s.id = g.season_id
            WHERE s.organisation_id = CAST(:org AS UUID) AND s.id = CAST(:season AS UUID)
            """
        ),
        {"org": str(org_id), "season": str(season_id)},
    )
    return [(r.guid, r.grade_id, r.grade_name, r.season_name) for r in res]


async def _reference_round(db: AsyncSession, org, raw: str):
    """Resolve a pasted match reference into the anchor match plus every club
    match in the same round.

    The anchor is fetched DIRECTLY by id (``gr.get_match_detail``) rather than
    found by fanning out across the org's "current" (latest-by-year) season's
    grades — a pasted link is exactly for the case the no-link pulls can't
    reach: an off-season or a past round, which by definition may belong to
    an OLDER season than whatever's currently "latest". The anchor's own
    grade tells us which season it's actually in, and that season's grades
    (not "the latest one") are what get searched for the rest of the round.

    Returns ``(payload, None)`` when the reference can't anchor a round (the
    payload is the invalid/playhq/not_found dict to return as-is), or
    ``(None, ctx)`` where ctx carries the anchor, the round's club matches
    (each ``(grade_guid, raw_match)``), the grade-name map and the season.
    """
    ref = parse_reference(raw)
    if not ref:
        return {"kind": "invalid", "message": _INVALID_REF_MESSAGE}, None
    if ref.get("playhq_code"):
        return {"kind": "playhq", "message": _PLAYHQ_REF_MESSAGE}, None

    match_id = ref.get("match_id") or ""
    anchor = await gr.get_match_detail(match_id)
    if not anchor:
        return {"kind": "not_found", "message": _NOT_FOUND_MESSAGE}, None

    grade_guid = (anchor.get("grade") or {}).get("id")
    season_row = await _grade_season(db, org.id, grade_guid) if grade_guid else None
    if not season_row:
        return {"kind": "not_found", "message": _NOT_FOUND_MESSAGE}, None
    season_id, season = season_row

    keys = club_match_keys(org)
    anchor_home, anchor_away = _match_home_away(anchor)
    if not any(k in anchor_home.lower() or k in anchor_away.lower() for k in keys):
        # A real match, in one of our grades, but not one of our sides — a
        # grade is a whole competition, not club-exclusive.
        return {"kind": "not_found", "message": _NOT_FOUND_MESSAGE}, None

    rows = await _grade_rows_for_season(db, org.id, season_id)
    if not rows:
        return {"kind": "round", "season": season, "club": _club_dict(org), "dates": []}, None
    grade_name_by_guid = {guid: gname for guid, _, gname, _ in rows}

    # Full grade match lists (any status, any date) — the same endpoint the
    # fixtures/results discovery reads, minus their status/date windows, so an
    # off-season or long-finished round is still findable.
    discovered = await asyncio.gather(
        *[gr.get_grade_matches(guid) for guid, *_ in rows],
        return_exceptions=True,
    )
    all_matches: list[tuple[str, dict]] = []
    for (guid, *_), lst in zip(rows, discovered):
        if not isinstance(lst, list):
            continue
        for m in lst:
            all_matches.append((guid, m))

    anchor_day, _ = _match_day_time(anchor)
    try:
        anchor_date = date.fromisoformat(anchor_day)
    except (ValueError, TypeError):
        anchor_date = None
    anchor_round = _match_round_name(anchor).lower()

    kept: list[tuple[str, dict]] = []
    seen: set = set()
    for guid, m in all_matches:
        home, away = _match_home_away(m)
        if not any(k in home.lower() or k in away.lower() for k in keys):
            continue
        day, _tm = _match_day_time(m)
        in_window = False
        if anchor_date and day:
            try:
                in_window = abs((date.fromisoformat(day) - anchor_date).days) <= _ROUND_WINDOW_DAYS
            except ValueError:
                in_window = False
        same_round = bool(anchor_round) and _match_round_name(m).lower() == anchor_round
        if not (in_window or same_round):
            continue
        mid = m.get("id")
        if not mid or mid in seen:
            continue
        seen.add(mid)
        kept.append((guid, m))

    ctx = {
        "anchor": anchor,
        "anchor_day": anchor_day,
        "anchor_round": _match_round_name(anchor),
        "matches": kept,
        "grade_name_by_guid": grade_name_by_guid,
        "season": season,
        "keys": keys,
    }
    return None, ctx


async def social_fixtures_for_reference(db: AsyncSession, org, raw: str) -> dict:
    """The whole round's club fixtures, anchored on one pasted match link.

    Any status is kept (a club may build the fixtures post after some games
    have started, or well after the round). One date bucket, keyed on the
    anchor's date, so the frontend applies dates[0] exactly like the
    no-argument pull."""
    err, ctx = await _reference_round(db, org, raw)
    if err is not None:
        return err
    rows = []
    for guid, m in ctx["matches"]:
        home, away = _match_home_away(m)
        hl, al = home.lower(), away.lower()
        keys = ctx["keys"]
        if any(k in al for k in keys) and not any(k in hl for k in keys):
            ha, opp = "A", home
        else:
            ha, opp = "H", away
        day, tm = _match_day_time(m)
        rows.append((day, tm, {
            "grade": (ctx["grade_name_by_guid"].get(guid) or "").upper(),
            "opp": strip_team_suffix(opp).upper(),
            "oppMono": _mono(opp),
            "ha": ha,
            "time": _to_12h(tm),
            "venue": (((m.get("venue") or {}).get("name")) or "").upper(),
        }))
    rows.sort(key=lambda r: (r[0], r[1]))
    bucket = {
        "date": ctx["anchor_day"],
        "label": _label(ctx["anchor_day"]),
        "round": _round_label(ctx["anchor_round"]),
        "fixtures": [r[2] for r in rows],
    }
    return {"kind": "round", "season": ctx["season"], "club": _club_dict(org), "dates": [bucket]}


async def social_results_for_reference(db: AsyncSession, org, raw: str) -> dict:
    """The whole round's completed club results, anchored on one pasted match
    link. Scores come from each match's scorecard, exactly like social_results;
    only completed matches (statusId 3) in the round window are fetched. The
    anchor itself doesn't have to be completed — whatever the window holds is
    returned."""
    err, ctx = await _reference_round(db, org, raw)
    if err is not None:
        return err
    completed = [
        (guid, m) for guid, m in ctx["matches"]
        if str(m.get("statusId")) == "3"
    ][:_RESULT_MAX_MATCHES]
    if not completed:
        return {"kind": "no_results", "message": "No completed matches found for that round yet."}

    cards = await asyncio.gather(
        *[gr.get_match_scorecard(m.get("id")) for _, m in completed],
        return_exceptions=True,
    )
    results = []
    for (guid, m), sc in zip(completed, cards):
        if not isinstance(sc, dict):
            continue
        row = _result_row(sc, org, ctx["keys"], ctx["grade_name_by_guid"].get(guid) or "")
        if row:
            results.append(row)
    if not results:
        return {"kind": "no_results", "message": "No completed matches found for that round yet."}
    results.sort(key=lambda r: r["grade"])
    bucket = {
        "date": ctx["anchor_day"],
        "label": _label(ctx["anchor_day"]),
        "round": _round_label(ctx["anchor_round"]),
        "results": results,
    }
    return {"kind": "round", "season": ctx["season"], "club": _club_dict(org), "dates": [bucket]}


# ── Player of the match ──────────────────────────────────────────────────────

def _split_first_last(raw: str | None) -> tuple[str, str]:
    """'Surname, First' or 'First Surname' -> (first, last) — the same split
    conventions _perf_name uses, kept as the two halves."""
    raw = (raw or "").strip()
    if not raw:
        return "", ""
    if "," in raw:
        last, first = (x.strip() for x in raw.split(",", 1))
        return first, last
    parts = raw.split()
    if len(parts) == 1:
        return "", parts[0]
    return parts[0], " ".join(parts[1:])


def _overs_to_balls(o) -> int:
    """Cricket-notation overs ('10.2' = 10 overs 2 balls) -> balls."""
    try:
        f = float(str(o or 0).replace(",", "."))
    except (TypeError, ValueError):
        return 0
    whole = int(f)
    part = round((f - whole) * 10)
    return whole * 6 + part


async def social_potm(db: AsyncSession, org, match_id: str) -> dict:
    """Rank our own side's performances in one match into a player-of-the-match
    shortlist, from the Grassroots scorecard.

    Our batting rows live in our innings' batting; our bowling and fielding
    rows live in the OPPOSITION's batting innings (we bowl and field while
    they bat) — the same semantics sync.py's per-game inserts follow."""
    raw = await gr.get_match_scorecard(match_id)
    if raw is None:
        raise HTTPException(404, "Scorecard not found — the match may not be completed yet")

    ms = raw.get("matchSummary") or {}
    teams_raw = raw.get("teams") or []
    innings = raw.get("innings") or []
    keys = club_match_keys(org)
    org_id = str(org.id).lower()

    # Identify our team exactly like _result_row: owning org id first, then the
    # club-name keys.
    def is_ours(t: dict) -> bool:
        if ((t.get("owningOrganisation") or {}).get("id") or "").lower() == org_id:
            return True
        dn = (t.get("displayName") or "").lower()
        return any(k in dn for k in keys)

    our_team = next((t for t in teams_raw if is_ours(t)), None)
    if not our_team:
        raise HTTPException(404, "That match doesn't look like one of your club's — no team matched your club name")
    our_id = (our_team.get("id") or "").lower()
    opp_team = next((t for t in teams_raw if (t.get("id") or "").lower() != our_id), None)
    opp_id = (opp_team.get("id") or "").lower() if opp_team else None

    # Roster names, same split as the single-scorecard import: the fuller
    # displayName drives first/last, the "Initial Surname" short name drives
    # the _perf_name performer label.
    roster_full: dict[str, str] = {}
    roster_short: dict[str, str] = {}
    for rp in (our_team.get("players") or []) + (our_team.get("nonPlayingMembers") or []):
        rpid = (rp.get("participantId") or "").lower()
        if not rpid:
            continue
        dn = rp.get("displayName") or rp.get("name")
        if dn and rpid not in roster_full:
            roster_full[rpid] = dn.strip()
        sn = rp.get("playerShortName") or dn or rp.get("name")
        if sn and rpid not in roster_short:
            roster_short[rpid] = sn.strip()

    # Accumulate per OUR participant across every innings (a two-day game has
    # two innings a side).
    perf: dict[str, dict] = {}

    def _slot(pid: str, row_name: str | None) -> dict:
        p = perf.setdefault(pid, {
            "name": None,
            "bat": None,   # {r, b, fours, sixes, outs}
            "bowl": None,  # {balls, m, r, w}
            "field": None, # {catches, catches_wk, stumpings, run_outs}
        })
        if not p["name"]:
            p["name"] = (row_name or "").strip() or None
        return p

    for inn in innings:
        tid = _team_id_from_inn(inn)
        if tid == our_id:
            for b in (inn.get("batting") or []):
                pid = (b.get("participantId") or "").lower()
                if not pid:
                    continue
                dt = (b.get("dismissalType") or "").lower()
                if dt in _DNB_TYPES:
                    continue
                p = _slot(pid, b.get("playerShortName"))
                bat = p["bat"] or {"r": 0, "b": 0, "fours": 0, "sixes": 0, "outs": 0}
                bat["r"] += int(b.get("runsScored") or 0)
                bat["b"] += int(b.get("ballsFaced") or 0)
                bat["fours"] += int(b.get("foursScored") or 0)
                bat["sixes"] += int(b.get("sixesScored") or 0)
                dt_id = b.get("dismissalTypeId") or 0
                not_out = dt_id == _NOT_OUT_ID or dt == "not out"
                if not not_out:
                    bat["outs"] += 1
                p["bat"] = bat
        else:
            # Opposition batting: our bowling and fielding.
            for bw in (inn.get("bowling") or []):
                pid = (bw.get("participantId") or "").lower()
                if not pid:
                    continue
                p = _slot(pid, bw.get("playerShortName"))
                bowl = p["bowl"] or {"balls": 0, "m": 0, "r": 0, "w": 0}
                bowl["balls"] += _overs_to_balls(bw.get("oversBowled"))
                bowl["m"] += int(bw.get("maidensBowled") or 0)
                bowl["r"] += int(bw.get("runsConceded") or 0)
                bowl["w"] += int(bw.get("wicketsTaken") or 0)
                p["bowl"] = bowl
            # Same field names sync.py's fielding-stats insert reads:
            # totalCatches (else catches + wicketKeeperCatches),
            # wicketKeeperCatches, stumpings, runOuts.
            for f in (inn.get("fielding") or []):
                pid = (f.get("participantId") or "").lower()
                if not pid:
                    continue
                catches_wk = int(f.get("wicketKeeperCatches") or 0)
                catches_total = f.get("totalCatches")
                if catches_total is None:
                    catches_total = int(f.get("catches") or 0) + catches_wk
                catches_total = int(catches_total or 0)
                stump = int(f.get("stumpings") or 0)
                ro = int(f.get("runOuts") or 0)
                if not (catches_total or catches_wk or stump or ro):
                    continue
                p = _slot(pid, f.get("playerShortName"))
                fld = p["field"] or {"catches": 0, "catches_wk": 0, "stumpings": 0, "run_outs": 0}
                fld["catches"] += catches_total
                fld["catches_wk"] += catches_wk
                fld["stumpings"] += stump
                fld["run_outs"] += ro
                p["field"] = fld

    # One org-scoped players lookup for every participant — the shared-game
    # rule: a participant is only "ours" through players.organisation_id, and
    # a per-club uuid5 player is found via grassroots_id.
    guids = sorted(pid for pid in perf)
    db_id_by_guid: dict[str, str] = {}
    if guids:
        res = await db.execute(
            text(
                """
                SELECT id::text AS db_id,
                       LOWER(id::text) AS id_key,
                       LOWER(COALESCE(grassroots_id, id::text)) AS gr_key
                FROM players
                WHERE organisation_id = CAST(:org AS UUID)
                  AND (LOWER(id::text) IN :guids
                       OR LOWER(COALESCE(grassroots_id, '')) IN :guids)
                """
            ).bindparams(bindparam("guids", expanding=True)),
            {"org": str(org.id), "guids": guids},
        )
        for r in res:
            db_id_by_guid[r.id_key] = r.db_id
            db_id_by_guid[r.gr_key] = r.db_id

    players = []
    for pid, p in perf.items():
        bat, bowl, fld = p["bat"], p["bowl"], p["field"]
        if not (bat or bowl or fld):
            continue
        batting = None
        if bat:
            batting = {
                "r": bat["r"],
                "b": bat["b"],
                "fours": bat["fours"],
                "sixes": bat["sixes"],
                "sr": round(bat["r"] / bat["b"] * 100, 2) if bat["b"] > 0 else 0,
                "notOut": bat["outs"] == 0,
            }
        bowling = None
        if bowl:
            overs = bowl["balls"] / 6 if bowl["balls"] else 0
            bowling = {
                "o": f"{bowl['balls'] // 6}.{bowl['balls'] % 6}",
                "m": bowl["m"],
                "r": bowl["r"],
                "w": bowl["w"],
                "econ": round(bowl["r"] / overs, 2) if overs > 0 else 0,
            }
        points = (
            _POTM_RUN * (bat["r"] if bat else 0)
            + _POTM_WICKET * (bowl["w"] if bowl else 0)
            + _POTM_MAIDEN * (bowl["m"] if bowl else 0)
        )
        if fld:
            points += _POTM_FIELD_DISMISSAL * (
                (fld["catches"] - fld["catches_wk"]) + fld["stumpings"] + fld["run_outs"]
            )
            points += _POTM_WK_CATCH * fld["catches_wk"]
        first, last = _split_first_last(roster_full.get(pid) or p["name"])
        players.append({
            "first": first,
            "last": last,
            "short": _perf_name(roster_short.get(pid) or p["name"]),
            "pid": db_id_by_guid.get(pid),
            "points": points,
            "batting": batting,
            "bowling": bowling,
            "fielding": fld,
        })
    players.sort(key=lambda x: -x["points"])

    # Match block. Round/venue/date live at the TOP level of a /scores/* match,
    # with matchSummary tried first — same fallback chain as the single
    # scorecard import in admin.py.
    inn_by_team: dict[str, dict] = {}
    for i in innings:
        tid = _team_id_from_inn(i)
        if tid and tid not in inn_by_team:
            inn_by_team[tid] = i
    outcome = "T"
    for st in (ms.get("teams") or []):
        if (st.get("id") or "").lower() != our_id:
            continue
        rt = (st.get("resultType") or "").upper()
        if st.get("isWinner") or rt.startswith("WON"):
            outcome = "W"
        elif rt.startswith("LOST"):
            outcome = "L"
        else:
            outcome = "T"
        break
    opp_name = (opp_team.get("displayName") if opp_team else None) \
        or ((opp_team or {}).get("owningOrganisation") or {}).get("name") or "OPPONENT"
    round_raw = ms.get("round") or raw.get("round") or ""
    if isinstance(round_raw, dict):
        round_name = round_raw.get("name") or round_raw.get("shortName") or ""
    else:
        round_name = str(round_raw)
    date_raw = (
        ms.get("dateTimeUTC")
        or ms.get("startDateTime")
        or ((raw.get("matchSchedule") or [{}])[0] or {}).get("startDateTime")
        or ""
    )
    result_text = (
        ms.get("result") or ms.get("resultText") or ms.get("statusText")
        or raw.get("resultText") or ""
    )
    match = {
        "opponent": strip_team_suffix(opp_name).upper(),
        "oppMono": _mono(opp_name),
        "grade": ((raw.get("grade") or {}).get("name") or "").upper(),
        "round": _round_label(round_name),
        "date": date_raw[:10] if date_raw else "",
        "venue": ((ms.get("venue") or raw.get("venue")) or {}).get("name") or "",
        "result": result_text.upper(),
        "us": _score_str(inn_by_team.get(our_id)),
        "them": _score_str(inn_by_team.get(opp_id)),
        "outcome": outcome,
        "margin": _margin_from_text(ms.get("result") or ms.get("statusText")),
    }
    return {"match": match, "players": players}
