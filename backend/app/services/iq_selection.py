"""BetterIQ — Selection analysis (master-plan Phase 2).

Boundary with BetterSelect: **BetterSelect picks the team; BetterIQ analyses and
justifies the pick.** Crucially this reuses BetterSelect's *own* selection pool
(`services/selection_pool.assemble_selection`) so eligibility — the 12-month
recency wall, the women's/men's gender wall, squad tier (same-XI / promotion /
drop-down) and per-date availability — is **identical** to what BetterSelect
shows. (Re-deriving it here previously let ghosts through: a women's-grade player
and years-dormant names surfaced as "promote" picks for a men's 2nd XI.)

On top of that shared pool we layer: XI **balance**, recent **form**, **warnings**
(now including ineligible picks — wrong gender, inactive, dormant, unavailable),
**promote/rest**, **fairness** (season load + playing up/down), an opponent
**match-up** tie-in, and a one-line **verdict**.
"""
from __future__ import annotations

import uuid

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Fixture
from app.services.iq import resolve_opponent
from app.services.selection_pool import assemble_selection

THIN_ATTACK = 5            # fewer front-line bowling options than this → warn
OUT_OF_FORM_AVG = 15.0     # recent batting average below this (min 3 inns) → flag
PROMOTE_LIMIT = 6
RECENT_GAMES = 5

_PACE = {"FAST", "FAST_MEDIUM", "MEDIUM", "MEDIUM_FAST"}
_SPIN = {"FINGER_SPIN", "WRIST_SPIN"}
_ORG_SCOPE = " JOIN grades gr ON gr.id = g.grade_id JOIN seasons s ON s.id = gr.season_id"


def _skills(sp) -> set[str]:
    return {str(s).upper() for s in (sp or []) if s}


def _tier_updown(tier) -> str | None:
    # Pool tier: 2 = squad one grade below the fixture (promotion → playing UP),
    # 3 = squad one grade above (drop-down → playing DOWN).
    return "up" if tier == 2 else ("down" if tier == 3 else None)


async def list_lineups(db: AsyncSession, club) -> list[dict]:
    """Fixtures with a saved lineup, soonest-upcoming first then recent past."""
    res = await db.execute(
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
        {"org": str(club.id)},
    )
    from datetime import date
    today = date.today()
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
    upcoming = sorted([x for x in rows if x["_d"] and x["_d"] >= today], key=lambda x: x["_d"])
    past = sorted([x for x in rows if not x["_d"] or x["_d"] < today],
                  key=lambda x: (x["_d"] is not None, x["_d"]), reverse=True)
    out = upcoming + past
    for x in out:
        x.pop("_d", None)
    return out[:40]


async def _recent_scores(db: AsyncSession, org_id: str) -> dict[str, dict]:
    """Per-player last-5 batting scores + bowling wicket-hauls (club-wide)."""
    form: dict[str, dict] = {}
    bat = await db.execute(
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
            SELECT player_id::text AS id, runs, not_out FROM innings WHERE rn <= :n ORDER BY player_id, rn
            """
        ),
        {"org": org_id, "n": RECENT_GAMES},
    )
    for r in bat.mappings():
        d = form.setdefault(r["id"], {"bat": [], "bowl": []})
        d["bat"].append(f"{r['runs']}*" if r["not_out"] else str(r["runs"]))
    bowl = await db.execute(
        text(
            f"""
            WITH spells AS (
                SELECT bs.player_id, bs.wickets,
                       ROW_NUMBER() OVER (
                           PARTITION BY bs.player_id ORDER BY g.played_at DESC NULLS LAST, bs.id DESC
                       ) AS rn
                FROM v_effective_bowling_spells bs
                JOIN v_effective_games g ON g.id = bs.game_id{_ORG_SCOPE}
                WHERE s.organisation_id = CAST(:org AS UUID)
            )
            SELECT player_id::text AS id, wickets FROM spells WHERE rn <= :n ORDER BY player_id, rn
            """
        ),
        {"org": org_id, "n": RECENT_GAMES},
    )
    for r in bowl.mappings():
        d = form.setdefault(r["id"], {"bat": [], "bowl": []})
        d["bowl"].append(r["wickets"] or 0)
    # Derive a recent batting average (outs only) for the out-of-form check.
    for d in form.values():
        outs = sum(1 for x in d["bat"] if not x.endswith("*"))
        runs = sum(int(x.rstrip("*")) for x in d["bat"])
        d["recent_avg"] = round(runs / outs, 1) if outs else None
        d["bat_inns"] = len(d["bat"])
    return form


async def _season_load(db: AsyncSession, grade_id: str | None) -> dict[str, int]:
    """This-season match count per player (for fairness/load), via the fixture's grade's season."""
    if not grade_id:
        return {}
    res = await db.execute(
        text(
            """
            SELECT pss.player_id::text AS id, COALESCE(SUM(pss.matches), 0) AS m
            FROM player_season_stats pss
            WHERE pss.season_id = (SELECT season_id FROM grades WHERE id = CAST(:gid AS UUID))
            GROUP BY pss.player_id
            """
        ),
        {"gid": grade_id},
    )
    return {r["id"]: r["m"] for r in res.mappings()}


async def _vs_opponent(db: AsyncSession, org_id: str, opp_key: str) -> dict[str, dict]:
    """Each of our players' record vs this opponent (match-up tie-in)."""
    out: dict[str, dict] = {}
    bat = await db.execute(
        text(
            f"""
            SELECT bi.player_id::text AS id,
                   COALESCE(SUM(bi.runs) FILTER (WHERE bi.did_not_bat IS NOT TRUE), 0) AS runs,
                   COUNT(*) FILTER (WHERE bi.did_not_bat IS NOT TRUE AND NOT bi.not_out AND bi.dismissal_type IS NOT NULL) AS outs
            FROM v_effective_batting_innings bi
            JOIN v_effective_games g ON g.id = bi.game_id{_ORG_SCOPE}
            WHERE s.organisation_id = CAST(:org AS UUID) AND COALESCE(g.opp_org_id, g.opp_club_name) = :k
            GROUP BY bi.player_id
            """
        ),
        {"org": org_id, "k": opp_key},
    )
    for r in bat.mappings():
        runs, outs = r["runs"] or 0, r["outs"] or 0
        if runs:
            out.setdefault(r["id"], {})["bat"] = {"runs": runs, "avg": round(runs / outs, 1) if outs else None}
    bowl = await db.execute(
        text(
            f"""
            SELECT bs.player_id::text AS id,
                   COALESCE(SUM(bs.wickets), 0) AS wkts, COALESCE(SUM(bs.runs), 0) AS runs
            FROM v_effective_bowling_spells bs
            JOIN v_effective_games g ON g.id = bs.game_id{_ORG_SCOPE}
            WHERE s.organisation_id = CAST(:org AS UUID) AND COALESCE(g.opp_org_id, g.opp_club_name) = :k
            GROUP BY bs.player_id
            """
        ),
        {"org": org_id, "k": opp_key},
    )
    for r in bowl.mappings():
        wkts, runs = r["wkts"] or 0, r["runs"] or 0
        if wkts:
            out.setdefault(r["id"], {})["bowl"] = {"wickets": wkts, "avg": round(runs / wkts, 1) if wkts else None}
    return out


async def selection_analysis(db: AsyncSession, club, fixture_id: str) -> dict | None:
    """Analyse a fixture's saved XI on top of BetterSelect's eligibility pool."""
    fx = await db.get(Fixture, uuid.UUID(fixture_id))
    if not fx or fx.organisation_id != club.id:
        return None

    sel = await assemble_selection(db, club, fx)
    meta = (await db.execute(
        text("SELECT t.name AS team_name, gr.name AS grade_name FROM fixtures f "
             "LEFT JOIN teams t ON t.id = f.team_id LEFT JOIN grades gr ON gr.id = f.grade_id "
             "WHERE f.id = CAST(:fid AS UUID)"),
        {"fid": fixture_id},
    )).mappings().first() or {}
    pool = {p["id"]: p for p in sel["pool"]}
    lineup = sel["lineup"]
    selected_ids = {row["player_id"] for row in lineup}
    grade_id = sel["fixture"].get("grade_id")

    form = await _recent_scores(db, str(club.id))
    load = await _season_load(db, grade_id)

    # Opponent match-up tie-in (only if the fixture resolves to a club we've played).
    opp_key, opp_name, _ = await resolve_opponent(db, str(club.id), fixture_id=fixture_id)
    vs_opp = await _vs_opponent(db, str(club.id), opp_key) if opp_key else {}

    # ── Names for any selected player missing from the pool (e.g. is_player=False) ──
    missing = [pid for pid in selected_ids if pid not in pool]
    name_fallback: dict[str, str] = {}
    if missing:
        nf = await db.execute(
            text("SELECT id::text AS id, COALESCE(display_name_override, name) AS name "
                 "FROM players WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
            {"ids": [uuid.UUID(x) for x in missing]},
        )
        name_fallback = {r["id"]: r["name"] for r in nf.mappings()}

    players = []
    pace = spin = bowl_opts = keepers = captains = openers = lh = rh = allr = spec_bat = 0
    for row in sorted(lineup, key=lambda r: (r["batting_order"] or 999)):
        pid = row["player_id"]
        p = pool.get(pid, {})
        skills = _skills(p.get("skill_positions"))
        bt = (p.get("bowling_type") or "").upper()
        does_bowl = "BWL" in skills or "ALL" in skills or bool(bt)
        is_ar = "ALL" in skills or ("BWL" in skills and (skills & {"BAT", "WKT"}))
        is_keeper = bool(row["is_wicket_keeper"]) or "WKT" in skills

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
        if row["is_captain"]:
            captains += 1
        if p.get("is_opening_batsman"):
            openers += 1
        hand = (p.get("batting_hand") or "").upper()
        if hand == "LEFT":
            lh += 1
        elif hand == "RIGHT":
            rh += 1

        f = form.get(pid, {})
        # Eligibility flags carried from the shared pool (the bug-fix surface).
        flags = []
        if p:
            if not p.get("gender_ok", True):
                flags.append("wrong-grade")
            if p.get("is_inactive"):
                flags.append("inactive")
            elif p.get("is_dormant"):
                flags.append("dormant")
        if p.get("availability") == "UNAVAILABLE":
            flags.append("unavailable")

        players.append({
            "player_id": pid,
            "name": p.get("display_name") or name_fallback.get(pid, "Unknown"),
            "batting_order": row["batting_order"],
            "is_captain": bool(row["is_captain"]),
            "is_wicket_keeper": is_keeper,
            "skills": sorted(skills),
            "bowling_type": p.get("bowling_type"),
            "is_opener": bool(p.get("is_opening_batsman")),
            "availability": p.get("availability"),
            "last_played": p.get("last_played"),
            "season_matches": load.get(pid, 0),
            "play_updown": _tier_updown(p.get("tier")),
            "recent_scores": f.get("bat", []),
            "recent_wickets": f.get("bowl", []),
            "recent_avg": f.get("recent_avg"),
            "form_score": p.get("score"),
            "vs_opponent": vs_opp.get(pid),
            "flags": flags,
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

    wrong_grade = [p["name"] for p in players if "wrong-grade" in p["flags"]]
    if wrong_grade:
        warnings.append({"level": "warn", "text": "Different-grade (e.g. women's) player picked: " + ", ".join(wrong_grade) + "."})
    inactive = [p["name"] for p in players if "inactive" in p["flags"]]
    if inactive:
        warnings.append({"level": "warn", "text": "Marked inactive: " + ", ".join(inactive) + "."})
    dormant = [p["name"] for p in players if "dormant" in p["flags"]]
    if dormant:
        warnings.append({"level": "warn", "text": "Hasn't played in a while: " + ", ".join(dormant) + "."})
    unavailable = [p["name"] for p in players if "unavailable" in p["flags"]]
    if unavailable:
        warnings.append({"level": "warn", "text": "Selected but marked unavailable: " + ", ".join(unavailable) + "."})
    cold = [p["name"] for p in players
            if p["recent_avg"] is not None and p["recent_avg"] < OUT_OF_FORM_AVG
            and "BAT" in p["skills"] and len(p["recent_scores"]) >= 3]
    if cold:
        warnings.append({"level": "info", "text": "Out of form with the bat: " + ", ".join(cold) + "."})

    # ── Promote: eligible (recent + right gender + squad tier), available, left out ──
    promote = []
    for p in sel["pool"]:
        if p["id"] in selected_ids or not p.get("autofill_eligible"):
            continue
        if p.get("availability") == "UNAVAILABLE":
            continue
        f = form.get(p["id"], {})
        promote.append({
            "player_id": p["id"], "name": p["display_name"], "score": p["score"],
            "recent_scores": f.get("bat", []), "recent_wickets": f.get("bowl", []),
            "recent_avg": f.get("recent_avg"), "play_updown": _tier_updown(p.get("tier")),
            "availability": p.get("availability"), "vs_opponent": vs_opp.get(p["id"]),
        })
    promote.sort(key=lambda x: (x["score"] or 0), reverse=True)
    promote = promote[:PROMOTE_LIMIT]

    # ── Rest / watch: picked but ineligible or out of form ──
    rest = []
    for p in players:
        reasons = []
        if "dormant" in p["flags"]:
            reasons.append("hasn't played recently")
        if "inactive" in p["flags"]:
            reasons.append("inactive")
        if p["recent_avg"] is not None and p["recent_avg"] < OUT_OF_FORM_AVG \
                and "BAT" in p["skills"] and len(p["recent_scores"]) >= 3:
            reasons.append("out of form")
        if reasons:
            rest.append({"player_id": p["player_id"], "name": p["name"],
                         "recent_scores": p["recent_scores"], "recent_avg": p["recent_avg"],
                         "reason": ", ".join(reasons)})

    # ── Verdict (one-liner) ──
    warn_count = sum(1 for w in warnings if w["level"] == "warn")
    if warn_count == 0:
        verdict = "Well-balanced XI — no selection flags."
    else:
        verdict = f"{warn_count} thing{'s' if warn_count != 1 else ''} to look at before locking it in."

    return {
        "fixture": {
            "fixture_id": sel["fixture"]["id"], "opponent_name": sel["fixture"]["opponent_name"],
            "played_on": sel["fixture"]["played_on"], "home_away": sel["fixture"]["home_away"],
            "venue": sel["fixture"]["venue"], "team_name": meta.get("team_name"), "grade_name": meta.get("grade_name"),
            "opponent_key": opp_key, "opponent_resolved_name": opp_name,
        },
        "verdict": verdict,
        "balance": balance,
        "players": players,
        "warnings": warnings,
        "promote": promote,
        "rest": rest,
        "team_size_target": sel.get("default_team_size", 11),
        "coverage": {
            "notes": [
                "Eligibility (recency, gender, squad) matches BetterSelect's selection board exactly.",
                "Form is the last 5 innings/spells; availability is the answer for the match date.",
                ("Match-up column shows each player's record vs " + opp_name + ".") if opp_key and opp_name else
                "No opponent history matched, so the match-up column is blank.",
            ]
        },
    }
