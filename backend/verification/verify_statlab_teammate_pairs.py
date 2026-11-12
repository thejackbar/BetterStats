"""StatLab teammate pair reports: games together, win rate together, bowler and fielder
dismissals (with the wicketkeeper filter), opening bowling pairs, opening batting pairs.

Hand-built games with known answers, run through the SHIPPED `statlab.run_derived` over the
real `v_effective_*` views (taken from the migrations).

Cast (club "Us CC"): A keeps wicket, B and C bowl. LOAN is another club's player lent for a game.

  S1 (season 2025)
  G1  win   A B C                  roster + scorecard. B bowls first, C second, A third.
  G2  win   A B  (+ C)             C has a spell and no roster line: in the match, placed on A and B's side
  G3  loss  A B C                  LOAN opens the bowling, then B, then C
  G4  draw  A C                    no winner
  G5  win   B C                    HAND-TYPED / IMPORTED: no roster line, scorecard rows only, side unknown
  G6  called off (ABANDONED)       A B C named, nothing recorded: not a match
  G7  win   A C on 'Us', B on 'Them'   an intra-club fixture: two sides, A and B were opponents
  S2 (season 2026)
  G8  win   A B                    a scorecard line each (a roster alone with nothing recorded reads as unplayed)

Games together (all seasons): A&C 5 (G1 G2 G3 G4 G7), A&B 4 (G1 G2 G3 G8), B&C 4 (G1 G2 G3 G5).
  The washout is not a game, G7 does not pair A with B, and G7's two club sides do not double A&C.
  B&C: G5 has no side, so it is a game together with no result (sided games 3).

Run:  DATABASE_URL=postgresql+asyncpg://root@/pl_verify?host=/var/run/postgresql \
      python verification/verify_statlab_teammate_pairs.py

Control: on the previous commit none of these reports exists, so every read below reports a
failure instead of crashing (answers are read through `safe`).
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

import verify_records_partnership_grade_names as base
from app.services import statlab

check = base.check
ORG = base.ORG
OTHER = base.OPP
A, B, C, LOAN = (uuid.uuid4() for _ in range(4))
NAMES = {A: "Aaron Keeper", B: "Ben Bowler", C: "Cal Catcher"}


async def seed(session) -> dict:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    for oid, name, slug in ((ORG, "Us CC", "us"), (OTHER, "Them CC", "them")):
        await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)",
                 i=oid, n=name, s=slug)
    s1, s2, g1, g2 = (uuid.uuid4() for _ in range(4))
    await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:s, :o, 'Season 2025', 2025)", s=s1, o=ORG)
    await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:s, :o, 'Season 2026', 2026)", s=s2, o=ORG)
    for g, s in ((g1, s1), (g2, s2)):
        await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                 "VALUES (:g, :s, '1st Grade', :gid, 'senior', ARRAY['senior'])", g=g, s=s, gid=str(g))
    for pid, nm, org in ((A, NAMES[A], ORG), (B, NAMES[B], ORG), (C, NAMES[C], ORG), (LOAN, "Loan Player", OTHER)):
        await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                 "VALUES (:p, :o, :n, :gid, 'active')", p=pid, o=org, n=nm, gid=str(pid))

    games: dict[str, uuid.UUID] = {}

    async def game(label, grade, day, winner, roster, *, status="COMPLETED", intra=False, month=10):
        gid = uuid.uuid4()
        games[label] = gid
        await ex("INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_org_id, away_org_id, "
                 "winning_team, result, match_format, status) "
                 "VALUES (:g, :gr, :d, 'Us', 'Them', :o, :o2, :w, :res, 'One Day', :st)",
                 g=gid, gr=grade, d=date(2025 if grade == g1 else 2026, month, day), o=ORG,
                 o2=ORG if intra else None, w=winner,
                 res={"Us": "WIN", "Them": "LOSS"}.get(winner, "DRAW"), st=status)
        for pid, team in roster:
            await ex("INSERT INTO game_appearances (game_id, player_id, team_name, is_reserve) "
                     "VALUES (:g, :p, :t, false)", g=gid, p=pid, t=team)
        return gid

    G1 = await game("G1", g1, 1, "Us", [(A, "Us"), (B, "Us"), (C, "Us")])
    G2 = await game("G2", g1, 2, "Us", [(A, "Us"), (B, "Us")])
    G3 = await game("G3", g1, 3, "Them", [(A, "Us"), (B, "Us"), (C, "Us")])
    G4 = await game("G4", g1, 4, None, [(A, "Us"), (C, "Us")])
    G5 = await game("G5", g1, 5, "Us", [])
    await game("G6", g1, 6, None, [(A, "Us"), (B, "Us"), (C, "Us")], status="ABANDONED")
    G7 = await game("G7", g1, 7, "Us", [(A, "Us"), (C, "Us"), (B, "Them")], intra=True)
    G8 = await game("G8", g2, 1, "Us", [(A, "Us"), (B, "Us")])

    # G5: scorecard rows only, so the match exists through the same union StatLab's MATCHES column reads.
    for pid in (B, C):
        await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, dismissal_type, "
                 "not_out, batting_position, did_not_bat) VALUES (:g, :p, 1, 10, 12, 'bowled', false, 5, false)",
                 g=G5, p=pid)
    # G8: a roster alone is not a match once CA says COMPLETED with nothing recorded (looks_unplayed_sql).
    for pid in (A, B):
        await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, dismissal_type, "
                 "not_out, batting_position, did_not_bat) VALUES (:g, :p, 1, 12, 14, 'bowled', false, 4, false)",
                 g=G8, p=pid)
    # G7: A and C played for Us; B for Them. Both sides have a batting line.
    for pid in (A, C, B):
        await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, dismissal_type, "
                 "not_out, batting_position, did_not_bat) VALUES (:g, :p, 1, 8, 10, 'bowled', false, 6, false)",
                 g=G7, p=pid)

    # Bowling order is the spell id, so insert in card order.
    async def spells(gid, inn, order):
        for pid, wk in order:
            await ex("INSERT INTO bowling_spells (game_id, player_id, innings_number, overs, maidens, runs, wickets) "
                     "VALUES (:g, :p, :i, 6, 0, 30, :w)", g=gid, p=pid, i=inn, w=wk)

    await spells(G1, 1, [(B, 2), (C, 1), (A, 0)])
    await spells(G2, 1, [(B, 1), (C, 1)])
    await spells(G3, 1, [(LOAN, 0), (B, 1), (C, 0)])
    await spells(G4, 1, [(A, 1), (C, 0)])

    # Wickets: (game, bowler, fielder, dismissal, caught_behind)
    wk = [
        (G1, B, A, "caught", True), (G1, B, A, "caught", True), (G1, B, A, "stumped", None),
        (G1, B, C, "caught", False), (G1, B, C, "caught", None),   # None: recorded before keeper catches were tracked
        (G1, B, None, "bowled", None), (G1, B, None, "caught and bowled", None),
        (G2, C, A, "caught", True), (G2, C, B, "caught", False), (G2, C, B, "caught", False),
        (G3, B, C, "caught", False),
        (G8, B, A, "caught", True),
    ]
    for gid, bw, fl, dt, cb in wk:
        await ex("INSERT INTO bowler_wickets (game_id, innings_number, bowler_id, fielder_id, batter_name, "
                 "dismissal_type, caught_behind) VALUES (:g, 1, :b, :f, 'X Batter', :d, :c)",
                 g=gid, b=bw, f=fl, d=dt, c=cb)

    # First-wicket stands: A&B twice (once with the pair the other way round), A&C once, a wicket-2 stand,
    # and a stand with another club's player.
    stands = [(G1, 1, A, B, 60), (G2, 1, B, A, 45), (G3, 1, A, C, 30), (G1, 2, A, C, 80), (G4, 1, A, LOAN, 99)]
    for gid, wkt, b1, b2, runs in stands:
        await ex("INSERT INTO partnerships (game_id, innings_number, wicket_number, batter1_id, batter2_id, runs, "
                 "balls, batter1_runs, batter2_runs, is_club_innings) "
                 "VALUES (:g, 1, :w, :a, :b, :r, 60, :r, 0, true)", g=gid, w=wkt, a=b1, b=b2, r=runs)
    await session.commit()
    await session.execute(text("ANALYZE"))
    await session.commit()
    return {"s1": s1, "s2": s2}


async def run(session, name, context=None, limit=100):
    return (await statlab.run_derived(
        session, name=name, org_id=str(ORG), limit=limit, context=dict(context or {})))["rows"]


async def safe(session, *a, **kw):
    """The rows, or [] with the reason printed, so a control run reports instead of crashing."""
    try:
        return await run(session, *a, **kw)
    except Exception as e:  # noqa: BLE001 - the control run on the old code lands here
        await session.rollback()
        print(f"      (query failed: {str(e)[:90]})")
        return []


def pair(r):
    return frozenset((r.get("player_a_name"), r.get("player_b_name")))


def by_pair(rows):
    return {pair(r): r for r in rows}


AB = frozenset((NAMES[A], NAMES[B]))
AC = frozenset((NAMES[A], NAMES[C]))
BC = frozenset((NAMES[B], NAMES[C]))


def figs(r, *keys):
    """The named fields as plain numbers (a Decimal 66.7 never equals the float 66.7)."""
    return tuple(float(v) if isinstance(v, Decimal) else v for v in ((r or {}).get(k) for k in keys))


async def main() -> None:
    await base.build_schema()
    async with base.Session() as session:
        seasons = await seed(session)

    async with base.Session() as session:
        print("\n-- most games played together --")
        rows = await safe(session, "games_together")
        got = by_pair(rows)
        check("three pairs, no others (the lent player has no club row)", set(got) == {AB, AC, BC}, str(set(got)))
        check("A&C: G1 G2 G3 G4 G7 = 5, G7's two club sides not double counted, G2 through C's spell alone",
              figs(got.get(AC), "games") == (5,), str(got.get(AC)))
        check("A&B: G1 G2 G3 G8 = 4, not G6 (called off) and not G7 (opposite sides)",
              figs(got.get(AB), "games") == (4,), str(got.get(AB)))
        check("B&C: G1 G2 G3 and the sideless G5 = 4", figs(got.get(BC), "games") == (4,), str(got.get(BC)))
        check("A&C record: 3 won (G1 G2 G7), 1 lost (G3), 1 drawn (G4), 60.0%",
              figs(got.get(AC), "wins", "losses", "draws", "win_pct", "sided_games") == (3, 1, 1, 60.0, 5),
              str(got.get(AC)))
        check("A&B record: 3 won (G1 G2 G8), 1 lost (G3), 75.0%",
              figs(got.get(AB), "wins", "losses", "draws", "win_pct") == (3, 1, 0, 75.0), str(got.get(AB)))
        check("B&C: the hand-typed game is a game together but has no result (sided 3, 2-1, 66.7%)",
              figs(got.get(BC), "wins", "losses", "sided_games", "win_pct") == (2, 1, 3, 66.7), str(got.get(BC)))
        check("ranked by games then wins: A&C (5), A&B (4, 3 wins), B&C (4, 2 wins)",
              [pair(r) for r in rows] == [AC, AB, BC], str([sorted(pair(r)) for r in rows]))
        check("first and last game dates are there",
              figs(got.get(AB), "first_game", "last_game") != (None, None), str(got.get(AB)))

        print("\n-- a season narrows the games --")
        s1 = by_pair(await safe(session, "games_together", {"season_id": str(seasons["s1"])}))
        check("season 2025 only: A&B drops G8 (3 games)", figs(s1.get(AB), "games", "wins") == (3, 2), str(s1.get(AB)))
        s2 = by_pair(await safe(session, "games_together", {"season_id": str(seasons["s2"])}))
        check("season 2026 only: one pair, A&B, one game", set(s2) == {AB} and figs(s2.get(AB), "games") == (1,),
              str(set(s2)))

        print("\n-- one player's pairs --")
        mine = await safe(session, "games_together", {"player_id": str(B)})
        check("B: A&B and B&C only", {pair(r) for r in mine} == {AB, BC}, str([sorted(pair(r)) for r in mine]))
        check("the figures on B's rows are the unfiltered figures",
              all(figs(r, "games", "wins") == figs(got[pair(r)], "games", "wins") for r in mine))

        print("\n-- best win rate together --")
        none = await safe(session, "win_rate_together")
        check("default floor of 10 games: nobody qualifies, an empty table not a guess", none == [], str(none))
        low = await safe(session, "win_rate_together", {"min_games": 2})
        check("floor 2: A&B 75.0, B&C 66.7 (3 sided games), A&C 60.0",
              [(pair(r), float(r.get("win_pct"))) for r in low] == [(AB, 75.0), (BC, 66.7), (AC, 60.0)],
              str([(sorted(pair(r)), r.get("win_pct")) for r in low]))
        four = await safe(session, "win_rate_together", {"min_games": 4})
        check("floor 4 counts games with a known side: B&C (3 sided of 4) is out, A&B and A&C stay",
              {pair(r) for r in four} == {AB, AC}, str([sorted(pair(r)) for r in four]))
        check("a pair's win % is wins over games with a known side, not over every game",
              figs(by_pair(low).get(BC), "win_pct", "sided_games", "games") == (66.7, 3, 4))

        print("\n-- bowler and fielder dismissals --")
        allr = await safe(session, "bowler_fielder_dismissals")
        d = {(r["player_a_name"], r["player_b_name"]): r for r in allr}
        check("B->A: 3 catches behind + 1 in S2 + 1 stumping = 4", figs(d.get((NAMES[B], NAMES[A])), "dismissals", "catches", "catches_wk", "stumpings") == (4, 3, 3, 1), str(d.get((NAMES[B], NAMES[A]))))
        check("B->C: 3 (two catches, one with the keeper flag not recorded)",
              figs(d.get((NAMES[B], NAMES[C])), "dismissals", "catches_wk") == (3, 0), str(d.get((NAMES[B], NAMES[C]))))
        check("C->B: 2, C->A: 1", figs(d.get((NAMES[C], NAMES[B])), "dismissals") == (2,)
              and figs(d.get((NAMES[C], NAMES[A])), "dismissals") == (1,))
        check("bowled and caught-and-bowled have no second player, so no row",
              len(allr) == 4, str([(r["player_a_name"], r["player_b_name"]) for r in allr]))
        check("ordered by dismissals: B->A (4) first", allr and (allr[0]["player_a_name"], allr[0]["player_b_name"]) == (NAMES[B], NAMES[A]))
        check("the row names bowler as A and fielder as B", d and all(k[0] != k[1] for k in d))

        kp = await safe(session, "bowler_fielder_dismissals", {"fielder_role": "keeper"})
        k = {(r["player_a_name"], r["player_b_name"]): r for r in kp}
        check("keeper only: just the pairs that end at the keeper", set(k) == {(NAMES[B], NAMES[A]), (NAMES[C], NAMES[A])},
              str(set(k)))
        check("keeper only: B->A is 4 (catches behind and the stumping), C->A is 1",
              figs(k.get((NAMES[B], NAMES[A])), "dismissals", "stumpings") == (4, 1) and
              figs(k.get((NAMES[C], NAMES[A])), "dismissals") == (1,), str(k))

        fl = await safe(session, "bowler_fielder_dismissals", {"fielder_role": "fielder"})
        f = {(r["player_a_name"], r["player_b_name"]): r for r in fl}
        check("fielders only: B->C and C->B, never the keeper", set(f) == {(NAMES[B], NAMES[C]), (NAMES[C], NAMES[B])},
              str(set(f)))
        check("fielders only: a catch with the keeper flag unknown is left out (B->C is 2, not 3)",
              figs(f.get((NAMES[B], NAMES[C])), "dismissals") == (2,), str(f.get((NAMES[B], NAMES[C]))))
        check("an unrecognised role reads as all", len(await safe(session, "bowler_fielder_dismissals", {"fielder_role": "zzz"})) == 4)

        ps = await safe(session, "bowler_fielder_dismissals", {"season_id": str(seasons["s1"]), "fielder_role": "keeper"})
        pk = {(r["player_a_name"], r["player_b_name"]): r for r in ps}
        check("season 2025 keeper: B->A drops the S2 catch (3)", figs(pk.get((NAMES[B], NAMES[A])), "dismissals") == (3,), str(pk))
        one = await safe(session, "bowler_fielder_dismissals", {"player_id": str(C)})
        check("pick C: every pair has C on it (as bowler or fielder)",
              bool(one) and all(NAMES[C] in (r["player_a_name"], r["player_b_name"]) for r in one), str(len(one)))

        print("\n-- opening bowling pairs --")
        ob = await safe(session, "opening_bowling_pairs")
        o = by_pair(ob)
        check("B&C opened in G1 and G2 only: G3's lent opener is numbered, so B is the second opener there and C is out",
              figs(o.get(BC), "innings", "matches", "wickets") == (2, 2, 5), str(o.get(BC)))
        check("A&C opened in G4", figs(o.get(AC), "innings") == (1,), str(o.get(AC)))
        check("no pair with the lent player and nothing for A&B", set(o) == {BC, AC}, str(set(o)))
        check("most innings first", [pair(r) for r in ob][:1] == [BC])

        print("\n-- opening batting pairs --")
        op = await safe(session, "opening_batting_pairs")
        p = by_pair(op)
        check("A&B shared two first-wicket stands whichever way round they are recorded",
              figs(p.get(AB), "stands", "total_runs", "best", "average", "fifty_stands") == (2, 105, 60, 52.5, 1),
              str(p.get(AB)))
        check("A&C: one first-wicket stand; the wicket-2 stand is not counted",
              figs(p.get(AC), "stands", "total_runs") == (1, 30), str(p.get(AC)))
        check("a stand with another club's player is not a pair of ours", set(p) == {AB, AC}, str(set(p)))
        check("most stands first", [pair(r) for r in op][:1] == [AB])

        print("\n-- the registry --")
        sch = statlab.schema()["derived"]
        for key in ("games_together", "win_rate_together", "bowler_fielder_dismissals",
                    "opening_bowling_pairs", "opening_batting_pairs"):
            check(f"{key} is in the schema with a pair of player columns",
                  key in sch and {c.get("kind") for c in sch[key]["columns"]} >= {"player_a", "player_b"})
        check("the old catches-only report is still there for saved reports", "bowler_fielder_combo" in sch)

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    if base.FAIL:
        print("\n".join(base.FAILURES))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
