"""BetterSocials' data imports, answered from the football database.

The post designer (frontend/src/pages/admin/AdminSocialPost.jsx) is shared with
cricket and reads its data through a handful of ``/admin/social/*`` endpoints.
In cricket those live in ``routers/admin.py`` and read Cricket Australia's
feeds; that router is not mounted on the football backend, so the same paths
are answered here from what the football sync (and the results import) already
stored. The designer needs no football branch to fetch its data, only to read
the one football-shaped stat block (``football``) a player of the match carries.

Every payload has the shape cricket's version returns, so the roundup
templates (fixtures, results) and the lineup/spotlight templates take it as is:

* ``/admin/social/fixtures``  — upcoming games grouped by match-day.
* ``/admin/social/results``   — recent finished games grouped by match-day,
  scores written the football way ("12.8 (80)").
* ``/admin/social/match-lookup`` — a game id resolves straight to it; anything
  else offers the club's recent finished games to pick from. Football has no
  pasted-link id space to decode, so a link is never guessed at.
* ``/admin/social/potm/{game_id}`` — our side's players for one game, ranked by
  the best-on-ground ranking PlayHQ publishes, then goals.
* ``/organisations/{org_id}/lineups`` — our published team lists, for a lineup
  post. Football team lists arrive with the game's stats, so these are the
  club's most recent games rather than the next one.

Nothing here calls PlayHQ: all of it is a read of held data, so a post can be
built while the upstream is down.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import require_module
from app.models.db import Organisation, get_db
from app.routers.auth import get_current_club
from app.services.social_rounds import _club_dict, _label, _mono, _round_label, _to_12h
from app.services.sync import strip_team_suffix as _strip_cricket_suffix

router = APIRouter(tags=["afl-social"], dependencies=[Depends(require_module("socials"))])

# A post names the club, not its legal name: "Rivals" rather than "Rivals
# Football Club". Cricket's own tidier (services/sync.strip_team_suffix) knows
# cricket's suffixes; these are football's, stripped after it.
_FOOTY_SUFFIX = re.compile(
    r"\s+(?:(?:amateur|junior|senior|women'?s)\s+)?(?:football(?:\s*(?:&|and)\s*netball)?\s+club|"
    r"football\s+(?:&|and)\s+netball|a?fnc|a?fc|jfc|sfc)\.?\s*$",
    re.IGNORECASE,
)


def strip_team_suffix(name: str) -> str:
    return _FOOTY_SUFFIX.sub("", _strip_cricket_suffix(name or "")).strip()


RESULT_WINDOW_DAYS = 28
RESULT_MAX_DATES = 4
FIXTURE_MAX_DATES = 4
MAX_CANDIDATES = 20

_GAMES = """
    SELECT g.id, g.played_at, g.home_team, g.away_team, g.home_club, g.away_club, g.venue,
           gr.id AS grade_id, gr.name AS grade_name, gr.display_order,
           s.name AS season_name,
           d.round_name, d.status, d.start_time, d.our_side,
           d.home_goals, d.home_behinds, d.home_score,
           d.away_goals, d.away_behinds, d.away_score,
           d.home_logo_url, d.away_logo_url, d.venue_name,
           COALESCE(d.is_bye, false) AS is_bye
    FROM games g
    JOIN grades gr ON gr.id = g.grade_id
    JOIN seasons s ON s.id = gr.season_id
    JOIN afl_game_details d ON d.game_id = g.id
    WHERE s.organisation_id = :org AND COALESCE(d.is_bye, false) = false
"""


def _sides(r: dict) -> tuple[str, str]:
    """(our side, their side) as HOME/AWAY. A game with no side recorded is
    read as ours at home, the same default the results import stores."""
    ours = r.get("our_side") or "HOME"
    return ours, ("AWAY" if ours == "HOME" else "HOME")


def _team(r: dict, side: str) -> str:
    return (r.get("home_team") if side == "HOME" else r.get("away_team")) or ""


def _score(r: dict, side: str) -> Optional[str]:
    p = "home" if side == "HOME" else "away"
    goals, behinds, total = r.get(f"{p}_goals"), r.get(f"{p}_behinds"), r.get(f"{p}_score")
    if total is None and goals is not None and behinds is not None:
        total = goals * 6 + behinds
    if total is None:
        return None
    if goals is None or behinds is None:
        return str(total)
    return f"{goals}.{behinds} ({total})"


def _total(r: dict, side: str) -> Optional[int]:
    p = "home" if side == "HOME" else "away"
    total = r.get(f"{p}_score")
    if total is None and r.get(f"{p}_goals") is not None and r.get(f"{p}_behinds") is not None:
        total = r[f"{p}_goals"] * 6 + r[f"{p}_behinds"]
    return total


def outcome_and_margin(us: Optional[int], them: Optional[int]) -> tuple[str, str]:
    if us is None or them is None:
        return "T", ""
    if us == them:
        return "T", "DRAWN"
    diff = abs(us - them)
    return ("W" if us > them else "L"), f"BY {diff} POINT{'S' if diff != 1 else ''}"


def _logo(r: dict, side: str) -> Optional[str]:
    return r.get("home_logo_url") if side == "HOME" else r.get("away_logo_url")


def _iso(d) -> str:
    return d.isoformat() if d else ""


@router.get("/admin/social/fixtures")
async def social_fixtures(q: Optional[str] = None,
                          club: Organisation = Depends(get_current_club),
                          db: AsyncSession = Depends(get_db)):
    res = await db.execute(text(_GAMES + """
          AND g.played_at >= CURRENT_DATE
          AND COALESCE(d.status, 'UPCOMING') <> 'FINAL'
        ORDER BY g.played_at, d.start_time NULLS LAST
    """), {"org": str(club.id)})
    rows = [dict(r) for r in res.mappings().all()]
    season = next((r["season_name"] for r in rows if r["season_name"]), None)
    by_date: dict[str, dict] = {}
    for r in rows:
        day = _iso(r["played_at"])
        if day not in by_date and len(by_date) >= FIXTURE_MAX_DATES:
            break
        bucket = by_date.setdefault(day, {"date": day, "label": _label(day), "round": "", "fixtures": []})
        if not bucket["round"]:
            bucket["round"] = _round_label(r["round_name"])
        ours, theirs = _sides(r)
        opp = _team(r, theirs)
        bucket["fixtures"].append({
            "grade": (r["grade_name"] or "").upper(),
            "gradeOrder": r["display_order"],
            "opp": strip_team_suffix(opp).upper(),
            "oppMono": _mono(opp),
            "ha": "H" if ours == "HOME" else "A",
            "time": _to_12h(r["start_time"]),
            "venue": (r["venue_name"] or r["venue"] or "").upper(),
            "oppLogo": _logo(r, theirs),
        })
    out = {"season": season, "club": _club_dict(club), "dates": list(by_date.values())}
    return {"kind": "round", **out} if q else out


async def _recent_final(db: AsyncSession, org_id, days: int) -> list[dict]:
    since = date.today() - timedelta(days=days)
    res = await db.execute(text(_GAMES + """
          AND d.status = 'FINAL' AND g.played_at >= :since
        ORDER BY g.played_at DESC
    """), {"org": str(org_id), "since": since})
    return [dict(r) for r in res.mappings().all()]


def result_row(r: dict) -> Optional[dict]:
    ours, theirs = _sides(r)
    us, them = _score(r, ours), _score(r, theirs)
    if us is None or them is None:
        return None
    outcome, margin = outcome_and_margin(_total(r, ours), _total(r, theirs))
    opp = _team(r, theirs)
    return {
        "grade": (r["grade_name"] or "").upper(),
        "gradeOrder": r["display_order"],
        "opp": strip_team_suffix(opp).upper(),
        "oppMono": _mono(opp),
        "us": us,
        "them": them,
        "outcome": outcome,
        "margin": margin,
        # The cricket roundups carry top performers; a football result's are
        # the goal kickers, which the Results wrap does not draw, so empty.
        "topBat": [],
        "topBowl": [],
        "oppLogo": _logo(r, theirs),
    }


@router.get("/admin/social/results")
async def social_results(q: Optional[str] = None,
                         club: Organisation = Depends(get_current_club),
                         db: AsyncSession = Depends(get_db)):
    rows = await _recent_final(db, club.id, RESULT_WINDOW_DAYS)
    season = next((r["season_name"] for r in rows if r["season_name"]), None)
    by_date: dict[str, dict] = {}
    for r in rows:
        day = _iso(r["played_at"])
        if day not in by_date and len(by_date) >= RESULT_MAX_DATES:
            break
        row = result_row(r)
        if not row:
            continue
        bucket = by_date.setdefault(day, {"date": day, "label": _label(day), "round": "", "results": []})
        if not bucket["round"]:
            bucket["round"] = _round_label(r["round_name"])
        bucket["results"].append(row)
    out = {"season": season, "club": _club_dict(club), "dates": list(by_date.values())}
    return {"kind": "round", **out} if q else out


def _card(r: dict) -> dict:
    ours, theirs = _sides(r)
    return {
        "match_id": str(r["id"]),
        "date": _iso(r["played_at"]),
        "round": r["round_name"] or "",
        "grade": r["grade_name"] or "",
        "team": strip_team_suffix(_team(r, ours)),
        "opponent": strip_team_suffix(_team(r, theirs)),
        "home_away": "H" if ours == "HOME" else "A",
        "venue": r["venue_name"] or r["venue"] or "",
    }


@router.get("/admin/social/match-lookup")
async def social_match_lookup(q: str = "",
                              club: Organisation = Depends(get_current_club),
                              db: AsyncSession = Depends(get_db)):
    raw = (q or "").strip()
    # A game id (a BetterFootball match link ends in one) goes straight to it,
    # but only if it is one of this club's games.
    tail = raw.rstrip("/").split("/")[-1] if raw else ""
    try:
        gid = uuid.UUID(tail)
    except ValueError:
        gid = None
    if gid:
        hit = await db.execute(text(_GAMES + " AND g.id = :gid"), {"org": str(club.id), "gid": str(gid)})
        if hit.first():
            return {"kind": "match", "source": "betterfootball", "match_id": str(gid)}
    rows = await _recent_final(db, club.id, 120)
    return {
        "kind": "choose", "source": "betterfootball",
        "message": "Pick the match below.",
        "matches": [_card(r) for r in rows[:MAX_CANDIDATES]],
    }


@router.get("/admin/social/potm/{game_id}")
async def social_potm(game_id: str,
                      club: Organisation = Depends(get_current_club),
                      db: AsyncSession = Depends(get_db)):
    try:
        gid = uuid.UUID(game_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid match id")
    res = await db.execute(text(_GAMES + " AND g.id = :gid"), {"org": str(club.id), "gid": str(gid)})
    r = res.mappings().first()
    if not r:
        raise HTTPException(status_code=404, detail="That match isn't one of your club's")
    r = dict(r)
    ours, theirs = _sides(r)
    lines = await db.execute(text("""
        SELECT l.player_id, l.name, l.goals, l.behinds, l.bog_ranking
        FROM afl_player_game_lines l
        WHERE l.game_id = :gid AND l.side = :side
        ORDER BY l.bog_ranking NULLS LAST, l.goals DESC, l.behinds DESC, l.name
    """), {"gid": str(gid), "side": ours})
    players = []
    for ln in lines.mappings().all():
        name = (ln["name"] or "").strip()
        if "," in name:
            last, first = [p.strip() for p in name.split(",", 1)]
        else:
            parts = name.split()
            first, last = (" ".join(parts[:-1]), parts[-1]) if len(parts) > 1 else ("", name)
        players.append({
            "pid": str(ln["player_id"]) if ln["player_id"] else None,
            "first": first, "last": last,
            "short": f"{first[:1]} {last}".strip() if first else last,
            "football": {"goals": ln["goals"] or 0, "behinds": ln["behinds"] or 0,
                         "bog_ranking": ln["bog_ranking"]},
        })
    outcome, margin = outcome_and_margin(_total(r, ours), _total(r, theirs))
    opp = _team(r, theirs)
    return {
        "match": {
            "opponent": strip_team_suffix(opp).upper(),
            "oppMono": _mono(opp),
            "grade": (r["grade_name"] or "").upper(),
            "round": _round_label(r["round_name"]),
            "date": _iso(r["played_at"]),
            "venue": r["venue_name"] or r["venue"] or "",
            "result": "",
            "us": _score(r, ours),
            "them": _score(r, theirs),
            "outcome": outcome,
            "margin": margin,
        },
        "players": players,
    }


@router.get("/organisations/{org_id}/lineups")
async def social_lineups(org_id: str,
                         mode: str = "upcoming",
                         limit: int = Query(20, ge=1, le=60),
                         club: Organisation = Depends(get_current_club),
                         db: AsyncSession = Depends(get_db)):
    if str(club.id) != org_id:
        raise HTTPException(status_code=404, detail="Club not found")
    res = await db.execute(text(_GAMES + """
          AND EXISTS (SELECT 1 FROM afl_player_game_lines l WHERE l.game_id = g.id)
        ORDER BY g.played_at DESC LIMIT :lim
    """), {"org": str(club.id), "lim": limit})
    games = [dict(r) for r in res.mappings().all()]
    if not games:
        return {"matches": []}
    lines = await db.execute(text("""
        SELECT l.game_id, l.side, l.player_id, l.playhq_participant_id, l.name,
               l.jumper_number, l.is_captain
        FROM afl_player_game_lines l
        WHERE l.game_id = ANY(CAST(:ids AS uuid[]))
        ORDER BY l.game_id, l.side, NULLIF(regexp_replace(COALESCE(l.jumper_number, ''), '\\D', '', 'g'), '')::int NULLS LAST, l.name
    """), {"ids": [str(g["id"]) for g in games]})
    by_game: dict = {}
    for ln in lines.mappings().all():
        by_game.setdefault((str(ln["game_id"]), ln["side"]), []).append({
            "player_id": str(ln["player_id"]) if ln["player_id"] else None,
            "participant_id": ln["playhq_participant_id"],
            "name": ln["name"],
            "jumper_number": ln["jumper_number"],
            "is_captain": bool(ln["is_captain"]),
            "is_wicket_keeper": False,
        })
    out = []
    for g in games:
        ours, theirs = _sides(g)
        gid = str(g["id"])
        teams = []
        for side in (ours, theirs):
            name = _team(g, side)
            players = by_game.get((gid, side), [])
            teams.append({
                "is_ours": side == ours,
                "name": name,
                "club": strip_team_suffix(name),
                "logo_url": _logo(g, side),
                "published": bool(players),
                "players": players,
            })
        out.append({
            "match_id": gid,
            "date": _iso(g["played_at"]),
            "time": _to_12h(g["start_time"]),
            "round": g["round_name"] or "",
            "venue": g["venue_name"] or g["venue"] or "",
            "grade": g["grade_name"] or "",
            "status": "COMPLETED",
            "teams": teams,
        })
    return {"matches": out}
