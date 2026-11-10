"""A game belongs to no club: the reads that scoped games by the SEASON'S owner.

A fixture two synced clubs played is ONE `games` row under whichever club's season
row synced it first. Reads that decided "this game is ours" or "this game is in our
season" from that row's owner dropped the club's half of every such fixture. Found by
auditing every per-game read after the Fees fix (Angus Castley, Applecross). This
checks the sites fixed in that sweep, against a real Postgres, through the shipped
route bodies and services:

  * StatLab: a picked season (single and multi-select) keeps the game stored under
    the other club's season row; a season total is one row, not two; the other
    club's players and an unrelated club's game never come in
  * the Club records tab with a season picked
  * the admin Games list, with and without a season, and its players_named count
  * the scorecard duplicate check (it let a synced fixture be uploaded again)
  * public Lineups (past mode) with a season picked
  * BetterIQ's season clause for player deep-dives and the selection season load

Every "is there" check is paired with an "is not there" check (the other club's
player, an unrelated club's game), so a read that simply stopped filtering fails.

Run the control against the previous commit (`git stash` the services and routers
changes, keep this file) and it must fail on exactly the dropped game.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/shared_verify?host=/tmp/pgv&port=5544 \
      python verification/verify_shared_fixture_reads.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import verify_rate_coverage as base  # noqa: E402  (builds the engine from DATABASE_URL)
from sqlalchemy import text  # noqa: E402

check = base.check

A, B, C = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()          # our club, the opponent, a stranger
SA, SB, SC = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()       # each club's row of Summer 2026/27
GA, GB, GC = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
PA, PB, PC = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()       # Angus (ours), Olly (theirs), a stranger
G_OWN, G_SHARED, G_STRANGER = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
PLAYED = '[{"runs_scored": 120, "wickets": 5}]'


async def seed(session) -> None:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    for oid, nm in ((A, "Applecross"), (B, "North Perth"), (C, "Somewhere Else")):
        await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)",
                 i=oid, n=nm, s=nm.lower().replace(" ", "-"))
    # One real-world season, held under each club's own row (same CA season GUID).
    for sid, oid in ((SA, A), (SB, B), (SC, C)):
        await ex("INSERT INTO seasons (id, organisation_id, name, year, grassroots_id) "
                 "VALUES (:i, :o, 'Summer 2026/27', 2026, 'CA-SEASON')", i=sid, o=oid)
    for gid, sid in ((GA, SA), (GB, SB), (GC, SC)):
        await ex("INSERT INTO grades (id, season_id, name, category) "
                 "VALUES (:i, :s, 'One Day Grade 4', 'senior')", i=gid, s=sid)
    for pid, oid, nm in ((PA, A, "Castley, Angus"), (PB, B, "Opposition, Olly"), (PC, C, "Stranger, Sam")):
        await ex("INSERT INTO players (id, organisation_id, name) VALUES (:i, :o, :n)", i=pid, o=oid, n=nm)

    async def game(gid, grade, d, home, away, home_org, away_org, winner):
        await ex("INSERT INTO games (id, grade_id, played_at, venue, result, match_format, status, "
                 "home_team, away_team, winning_team, home_org_id, away_org_id, innings_totals) "
                 "VALUES (:i, :g, :d, 'Oval', 'WIN', 'One Day', 'COMPLETED', :h, :a, :w, :ho, :ao, "
                 "CAST(:t AS JSONB))",
                 i=gid, g=grade, d=d, h=home, a=away, w=winner, ho=home_org, ao=away_org, t=PLAYED)

    # 17 Oct: under OUR season row (we synced first). 24 Oct: under THEIR season row.
    await game(G_OWN, GA, date(2026, 10, 17), "Applecross 7th XI", "SMCC 8th XI", A, B, "Applecross 7th XI")
    await game(G_SHARED, GB, date(2026, 10, 24), "North Perth 4th XI", "Applecross 7th XI", B, A,
               "Applecross 7th XI")
    # A game neither of our clubs is in, under a third club's row of the same season.
    await game(G_STRANGER, GC, date(2026, 10, 24), "Elsewhere 1st XI", "Elsewhere 2nd XI", C, C, "Elsewhere 1st XI")

    for g, pa_runs, pa_balls in ((G_OWN, 1, 0), (G_SHARED, 69, 105)):
        for pid, runs, balls in ((PA, pa_runs, pa_balls), (PB, 30, 40)):
            await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=g, p=pid)
            await ex("INSERT INTO batting_innings (game_id, player_id, runs, balls, not_out, innings_number, "
                     "batting_position) VALUES (:g, :p, :r, :b, false, 1, 1)", g=g, p=pid, r=runs, b=balls)
    await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=G_STRANGER, p=PC)
    await ex("INSERT INTO batting_innings (game_id, player_id, runs, balls, not_out, innings_number, "
             "batting_position) VALUES (:g, :p, 88, 90, false, 1, 1)", g=G_STRANGER, p=PC)
    # CA's own season total for Angus, under OUR season row: 2 matches, 70 runs.
    await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, not_outs, "
             "balls_faced, high_score, fifties, hundreds, ducks, fours, sixes) "
             "VALUES (:p, :s, 2, 2, 70, 1, 105, 69, 1, 0, 0, 5, 0)", p=PA, s=SA)
    await session.commit()


def runs_of(rows, pid):
    return sorted(int(r["runs"]) for r in rows if str(r.get("player_id")) == str(pid) and r.get("runs") is not None)


async def main() -> None:
    from app.services import statlab

    await base.build_schema()
    async with base.Session() as session:
        await seed(session)
        sa, org = str(SA), str(A)

        async def q(target, ctx, sort_by="runs"):
            return (await statlab.run_query(
                session, org_id=org, target=target, sort_by=sort_by, sort_dir="desc", limit=200,
                metric_filters=None, filter_tree=None, context=ctx))["rows"]

        print("\n— StatLab: a picked season keeps the game under the other club's season row —")
        inns = await q("innings_list", {"season_id": sa})
        check("innings list, season picked: both of Angus's innings (1 and 69)",
              runs_of(inns, PA) == [1, 69], str(runs_of(inns, PA)))
        check("(the other club's player is not listed)", all(str(r.get("player_id")) != str(PB) for r in inns))
        check("(an unrelated club's game and player are not listed)",
              all(str(r.get("player_id")) != str(PC) for r in inns))
        inns_multi = await q("innings_list", {"season_ids": [sa]})
        check("innings list, season multi-select: both innings", runs_of(inns_multi, PA) == [1, 69],
              str(runs_of(inns_multi, PA)))
        inns_none = await q("innings_list", {})
        check("(no season picked still lists both: the game was never the problem, the filter was)",
              runs_of(inns_none, PA) == [1, 69], str(runs_of(inns_none, PA)))
        matches = await q("match_list", {"season_id": sa}, sort_by="team_runs")
        check("match list, season picked: both matches", len(matches) == 2, str(len(matches)))

        live = await q("player_season", {"date_from": "2020-01-01"})
        mine = [r for r in live if str(r.get("player_id")) == str(PA)]
        check("player season, live path: one season row for Angus, not one per club's season row",
              len(mine) == 1, f"{len(mine)} rows: {[(r.get('season_name'), r.get('runs')) for r in mine]}")
        check("(and it carries both games)", bool(mine) and int(mine[0]["runs"]) == 70,
              str([int(r['runs']) for r in mine]))
        live_pick = await q("player_season", {"date_from": "2020-01-01", "season_id": sa})
        mine_pick = [r for r in live_pick if str(r.get("player_id")) == str(PA)]
        check("player season, live path with the season picked: one row, 70 runs",
              len(mine_pick) == 1 and int(mine_pick[0]["runs"]) == 70,
              str([(r.get('season_name'), int(r['runs'])) for r in mine_pick]))
        check("(the other club's player is not in it)",
              all(str(r.get("player_id")) != str(PB) for r in live_pick))

        derived = (await statlab.run_derived(
            session, name="most_runs_in_match", org_id=org, limit=50, context={"season_id": sa}))["rows"]
        check("a derived record with the season picked finds the 69 under the other club's row",
              69 in [int(r["runs"]) for r in derived if r.get("runs") is not None],
              str([r.get("runs") for r in derived]))

        print("\n— Club records, season picked —")
        from app.routers import records as rec
        payload = await rec.get_club_records(
            org_id=org, season_id=sa, grade_id=None, grade_name=None, finals_only=False,
            categories="all", formats=None, competitions=None, db=session, viewer=None)
        flat = repr(payload)
        check("the club record book sees the game under the other club's season row",
              str(G_SHARED) in flat, flat[:200])
        check("(and our own game, so the check can tell the two apart)", str(G_OWN) in flat)
        check("(and not the stranger's game)", str(G_STRANGER) not in flat)

        print("\n— Admin Games list —")
        from app.routers import club_admin as ca
        from app.models.db import Organisation
        club = await session.get(Organisation, A)
        for label, season in (("no season", None), ("season picked", sa)):
            rows = await ca.list_games(season_id=season, current_user=None, club=club, db=session)
            ids = {r["id"] for r in rows}
            check(f"Games list, {label}: both of our fixtures", {str(G_OWN), str(G_SHARED)} <= ids, str(ids))
            check(f"Games list, {label}: not the stranger's", str(G_STRANGER) not in ids)

        print("\n— Scorecard duplicate check —")
        from app.routers import manual_entries as me
        dup = await me.check_scorecard_duplicate(
            played_at="2026-10-24", opponent="North Perth", exclude_id="", current_user=None, club=club, db=session)
        found = {m["id"] for m in dup["matches"]}
        check("uploading a scorecard for 24 Oct warns: the synced fixture is already there",
              str(G_SHARED) in found, str(found))
        check("(and does not offer the stranger's game of the same day)", str(G_STRANGER) not in found)

        print("\n— Public Lineups, past games with a season picked —")
        import app.services.lineups as lineups
        from app.routers import organisations as orgs
        seen: dict = {}

        async def fake_lineups(db, org, match_ids):
            seen["ids"] = list(match_ids)
            return [{"match_id": m} for m in match_ids]
        real = lineups.org_lineups
        lineups.org_lineups = fake_lineups
        try:
            await orgs.get_org_lineups(
                org_id=org, mode="past", season_id=sa, grade_id=None, category=None, finals_only=False,
                offset=0, limit=6, db=session, viewer=None)
        finally:
            lineups.org_lineups = real
        ids = set(seen.get("ids", []))
        check("Lineups past games include the fixture under the other club's row",
              {str(G_OWN), str(G_SHARED)} <= ids, str(ids))
        check("(and not the stranger's)", str(G_STRANGER) not in ids)

        print("\n— BetterIQ season clauses —")
        from app.services import iq_trends, iq_selection
        clause = iq_trends._pull_filters(sa, None)
        got = {r[0] for r in (await session.execute(text(
            "SELECT g.id FROM v_effective_games g LEFT JOIN grades gr ON gr.id = g.grade_id "
            f"WHERE (g.organisation_id = :org OR g.home_org_id = :org OR g.away_org_id = :org) {clause}"),
            {"org": A, "season": sa, "org_id": A})).all()}
        check("a season-filtered deep-dive pull keeps both of our games", {G_OWN, G_SHARED} <= got, str(got))
        check("(and not the stranger's)", G_STRANGER not in got)
        load = await iq_selection._season_load(session, str(GA), org)
        check("selection season load counts both of Angus's games in the grade",
              load.get(str(PA)) == 2, str(load))
        check("(and none for the other club's player)", str(PB) not in load)

    await base.engine.dispose()
    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    if base.FAIL:
        for f in base.FAILURES:
            print("  -", f)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
