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
from datetime import datetime, timedelta, timezone

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Fixture
from app.services.grade_labels import strip_sponsor_suffix
from app.services.iq import resolve_opponent
from app.services.iq_filters import grade_base, grade_canonical_label, grade_match_clause, season_member_clause
from app.services.selection_pool import assemble_selection

THIN_ATTACK = 5            # fewer front-line bowling options than this → warn
OUT_OF_FORM_AVG = 15.0     # recent batting average below this (min 3 inns) → flag
PROMOTE_LIMIT = 6
RECENT_GAMES = 5
STALE_AVAIL_DAYS = 14      # availability answers older than this are "stale"

_PACE = {"FAST", "FAST_MEDIUM", "MEDIUM", "MEDIUM_FAST"}
_SPIN = {"FINGER_SPIN", "WRIST_SPIN"}
# Ownership joins + predicate — mirrors aggregations._club_results (migrations
# 167/169): grades LEFT JOINed, season off the view's own g.season_id, and a
# game is ours if we're home/away org, it's our manual game (organisation_id),
# the grade's season is ours, or one of our players has a recorded appearance.
# The old INNER grades→seasons chain silently dropped grade-less manual games
# and shared fixtures whose grade belongs to whichever club synced first.
_OWN_JOIN = " LEFT JOIN grades gr ON gr.id = g.grade_id LEFT JOIN seasons s ON s.id = g.season_id"
_OWN_PRED = """(
    g.organisation_id = CAST(:org AS UUID)
    OR g.home_org_id = CAST(:org AS UUID)
    OR g.away_org_id = CAST(:org AS UUID)
    OR s.organisation_id = CAST(:org AS UUID)
    OR EXISTS (
        SELECT 1 FROM game_appearances oga
        JOIN players op ON op.id = oga.player_id
        WHERE oga.game_id = g.id AND op.organisation_id = CAST(:org AS UUID)
    )
)"""


def _skills(sp) -> set[str]:
    return {str(s).upper() for s in (sp or []) if s}


def _tier_updown(tier) -> str | None:
    # Pool tier: 2 = squad one grade below the fixture (promotion → playing UP),
    # 3 = squad one grade above (drop-down → playing DOWN).
    return "up" if tier == 2 else ("down" if tier == 3 else None)


_AVAIL_RANK = {"AVAILABLE": 0, "MAYBE": 1, "NO_RESPONSE": 2}


def _is_keeper(p) -> bool:
    return "WKT" in _skills(p.get("skill_positions"))


def _does_bowl(p) -> bool:
    sk = _skills(p.get("skill_positions"))
    return "BWL" in sk or "ALL" in sk or bool(p.get("bowling_type"))


def _best_available_xi(pool: list[dict], target: int) -> list[dict]:
    """Greedy best-available XI from the eligible pool: top form, available first,
    then constraint-repaired to include a keeper and ≥5 bowling options.

    A clash-blocked player (already named in a same-day XI that this fixture
    does not outrank — the pool's ``clash_blocks``) is not available to this
    XI, so they're excluded the same way the board itself refuses the pick."""
    cands = [p for p in pool if p.get("autofill_eligible") and p.get("availability") != "UNAVAILABLE"
             and not p.get("clash_blocks")]
    cands.sort(key=lambda p: (_AVAIL_RANK.get(p.get("availability"), 3), -(p.get("score") or 0)))
    if len(cands) <= target:
        return sorted(cands, key=lambda p: -(p.get("score") or 0))

    picked, bench = cands[:target], cands[target:]

    # Ensure a keeper.
    if not any(_is_keeper(p) for p in picked):
        kp = next((p for p in bench if _is_keeper(p)), None)
        if kp:
            drop = min(picked, key=lambda p: (p.get("score") or 0))
            picked.remove(drop); picked.append(kp); bench.remove(kp); bench.append(drop)

    # Ensure ≥5 bowling options (don't trade away the keeper).
    def nbowl(lst): return sum(1 for p in lst if _does_bowl(p))
    guard = 0
    while nbowl(picked) < 5 and guard < target:
        guard += 1
        add = next((p for p in sorted(bench, key=lambda p: -(p.get("score") or 0)) if _does_bowl(p)), None)
        if not add:
            break
        droppable = [p for p in picked if not _is_keeper(p) and not _does_bowl(p)] or \
                    [p for p in picked if not _is_keeper(p)]
        if not droppable:
            break
        drop = min(droppable, key=lambda p: (p.get("score") or 0))
        picked.remove(drop); picked.append(add); bench.remove(add); bench.append(drop)

    return sorted(picked, key=lambda p: -(p.get("score") or 0))


async def list_lineups(db: AsyncSession, club, grade_id: str | None = None) -> list[dict]:
    """Fixtures with a saved lineup, soonest-upcoming first then recent past.

    ``grade_id`` (a grades row id) filters server-side BEFORE the 40-row cap,
    matching the fixture's own grade id or its sponsor-stripped base NAME (so
    sibling season rows of the same competition grade match too). A fixture
    with no grade_id stays visible under any filter — resolving its grade via
    the synced game's playhq_id would cost a per-row cast/join for a picker,
    and dropping it would hide a real saved XI."""
    grade_clause = ""
    params: dict = {"org": str(club.id)}
    if grade_id:
        grade_clause = f"""
              AND (
                f.grade_id IS NULL
                OR f.grade_id = CAST(:grade_id AS UUID)
                OR {grade_base("COALESCE(gr.display_name_override, gr.name)")} = (
                    SELECT {grade_base("COALESCE(g2.display_name_override, g2.name)")}
                    FROM grades g2 WHERE g2.id = CAST(:grade_id AS UUID))
              )"""
        params["grade_id"] = grade_id
    res = await db.execute(
        text(
            f"""
            SELECT f.id::text AS id, f.opponent_name, f.played_on, f.home_away,
                   f.venue, gr.name AS grade_name, t.name AS team_name,
                   COUNT(fl.player_id) AS lineup_count
            FROM fixtures f
            LEFT JOIN fixture_lineups fl ON fl.fixture_id = f.id
            LEFT JOIN grades gr ON gr.id = f.grade_id
            LEFT JOIN teams t ON t.id = f.team_id
            WHERE f.organisation_id = CAST(:org AS UUID){grade_clause}
            GROUP BY f.id, f.opponent_name, f.played_on, f.home_away, f.venue,
                     gr.display_name_override, gr.name, t.name
            HAVING COUNT(fl.player_id) > 0 OR f.played_on >= CURRENT_DATE
            """
        ),
        params,
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
    """Per-player last-5 batting scores + bowling wicket-hauls (club-wide).

    The innings pull is scoped to OUR players (a shared both-synced fixture's
    one games row carries both clubs' innings) and the games universe is the
    canonical ownership predicate, so a grade-less manual game still counts.
    NOTE: intentionally a different window from selection_pool's own form
    computation — the pool scores on the last-4 raw per-innings rows, this
    strip shows the last-5 over the effective views. Don't unify them here.
    """
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
                JOIN players p ON p.id = bi.player_id AND p.organisation_id = CAST(:org AS UUID)
                JOIN v_effective_games g ON g.id = bi.game_id{_OWN_JOIN}
                WHERE {_OWN_PRED}
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
                JOIN players p ON p.id = bs.player_id AND p.organisation_id = CAST(:org AS UUID)
                JOIN v_effective_games g ON g.id = bs.game_id{_OWN_JOIN}
                WHERE {_OWN_PRED}
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


async def _season_load(db: AsyncSession, grade_id: str | None, org_id: str | None = None) -> dict[str, int]:
    """Games in THIS GRADE this season per player (for fairness/load).

    The season is year-expanded (all the org's season rows sharing the fixture
    grade's year — the iq_filters convention, since one real season is stored
    as several rows) and scoped to the fixture's grade by its merged,
    sponsor-stripped base NAME via ``grade_match_clause``, counted from
    org-scoped ``game_appearances`` — ``player_season_stats`` carries no grade
    dimension, so a grade-scoped load can only come from per-game rows. The
    old read summed the whole season's pss matches across every grade."""
    if not grade_id or not org_id:
        return {}
    g = (await db.execute(
        text("SELECT season_id::text AS season_id, COALESCE(display_name_override, name) AS name "
             "FROM grades WHERE id = CAST(:gid AS UUID)"),
        {"gid": grade_id},
    )).mappings().first()
    if not g or not g["season_id"]:
        return {}
    res = await db.execute(
        text(
            f"""
            SELECT ga.player_id::text AS id, COUNT(DISTINCT ga.game_id) AS m
            FROM game_appearances ga
            JOIN players p ON p.id = ga.player_id AND p.organisation_id = CAST(:org AS UUID)
            JOIN v_effective_games g ON g.id = ga.game_id
            JOIN grades gr ON gr.id = g.grade_id
            WHERE TRUE {season_member_clause('gr.season_id', g["season_id"])}
              AND {grade_match_clause(grade_canonical_label('gr', 'org'))}
            GROUP BY ga.player_id
            """
        ),
        {"org": org_id, "season": g["season_id"], "grade": strip_sponsor_suffix(g["name"])},
    )
    return {r["id"]: int(r["m"] or 0) for r in res.mappings()}


async def _vs_opponent(db: AsyncSession, org_id: str, opp_key: str) -> dict[str, dict]:
    """Each of our players' record vs this opponent (match-up tie-in).

    The innings pulls are scoped to OUR players — on a shared both-synced
    fixture the one games row carries both clubs' rows, so an unscoped read
    would fold the opponent's own batting/bowling into "our record vs them"."""
    out: dict[str, dict] = {}
    bat = await db.execute(
        text(
            f"""
            SELECT bi.player_id::text AS id,
                   COALESCE(SUM(bi.runs) FILTER (WHERE bi.did_not_bat IS NOT TRUE), 0) AS runs,
                   COUNT(*) FILTER (WHERE bi.did_not_bat IS NOT TRUE AND NOT bi.not_out AND bi.dismissal_type IS NOT NULL) AS outs
            FROM v_effective_batting_innings bi
            JOIN players p ON p.id = bi.player_id AND p.organisation_id = CAST(:org AS UUID)
            JOIN v_effective_games g ON g.id = bi.game_id{_OWN_JOIN}
            WHERE {_OWN_PRED} AND COALESCE(g.opp_org_id, g.opp_club_name) = :k
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
            JOIN players p ON p.id = bs.player_id AND p.organisation_id = CAST(:org AS UUID)
            JOIN v_effective_games g ON g.id = bs.game_id{_OWN_JOIN}
            WHERE {_OWN_PRED} AND COALESCE(g.opp_org_id, g.opp_club_name) = :k
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
    load = await _season_load(db, grade_id, str(club.id))

    # When each player's availability answer for the match date was recorded
    # (per-date rows only — a period-fallback answer has no per-date row and
    # simply carries no timestamp). Backs the stale-answer count below.
    answered_at: dict[str, datetime] = {}
    if fx.played_on:
        av = await db.execute(
            text("SELECT player_id::text AS id, COALESCE(recorded_at, created_at) AS at "
                 "FROM player_availability "
                 "WHERE organisation_id = CAST(:org AS UUID) AND avail_date = :d"),
            {"org": str(club.id), "d": fx.played_on},
        )
        for r in av.mappings():
            if r["at"] is not None:
                answered_at[r["id"]] = r["at"]
    stale_cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_AVAIL_DAYS)

    def _answer_stale(ts) -> bool:
        if ts is None:
            return False
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts < stale_cutoff

    # Who's already picked in OTHER upcoming fixtures (cross-fixture awareness for
    # a multi-grade round) → player_id -> ["2nd XI vs …", …].
    picked_elsewhere: dict[str, list[str]] = {}
    other = await db.execute(
        text(
            """
            SELECT fl.player_id::text AS pid,
                   COALESCE(t.name, f.opponent_name, 'another fixture') AS where_
            FROM fixture_lineups fl
            JOIN fixtures f ON f.id = fl.fixture_id
            LEFT JOIN teams t ON t.id = f.team_id
            WHERE fl.organisation_id = CAST(:org AS UUID) AND f.id <> CAST(:fid AS UUID)
              AND (f.played_on IS NULL OR f.played_on >= CURRENT_DATE)
            ORDER BY f.played_on ASC NULLS LAST
            """
        ),
        {"org": str(club.id), "fid": fixture_id},
    )
    for r in other.mappings():
        picked_elsewhere.setdefault(r["pid"], []).append(r["where_"])

    # Opponent match-up tie-in (only if the fixture resolves to a club we've played).
    opp_key, opp_name, _ = await resolve_opponent(db, str(club.id), fixture_id=fixture_id)
    vs_opp = await _vs_opponent(db, str(club.id), opp_key) if opp_key else {}

    # ── Names for any selected player missing from the pool (e.g. is_player=False) ──
    missing = [pid for pid in selected_ids if pid not in pool]
    name_fallback: dict[str, str] = {}
    if missing:
        nf = await db.execute(
            text("SELECT id::text AS id, COALESCE(display_name_override, name) AS name "
                 "FROM players WHERE id IN :ids AND organisation_id = CAST(:org AS UUID)"
                 ).bindparams(bindparam("ids", expanding=True)),
            {"ids": [uuid.UUID(x) for x in missing], "org": str(club.id)},
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
            # The pool's 12-month autofill recency wall — a player outside it
            # is ineligible on BetterSelect's own board, so a saved pick of
            # them deserves a flag here too.
            if p.get("recent_ok") is False:
                flags.append("not-recent")
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
            "availability_answered_at": (answered_at[pid].isoformat() if pid in answered_at else None),
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
        warnings.append({"level": "warn", "text": f"Thin attack: only {bowl_opts} front-line bowling options."})
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
    # The club's own association rules, from the same pool BetterSelect draws
    # its board from — so IQ and the board never disagree about who may play.
    # Blocking breaches read as warnings here; this screen advises, it doesn't
    # save anything.
    picked_ids = {p["player_id"] for p in players}
    rule_lines: dict[str, list[str]] = {}
    for entry in sel.get("pool", []):
        if entry["id"] not in picked_ids:
            continue
        for f in entry.get("rule_flags", []):
            rule_lines.setdefault(f["name"], []).append(f"{entry['display_name']} ({f['detail']})")
    for rule_name, who in rule_lines.items():
        warnings.append({"level": "warn", "text": f"{rule_name}: " + ", ".join(who) + "."})
    for team_rule in (sel.get("rules", {}) or {}).get("team", []):
        if team_rule["kind"] != "overseas":
            continue
        n = len([pid for pid in team_rule.get("player_ids", []) if pid in picked_ids])
        cap = (team_rule.get("config") or {}).get("max_in_xi", 1)
        if n > cap:
            warnings.append({"level": "warn",
                             "text": f"{team_rule['name']}: {n} overseas players named, {cap} allowed."})

    not_recent = [p["name"] for p in players if "not-recent" in p["flags"]]
    if not_recent:
        warnings.append({"level": "warn", "text": "Outside BetterSelect's 12-month selection window: " + ", ".join(not_recent) + "."})
    cold = [p["name"] for p in players
            if p["recent_avg"] is not None and p["recent_avg"] < OUT_OF_FORM_AVG
            and "BAT" in p["skills"] and len(p["recent_scores"]) >= 3]
    if cold:
        warnings.append({"level": "info", "text": "Out of form with the bat: " + ", ".join(cold) + "."})

    # ── Promote: eligible (recent + right gender + squad tier), available, left out ──
    # A clash-blocked candidate (already named in a same-day XI this fixture
    # doesn't outrank — the pool's `clash_blocks`) isn't a real promote option;
    # they're surfaced separately in `clash_excluded` so the selector sees WHY.
    promote = []
    clash_excluded = []
    for p in sel["pool"]:
        if p["id"] in selected_ids or not p.get("autofill_eligible"):
            continue
        if p.get("availability") == "UNAVAILABLE":
            continue
        f = form.get(p["id"], {})
        if p.get("clash_blocks"):
            clash_excluded.append({
                "player_id": p["id"], "name": p["display_name"], "score": p["score"],
                "picked_in": p.get("clash", []),
                "clash_detail": p.get("clash_detail", []),
            })
            continue
        promote.append({
            "player_id": p["id"], "name": p["display_name"], "score": p["score"],
            "recent_scores": f.get("bat", []), "recent_wickets": f.get("bowl", []),
            "recent_avg": f.get("recent_avg"), "play_updown": _tier_updown(p.get("tier")),
            "availability": p.get("availability"), "vs_opponent": vs_opp.get(p["id"]),
        })
    promote.sort(key=lambda x: (x["score"] or 0), reverse=True)
    promote = promote[:PROMOTE_LIMIT]
    clash_excluded.sort(key=lambda x: (x["score"] or 0), reverse=True)

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

    # ── Best available XI (from the eligible pool) + diff vs the pick ──
    target = sel.get("default_team_size") or 11
    best = _best_available_xi(sel["pool"], target)
    best_ids = {p["id"] for p in best}

    def _shape_best(p):
        f = form.get(p["id"], {})
        return {
            "player_id": p["id"], "name": p["display_name"],
            "skills": sorted(_skills(p.get("skill_positions"))),
            "score": p.get("score"), "availability": p.get("availability"),
            "play_updown": _tier_updown(p.get("tier")),
            "recent_scores": f.get("bat", []), "in_xi": p["id"] in selected_ids,
        }
    best_xi = [_shape_best(p) for p in best]
    suggest_in = [_shape_best(p) for p in best if p["id"] not in selected_ids]
    suggest_out = [{"player_id": p["player_id"], "name": p["name"], "flags": p["flags"]}
                   for p in players if p["player_id"] not in best_ids]

    # ── Full eligible pool (every selectable squad player, incl. promotion /
    # drop-down candidates) so the UI can build a best XI from scratch on an empty
    # fixture, show ALL squad availability, and let the user add/remove anyone —
    # not just the saved XI ∪ promotes. ──
    order_by_id = {r["player_id"]: r for r in lineup}
    pool_out = []
    for p in sel["pool"]:
        f = form.get(p["id"], {})
        skills = _skills(p.get("skill_positions"))
        flags = []
        if not p.get("gender_ok", True):
            flags.append("wrong-grade")
        if p.get("is_inactive"):
            flags.append("inactive")
        elif p.get("is_dormant"):
            flags.append("dormant")
        if p.get("recent_ok") is False:
            flags.append("not-recent")
        if p.get("availability") == "UNAVAILABLE":
            flags.append("unavailable")
        lrow = order_by_id.get(p["id"])
        pool_out.append({
            "player_id": p["id"], "name": p["display_name"],
            "skills": sorted(skills), "bowling_type": p.get("bowling_type"),
            "is_wicket_keeper": ("WKT" in skills) or bool(lrow and lrow["is_wicket_keeper"]),
            "is_opener": bool(p.get("is_opening_batsman")),
            "availability": p.get("availability"),
            "autofill_eligible": bool(p.get("autofill_eligible")),
            "play_updown": _tier_updown(p.get("tier")),
            "squads": p.get("squads", []),
            "squad_team_id": p.get("squad_team_id"),
            # Other UPCOMING fixtures this player is ALSO selected in (cross-fixture
            # awareness — so a selector can see who's already picked elsewhere).
            "clash": picked_elsewhere.get(p["id"], []),
            "season_matches": load.get(p["id"], 0),
            "recent_scores": f.get("bat", []), "recent_wickets": f.get("bowl", []),
            "recent_avg": f.get("recent_avg"), "form_score": p.get("score"),
            "vs_opponent": vs_opp.get(p["id"]),
            "in_xi": p["id"] in selected_ids,
            "batting_order": lrow["batting_order"] if lrow else None,
            "is_captain": bool(lrow["is_captain"]) if lrow else False,
            "flags": flags,
        })
    # Keep any saved player who falls outside the eligibility pool (so the saved
    # XI is preserved faithfully and they can still be removed). The defaults
    # ahead of **pl fill the pool-row-only keys a `players` row doesn't carry
    # (they'd otherwise be undefined on the frontend); pl's own values win.
    pool_ids = {p["id"] for p in sel["pool"]}
    for pl in players:
        if pl["player_id"] not in pool_ids:
            pool_out.append({
                "squads": [], "squad_team_id": None, "clash": None,
                "season_matches": None,
                **pl, "in_xi": True, "autofill_eligible": False,
            })

    # ── Verdict (one-liner) ──
    warn_count = sum(1 for w in warnings if w["level"] == "warn")
    if warn_count == 0:
        verdict = "Well-balanced XI, no selection flags."
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
        "pool": pool_out,
        "warnings": warnings,
        "promote": promote,
        "clash_excluded": clash_excluded,
        "rest": rest,
        "best_xi": best_xi,
        "suggest_in": suggest_in,
        "suggest_out": suggest_out,
        "team_size_target": sel.get("default_team_size", 11),
        # Selected players whose per-date availability answer is older than
        # STALE_AVAIL_DAYS (period-fallback answers carry no timestamp and
        # aren't counted).
        "stale_answers": sum(1 for pl in players if _answer_stale(answered_at.get(pl["player_id"]))),
        # What `season_matches` now counts (grade-scoped, year-expanded season).
        "season_matches_label": "games in this grade this season",
        "coverage": {
            "notes": [
                "Eligibility (recency, gender, squad) matches BetterSelect's selection board exactly; "
                "promote and best-XI suggestions also honour same-day clash blocks (a player already "
                "named in an XI this fixture doesn't outrank is listed under clash_excluded, not promoted).",
                "Form is the last 5 innings/spells; availability is the answer for the match date.",
                "Season load counts games in this fixture's grade across the season's rows.",
                ("Match-up column shows each player's record vs " + opp_name + ".") if opp_key and opp_name else
                "No opponent history matched, so the match-up column is blank.",
            ]
        },
    }
