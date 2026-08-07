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
"""
from __future__ import annotations

import asyncio
import re
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import grassroots_scores_client as gr
from app.services.club_match import club_match_keys
from app.services.fixtures_source import _current_grade_rows, org_grassroots_fixtures
from app.services.sync import strip_team_suffix

# Bound the results scorecard fan-out: at most a few recent match-days / matches.
_RESULT_WINDOW_DAYS = 90
_RESULT_MAX_DATES = 3
_RESULT_MAX_MATCHES = 24

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
    # NOT our own grades.id. See GradeRow.
    grade_name_by_guid = {r.guid: r.grade_name for r in rows}
    season = next((r.season_name for r in rows if r.season_name), None)
    since = (date.today() - timedelta(days=_RESULT_WINDOW_DAYS)).isoformat()

    discovered = await asyncio.gather(
        *[gr.get_grade_results(r.guid, since=since) for r in rows],
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
