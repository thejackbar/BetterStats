"""A read-only health check of a club's Fantasy season, found by looking at Sunbury CC (Nov 2026).

Four players on one scorecard scored nothing and the rounds did not follow the draw. Each cause had
a different symptom, so this looks for all of them at once and says in words what it found:

* ``long_rounds``       a stored round longer than ``fantasy_engine.MAX_ROUND_SPAN_DAYS``. Every week of
                        a season whose two day games start on alternate Saturdays used to be joined into
                        one round (a seven week round, locked at its first kick-off, never scored).
* ``draw_mismatch``     rounds whose stored dates differ from what the live draw now gives for that round
                        number. A round that is not scored follows the draw by itself overnight; a scored
                        one needs the "Fix round dates" button (``fantasy_realign``).
* ``uncovered_games``   a game of the club's, in the season's year and grades, dated outside every
                        round. It scores for nobody and no sync helps.
* ``blocking_round``    a round that ended but is not confirmed while a later round has started. The
                        member screens treat the FIRST unscored round as the live one, so everything
                        after it is hidden until it is confirmed.
* ``drift``             players whose stored points differ from what the scorecards give now, per round.
* ``zero_stat_pool``    pool players picked by teams who have no games this season while a same-name
                        record does (a hand-added twin).

Read only: nothing is written. ``check_draw=False`` skips the Cricket Australia calls (the draw
comparison). One call per grade is made otherwise, through the client's own 30 minute cache.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import fantasy_engine, fantasy_pool_check
from app.services.club_grades import club_game_sql

DRIFT_NAMES = 8


async def audit_season(db: AsyncSession, fs, check_draw: bool = True, today: date | None = None) -> dict:
    today = today or date.today()
    out: dict = {"season_year": fs.season_year, "long_rounds": [], "draw_mismatch": [], "uncovered_games": [],
                 "blocking_round": None, "drift": [], "zero_stat_pool": [], "draw_checked": False,
                 "live_sync_on": (fs.rules or {}).get("live_sync") is not False}
    rounds = (await db.execute(text("""
        SELECT id, round_number, status, start_date, end_date, live_checked_at FROM fantasy_rounds
        WHERE fantasy_season_id = CAST(:f AS UUID) ORDER BY round_number"""), {"f": str(fs.id)})).mappings().all()
    out["rounds"] = len(rounds)
    out["rounds_scored"] = sum(1 for r in rounds if r["status"] == "scored")
    dated = [r for r in rounds if r["start_date"] and r["end_date"]]

    for r in dated:
        days = (r["end_date"] - r["start_date"]).days
        if days > fantasy_engine.MAX_ROUND_SPAN_DAYS:
            out["long_rounds"].append({"round": r["round_number"], "status": r["status"], "days": days,
                                       "start": r["start_date"].isoformat(), "end": r["end_date"].isoformat()})

    if check_draw:
        try:
            windows, *_rest = await fantasy_engine.draw_windows(db, fs)
            out["draw_checked"] = bool(windows)
            stored = {r["round_number"]: r for r in rounds}
            for n, (first, last) in enumerate(windows, start=1):
                r = stored.get(n)
                if r is None:
                    out["draw_mismatch"].append({"round": n, "status": "missing", "stored": None,
                                                 "draw": [first.isoformat(), last.isoformat()]})
                elif (r["start_date"], r["end_date"]) != (first, last):
                    out["draw_mismatch"].append({
                        "round": n, "status": r["status"],
                        "stored": [r["start_date"].isoformat() if r["start_date"] else None,
                                   r["end_date"].isoformat() if r["end_date"] else None],
                        "draw": [first.isoformat(), last.isoformat()]})
        except Exception as e:  # noqa: BLE001  a CA blip must not hide the other findings
            out["draw_error"] = str(e)

    grades = await fantasy_engine._grade_scope(db, fs)
    if dated:
        rows = (await db.execute(text(f"""
            SELECT g.id, g.played_at::date AS d, g.home_team, g.away_team
            FROM v_effective_games g
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE {club_game_sql("g", "org")} AND s.year = :year AND g.played_at IS NOT NULL
              {fantasy_engine._grade_clause(grades)}
            ORDER BY g.played_at"""),
            {"org": str(fs.organisation_id), "year": fs.season_year, "grades": grades})).mappings().all()
        for g in rows:
            if not any(r["start_date"] <= g["d"] <= r["end_date"] for r in dated):
                out["uncovered_games"].append({"date": g["d"].isoformat(), "match": f"{g['home_team']} v {g['away_team']}",
                                               "game_id": str(g["id"])})

    # The first round that is not scored hides every later one from the members (public_fantasy._live_round).
    ordered = sorted(rounds, key=lambda r: r["round_number"])
    first_open = next((r for r in ordered if r["status"] != "scored"), None)
    if first_open is not None and first_open["end_date"] and first_open["end_date"] < today:
        later = [r for r in ordered if r["round_number"] > first_open["round_number"]
                 and r["start_date"] and r["start_date"] <= today]
        if later:
            out["blocking_round"] = {"round": first_open["round_number"], "status": first_open["status"],
                                     "ended": first_open["end_date"].isoformat(),
                                     "hides": [r["round_number"] for r in later]}

    from app.models.db import FantasyRound
    for r in dated:
        if r["start_date"] > today:
            continue
        rnd = await db.get(FantasyRound, r["id"])
        drift = await fantasy_engine.round_drift(db, fs, rnd)
        if drift:
            running = r["status"] != "scored"
            out["drift"].append({"round": r["round_number"], "status": r["status"], "running": running,
                                 "players": len(drift),
                                 "names": [f"{d['name']} {d['stored']:g} -> {d['now']:g}" for d in drift[:DRIFT_NAMES]]})
    out["zero_stat_pool"] = [z for z in await fantasy_pool_check.zero_stat_pool_players(db, fs.organisation_id)
                             if z["picked_by"] or z["twins"]]
    return out


def problems(res: dict) -> list[str]:
    """The findings as plain sentences, nothing for a healthy season."""
    p: list[str] = []
    for r in res["long_rounds"]:
        p.append(f"Round {r['round']} runs {r['start']} to {r['end']} ({r['days']} days, {r['status']}). A round that long locks "
                 f"managers out for weeks and cannot be confirmed until it ends.")
    missing = [r for r in res["draw_mismatch"] if r["status"] == "missing"]
    for r in res["draw_mismatch"]:
        if r["status"] == "missing":
            continue
        how = ("scored, so press Fix round dates on the overview" if r["status"] == "scored"
               else "not scored, so the nightly job moves it")
        p.append(f"Round {r['round']} is stored as {r['stored'][0]} to {r['stored'][1]}; the draw has {r['draw'][0]} to {r['draw'][1]} ({how}).")
    if missing:
        p.append(f"The draw has {len(missing)} more round(s) than are stored ({missing[0]['round']} to {missing[-1]['round']}, "
                 f"{missing[0]['draw'][0]} to {missing[-1]['draw'][1]}); the nightly job creates them.")
    if res["uncovered_games"]:
        ds = sorted({g["date"] for g in res["uncovered_games"]})
        p.append(f"{len(res['uncovered_games'])} game(s) fall in no round and score for nobody: {', '.join(ds[:6])}{'…' if len(ds) > 6 else ''}.")
    b = res["blocking_round"]
    if b:
        p.append(f"Round {b['round']} ended {b['ended']} and is {b['status']}, so rounds {', '.join(map(str, b['hides']))} are hidden from "
                 f"managers behind it. Confirm it.")
    for d in res["drift"]:
        what = "running" if d["running"] else "confirmed"
        p.append(f"Round {d['round']} ({what}): {d['players']} player(s) differ from their scorecards: {'; '.join(d['names'])}.")
    for z in res["zero_stat_pool"]:
        tw = f", twin has {z['twins'][0]['games']} game(s)" if z["twins"] else ""
        p.append(f"{z['name']} is in the pool, picked by {z['picked_by']}, with no games{tw}.")
    if res.get("draw_error"):
        p.append(f"Could not read the draw: {res['draw_error']}")
    return p
