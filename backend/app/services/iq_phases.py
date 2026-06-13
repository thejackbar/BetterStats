"""BetterIQ — innings phase analysis from ball-by-ball data.

CA community matches that were *live-scored* expose per-ball data at
``/scores/matches/{id}/balls`` (the scorecard flags them ``isBallByBall``). This
is the ONLY phase-capable source we have — most history is scorecard-level, so
the rest of BetterIQ stays scorecard-derived and clearly says so. We fetch a
small, recent set of matches on demand (mirroring the live-dossier pattern) and
aggregate a typical innings into Powerplay / Middle / Death.

Identity: a club's DB ``Organisation.id`` *is* its Cricket Australia GUID, which
is exactly ``teams[].owningOrganisation.id`` in the balls payload — so we pick
"our" innings (and an opponent's, via ``games.opp_org_id``) with no extra
mapping. When the opponent org id is missing we fall back to "the side that
isn't us".
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.iq_filters import season_grade_clause

from app.services import grassroots_scores_client as gr

logger = logging.getLogger(__name__)

PP_OVERS = 10        # first 10 overs = powerplay
DEATH_OVERS = 10     # last 10 overs = death
MAX_GAMES = 16       # politeness cap on live ball fetches per request
TARGET_INNINGS = 8   # stop fetching once we have enough innings to be stable


def _i(b, k):
    try:
        return int(b.get(k) or 0)
    except (TypeError, ValueError):
        return 0


def _ball_runs(b):
    return _i(b, "runsBat") + _i(b, "wides") + _i(b, "noBalls") + _i(b, "legByes") + _i(b, "byes") + _i(b, "penaltyRuns")


def _is_legal(b):
    return _i(b, "wides") == 0 and _i(b, "noBalls") == 0


def _phase_of(over, death_start):
    if over < PP_OVERS:
        return "pp"
    if over >= death_start:
        return "death"
    return "mid"


def _accumulate(balls, acc):
    """Fold one innings' balls into the running [runs, wkts, legal_balls] acc."""
    if not balls:
        return False
    last = max(_i(b, "overNumber") for b in balls)
    death_start = max(PP_OVERS, last - DEATH_OVERS + 1)
    for b in balls:
        ph = _phase_of(_i(b, "overNumber"), death_start)
        acc[ph][0] += _ball_runs(b)
        if b.get("dismissedParticipantId"):
            acc[ph][1] += 1
        if _is_legal(b):
            acc[ph][2] += 1
    return True


def _select_innings(payload, target_ca_id, exclude_ca_id=None):
    """Return the lists of balls for the innings batted by ``target_ca_id`` (a CA
    org GUID). If none match and ``exclude_ca_id`` is given, fall back to every
    innings NOT batted by that org (i.e. the opponent's)."""
    teams = payload.get("teams") or []
    own = {t.get("id"): ((t.get("owningOrganisation") or {}).get("id")) for t in teams}
    innings = payload.get("innings") or []
    hit = [inn.get("balls") or [] for inn in innings if target_ca_id and own.get(inn.get("battingTeamId")) == str(target_ca_id)]
    if hit:
        return hit
    if exclude_ca_id:
        return [inn.get("balls") or [] for inn in innings if own.get(inn.get("battingTeamId")) != str(exclude_ca_id)]
    return []


def _output(acc, n):
    n = max(n, 1)
    labels = [("Powerplay", "pp"), ("Middle", "mid"), ("Death", "death")]
    phases = []
    for label, key in labels:
        runs, wkts, balls = acc[key]
        overs_total = balls / 6
        phases.append({
            "label": label,
            "overs": round(overs_total / n, 1),
            "runs": round(runs / n),
            "wkts": round(wkts / n, 1),
            "rr": round(runs / overs_total, 2) if overs_total else 0,
        })
    return phases


def _insight(phases, who, verb="score"):
    """Build a phase read. ``who`` is the consistent subject of BOTH sentences
    (e.g. "We" for our batting, "Opponents" for what we concede) and ``verb`` is
    the run action ("score" when batting, "concede" / "leak" when bowling) so the
    two halves never contradict each other (the old copy hard-coded "They")."""
    if not phases or all(p["runs"] == 0 for p in phases):
        return None
    by_rr = sorted(phases, key=lambda p: p["rr"], reverse=True)
    top, low = by_rr[0], by_rr[-1]
    death = next((p for p in phases if p["label"] == "Death"), None)
    pp = next((p for p in phases if p["label"] == "Powerplay"), None)
    bits = [f"{who} {verb} fastest in the {top['label'].lower()} ({top['rr']} rpo) and slowest in the {low['label'].lower()} ({low['rr']} rpo)."]
    if death and pp and death["rr"] < pp["rr"] - 0.6:
        if verb == "concede":
            bits.append(f"{who} tighten up at the death rather than getting taken apart — the back end is a strength.")
        else:
            bits.append(f"{who} tend to stall at the death rather than accelerate — squeeze the back end.")
    elif death and pp and death["rr"] > pp["rr"] + 0.6:
        if verb == "concede":
            bits.append(f"{who} get away from us at the death — hold something back for the last 10.")
        else:
            bits.append(f"{who} accelerate hard at the death — hold something back for the last 10.")
    return " ".join(bits)


async def _aggregate(pairs, fallback_not=None, who="They", verb="score"):
    """pairs: list of (match_id, target_ca_id). Fetch balls for each, fold the
    target's innings into a typical-innings phase profile."""
    acc = {"pp": [0, 0, 0], "mid": [0, 0, 0], "death": [0, 0, 0]}
    n = 0
    games_used = 0
    for match_id, target in pairs:
        if n >= TARGET_INNINGS:
            break
        payload = await gr.get_match_balls(match_id)
        if not payload:
            continue
        innings = _select_innings(payload, target, exclude_ca_id=fallback_not)
        used = False
        for balls in innings:
            if _accumulate(balls, acc):
                n += 1
                used = True
        if used:
            games_used += 1
    if n == 0:
        return {"available": False, "innings": 0, "phases": [], "insight": None,
                "note": "No ball-by-ball data found for recent matches (older games are scorecard-only)."}
    phases = _output(acc, n)
    return {
        "available": True,
        "innings": n,
        "games": games_used,
        "total": sum(p["runs"] for p in phases),
        "phases": phases,
        "insight": _insight(phases, who, verb=verb),
        "note": "Estimated from ball-by-ball data for recent live-scored matches only.",
    }


# ``grade`` is a grade NAME (BetterIQ filters grades by name to collapse the
# per-season/per-club grade ids — see iq_team.team_grades); the season is
# year-expanded (one picked row scopes every sibling row of that real season —
# see iq_filters).
def _scope(season_id, grade_id):
    return season_grade_clause(season_id, grade_id)


async def team_phases(session: AsyncSession, org_id: str, season_id=None, grade_id=None, side="bat") -> dict:
    """Our team's typical innings shape from recent ball-by-ball games.

    ``side='bat'`` profiles OUR innings (how we score); ``side='bowl'`` profiles
    the opponent's innings in our games (what we concede) so the Batting and
    Bowling tabs each get their own, correctly-framed phase read."""
    rows = await session.execute(text(f"""
        SELECT g.id::text AS id, g.opp_org_id AS opp
        FROM games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE s.organisation_id = CAST(:org AS UUID) {_scope(season_id, grade_id)}
        ORDER BY g.played_at DESC NULLS LAST
        LIMIT :lim
    """), {"org": org_id, "season": season_id, "grade": grade_id, "lim": MAX_GAMES})
    recs = list(rows)
    if side == "bowl":
        # The side that isn't us in our games = what our attack concedes by phase.
        pairs = [(r.id, r.opp) for r in recs]
        out = await _aggregate(pairs, fallback_not=org_id, who="Opponents", verb="score")
        out["scope"] = "team_bowl"
        out["side"] = "bowl"
    else:
        pairs = [(r.id, org_id) for r in recs]
        out = await _aggregate(pairs, who="We", verb="score")
        out["scope"] = "team_bat"
        out["side"] = "bat"
    return out


async def opponent_phases(session: AsyncSession, org_id: str, opp_key=None, opp_name=None) -> dict:
    """An opponent's typical innings shape, taken from our recent games vs them
    (we keep both sides of every scorecard, and the ball feed carries both too)."""
    if not opp_key and not opp_name:
        return {"available": False, "innings": 0, "phases": [], "insight": None, "note": "Opponent not identified."}
    rows = await session.execute(text("""
        SELECT g.id::text AS id, g.opp_org_id AS opp
        FROM games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE s.organisation_id = CAST(:org AS UUID)
          AND (g.opp_org_id = :key OR lower(g.opp_club_name) = lower(:key) OR lower(g.opp_club_name) = lower(:name))
        ORDER BY g.played_at DESC NULLS LAST
        LIMIT :lim
    """), {"org": org_id, "key": opp_key or "", "name": opp_name or "", "lim": MAX_GAMES})
    pairs = [(r.id, r.opp) for r in rows]
    out = await _aggregate(pairs, fallback_not=org_id, who="They")
    out["scope"] = "opponent"
    return out
