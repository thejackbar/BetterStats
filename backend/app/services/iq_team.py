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

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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


async def _per_game(session: AsyncSession, org_id: str, season_id: str | None) -> list[dict]:
    season_clause = "AND gr.season_id = CAST(:season AS UUID)" if season_id else ""
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
        {"org": org_id, "season": season_id},
    )
    return [dict(r) for r in res.mappings()]


async def _partnerships(session: AsyncSession, org_id: str, season_id: str | None) -> list[dict]:
    season_clause = "AND gr.season_id = CAST(:season AS UUID)" if season_id else ""
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
        {"org": org_id, "season": season_id},
    )
    return [{"wicket": r["wk"], "avg_partnership": float(r["avg_p"]), "samples": r["n"]} for r in res.mappings()]


def _win_pct(w: int, dec: int) -> float | None:
    return round(100 * w / dec, 1) if dec else None


async def _team_fielding(session: AsyncSession, org_id: str, season_id: str | None) -> dict:
    """Top fielders, keepers and run-out specialists, plus the fielder→bowler
    combinations that take the most catches (brief §3/§9)."""
    season_clause = "AND s.id = CAST(:season AS UUID)" if season_id else ""
    res = await session.execute(
        text(
            f"""
            SELECT p.id::text AS id, COALESCE(p.display_name_override, p.name) AS name,
                   COALESCE(SUM(pss.catches_non_wk), 0) AS ct,
                   COALESCE(SUM(pss.run_outs), 0) AS ro,
                   COALESCE(SUM(pss.catches_wk), 0) AS ctwk,
                   COALESCE(SUM(pss.stumpings), 0) AS st
            FROM players p
            JOIN player_season_stats pss ON pss.player_id = p.id
            JOIN seasons s ON s.id = pss.season_id
            WHERE p.organisation_id = CAST(:org AS UUID) {season_clause}
            GROUP BY p.id, name
            """
        ),
        {"org": org_id, "season": season_id},
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
        {"org": org_id, "season": season_id},
    )
    combos = [{"fielder": r["fielder"], "bowler": r["bowler"], "count": r["n"]} for r in combos_res.mappings()]
    return {"fielders": fielders[:8], "keepers": keepers[:5], "combos": combos}


async def team_overview(session: AsyncSession, org_id: str, season_id: str | None = None) -> dict:
    games = await _per_game(session, org_id, season_id)
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

    partnerships = await _partnerships(session, org_id, season_id)
    fielding = await _team_fielding(session, org_id, season_id)
    win_lose = _how_we_win_lose(record, batting, innings, partnerships)

    return {
        "record": record,
        "batting": batting,
        "bowling": bowling,
        "innings": innings,
        "score_bands": score_bands,
        "venues": venues[:10],
        "partnerships": partnerships,
        "fielding": fielding,
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
