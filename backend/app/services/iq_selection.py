"""BetterIQ — Selection analysis (master-plan Phase 2).

Boundary with BetterSelect: **BetterSelect picks the team; BetterIQ analyses and
justifies the pick.** We read a fixture's saved lineup (``fixture_lineups``) plus
player attributes and recent form, and surface:

- **Balance** of the chosen XI — batting depth, bowling options (pace/spin,
  arm), all-rounders, keeper & captain presence, RH/LH mix, openers.
- **Form** — each picked player's last-N batting/bowling, and **warnings**
  (no keeper, thin attack, out-of-form picks, picked-but-unavailable).
- **Promote / rest** — in-form available squad players left out (promote) and
  picked players who are out of form (rest/watch).
- **Fairness across grades** — this-season match load, and who's playing up or
  down vs their usual squad (``teams.sequence``).

All reads over data we already hold. Org-scoping via ``seasons.organisation_id``
for per-game rows (records.py pattern); fixtures/lineups carry organisation_id.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

RECENT_GAMES = 5          # innings/spells per player for the form snapshot
THIN_ATTACK = 5           # fewer front-line bowling options than this → warn
OUT_OF_FORM_AVG = 15.0    # recent batting average below this (min 3 inns) → flag
PROMOTE_LIMIT = 6

_PACE = {"FAST", "FAST_MEDIUM", "MEDIUM", "MEDIUM_FAST"}
_SPIN = {"FINGER_SPIN", "WRIST_SPIN"}
_ORG_SCOPE = " JOIN grades gr ON gr.id = g.grade_id JOIN seasons s ON s.id = gr.season_id"


def _skills(sp) -> set[str]:
    return {str(s).upper() for s in (sp or []) if s}


def _bowls(skills: set[str], bowling_type: str | None) -> bool:
    return "BWL" in skills or "ALL" in skills or bool(bowling_type)


def _recent_avg(scores: list[dict]) -> float | None:
    runs = sum(x["runs"] for x in scores)
    outs = sum(1 for x in scores if not x["not_out"])
    return round(runs / outs, 2) if outs else None


async def list_lineups(session: AsyncSession, org_id: str) -> list[dict]:
    """Fixtures with a saved lineup, soonest-upcoming first then recent past."""
    res = await session.execute(
        text(
            """
            SELECT f.id::text AS id, f.opponent_name, f.played_on, f.home_away,
                   f.venue, gr.name AS grade_name, t.name AS team_name,
                   COUNT(fl.player_id) AS lineup_count
            FROM fixtures f
            JOIN fixture_lineups fl ON fl.fixture_id = f.id
            LEFT JOIN grades gr ON gr.id = f.grade_id
            LEFT JOIN teams t ON t.id = f.team_id
            WHERE f.organisation_id = CAST(:org AS UUID)
            GROUP BY f.id, f.opponent_name, f.played_on, f.home_away, f.venue, gr.name, t.name
            """
        ),
        {"org": org_id},
    )
    rows = [
        {
            "fixture_id": r["id"], "opponent_name": r["opponent_name"],
            "played_on": r["played_on"].isoformat() if r["played_on"] else None,
            "home_away": r["home_away"], "venue": r["venue"],
            "grade_name": r["grade_name"], "team_name": r["team_name"],
            "lineup_count": r["lineup_count"], "_d": r["played_on"],
        }
        for r in res.mappings()
    ]
    from datetime import date
    today = date.today()
    upcoming = sorted([x for x in rows if x["_d"] and x["_d"] >= today], key=lambda x: x["_d"])
    past = sorted([x for x in rows if not x["_d"] or x["_d"] < today],
                  key=lambda x: (x["_d"] is not None, x["_d"]), reverse=True)
    out = upcoming + past
    for x in out:
        x.pop("_d", None)
    return out[:40]


async def _recent_form(session: AsyncSession, org_id: str) -> dict[str, dict]:
    """Per-player last-N batting scores + bowling wicket-hauls, club-wide."""
    form: dict[str, dict] = {}
    bat = await session.execute(
        text(
            f"""
            WITH innings AS (
                SELECT bi.player_id, bi.runs, bi.not_out,
                       ROW_NUMBER() OVER (
                           PARTITION BY bi.player_id ORDER BY g.played_at DESC NULLS LAST, bi.id DESC
                       ) AS rn
                FROM v_effective_batting_innings bi
                JOIN v_effective_games g ON g.id = bi.game_id{_ORG_SCOPE}
                WHERE s.organisation_id = CAST(:org AS UUID)
                  AND bi.did_not_bat IS NOT TRUE AND bi.runs IS NOT NULL
            )
            SELECT player_id::text AS id, runs, not_out FROM innings WHERE rn <= :n
            ORDER BY player_id, rn
            """
        ),
        {"org": org_id, "n": RECENT_GAMES},
    )
    for r in bat.mappings():
        form.setdefault(r["id"], {"bat": [], "bowl": []})["bat"].append(
            {"runs": r["runs"], "not_out": bool(r["not_out"])}
        )
    bowl = await session.execute(
        text(
            f"""
            WITH spells AS (
                SELECT bs.player_id, bs.wickets, bs.runs,
                       ROW_NUMBER() OVER (
                           PARTITION BY bs.player_id ORDER BY g.played_at DESC NULLS LAST, bs.id DESC
                       ) AS rn
                FROM v_effective_bowling_spells bs
                JOIN v_effective_games g ON g.id = bs.game_id{_ORG_SCOPE}
                WHERE s.organisation_id = CAST(:org AS UUID)
            )
            SELECT player_id::text AS id, wickets, runs FROM spells WHERE rn <= :n
            ORDER BY player_id, rn
            """
        ),
        {"org": org_id, "n": RECENT_GAMES},
    )
    for r in bowl.mappings():
        form.setdefault(r["id"], {"bat": [], "bowl": []})["bowl"].append(
            {"wickets": r["wickets"] or 0, "runs": r["runs"] or 0}
        )
    return form


def _form_block(f: dict | None) -> dict:
    """Shape a player's recent form for the API + a composite score."""
    f = f or {"bat": [], "bowl": []}
    bat, bowl = f["bat"], f["bowl"]
    recent_runs = [(f"{x['runs']}*" if x["not_out"] else str(x["runs"])) for x in bat]
    recent_wkts = [str(x["wickets"]) for x in bowl]
    bat_total = sum(x["runs"] for x in bat)
    wkt_total = sum(x["wickets"] for x in bowl)
    return {
        "recent_scores": recent_runs,
        "recent_wickets": recent_wkts,
        "recent_avg": _recent_avg(bat),
        "recent_runs": bat_total,
        "recent_wkts_total": wkt_total,
        "bat_inns": len(bat),
        # Composite: runs + wickets weighted, for ranking promote candidates.
        "score": bat_total + wkt_total * 18,
    }


async def selection_analysis(session: AsyncSession, org_id: str, fixture_id: str) -> dict | None:
    """Analyse a fixture's saved XI: balance, form, warnings, promote/rest, fairness."""
    frow = await session.execute(
        text(
            """
            SELECT f.id::text AS id, f.opponent_name, f.played_on, f.home_away, f.venue,
                   f.team_id::text AS team_id, t.name AS team_name, t.sequence AS team_seq,
                   gr.name AS grade_name, gr.season_id::text AS season_id
            FROM fixtures f
            LEFT JOIN teams t ON t.id = f.team_id
            LEFT JOIN grades gr ON gr.id = f.grade_id
            WHERE f.id = CAST(:fid AS UUID) AND f.organisation_id = CAST(:org AS UUID)
            """
        ),
        {"fid": fixture_id, "org": org_id},
    )
    fx = frow.mappings().first()
    if not fx:
        return None

    lu = await session.execute(
        text(
            """
            SELECT p.id::text AS id, COALESCE(p.display_name_override, p.name) AS name,
                   fl.batting_order, fl.is_captain, fl.is_wicket_keeper,
                   p.skill_positions, p.batting_hand, p.bowling_action, p.bowling_type,
                   p.is_opening_batsman, p.status, p.squad_team_id::text AS squad_team_id
            FROM fixture_lineups fl
            JOIN players p ON p.id = fl.player_id
            WHERE fl.fixture_id = CAST(:fid AS UUID) AND fl.organisation_id = CAST(:org AS UUID)
            ORDER BY fl.batting_order ASC NULLS LAST, name
            """
        ),
        {"fid": fixture_id, "org": org_id},
    )
    lineup_rows = lu.mappings().all()

    form = await _recent_form(session, org_id)
    team_seq = await _team_sequences(session, org_id)
    avail = await _availability_on(session, org_id, fx["played_on"])
    load = await _season_load(session, fx["season_id"]) if fx["season_id"] else {}

    fixture_seq = fx["team_seq"]
    selected_ids = set()
    players = []
    pace = spin = bowl_opts = keepers = captains = openers = lh = rh = allr = spec_bat = 0

    for r in lineup_rows:
        pid = r["id"]
        selected_ids.add(pid)
        skills = _skills(r["skill_positions"])
        bt = (r["bowling_type"] or "").upper()
        does_bowl = _bowls(skills, r["bowling_type"])
        is_ar = "ALL" in skills or ("BWL" in skills and (skills & {"BAT", "WKT"}))
        is_keeper = bool(r["is_wicket_keeper"]) or "WKT" in skills

        if does_bowl:
            bowl_opts += 1
            if bt in _PACE:
                pace += 1
            elif bt in _SPIN:
                spin += 1
        if is_ar:
            allr += 1
        elif "BAT" in skills or is_keeper:
            spec_bat += 1
        if is_keeper:
            keepers += 1
        if r["is_captain"]:
            captains += 1
        if r["is_opening_batsman"]:
            openers += 1
        if (r["batting_hand"] or "").upper() == "LEFT":
            lh += 1
        elif (r["batting_hand"] or "").upper() == "RIGHT":
            rh += 1

        # Playing up/down vs usual squad (lower sequence = higher team).
        updown = None
        sq_seq = team_seq.get(r["squad_team_id"]) if r["squad_team_id"] else None
        if sq_seq is not None and fixture_seq is not None and sq_seq != fixture_seq:
            updown = "up" if sq_seq > fixture_seq else "down"

        fb = _form_block(form.get(pid))
        players.append({
            "player_id": pid, "name": r["name"], "batting_order": r["batting_order"],
            "is_captain": bool(r["is_captain"]), "is_wicket_keeper": is_keeper,
            "skills": sorted(skills), "bowling_type": r["bowling_type"],
            "batting_hand": r["batting_hand"], "is_opener": bool(r["is_opening_batsman"]),
            "availability": avail.get(pid), "season_matches": load.get(pid, 0),
            "play_updown": updown, "active": r["status"] == "active",
            **{k: fb[k] for k in ("recent_scores", "recent_wickets", "recent_avg", "score")},
        })

    size = len(players)
    balance = {
        "size": size, "specialist_batters": spec_bat, "all_rounders": allr,
        "bowling_options": bowl_opts, "pace": pace, "spin": spin,
        "keepers": keepers, "captains": captains, "openers": openers,
        "left_hand_bat": lh, "right_hand_bat": rh,
    }

    # ── Warnings ──
    warnings = []
    if keepers == 0:
        warnings.append({"level": "warn", "text": "No specialist wicket-keeper in the XI."})
    elif keepers > 1:
        warnings.append({"level": "info", "text": f"{keepers} keepers selected."})
    if captains == 0:
        warnings.append({"level": "info", "text": "No captain marked on the lineup."})
    if bowl_opts < THIN_ATTACK:
        warnings.append({"level": "warn", "text": f"Thin attack — only {bowl_opts} front-line bowling options."})
    if bowl_opts and spin == 0:
        warnings.append({"level": "info", "text": "No spin option in the attack."})
    if bowl_opts and pace == 0:
        warnings.append({"level": "info", "text": "No pace option in the attack."})
    unavailable = [p["name"] for p in players if p["availability"] == "UNAVAILABLE"]
    if unavailable:
        warnings.append({"level": "warn", "text": "Selected but marked unavailable: " + ", ".join(unavailable) + "."})
    cold = [p["name"] for p in players
            if p["recent_avg"] is not None and p["recent_avg"] < OUT_OF_FORM_AVG
            and "BAT" in p["skills"] and len(p["recent_scores"]) >= 3]
    if cold:
        warnings.append({"level": "info", "text": "Out of form with the bat: " + ", ".join(cold) + "."})

    # ── Promote / rest ──
    promote = await _promote_candidates(session, org_id, selected_ids, form, avail, team_seq, fixture_seq)
    rest = [
        {"player_id": p["player_id"], "name": p["name"], "recent_avg": p["recent_avg"],
         "recent_scores": p["recent_scores"], "reason": "out of form"}
        for p in players
        if p["recent_avg"] is not None and p["recent_avg"] < OUT_OF_FORM_AVG
        and "BAT" in p["skills"] and len(p["recent_scores"]) >= 3
    ]

    return {
        "fixture": {
            "fixture_id": fx["id"], "opponent_name": fx["opponent_name"],
            "played_on": fx["played_on"].isoformat() if fx["played_on"] else None,
            "home_away": fx["home_away"], "venue": fx["venue"],
            "team_name": fx["team_name"], "grade_name": fx["grade_name"],
        },
        "balance": balance,
        "players": players,
        "warnings": warnings,
        "promote": promote,
        "rest": rest,
        "coverage": {
            "notes": [
                "Form is the last 5 innings/spells; availability is explicit answers for the match date.",
                "Roles use each player's skill tags and bowling type — set these in BetterSelect for sharper analysis.",
            ]
        },
    }


async def _team_sequences(session: AsyncSession, org_id: str) -> dict[str, int]:
    res = await session.execute(
        text("SELECT id::text AS id, sequence FROM teams WHERE organisation_id = CAST(:org AS UUID)"),
        {"org": org_id},
    )
    return {r["id"]: r["sequence"] for r in res.mappings()}


async def _availability_on(session: AsyncSession, org_id: str, on_date) -> dict[str, str]:
    if not on_date:
        return {}
    res = await session.execute(
        text(
            "SELECT player_id::text AS id, status FROM player_availability"
            " WHERE organisation_id = CAST(:org AS UUID) AND avail_date = :d"
        ),
        {"org": org_id, "d": on_date},
    )
    return {r["id"]: r["status"] for r in res.mappings()}


async def _season_load(session: AsyncSession, season_id: str) -> dict[str, int]:
    res = await session.execute(
        text(
            "SELECT player_id::text AS id, COALESCE(SUM(matches), 0) AS m"
            " FROM player_season_stats WHERE season_id = CAST(:sid AS UUID) GROUP BY player_id"
        ),
        {"sid": season_id},
    )
    return {r["id"]: r["m"] for r in res.mappings()}


async def _promote_candidates(session, org_id, selected_ids, form, avail, team_seq, fixture_seq) -> list[dict]:
    """In-form active players not in the XI and not marked unavailable."""
    res = await session.execute(
        text(
            """
            SELECT p.id::text AS id, COALESCE(p.display_name_override, p.name) AS name,
                   p.skill_positions, p.squad_team_id::text AS squad_team_id
            FROM players p
            WHERE p.organisation_id = CAST(:org AS UUID) AND p.status = 'active'
            """
        ),
        {"org": org_id},
    )
    out = []
    for r in res.mappings():
        pid = r["id"]
        if pid in selected_ids or avail.get(pid) == "UNAVAILABLE":
            continue
        fb = _form_block(form.get(pid))
        if fb["bat_inns"] < 2 and fb["recent_wkts_total"] < 2:
            continue  # no meaningful recent activity
        sq_seq = team_seq.get(r["squad_team_id"]) if r["squad_team_id"] else None
        updown = None
        if sq_seq is not None and fixture_seq is not None and sq_seq != fixture_seq:
            updown = "up" if sq_seq > fixture_seq else "down"
        out.append({
            "player_id": pid, "name": r["name"], "score": fb["score"],
            "recent_scores": fb["recent_scores"], "recent_wickets": fb["recent_wickets"],
            "recent_avg": fb["recent_avg"], "play_updown": updown,
            "available": avail.get(pid),
        })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:PROMOTE_LIMIT]
