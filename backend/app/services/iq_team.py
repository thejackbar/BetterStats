"""BetterIQ — our own team self-analysis (analytics brief §7/§8).

The mirror of the opposition dossier, pointed at us. Everything is reconstructed
from stored per-innings data (no live fetch):

- **Our team score** for a game = ``SUM(batting_innings.runs)`` (our batters).
- **Opponent score** = ``SUM(bowling_spells.runs)`` (runs our bowlers conceded).
  Both exclude some extras we don't store, so they're close-but-not-exact — fine
  for averages, score bands and bat-first/chase splits.
- **Batted first** = we have batting rows in innings 1.
- **Home/away** derived from the known opponent name vs the game's home/away club
  (same trick as ``iq._head_to_head``).

Org-scoped via grades→seasons over the ``v_effective_*`` views. Aggregation is
done in Python over one per-game pull so every cut (record, profile, bands,
venues) comes from a single query.
"""
from __future__ import annotations

import logging
import statistics

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def _safe(session: AsyncSession, factory, default):
    """Run an optional add-on analysis; if it fails, log it and roll the session
    back so the remaining add-ons (and the core response) still succeed. Keeps a
    single broken query from blanking the whole Team analysis page."""
    try:
        return await factory()
    except Exception:
        logger.exception("team_overview add-on failed")
        try:
            await session.rollback()
        except Exception:
            pass
        return default

# "What score wins" bands when batting first.
_BANDS = [(0, 120, "<120"), (120, 150, "120–149"), (150, 180, "150–179"), (180, 10_000, "180+")]


def _avg(vals: list) -> float | None:
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


async def team_seasons(session: AsyncSession, org_id: str) -> list[dict]:
    res = await session.execute(
        text(
            """
            SELECT s.id::text AS id, s.name, s.year
            FROM seasons s
            WHERE s.organisation_id = CAST(:org AS UUID)
              AND EXISTS (SELECT 1 FROM grades gr WHERE gr.season_id = s.id)
            ORDER BY s.year DESC NULLS LAST, s.name DESC
            """
        ),
        {"org": org_id},
    )
    return [{"season_id": r["id"], "name": r["name"], "year": r["year"]} for r in res.mappings()]


async def team_grades(session: AsyncSession, org_id: str, season_id: str | None) -> list[dict]:
    """Grades (teams) the club fielded — for the team filter.

    A CA grade is per-season *and* per-club (the same competition grade gets a new
    ``grades`` row keyed on a fresh uuid5 every season), so listing raw ids gives
    one "1st Grade" row per season. The filter is meant to mean "show me 1st Grade"
    across whatever seasons are in view, so we de-duplicate by NAME and key the
    filter on the name — ``_scope`` matches ``gr.name`` (scoped to the chosen
    season when one is set). The returned ``grade_id`` IS the name.

    Each row also carries ``season_id`` so the global Team filter can scope its
    options to the selected season — a club only fielded a given grade in some
    seasons, and offering one it didn't field returned an empty dashboard."""
    season_clause = "AND gr.season_id = CAST(:season AS UUID)" if season_id else ""
    res = await session.execute(
        text(
            f"""
            SELECT gr.name AS name, gr.season_id::text AS season_id
            FROM grades gr
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = CAST(:org AS UUID) {season_clause}
              AND EXISTS (SELECT 1 FROM v_effective_games g WHERE g.grade_id = gr.id)
            GROUP BY gr.name, gr.season_id
            ORDER BY gr.name
            """
        ),
        {"org": org_id, "season": season_id},
    )
    return [{"grade_id": r["name"], "name": r["name"], "season_id": r["season_id"]} for r in res.mappings()]


# Scope clause for the per-game functions. ``grade`` is a grade NAME (see
# ``team_grades``) — matching by name collapses the per-season/per-club grade ids
# so picking "1st Grade" works across a single season, a range, or all-time. A
# season + grade narrows to that season's grade; ``gr`` is the grades alias.
def _scope(season_id: str | None, grade_id: str | None) -> str:
    clauses = []
    if season_id:
        clauses.append("AND gr.season_id = CAST(:season AS UUID)")
    if grade_id:
        clauses.append("AND gr.name = :grade")
    return " ".join(clauses)


async def _per_game(session: AsyncSession, org_id: str, season_id: str | None, grade_id: str | None = None) -> list[dict]:
    season_clause = _scope(season_id, grade_id)
    res = await session.execute(
        text(
            f"""
            WITH our_games AS (
                SELECT g.id, g.played_at, g.result, g.venue, gr.name AS grade_name,
                       CASE WHEN g.away_club = g.opp_club_name THEN 'HOME'
                            WHEN g.home_club = g.opp_club_name THEN 'AWAY' ELSE NULL END AS our_venue
                FROM v_effective_games g
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id
                WHERE s.organisation_id = CAST(:org AS UUID) {season_clause}
            ),
            bat AS (
                SELECT bi.game_id,
                       SUM(bi.runs) AS our_runs,
                       SUM(COALESCE(bi.balls, 0)) AS our_balls,
                       SUM(4 * COALESCE(bi.fours, 0) + 6 * COALESCE(bi.sixes, 0)) AS boundary_runs,
                       COUNT(*) FILTER (WHERE bi.did_not_bat IS NOT TRUE AND NOT bi.not_out AND bi.dismissal_type IS NOT NULL) AS wkts_lost,
                       COALESCE(SUM(bi.runs) FILTER (WHERE bi.batting_position BETWEEN 1 AND 3), 0) AS top3,
                       COALESCE(SUM(bi.runs) FILTER (WHERE bi.batting_position BETWEEN 4 AND 7), 0) AS mid,
                       COALESCE(SUM(bi.runs) FILTER (WHERE bi.batting_position >= 8), 0) AS low,
                       BOOL_OR(bi.innings_number = 1) AS batted_first
                FROM v_effective_batting_innings bi
                JOIN our_games og ON og.id = bi.game_id
                WHERE bi.did_not_bat IS NOT TRUE
                GROUP BY bi.game_id
            ),
            bowl AS (
                SELECT bs.game_id, SUM(bs.runs) AS opp_runs, SUM(bs.wickets) AS wkts_taken
                FROM v_effective_bowling_spells bs
                JOIN our_games og ON og.id = bs.game_id
                GROUP BY bs.game_id
            )
            SELECT og.result, og.venue, og.our_venue,
                   b.our_runs, b.our_balls, b.boundary_runs, b.wkts_lost,
                   b.top3, b.mid, b.low, b.batted_first,
                   bw.opp_runs, bw.wkts_taken
            FROM our_games og
            LEFT JOIN bat b ON b.game_id = og.id
            LEFT JOIN bowl bw ON bw.game_id = og.id
            """
        ),
        {"org": org_id, "season": season_id, "grade": grade_id},
    )
    return [dict(r) for r in res.mappings()]


async def _partnerships(session: AsyncSession, org_id: str, season_id: str | None, grade_id: str | None = None) -> list[dict]:
    season_clause = _scope(season_id, grade_id)
    res = await session.execute(
        text(
            f"""
            SELECT p.wicket_number AS wk, ROUND(AVG(p.runs)::numeric, 1) AS avg_p, COUNT(*) AS n
            FROM partnerships p
            JOIN v_effective_games g ON g.id = p.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = CAST(:org AS UUID)
              AND p.is_club_innings IS TRUE AND p.wicket_number BETWEEN 1 AND 10 {season_clause}
            GROUP BY p.wicket_number
            HAVING COUNT(*) >= 3
            ORDER BY p.wicket_number
            """
        ),
        {"org": org_id, "season": season_id, "grade": grade_id},
    )
    return [{"wicket": r["wk"], "avg_partnership": float(r["avg_p"]), "samples": r["n"]} for r in res.mappings()]


def _win_pct(w: int, dec: int) -> float | None:
    return round(100 * w / dec, 1) if dec else None


async def _team_fielding(session: AsyncSession, org_id: str, season_id: str | None, grade_id: str | None = None) -> dict:
    """Top fielders (outfield catches), keepers (catches behind + stumpings) and
    run-out specialists, plus the fielder→bowler catching combos (brief §3/§9).
    Per-game (so it's season/team filterable); outfield catches are kept distinct
    from keeper catches (caught vs caught-behind): outfield = catches − catches_wk."""
    season_clause = _scope(season_id, grade_id)
    res = await session.execute(
        text(
            f"""
            SELECT p.id::text AS id, COALESCE(p.display_name_override, p.name) AS name,
                   COALESCE(SUM(GREATEST(fs.catches - COALESCE(fs.catches_wk, 0), 0)), 0) AS ct,
                   COALESCE(SUM(fs.run_outs), 0) AS ro,
                   COALESCE(SUM(fs.catches_wk), 0) AS ctwk,
                   COALESCE(SUM(fs.stumpings), 0) AS st
            FROM v_effective_fielding_stats fs
            JOIN players p ON p.id = fs.player_id
            JOIN v_effective_games g ON g.id = fs.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = CAST(:org AS UUID) {season_clause}
            GROUP BY p.id, p.display_name_override, p.name
            """
        ),
        {"org": org_id, "season": season_id, "grade": grade_id},
    )
    fielders, keepers = [], []
    for r in res.mappings():
        if r["ct"] or r["ro"]:
            fielders.append({"player_id": r["id"], "name": r["name"], "catches": r["ct"], "run_outs": r["ro"], "total": r["ct"] + r["ro"]})
        if r["ctwk"] or r["st"]:
            keepers.append({"player_id": r["id"], "name": r["name"], "catches": r["ctwk"], "stumpings": r["st"], "total": r["ctwk"] + r["st"]})
    fielders.sort(key=lambda x: (x["total"], x["catches"]), reverse=True)
    keepers.sort(key=lambda x: x["total"], reverse=True)

    combos_res = await session.execute(
        text(
            f"""
            SELECT COALESCE(pf.display_name_override, pf.name) AS fielder,
                   COALESCE(pb.display_name_override, pb.name) AS bowler, COUNT(*) AS n
            FROM bowler_wickets bw
            JOIN players pf ON pf.id = bw.fielder_id
            JOIN players pb ON pb.id = bw.bowler_id
            JOIN v_effective_games g ON g.id = bw.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = CAST(:org AS UUID) AND bw.fielder_id IS NOT NULL {season_clause}
            GROUP BY pf.id, fielder, pb.id, bowler
            HAVING COUNT(*) >= 3
            ORDER BY n DESC
            LIMIT 8
            """
        ),
        {"org": org_id, "season": season_id, "grade": grade_id},
    )
    combos = [{"fielder": r["fielder"], "bowler": r["bowler"], "count": r["n"]} for r in combos_res.mappings()]
    return {"fielders": fielders[:8], "keepers": keepers[:5], "combos": combos}


async def _all_rounders(session: AsyncSession, org_id: str, season_id: str | None, grade_id: str | None = None) -> list[dict]:
    """All-rounder analysis (brief §5) — players who contribute with both bat and
    ball, ranked by the classic batting-average − bowling-average difference."""
    season_clause = _scope(season_id, grade_id)
    min_inns, min_wkts = (4, 4) if (season_id or grade_id) else (10, 10)
    res = await session.execute(
        text(
            f"""
            WITH bat AS (
                SELECT bi.player_id AS pid, COUNT(*) AS inns, COALESCE(SUM(bi.runs), 0) AS runs,
                       COALESCE(SUM(CASE WHEN bi.not_out THEN 1 ELSE 0 END), 0) AS nout
                FROM v_effective_batting_innings bi
                JOIN v_effective_games g ON g.id = bi.game_id
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id
                WHERE s.organisation_id = CAST(:org AS UUID) AND bi.runs IS NOT NULL {season_clause}
                GROUP BY bi.player_id
            ),
            bowl AS (
                SELECT bs.player_id AS pid, COALESCE(SUM(bs.wickets), 0) AS wkts,
                       COALESCE(SUM(bs.runs), 0) AS conceded
                FROM v_effective_bowling_spells bs
                JOIN v_effective_games g ON g.id = bs.game_id
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id
                WHERE s.organisation_id = CAST(:org AS UUID) {season_clause}
                GROUP BY bs.player_id
            )
            SELECT p.id::text AS id, COALESCE(p.display_name_override, p.name) AS name,
                   bat.inns, bat.runs, bat.nout, bowl.wkts, bowl.conceded
            FROM players p
            JOIN bat ON bat.pid = p.id
            JOIN bowl ON bowl.pid = p.id
            WHERE p.organisation_id = CAST(:org AS UUID) AND bat.inns >= :min_inns AND bowl.wkts >= :min_wkts
            """
        ),
        {"org": org_id, "season": season_id, "grade": grade_id, "min_inns": min_inns, "min_wkts": min_wkts},
    )
    rows = []
    for r in res.mappings():
        outs = r["inns"] - r["nout"]
        bat_avg = round(r["runs"] / outs, 1) if outs > 0 else None
        bowl_avg = round(r["conceded"] / r["wkts"], 1) if r["wkts"] else None
        diff = round(bat_avg - bowl_avg, 1) if (bat_avg is not None and bowl_avg is not None) else None
        if bat_avg is not None and bowl_avg is not None:
            if bat_avg >= 20 and bowl_avg <= 30:
                role = "Genuine all-rounder"
            elif bat_avg >= bowl_avg:
                role = "Batting all-rounder"
            else:
                role = "Bowling all-rounder"
        else:
            role = "All-rounder"
        rows.append({
            "player_id": r["id"], "name": r["name"], "innings": r["inns"], "runs": r["runs"],
            "bat_avg": bat_avg, "wickets": r["wkts"], "bowl_avg": bowl_avg, "diff": diff, "role": role,
        })
    rows.sort(key=lambda x: (x["diff"] is not None, x["diff"] if x["diff"] is not None else -999), reverse=True)
    return rows[:12]


async def _batting_pairs(session: AsyncSession, org_id: str, season_id: str | None, grade_id: str | None = None) -> list[dict]:
    """Same-team batting partnerships by player pair (brief §11.1) — which two
    batters have the most prolific record at the crease together."""
    season_clause = _scope(season_id, grade_id)
    res = await session.execute(
        text(
            f"""
            WITH pr AS (
                SELECT LEAST(p.batter1_id, p.batter2_id) AS a,
                       GREATEST(p.batter1_id, p.batter2_id) AS b,
                       p.runs AS runs, p.wicket_number AS wk
                FROM partnerships p
                JOIN v_effective_games g ON g.id = p.game_id
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id
                WHERE s.organisation_id = CAST(:org AS UUID)
                  AND p.is_club_innings IS TRUE
                  AND p.batter1_id IS NOT NULL AND p.batter2_id IS NOT NULL
                  AND p.batter1_id <> p.batter2_id
                  AND p.runs IS NOT NULL {season_clause}
            )
            SELECT COALESCE(pa.display_name_override, pa.name) AS a_name,
                   COALESCE(pb.display_name_override, pb.name) AS b_name,
                   COUNT(*) AS stands, COALESCE(SUM(pr.runs), 0) AS total, MAX(pr.runs) AS best,
                   COUNT(*) FILTER (WHERE pr.runs >= 50) AS fifties,
                   COUNT(*) FILTER (WHERE pr.wk = 1) AS opening
            FROM pr
            JOIN players pa ON pa.id = pr.a
            JOIN players pb ON pb.id = pr.b
            GROUP BY pa.id, a_name, pb.id, b_name
            HAVING COUNT(*) >= :min_stands
            ORDER BY COALESCE(SUM(pr.runs), 0) DESC
            LIMIT 12
            """
        ),
        {"org": org_id, "season": season_id, "grade": grade_id, "min_stands": 2 if (season_id or grade_id) else 3},
    )
    pairs = []
    for r in res.mappings():
        stands = r["stands"]
        pairs.append({
            "a": r["a_name"], "b": r["b_name"], "stands": stands, "runs": r["total"],
            "avg": round(r["total"] / stands, 1) if stands else None,
            "best": r["best"], "fifties": r["fifties"],
            "opening": bool(r["opening"] and r["opening"] >= stands / 2),
        })
    return pairs


_PACE_TYPES = ("FAST", "FAST_MEDIUM", "MEDIUM", "MEDIUM_FAST")
_SPIN_TYPES = ("FINGER_SPIN", "WRIST_SPIN")


async def _attack_structure(session: AsyncSession, org_id: str, season_id: str | None, grade_id: str | None = None) -> dict | None:
    """Bowling attack structure (brief §8.3) — pace/spin balance and each
    frontline bowler's workload and role. Overs are stored in cricket notation
    (10.2 = 10 overs 2 balls) so they're converted to balls before summing."""
    season_clause = _scope(season_id, grade_id)
    min_balls = 60 if (season_id or grade_id) else 300
    res = await session.execute(
        text(
            f"""
            WITH sp AS (
                SELECT bs.player_id AS pid,
                       (FLOOR(bs.overs) * 6 + ROUND((bs.overs - FLOOR(bs.overs)) * 10))::int AS balls,
                       COALESCE(bs.runs, 0) AS runs, COALESCE(bs.wickets, 0) AS wkts
                FROM v_effective_bowling_spells bs
                JOIN v_effective_games g ON g.id = bs.game_id
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id
                WHERE s.organisation_id = CAST(:org AS UUID) AND bs.overs IS NOT NULL {season_clause}
            )
            SELECT p.id::text AS id, COALESCE(p.display_name_override, p.name) AS name,
                   p.bowling_type AS bt, SUM(sp.balls) AS balls,
                   SUM(sp.runs) AS runs, SUM(sp.wkts) AS wkts
            FROM sp JOIN players p ON p.id = sp.pid
            GROUP BY p.id, name, p.bowling_type
            HAVING SUM(sp.balls) >= :min_balls
            ORDER BY SUM(sp.balls) DESC
            """
        ),
        {"org": org_id, "season": season_id, "grade": grade_id, "min_balls": min_balls},
    )
    pace = spin = unknown = 0
    bowlers = []
    for r in res.mappings():
        balls = int(r["balls"] or 0)
        if not balls:
            continue
        bt = r["bt"]
        if bt in _PACE_TYPES:
            pace += balls
        elif bt in _SPIN_TYPES:
            spin += balls
        else:
            unknown += balls
        wkts, runs = int(r["wkts"] or 0), int(r["runs"] or 0)
        econ = round(runs * 6 / balls, 2)
        sr = round(balls / wkts, 1) if wkts else None
        avg = round(runs / wkts, 1) if wkts else None
        if wkts and sr is not None and sr <= 30:
            role = "Strike"
        elif econ <= 3.8:
            role = "Containment"
        else:
            role = "Stock"
        bowlers.append({
            "player_id": r["id"], "name": r["name"],
            "pace": bt in _PACE_TYPES, "spin": bt in _SPIN_TYPES,
            "overs": f"{balls // 6}.{balls % 6}", "wickets": wkts,
            "econ": econ, "avg": avg, "sr": sr, "role": role,
        })
    total = pace + spin + unknown
    if total == 0:
        return None
    return {
        "pace_pct": round(100 * pace / total),
        "spin_pct": round(100 * spin / total),
        "unknown_pct": round(100 * unknown / total),
        "bowlers": bowlers[:10],
    }


async def _collapses(session: AsyncSession, org_id: str, season_id: str | None, grade_id: str | None = None) -> dict | None:
    """Collapse analysis (brief §7.5) — how often we lose a cluster of wickets
    cheaply. Reconstructs fall-of-wickets from stored partnership runs and finds
    the worst 3-consecutive-wicket span per club innings."""
    from collections import defaultdict

    season_clause = _scope(season_id, grade_id)
    res = await session.execute(
        text(
            f"""
            SELECT p.game_id::text AS gid, p.innings_number AS inn,
                   p.wicket_number AS wk, p.runs AS runs
            FROM partnerships p
            JOIN v_effective_games g ON g.id = p.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = CAST(:org AS UUID) AND p.is_club_innings IS TRUE
              AND p.wicket_number BETWEEN 1 AND 10 AND p.runs IS NOT NULL {season_clause}
            ORDER BY p.game_id, p.innings_number, p.wicket_number
            """
        ),
        {"org": org_id, "season": season_id, "grade": grade_id},
    )
    innings: dict[tuple, dict[int, int]] = defaultdict(dict)
    for r in res.mappings():
        innings[(r["gid"], r["inn"])][int(r["wk"])] = int(r["runs"])

    THRESH = 15
    analysed = collapse_count = 0
    start_hist: dict[int, int] = defaultdict(int)
    worst = None  # (runs, start_wicket)
    for wkmap in innings.values():
        if len(wkmap) < 3:
            continue
        analysed += 1
        best_min = best_start = None
        for k in sorted(wkmap):
            if (k + 1) in wkmap and (k + 2) in wkmap:
                span = wkmap[k] + wkmap[k + 1] + wkmap[k + 2]
                if best_min is None or span < best_min:
                    best_min, best_start = span, k
        if best_min is not None and best_min <= THRESH:
            collapse_count += 1
            start_hist[best_start] += 1
            if worst is None or best_min < worst[0]:
                worst = (best_min, best_start)
    if analysed == 0:
        return None
    by_start = [{"wicket": w, "count": c} for w, c in sorted(start_hist.items(), key=lambda x: -x[1])][:5]
    return {
        "innings_analysed": analysed,
        "collapse_count": collapse_count,
        "collapse_pct": round(100 * collapse_count / analysed, 1),
        "threshold": THRESH,
        "by_start_wicket": by_start,
        "worst": {"runs": worst[0], "start_wicket": worst[1], "wickets": 3} if worst else None,
    }


async def _captaincy(session: AsyncSession, org_id: str, season_id: str | None, grade_id: str | None = None) -> list[dict]:
    """Captaincy & leadership (brief §4) — each captain's W/L record, finals
    record and the team's average score under them. Captains come from
    ``game_appearances.is_captain``; the team score is reconstructed the same way
    as ``_per_game`` (SUM of our batting). Toss-decision analysis isn't reachable
    — we don't store the toss."""
    season_clause = _scope(season_id, grade_id)
    min_games = 3
    res = await session.execute(
        text(
            f"""
            WITH our_games AS (
                SELECT g.id, g.result, g.is_final
                FROM v_effective_games g
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id
                WHERE s.organisation_id = CAST(:org AS UUID) {season_clause}
            ),
            scores AS (
                SELECT bi.game_id, SUM(bi.runs) AS our_runs
                FROM v_effective_batting_innings bi
                JOIN our_games og ON og.id = bi.game_id
                WHERE bi.did_not_bat IS NOT TRUE
                GROUP BY bi.game_id
            )
            SELECT p.id::text AS id, COALESCE(p.display_name_override, p.name) AS name,
                   COUNT(*) AS led,
                   COUNT(*) FILTER (WHERE og.result = 'WIN') AS wins,
                   COUNT(*) FILTER (WHERE og.result = 'LOSS') AS losses,
                   COUNT(*) FILTER (WHERE og.result IN ('DRAW', 'TIE')) AS draws,
                   COUNT(*) FILTER (WHERE og.is_final IS TRUE) AS finals,
                   COUNT(*) FILTER (WHERE og.is_final IS TRUE AND og.result = 'WIN') AS finals_won,
                   AVG(sc.our_runs) AS avg_score
            FROM game_appearances ga
            JOIN our_games og ON og.id = ga.game_id
            JOIN players p ON p.id = ga.player_id
            LEFT JOIN scores sc ON sc.game_id = ga.game_id
            WHERE ga.is_captain IS TRUE
            GROUP BY p.id, p.display_name_override, p.name
            HAVING COUNT(*) >= :min_games
            ORDER BY COUNT(*) DESC, COUNT(*) FILTER (WHERE og.result = 'WIN') DESC
            """
        ),
        {"org": org_id, "season": season_id, "grade": grade_id, "min_games": min_games},
    )
    out = []
    for r in res.mappings():
        wins, losses = int(r["wins"] or 0), int(r["losses"] or 0)
        out.append({
            "player_id": r["id"], "name": r["name"], "led": int(r["led"]),
            "wins": wins, "losses": losses, "draws": int(r["draws"] or 0),
            "win_pct": _win_pct(wins, wins + losses),
            "finals": int(r["finals"] or 0), "finals_won": int(r["finals_won"] or 0),
            "avg_score": round(float(r["avg_score"]), 1) if r["avg_score"] is not None else None,
        })
    # Best record as skipper first: win% desc (None last), then more games led,
    # then more wins — so the most successful captain tops the board.
    out.sort(key=lambda c: (c["win_pct"] if c["win_pct"] is not None else -1.0, c["led"], c["wins"]), reverse=True)
    return out


async def _discipline(session: AsyncSession, org_id: str, season_id: str | None, grade_id: str | None = None) -> dict | None:
    """Bowling discipline / extras (brief §2.9/§8.5) — wides & no-balls per over
    and extras as a share of runs conceded, club-wide and per bowler. Often
    decisive at community level. Overs are cricket notation (10.2 = 10 overs 2
    balls) so they're converted to balls before summing. Returns None when no
    extras are recorded at all (older scorecards omit them) so we never show a
    misleading 'spotless' card."""
    season_clause = _scope(season_id, grade_id)
    min_balls = 60 if (season_id or grade_id) else 300
    res = await session.execute(
        text(
            f"""
            WITH sp AS (
                SELECT bs.player_id AS pid,
                       (FLOOR(bs.overs) * 6 + ROUND((bs.overs - FLOOR(bs.overs)) * 10))::int AS balls,
                       COALESCE(bs.runs, 0) AS runs,
                       COALESCE(bs.wides, 0) AS wides,
                       COALESCE(bs.no_balls, 0) AS nb
                FROM v_effective_bowling_spells bs
                JOIN v_effective_games g ON g.id = bs.game_id
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id
                WHERE s.organisation_id = CAST(:org AS UUID) AND bs.overs IS NOT NULL {season_clause}
            )
            SELECT p.id::text AS id, COALESCE(p.display_name_override, p.name) AS name,
                   SUM(sp.balls) AS balls, SUM(sp.runs) AS runs,
                   SUM(sp.wides) AS wides, SUM(sp.nb) AS nb
            FROM sp JOIN players p ON p.id = sp.pid
            GROUP BY p.id, p.display_name_override, p.name
            """
        ),
        {"org": org_id, "season": season_id, "grade": grade_id},
    )
    rows = [dict(r) for r in res.mappings()]
    tot_balls = sum(int(r["balls"] or 0) for r in rows)
    tot_runs = sum(int(r["runs"] or 0) for r in rows)
    tot_w = sum(int(r["wides"] or 0) for r in rows)
    tot_nb = sum(int(r["nb"] or 0) for r in rows)
    tot_extras = tot_w + tot_nb
    if tot_balls == 0 or tot_extras == 0:
        return None
    overs_dec = tot_balls / 6
    def _po(x):
        return round(x / overs_dec, 2) if overs_dec else None

    ranked = []
    for r in rows:
        b = int(r["balls"] or 0)
        if b < min_balls:
            continue
        ex = int(r["wides"] or 0) + int(r["nb"] or 0)
        ov = b / 6
        ranked.append({
            "player_id": r["id"], "name": r["name"],
            "overs": f"{b // 6}.{b % 6}",
            "wides": int(r["wides"] or 0), "no_balls": int(r["nb"] or 0),
            "extras": ex, "extras_per_over": round(ex / ov, 2) if ov else None,
        })
    # Worst offenders first (highest extras/over) so they can be identified and
    # coached — the page is a discipline-correction tool, not a leaderboard.
    ranked.sort(key=lambda x: x["extras_per_over"] if x["extras_per_over"] is not None else -1.0, reverse=True)
    return {
        "overs": f"{tot_balls // 6}.{tot_balls % 6}",
        "wides": tot_w, "no_balls": tot_nb, "extras": tot_extras,
        "runs_conceded": tot_runs,
        "extras_per_over": _po(tot_extras),
        "wides_per_over": _po(tot_w),
        "nb_per_over": _po(tot_nb),
        "extras_pct": round(100 * tot_extras / tot_runs, 1) if tot_runs else None,
        "bowlers": ranked[:10],
    }


async def _wickets_quality(session: AsyncSession, org_id: str, season_id: str | None, grade_id: str | None = None) -> dict | None:
    """Team wicket-taking quality (brief §8.4) — the club-wide roll-up of
    ``bowler_wickets``: do our bowlers take *top-order* wickets or just tail-end
    ones, and do we remove *set* batters or pick off new ones. Same table the
    per-bowler deep-dive uses, aggregated across the attack."""
    season_clause = _scope(season_id, grade_id)
    res = await session.execute(
        text(
            f"""
            SELECT bw.batter_position AS pos, bw.batter_runs AS runs,
                   bw.dismissal_type AS dt, bw.caught_behind AS cb
            FROM bowler_wickets bw
            JOIN v_effective_games g ON g.id = bw.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = CAST(:org AS UUID) {season_clause}
            """
        ),
        {"org": org_id, "season": season_id, "grade": grade_id},
    )
    rows = [dict(r) for r in res.mappings()]
    if not rows:
        return None
    total = len(rows)
    posed = [r for r in rows if r["pos"] is not None]
    np_ = len(posed)
    top = sum(1 for r in posed if 1 <= r["pos"] <= 3)
    mid = sum(1 for r in posed if 4 <= r["pos"] <= 7)
    tail = sum(1 for r in posed if r["pos"] >= 8)
    withr = [r for r in rows if r["runs"] is not None]
    nr = len(withr)
    set_w = sum(1 for r in withr if r["runs"] >= 30)
    new_w = sum(1 for r in withr if r["runs"] < 10)
    # Score-at-dismissal histogram in 10-run bands (0–9, 10–19, …, 50+) — at what
    # score do we usually remove a batter (brief: "what score a batsman is usually
    # removed on"). 50+ is bucketed together to keep the tail readable.
    score_bands: list[dict] = []
    if nr:
        bands = [(0, 9), (10, 19), (20, 29), (30, 39), (40, 49)]
        for lo, hi in bands:
            cnt = sum(1 for r in withr if lo <= r["runs"] <= hi)
            score_bands.append({"band": f"{lo}–{hi}", "lo": lo, "count": cnt, "pct": round(100 * cnt / nr)})
        fifty = sum(1 for r in withr if r["runs"] >= 50)
        score_bands.append({"band": "50+", "lo": 50, "count": fifty, "pct": round(100 * fifty / nr)})
    dism: dict[str, int] = {}
    for r in rows:
        d = (r["dt"] or "").strip().lower()
        if not d:
            continue
        caught_plain = d.startswith("caught") and "bowled" not in d
        key = ("caught behind" if caught_plain and r.get("cb") else
               "caught" if caught_plain else
               "bowled" if d == "bowled" else
               "lbw" if "lbw" in d or "leg before" in d else
               "stumped" if d == "stumped" else
               "c & b" if ("bowled" in d and "caught" in d) else
               "run out" if "run out" in d else d)
        dism[key] = dism.get(key, 0) + 1
    dismissals = sorted(
        ({"type": k, "count": v, "pct": round(100 * v / total)} for k, v in dism.items()),
        key=lambda x: x["count"], reverse=True,
    )[:6]
    return {
        "total": total,
        "top": top, "middle": mid, "tail": tail,
        "top_pct": round(100 * top / np_) if np_ else None,
        "tail_pct": round(100 * tail / np_) if np_ else None,
        "set": set_w, "new": new_w,
        "set_pct": round(100 * set_w / nr) if nr else None,
        "new_pct": round(100 * new_w / nr) if nr else None,
        "score_bands": score_bands,
        "dismissals": dismissals,
    }


async def _collapse_bowlers(session: AsyncSession, org_id: str, season_id: str | None, grade_id: str | None = None) -> dict | None:
    """Collapse-causing bowlers (net-new) — which bowlers take wickets in *bursts*
    (3+ in an innings) and at what economy. Distinct from _wickets_quality (which
    profiles top-order vs tail): this is the "runs through a side" angle for the
    economy-vs-fall-of-wickets read. Joins bowler_wickets (wicket events) to
    bowling_spells (economy). Org-scoped, so the dossier reuses it for a synced
    opponent's bowling strengths/weaknesses too — no duplicate logic.
    """
    season_clause = _scope(season_id, grade_id)
    params = {"org": org_id, "season": season_id, "grade": grade_id}
    res = await session.execute(
        text(
            f"""
            SELECT bw.bowler_id::text AS pid,
                   COALESCE(pl.display_name_override, pl.name) AS name,
                   bw.game_id::text AS gid, bw.innings_number AS inn,
                   COUNT(*) AS wkts
            FROM bowler_wickets bw
            JOIN players pl ON pl.id = bw.bowler_id
            JOIN v_effective_games g ON g.id = bw.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = CAST(:org AS UUID) {season_clause}
            GROUP BY 1, 2, 3, 4
            """
        ),
        params,
    )
    spells = [dict(r) for r in res.mappings()]
    if not spells:
        return None

    # Economy per bowler — overs are cricket notation (10.2 = 10 overs 2 balls).
    eco_res = await session.execute(
        text(
            f"""
            SELECT bs.player_id::text AS pid,
                   SUM(FLOOR(bs.overs) * 6 + ROUND((bs.overs - FLOOR(bs.overs)) * 10)) AS balls,
                   SUM(bs.runs) AS runs
            FROM v_effective_bowling_spells bs
            JOIN v_effective_games g ON g.id = bs.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = CAST(:org AS UUID) {season_clause}
              AND bs.overs IS NOT NULL
            GROUP BY 1
            """
        ),
        params,
    )
    eco = {r.pid: (float(r.runs or 0), float(r.balls or 0)) for r in eco_res}

    BURST = 3  # 3+ wickets in an innings = a collapse-inducing spell
    agg: dict = {}
    for sp in spells:
        a = agg.setdefault(sp["pid"], {"name": sp["name"], "wkts": 0, "bursts": 0, "best": 0, "five_fors": 0})
        a["wkts"] += sp["wkts"]
        a["best"] = max(a["best"], sp["wkts"])
        if sp["wkts"] >= BURST:
            a["bursts"] += 1
        if sp["wkts"] >= 5:
            a["five_fors"] += 1

    out = []
    for pid, a in agg.items():
        if a["bursts"] <= 0:
            continue
        runs, balls = eco.get(pid, (0.0, 0.0))
        out.append({
            "player_id": pid,
            "name": a["name"],
            "wickets": a["wkts"],
            "bursts": a["bursts"],
            "best_haul": a["best"],
            "five_fors": a["five_fors"],
            "economy": round(runs / (balls / 6), 2) if balls else None,
        })
    if not out:
        return None
    out.sort(key=lambda o: (o["bursts"], o["wickets"]), reverse=True)
    return {"bowlers": out[:10], "burst_threshold": BURST}


async def _team_starts(session: AsyncSession, org_id: str, season_id: str | None, grade_id: str | None = None) -> dict | None:
    """Team starts (brief §7.4) — our opening-partnership profile and how our
    win rate changes after a good vs a poor start. Opening stands come from
    ``partnerships`` (wicket 1, club innings); win rate joins the game result."""
    season_clause = _scope(season_id, grade_id)
    res = await session.execute(
        text(
            f"""
            SELECT p.runs AS stand, g.result
            FROM partnerships p
            JOIN v_effective_games g ON g.id = p.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = CAST(:org AS UUID)
              AND p.is_club_innings IS TRUE AND p.wicket_number = 1 AND p.runs IS NOT NULL {season_clause}
            """
        ),
        {"org": org_id, "season": season_id, "grade": grade_id},
    )
    rows = [dict(r) for r in res.mappings()]
    if not rows:
        return None
    stands = sorted(int(r["stand"]) for r in rows)
    n = len(stands)
    GOOD = 30
    decided = [r for r in rows if r["result"] in ("WIN", "LOSS")]
    good = [r for r in decided if int(r["stand"]) >= GOOD]
    poor = [r for r in decided if int(r["stand"]) < GOOD]
    def _wp(lst):
        return round(100 * sum(1 for r in lst if r["result"] == "WIN") / len(lst)) if lst else None
    return {
        "innings": n,
        "avg": round(sum(stands) / n, 1),
        "median": int(statistics.median(stands)),
        "best": stands[-1],
        "over_25": sum(1 for s in stands if s >= 25),
        "over_50": sum(1 for s in stands if s >= 50),
        "good_threshold": GOOD,
        "after_good": {"played": len(good), "win_pct": _wp(good)},
        "after_poor": {"played": len(poor), "win_pct": _wp(poor)},
    }


async def _role_ratings(session: AsyncSession, org_id: str, season_id: str | None, grade_id: str | None = None) -> list[dict] | None:
    """Role-adjusted batting (brief §15.4) — compare each batter only with others
    in the same slot. We bucket innings by batting position, pool a club average
    per bucket, then rate each player by how far their average in their *primary*
    bucket sits above (or below) that bucket's average. Stops an opener and a
    No. 8 being judged on the same yardstick."""
    from collections import defaultdict

    season_clause = _scope(season_id, grade_id)
    min_inns = 5 if (season_id or grade_id) else 12
    res = await session.execute(
        text(
            f"""
            SELECT bi.player_id::text AS pid, COALESCE(p.display_name_override, p.name) AS name,
                   CASE WHEN bi.batting_position BETWEEN 1 AND 2 THEN 'Opener'
                        WHEN bi.batting_position = 3 THEN 'First drop'
                        WHEN bi.batting_position BETWEEN 4 AND 6 THEN 'Middle order'
                        WHEN bi.batting_position BETWEEN 7 AND 8 THEN 'Lower order'
                        ELSE 'Tail' END AS bucket,
                   COUNT(*) AS inns,
                   SUM(bi.runs) AS runs,
                   COUNT(*) FILTER (WHERE NOT bi.not_out AND bi.dismissal_type IS NOT NULL) AS outs
            FROM v_effective_batting_innings bi
            JOIN players p ON p.id = bi.player_id
            JOIN v_effective_games g ON g.id = bi.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = CAST(:org AS UUID)
              AND bi.did_not_bat IS NOT TRUE AND bi.runs IS NOT NULL AND bi.batting_position IS NOT NULL {season_clause}
            GROUP BY bi.player_id, p.display_name_override, p.name, bucket
            """
        ),
        {"org": org_id, "season": season_id, "grade": grade_id},
    )
    rows = [dict(r) for r in res.mappings()]
    if not rows:
        return None
    bucket_runs: dict[str, int] = defaultdict(int)
    bucket_outs: dict[str, int] = defaultdict(int)
    by_player: dict[str, list] = defaultdict(list)
    for r in rows:
        bucket_runs[r["bucket"]] += int(r["runs"] or 0)
        bucket_outs[r["bucket"]] += int(r["outs"] or 0)
        by_player[r["pid"]].append(r)
    bucket_avg = {b: bucket_runs[b] / bucket_outs[b] for b in bucket_runs if bucket_outs[b] > 0}

    out = []
    for prows in by_player.values():
        primary = max(prows, key=lambda x: int(x["inns"] or 0))
        b = primary["bucket"]
        inns, outs = int(primary["inns"] or 0), int(primary["outs"] or 0)
        if inns < min_inns or outs == 0 or b not in bucket_avg:
            continue
        pavg = int(primary["runs"] or 0) / outs
        out.append({
            "player_id": primary["pid"], "name": primary["name"], "role": b,
            "innings": inns, "average": round(pavg, 1),
            "role_average": round(bucket_avg[b], 1), "delta": round(pavg - bucket_avg[b], 1),
        })
    out.sort(key=lambda x: x["delta"], reverse=True)
    return out[:12] if out else None


async def player_impact(session: AsyncSession, org_id: str, season_id: str | None = None, grade_id: str | None = None) -> dict:
    """Player Impact / club MVP board (brief §15.3) — a season-VALUE rating: who
    contributed the most over the season. Built from season TOTALS (runs, wickets,
    fielding dismissals) with average / economy as quality modifiers, z-scored
    across the squad and min-max scaled 0–100. Defaults to the latest season; pass
    a ``grade_id`` (a grade NAME) to rate only that grade.

    Totals — not per-match rates — because the MVP is about accumulated value over
    a season: 479 runs & 22 wickets across the year must outrank a high per-game
    rate off three games. (The earlier per-match version let small samples win.)"""
    seasons = await team_seasons(session, org_id)
    if not seasons:
        return {"season": None, "players": []}
    resolved = (next((s for s in seasons if s["season_id"] == season_id), None) if season_id else None) or seasons[0]
    year, sid = resolved.get("year"), resolved["season_id"]
    # Scope by the SEASON's org, NOT player membership (the cross-club anti-pattern
    # that emptied the board for shared-GUID players). Aggregate all season records
    # of the year (+ the latest season id) so a year split across season rows /
    # comps is fully counted.
    scope = "AND (s.year = :year OR s.id = CAST(:sid AS UUID))" if year is not None else "AND s.id = CAST(:sid AS UUID)"
    params = {"org": org_id, "year": year, "sid": sid, "grade": grade_id}

    if grade_id:
        # Grade-scoped from the per-grade stats table (grade NAME → its rows in
        # the year). No bowling balls column here, so economy is unavailable.
        res = await session.execute(
            text(
                f"""
                SELECT p.id::text AS id, COALESCE(p.display_name_override, p.name) AS name,
                       GREATEST(COALESCE(SUM(psg.matches), 0), COALESCE(SUM(psg.batting_innings), 0),
                                COALESCE(SUM(psg.bowling_innings), 0)) AS games,
                       COALESCE(SUM(psg.runs), 0) AS runs,
                       COALESCE(SUM(psg.batting_innings), 0) - COALESCE(SUM(psg.not_outs), 0) AS bat_outs,
                       COALESCE(SUM(psg.wickets), 0) AS wkts,
                       COALESCE(SUM(psg.catches), 0) + COALESCE(SUM(psg.run_outs), 0)
                         + COALESCE(SUM(psg.stumpings), 0) AS dis
                FROM players p
                JOIN player_season_grade_stats psg ON psg.player_id = p.id
                JOIN grades gr ON gr.id = psg.grade_id AND gr.name = :grade
                JOIN seasons s ON s.id = psg.season_id AND s.organisation_id = CAST(:org AS UUID) {scope}
                GROUP BY p.id, p.display_name_override, p.name
                HAVING GREATEST(COALESCE(SUM(psg.matches), 0), COALESCE(SUM(psg.batting_innings), 0),
                                COALESCE(SUM(psg.bowling_innings), 0)) >= 3
                """
            ),
            params,
        )
        pls = []
        for r in res.mappings():
            bat_outs = int(r["bat_outs"] or 0)
            pls.append({
                "id": r["id"], "name": r["name"], "matches": int(r["games"]),
                "runs": int(r["runs"]), "wickets": int(r["wkts"]), "dismissals": int(r["dis"]),
                "bat_avg": (int(r["runs"]) / bat_outs) if bat_outs > 0 else None,
                "econ": None,
            })
    else:
        res = await session.execute(
            text(
                f"""
                SELECT p.id::text AS id, COALESCE(p.display_name_override, p.name) AS name,
                       GREATEST(COALESCE(SUM(pss.matches), 0), COALESCE(SUM(pss.batting_innings), 0),
                                COALESCE(SUM(pss.bowling_innings), 0)) AS games,
                       COALESCE(SUM(pss.runs), 0) AS runs,
                       COALESCE(SUM(pss.batting_average * pss.batting_innings), 0) AS bavg_w,
                       COALESCE(SUM(pss.batting_innings) FILTER (WHERE pss.batting_average IS NOT NULL), 0) AS bavg_n,
                       COALESCE(SUM(pss.wickets), 0) AS wkts,
                       COALESCE(SUM(pss.runs_conceded), 0) AS rc,
                       COALESCE(SUM(pss.bowling_balls), 0) AS bb,
                       COALESCE(SUM(pss.catches_non_wk), 0) + COALESCE(SUM(pss.catches_wk), 0)
                         + COALESCE(SUM(pss.run_outs), 0) + COALESCE(SUM(pss.stumpings), 0) AS dis
                FROM players p
                JOIN player_season_stats pss ON pss.player_id = p.id
                JOIN seasons s ON s.id = pss.season_id AND s.organisation_id = CAST(:org AS UUID) {scope}
                GROUP BY p.id, p.display_name_override, p.name
                HAVING GREATEST(COALESCE(SUM(pss.matches), 0), COALESCE(SUM(pss.batting_innings), 0),
                                COALESCE(SUM(pss.bowling_innings), 0)) >= 3
                """
            ),
            params,
        )
        pls = []
        for r in res.mappings():
            pls.append({
                "id": r["id"], "name": r["name"], "matches": int(r["games"]),
                "runs": int(r["runs"]), "wickets": int(r["wkts"]), "dismissals": int(r["dis"]),
                "bat_avg": float(r["bavg_w"] / r["bavg_n"]) if r["bavg_n"] else None,
                "econ": float(r["rc"] * 6 / r["bb"]) if r["bb"] and r["bb"] >= 30 else None,
            })
    if not pls:
        return {"season": {"id": resolved["season_id"], "name": resolved["name"]}, "players": []}

    def zmap(key, invert=False, only_present=False):
        vals = [p[key] for p in pls if p[key] is not None] if only_present else [p[key] for p in pls]
        if len(vals) < 2:
            return {p["id"]: 0.0 for p in pls}
        mu, sd = statistics.mean(vals), statistics.pstdev(vals) or 1.0
        out = {}
        for p in pls:
            if p[key] is None:
                out[p["id"]] = 0.0
            else:
                z = (p[key] - mu) / sd
                out[p["id"]] = -z if invert else z
        return out

    # Volume (season totals) is the spine of the rating; average / economy add a
    # quality bonus. Each discipline contributes its POSITIVE value only, so a
    # specialist is rewarded for what they do and never penalised for not bowling.
    zb, zw, zf = zmap("runs"), zmap("wickets"), zmap("dismissals")
    ze = zmap("econ", invert=True, only_present=True)
    za = zmap("bat_avg", only_present=True)
    raw = {}
    for p in pls:
        pid = p["id"]
        bat_c = max(0.0, 0.7 * zb[pid] + 0.3 * za[pid])
        ball_c = max(0.0, 0.8 * zw[pid] + 0.35 * ze[pid])
        field_c = 0.3 * max(0.0, zf[pid])
        raw[pid] = bat_c + ball_c + field_c
        if bat_c > 0.5 and ball_c > 0.5:
            p["role"] = "All-round"
        else:
            comps = {"Batting": bat_c, "Bowling": ball_c, "Fielding": field_c}
            p["role"] = max(comps, key=comps.get) if max(comps.values()) > 0 else "Squad"
    lo, hi = min(raw.values()), max(raw.values())
    for p in pls:
        p["impact"] = round(100 * (raw[p["id"]] - lo) / (hi - lo)) if hi > lo else 50
        p["player_id"] = p.pop("id")  # match the player_id convention used elsewhere in IQ
        for k in ("bat_avg", "econ"):
            p.pop(k, None)
    pls.sort(key=lambda x: x["impact"], reverse=True)
    return {"season": {"id": resolved["season_id"], "name": resolved["name"]}, "players": pls[:12]}


def _dismissal_key(dt: str | None, caught_behind: bool | None = False) -> str | None:
    # Accepts both sync's short codes ("c"/"b"/"st", batting_innings) and free-text
    # long forms (manual entries). caught_behind splits the keeper catch out.
    d = (dt or "").strip().lower()
    if not d:
        return None
    if "run out" in d:
        return "run out"
    if ("bowled" in d and "caught" in d) or d in ("c&b", "c & b"):
        return "c & b"
    if d == "c" or d.startswith("c ") or d.startswith("caught"):
        return "caught behind" if caught_behind else "caught"
    if d in ("b", "bowled"):
        return "bowled"
    if "lbw" in d or "leg before" in d:
        return "lbw"
    if d in ("st", "stumped"):
        return "stumped"
    return d


async def _batting_extra(session: AsyncSession, org_id: str, season_id: str | None, grade_id: str | None = None) -> dict | None:
    """Extra batting analytics for the Batting tab (brief §1/§7), all derived from
    ONE per-innings pull over ``v_effective_batting_innings`` within scope:
      • ``top_scorers``       — leading run-makers (runs, inns, average)
      • ``by_position``       — average runs by batting position (1..11)
      • ``dismissals``        — how our batters get out (type mix)
      • ``dismissal_scores``  — 10-run bands of the score our batters fall on
    Returns ``None`` when there are no innings in scope."""
    from collections import defaultdict

    season_clause = _scope(season_id, grade_id)
    res = await session.execute(
        text(
            f"""
            SELECT bi.player_id::text AS pid, COALESCE(p.display_name_override, p.name) AS name,
                   bi.runs AS runs, bi.batting_position AS pos,
                   bi.not_out AS no, bi.dismissal_type AS dt, bi.caught_behind AS cb
            FROM v_effective_batting_innings bi
            JOIN players p ON p.id = bi.player_id
            JOIN v_effective_games g ON g.id = bi.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = CAST(:org AS UUID)
              AND bi.did_not_bat IS NOT TRUE AND bi.runs IS NOT NULL {season_clause}
            """
        ),
        {"org": org_id, "season": season_id, "grade": grade_id},
    )
    rows = [dict(r) for r in res.mappings()]
    if not rows:
        return None

    agg: dict[str, dict] = defaultdict(lambda: {"runs": 0, "inns": 0, "outs": 0, "name": ""})
    pos_runs: dict[int, int] = defaultdict(int)
    pos_inns: dict[int, int] = defaultdict(int)
    dism: dict[str, int] = defaultdict(int)
    dismissed_scores: list[int] = []
    for r in rows:
        a = agg[r["pid"]]
        a["name"] = r["name"]
        a["runs"] += int(r["runs"])
        a["inns"] += 1
        dismissed = (not r["no"]) and (r["dt"] is not None)
        if dismissed:
            a["outs"] += 1
            dismissed_scores.append(int(r["runs"]))
            k = _dismissal_key(r["dt"], r.get("cb"))
            if k:
                dism[k] += 1
        if r["pos"] is not None and 1 <= int(r["pos"]) <= 11:
            pos_runs[int(r["pos"])] += int(r["runs"])
            pos_inns[int(r["pos"])] += 1

    top_scorers = sorted(
        (
            {"player_id": pid, "name": a["name"], "runs": a["runs"], "innings": a["inns"],
             "avg": round(a["runs"] / a["outs"], 1) if a["outs"] else None}
            for pid, a in agg.items()
        ),
        key=lambda x: x["runs"], reverse=True,
    )[:8]
    by_position = [
        {"position": pos, "avg": round(pos_runs[pos] / pos_inns[pos], 1), "innings": pos_inns[pos]}
        for pos in sorted(pos_inns)
    ]
    nd = len(dismissed_scores)
    dismissal_scores: list[dict] = []
    if nd:
        for lo, hi in [(0, 9), (10, 19), (20, 29), (30, 39), (40, 49)]:
            cnt = sum(1 for sc in dismissed_scores if lo <= sc <= hi)
            dismissal_scores.append({"band": f"{lo}–{hi}", "lo": lo, "count": cnt, "pct": round(100 * cnt / nd)})
        fifty = sum(1 for sc in dismissed_scores if sc >= 50)
        dismissal_scores.append({"band": "50+", "lo": 50, "count": fifty, "pct": round(100 * fifty / nd)})
    total_d = sum(dism.values())
    dismissals = sorted(
        ({"type": k, "count": v, "pct": round(100 * v / total_d)} for k, v in dism.items()),
        key=lambda x: x["count"], reverse=True,
    )[:6]
    return {
        "top_scorers": top_scorers,
        "by_position": by_position,
        "dismissals": dismissals,
        "dismissal_scores": dismissal_scores,
    }


async def team_overview(session: AsyncSession, org_id: str, season_id: str | None = None, grade_id: str | None = None) -> dict:
    games = await _per_game(session, org_id, season_id, grade_id)
    decided = [g for g in games if g["result"] in ("WIN", "LOSS")]

    wins = sum(1 for g in games if g["result"] == "WIN")
    losses = sum(1 for g in games if g["result"] == "LOSS")
    draws = sum(1 for g in games if g["result"] in ("DRAW", "TIE"))

    def _ha(side):
        gs = [g for g in decided if g["our_venue"] == side]
        return {"played": len(gs), "wins": sum(1 for g in gs if g["result"] == "WIN")}

    # Batting profile (over games we have a score for).
    scored = [g for g in games if g["our_runs"] is not None]
    tot_runs = sum(g["our_runs"] for g in scored)
    record = {
        "matches": len(games), "wins": wins, "losses": losses, "draws": draws,
        "win_pct": _win_pct(wins, wins + losses),
        "home": _ha("HOME"), "away": _ha("AWAY"),
    }
    batting = {
        "avg_score": _avg([g["our_runs"] for g in scored]),
        "high_score": max((g["our_runs"] for g in scored), default=None),
        "low_score": min((g["our_runs"] for g in scored), default=None),
        "avg_wickets_lost": _avg([g["wkts_lost"] for g in scored]),
        "top_order_pct": round(100 * sum(g["top3"] or 0 for g in scored) / tot_runs) if tot_runs else None,
        "middle_pct": round(100 * sum(g["mid"] or 0 for g in scored) / tot_runs) if tot_runs else None,
        "lower_pct": round(100 * sum(g["low"] or 0 for g in scored) / tot_runs) if tot_runs else None,
        "boundary_pct": round(100 * sum(g["boundary_runs"] or 0 for g in scored) / tot_runs) if tot_runs else None,
    }
    # Team total distribution — how often we post a total in each band (over every
    # innings we have a score for). Same bands as "what score wins" so they read
    # together. Powers the Batting-tab "How big do we bat" chart.
    total_distribution = []
    if scored:
        n_sc = len(scored)
        for lo, hi, label in _BANDS:
            cnt = sum(1 for g in scored if lo <= g["our_runs"] < hi)
            total_distribution.append({"band": label, "count": cnt, "pct": round(100 * cnt / n_sc)})
    batting["total_distribution"] = total_distribution

    conceded = [g for g in games if g["opp_runs"] is not None]
    bowling = {
        "avg_conceded": _avg([g["opp_runs"] for g in conceded]),
        "avg_wickets_taken": _avg([g["wkts_taken"] for g in conceded]),
    }

    # Bat-first vs chase.
    bf = [g for g in decided if g["batted_first"] is True]
    ch = [g for g in decided if g["batted_first"] is False]
    innings = {
        "bat_first": {
            "played": len(bf), "wins": sum(1 for g in bf if g["result"] == "WIN"),
            "win_pct": _win_pct(sum(1 for g in bf if g["result"] == "WIN"), len(bf)),
            "avg_score": _avg([g["our_runs"] for g in bf if g["our_runs"] is not None]),
        },
        "chasing": {
            "played": len(ch), "wins": sum(1 for g in ch if g["result"] == "WIN"),
            "win_pct": _win_pct(sum(1 for g in ch if g["result"] == "WIN"), len(ch)),
            "avg_target": _avg([g["opp_runs"] for g in ch if g["opp_runs"] is not None]),
        },
    }

    # Par score (brief §15.9) — the median first-innings total in our bat-first
    # wins, plus the lowest we've successfully defended. "What's a winning score."
    bf_win_scores = sorted(g["our_runs"] for g in bf if g["result"] == "WIN" and g["our_runs"] is not None)
    innings["par"] = {
        "par_score": int(statistics.median(bf_win_scores)) if bf_win_scores else None,
        "lowest_defended": bf_win_scores[0] if bf_win_scores else None,
        "samples": len(bf_win_scores),
    }

    # "What score wins" — win% by our-score band when batting first.
    score_bands = []
    for lo, hi, label in _BANDS:
        band = [g for g in bf if g["our_runs"] is not None and lo <= g["our_runs"] < hi]
        if band:
            w = sum(1 for g in band if g["result"] == "WIN")
            score_bands.append({"band": label, "played": len(band), "wins": w, "win_pct": _win_pct(w, len(band))})

    # Venues — record + avg score.
    venue_map: dict[str, dict] = {}
    for g in games:
        if not g["venue"]:
            continue
        v = venue_map.setdefault(g["venue"], {"venue": g["venue"], "played": 0, "wins": 0, "losses": 0, "_runs": []})
        if g["result"] in ("WIN", "LOSS"):
            v["played"] += 1
            v["wins"] += g["result"] == "WIN"
            v["losses"] += g["result"] == "LOSS"
        if g["our_runs"] is not None:
            v["_runs"].append(g["our_runs"])
    venues = []
    for v in venue_map.values():
        if v["played"] >= 3:
            venues.append({"venue": v["venue"], "played": v["played"], "wins": v["wins"],
                           "losses": v["losses"], "avg_score": _avg(v["_runs"])})
    venues.sort(key=lambda x: x["played"], reverse=True)

    partnerships = await _safe(session, lambda: _partnerships(session, org_id, season_id, grade_id), [])
    fielding = await _safe(session, lambda: _team_fielding(session, org_id, season_id, grade_id), {"fielders": [], "keepers": [], "combos": []})
    all_rounders = await _safe(session, lambda: _all_rounders(session, org_id, season_id, grade_id), [])
    batting_pairs = await _safe(session, lambda: _batting_pairs(session, org_id, season_id, grade_id), [])
    collapses = await _safe(session, lambda: _collapses(session, org_id, season_id, grade_id), None)
    attack = await _safe(session, lambda: _attack_structure(session, org_id, season_id, grade_id), None)
    discipline = await _safe(session, lambda: _discipline(session, org_id, season_id, grade_id), None)
    captaincy = await _safe(session, lambda: _captaincy(session, org_id, season_id, grade_id), [])
    wickets_quality = await _safe(session, lambda: _wickets_quality(session, org_id, season_id, grade_id), None)
    collapse_bowlers = await _safe(session, lambda: _collapse_bowlers(session, org_id, season_id, grade_id), None)
    starts = await _safe(session, lambda: _team_starts(session, org_id, season_id, grade_id), None)
    role_ratings = await _safe(session, lambda: _role_ratings(session, org_id, season_id, grade_id), None)
    batting_extra = await _safe(session, lambda: _batting_extra(session, org_id, season_id, grade_id), None)
    win_lose = _how_we_win_lose(record, batting, innings, partnerships)

    return {
        "record": record,
        "batting": batting,
        "bowling": bowling,
        "innings": innings,
        "score_bands": score_bands,
        "venues": venues[:10],
        "partnerships": partnerships,
        "batting_pairs": batting_pairs,
        "collapses": collapses,
        "attack": attack,
        "discipline": discipline,
        "captaincy": captaincy,
        "wickets_quality": wickets_quality,
        "collapse_bowlers": collapse_bowlers,
        "starts": starts,
        "role_ratings": role_ratings,
        "batting_extra": batting_extra,
        "fielding": fielding,
        "all_rounders": all_rounders,
        "how_we_win": win_lose[0],
        "how_we_lose": win_lose[1],
        "coverage": {
            "notes": [
                "Team scores are reconstructed from per-innings data (our batting / our bowling), so they exclude some extras — close, not exact.",
                "Bat-first vs chase uses which innings we batted; home/away from the opponent vs the ground.",
            ]
        },
    }


def _ordinal(n: int) -> str:
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")


def _how_we_win_lose(record, batting, innings, partnerships):
    win, lose = [], []
    bf, ch = innings["bat_first"], innings["chasing"]
    if bf["win_pct"] is not None and ch["win_pct"] is not None and bf["played"] >= 4 and ch["played"] >= 4:
        if bf["win_pct"] - ch["win_pct"] >= 12:
            win.append(f"Stronger setting a target — {bf['win_pct']}% batting first vs {ch['win_pct']}% chasing.")
            lose.append("Less convincing in a chase — protect wickets early when batting second.")
        elif ch["win_pct"] - bf["win_pct"] >= 12:
            win.append(f"Better chasing — {ch['win_pct']}% win rate batting second vs {bf['win_pct']}% first.")
            lose.append("Less reliable setting a target — a few more runs batting first would help.")
    if batting.get("top_order_pct") and batting["top_order_pct"] >= 55:
        win.append(f"Top-order driven — {batting['top_order_pct']}% of our runs come from the top three.")
        lose.append("Over-reliant on the top three; early wickets leave the lower order exposed.")
    if batting.get("lower_pct") is not None and batting["lower_pct"] < 12:
        lose.append(f"Thin lower-order contribution ({batting['lower_pct']}% of runs) — a collapse runs deep.")
    qualified = [p for p in partnerships if p["samples"] >= 3]
    if len(qualified) >= 3:
        strong = max(qualified, key=lambda p: p["avg_partnership"])
        weak = min(qualified, key=lambda p: p["avg_partnership"])
        win.append(f"Strongest stand is the {_ordinal(strong['wicket'])} wicket (avg {strong['avg_partnership']}).")
        if weak["avg_partnership"] < strong["avg_partnership"] * 0.5:
            lose.append(f"We wobble around the {_ordinal(weak['wicket'])} wicket (avg {weak['avg_partnership']}).")
    return win, lose
