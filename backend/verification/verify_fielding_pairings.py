"""A fielder's catches and stumpings, wicket by wicket, against a real Postgres.

The Fielding tab shows season totals. This suite proves the new list under it: every catch and stumping a
player took, oldest first, the bowler each came off, and the per-bowler sums, read through the shipped route
body (`get_player_fielding_dismissals`) and the live effective views (`superseded_ddl` applied on top of the
shared harness, as the lifespan does).

Seeds Ryan Carmody, a keeper, and:

  G7  synced, 2000-02-05, A Grade, season 1999/00        stumped off Dan
  G1  synced, 2000-10-07, A Grade, One Day, shared with Rival CC
        stumped off Ben (batter 12) / caught behind off Cal / plain catch off Ben /
        bowled (no fielder) / caught-and-bowled (no fielder)
        + Rival CC's own keeper stumping off THEIR bowler          (the other club's rows on the shared game)
        + a row naming Carmody with a Rival CC bowler               (a cross-club bowler: must not be listed)
  G2  synced, 2000-10-21, A Grade, T20                    stumped off Dan; stumped off Harry (HIDDEN bowler)
  G3  synced, 2000-11-04, Under 16s (junior)              stumped off Ben   (out under the club default)
  M1  hand-entered, 2000-11-18, A Grade                   stumped off Cal; catch off Ben (caught_behind NULL)
  M2  hand-entered, 2000-12-02, NO grade                  stumped off Ben   (a grade-less game still counts)
  M3  hand-entered, 2000-10-07, paired to G1, synced wins stumped off Ben   (must not double count G1)
  G8  synced, 2000-12-16, paired to M4, club's card chosen stumped off Ben  (hidden: M4 is the shown copy)
  M4  hand-entered, 2000-12-16, the chosen card           stumped off Cal
  G5  synced, 2000-12-09, another club's game, Carmody's name on it    stumped off Ben (not our game)

Where CA's dismissal text names nobody ("st:  b: ") no pairing can be built, but the scorecard's fielding row
still credits the keeper. Those are added back as rows with no bowler:

  G9  synced, 2000-10-14, A Grade     fielding row: 2 stumpings, 1 keeper catch; NO pairing rows  -> 3 added
  G10 synced, 2000-10-28, A Grade     fielding row: 2 stumpings; one paired (off Lee)             -> 1 added
  G11 synced, 2000-11-11, A Grade     Carmody BOWLS a caught-and-bowled; fielding row: 1 catch    -> 0 added
  G12 synced, 2000-11-12, Under 16s   fielding row: 1 stumping, no pairing                        -> 1 added, juniors only
  G13 synced, 2000-12-10, another club's game, fielding row: 1 stumping                           -> 0 (not our game)
  G1 also gets a fielding row that matches its pairings exactly                                   -> 0 added

Every "this row is absent" check is paired with a raw query showing the row COULD be there, so a check that can
only pass is not a check. `CONTROL=1` switches off the club-ownership clause and the hidden-bowler mask; the
guard checks must then fail, and nothing may crash.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/fielding_verify?host=/var/run/postgresql&port=5439 \\
  python verification/verify_fielding_pairings.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from sqlalchemy import text

import verify_board_games_match_profile as b            # its schema and helpers; main() is guarded
from app.models.db import User
from app.routers.players import get_player_fielding_dismissals
from app.services import aggregations as agg
from app.services import fielding_pairings, superseded_ddl

ORG, OPP = b.ORG, b.OPP
Session, check = b.Session, b.check
CONTROL = bool(os.environ.get("CONTROL"))

RYAN, BEN, CAL, DAN, HARRY, LEE = (uuid.uuid4() for _ in range(6))
RIVAL_KEEPER, RIVAL_BOWLER, OTHER_KEEPER = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
ADMIN = uuid.uuid4()
S1, S0, S_OPP = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
G_A, G_A0, G_J, G_OPP = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
G1, G2, G3, G5, G7, G8, G9, G10, G11, G12, G13 = (uuid.uuid4() for _ in range(11))
M1, M2, M3, M4 = (uuid.uuid4() for _ in range(4))
CLUB_NAME = "Carmody Club"


async def build() -> None:
    await b.build_schema()
    async with b.engine.begin() as conn:
        for stmt in superseded_ddl.STATEMENTS:                      # the live views, as the lifespan applies them
            await conn.execute(text(stmt))
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, 'carmody', true)", i=ORG, n=CLUB_NAME)
        await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, 'Rival CC', 'rival', true)", i=OPP)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2000/01', 2000)", i=S1, o=ORG)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 1999/00', 1999)", i=S0, o=ORG)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2000/01', 2000)", i=S_OPP, o=OPP)
        for gid, sid, org, nm, cat in ((G_A, S1, ORG, "A Grade", "senior"), (G_A0, S0, ORG, "A Grade", "senior"),
                                       (G_J, S1, ORG, "Under 16s", "junior"), (G_OPP, S_OPP, OPP, "Rival A", "senior")):
            await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                     "VALUES (:i, :s, :n, :g, :c, ARRAY[CAST(:c AS text)])", i=gid, s=sid, n=nm, g=str(gid), c=cat)
        for pid, org, nm in ((RYAN, ORG, "Carmody, Ryan"), (BEN, ORG, "Bowler, Ben"), (CAL, ORG, "Quick, Cal"),
                             (DAN, ORG, "Spin, Dan"), (HARRY, ORG, "Hidden, Harry"), (LEE, ORG, "Late, Lee"),
                             (RIVAL_KEEPER, OPP, "Keeper, Rival"), (RIVAL_BOWLER, OPP, "Bowler, Rival"),
                             (OTHER_KEEPER, OPP, "Keeper, Other")):
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                     "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=org, n=nm, g=str(pid))
        await ex("UPDATE players SET is_public = false WHERE id = :i", i=HARRY)

        async def game(gid, grade, day, fmt, home_org, away_org, home="Carmody Club", away="Rival CC"):
            await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, match_format, "
                     "status, home_team, away_team) VALUES (:i, :g, :d, 'WIN', :h, :a, :f, 'COMPLETED', :ht, :at)",
                     i=gid, g=grade, d=date.fromisoformat(day), h=home_org, a=away_org, f=fmt, ht=home, at=away)

        async def manual(mid, grade, day, fmt=None, opposition="Rival CC"):
            await ex("INSERT INTO manual_games (id, organisation_id, season_id, grade_id, played_at, opposition, "
                     "result, match_format) VALUES (:i, :o, :s, :g, :d, :op, 'WIN', :f)",
                     i=mid, o=ORG, s=S1, g=grade, d=date.fromisoformat(day), op=opposition, f=fmt)

        async def bw(gid, bowler, fielder, kind, batter, runs, cb=None, inn=2):
            await ex("INSERT INTO bowler_wickets (game_id, innings_number, bowler_id, fielder_id, batter_name, "
                     "batter_position, batter_runs, dismissal_type, caught_behind) "
                     "VALUES (:g, :n, :b, :f, :bt, 4, :r, :k, :cb)",
                     g=gid, n=inn, b=bowler, f=fielder, bt=batter, r=runs, k=kind, cb=cb)

        async def mbw(mid, bowler, fielder, kind, batter, runs):
            await ex("INSERT INTO manual_bowler_wickets (manual_game_id, innings_number, bowler_id, fielder_id, "
                     "batter_name, batter_position, batter_runs, dismissal_type, caught_behind) "
                     "VALUES (:m, 2, :b, :f, :bt, 4, :r, :k, NULL)", m=mid, b=bowler, f=fielder, bt=batter, r=runs, k=kind)

        await game(G7, G_A0, "2000-02-05", "One Day", ORG, OPP)
        await bw(G7, DAN, RYAN, "stumped", "P Old", 4)

        await game(G1, G_A, "2000-10-07", "One Day", ORG, OPP)
        await bw(G1, BEN, RYAN, "stumped", "J Smith", 12)
        await bw(G1, CAL, RYAN, "caught", "K Jones", 30, cb=True)
        await bw(G1, BEN, RYAN, "caught", "L Brown", 7, cb=False)
        await bw(G1, BEN, None, "bowled", "Q Stump", 0)
        await bw(G1, DAN, None, "caught and bowled", "R Lee", 3)
        await bw(G1, RIVAL_BOWLER, RIVAL_KEEPER, "stumped", "Our Opener", 22, inn=1)     # the other club's own wicket
        await bw(G1, RIVAL_BOWLER, RYAN, "caught", "Cross Club", 9, cb=False)           # a cross-club bowler

        await game(G2, G_A, "2000-10-21", "T20", ORG, OPP)
        await bw(G2, DAN, RYAN, "stumped", "M Green", 15)
        await bw(G2, HARRY, RYAN, "stumped", "N Hall", 8)

        await game(G3, G_J, "2000-11-04", "One Day", ORG, OPP)
        await bw(G3, BEN, RYAN, "stumped", "Junior Opp", 2)

        await game(G5, G_OPP, "2000-12-09", "One Day", OPP, None, home="Rival CC", away="Elsewhere CC")
        await bw(G5, BEN, RYAN, "stumped", "Not Our Game", 1)

        await game(G8, G_A, "2000-12-16", "One Day", ORG, OPP)
        await bw(G8, BEN, RYAN, "stumped", "Synced Twin", 6)

        async def field(gid, st=0, c=0, wk=0):
            await ex("INSERT INTO fielding_stats (game_id, player_id, catches, catches_wk, run_outs, stumpings) "
                     "VALUES (:g, :p, :c, :w, 0, :s)", g=gid, p=RYAN, c=c, w=wk, s=st)

        await field(G1, st=1, c=2, wk=1)                                  # matches its pairings exactly
        await game(G9, G_A, "2000-10-14", "One Day", ORG, OPP)
        await field(G9, st=2, c=1, wk=1)                                  # names blank: no pairing rows at all
        await game(G10, G_A, "2000-10-28", "One Day", ORG, OPP)
        await bw(G10, LEE, RYAN, "stumped", "Z Partial", 3)
        await field(G10, st=2)                                            # one paired, one not
        await game(G11, G_A, "2000-11-11", "One Day", ORG, OPP)
        await bw(G11, RYAN, None, "caught and bowled", "Own Bowling", 14)
        await field(G11, c=1)                                             # his own catch off his own bowling
        await game(G12, G_J, "2000-11-12", "One Day", ORG, OPP)
        await field(G12, st=1)
        await game(G13, G_OPP, "2000-12-10", "One Day", OPP, None, home="Rival CC", away="Elsewhere CC")
        await field(G13, st=1)

        await manual(M1, G_A, "2000-11-18")
        await mbw(M1, CAL, RYAN, "stumped", "S Manual", 11)
        await mbw(M1, BEN, RYAN, "caught", "T Manual", 20)
        await manual(M2, None, "2000-12-02", opposition="Rival")
        await mbw(M2, BEN, RYAN, "stumped", "U Manual", 5)
        await manual(M3, G_A, "2000-10-07")
        await mbw(M3, BEN, RYAN, "stumped", "Double Count", 99)
        await manual(M4, G_A, "2000-12-16")
        await mbw(M4, CAL, RYAN, "stumped", "Chosen Card", 6)
        await ex("UPDATE manual_games SET superseded_by_game_id = :g WHERE id = :m", g=G1, m=M3)
        await ex("UPDATE manual_games SET superseded_by_game_id = :g, pair_prefers_import = true WHERE id = :m", g=G8, m=M4)

        await ex("INSERT INTO users (id, username, password_hash, failed_login_count) VALUES (:i, 'boss', 'x', 0)", i=ADMIN)
        await ex("INSERT INTO club_memberships (id, club_id, user_id, role) VALUES (:i, :c, :u, 'club_admin')",
                 i=uuid.uuid4(), c=ORG, u=ADMIN)
        await s.commit()


async def route(pid, viewer=None, **kw):
    args = dict(season_id=None, categories=None, formats=None, competitions=None, grades=None)
    args.update(kw)
    async with Session() as s:
        return await get_player_fielding_dismissals(player_id=str(pid), db=s, viewer=viewer, **args)


async def raw_count(sql, **kw):
    async with Session() as s:
        return (await s.execute(text(sql), kw)).scalar()


def of(d, kind=None):
    return [r for r in (d.get("rows") or []) if kind is None or r.get("kind") == kind]


def pairs(d, kind=None):
    return [((r.get("played_at") or "")[:10], r.get("bowler_name"), r.get("batter_name")) for r in of(d, kind)]


def line(d, bowler_name):
    return next((g for g in (d.get("by_bowler") or []) if g.get("bowler_name") == bowler_name), None) or {}


async def main() -> None:
    await build()
    if CONTROL:
        print("\n*** CONTROL: club-ownership clause and hidden-bowler mask are OFF; the guard checks must fail ***")

        async def no_club(session, player_id, params, alias="g"):
            params["club_org"] = await agg._player_org_id(session, player_id)
            return ""
        agg._club_game_clause = no_club
        fielding_pairings.mask_hidden_bowlers = lambda rows, ids: rows

    d = await route(RYAN)

    print("\n-- THE STUMPING LIST, FIRST TO MOST RECENT --")
    stumps = pairs(d, "stumping")
    named = [x for x in stumps if x[1] is not None]
    check("seven named stumpings: synced, hand-entered, grade-less and the chosen card",
          len(named) == 7, str(named))
    check("oldest first: the 5 Feb stumping off Dan opens the list, the 16 Dec chosen card closes it",
          bool(stumps) and stumps[0][:2] == ("2000-02-05", "Spin, Dan") and stumps[-1][:2] == ("2000-12-16", "Quick, Cal"),
          str(stumps[:1] + stumps[-1:]))
    check("dates never run backwards", [x[0] for x in stumps] == sorted(x[0] for x in stumps), str([x[0] for x in stumps]))
    check("each row names the bowler AND the batter stumped",
          ("2000-10-07", "Bowler, Ben", "J Smith") in stumps and ("2000-11-18", "Quick, Cal", "S Manual") in stumps,
          str(stumps))
    row = next((r for r in of(d, "stumping") if r.get("batter_name") == "J Smith"), {})
    check("a row carries the match, grade, season and the batter's score",
          row.get("home_team") == "Carmody Club" and row.get("away_team") == "Rival CC"
          and row.get("grade_name") == "A Grade" and row.get("season_name") == "Summer 2000/01"
          and row.get("batter_runs") == 12 and row.get("game_id") == str(G1), str(row))

    print("\n-- CATCHES AND CATCHES BEHIND --")
    check("one catch off Ben at G1, and the hand-entered one off Ben (caught_behind NULL reads as a plain catch)",
          sorted(pairs(d, "catch")) == [("2000-10-07", "Bowler, Ben", "L Brown"), ("2000-11-18", "Bowler, Ben", "T Manual")],
          str(pairs(d, "catch")))
    check("the keeper catch is its own kind, off Cal (and G9's, with no bowler recorded)",
          pairs(d, "caught_behind") == [("2000-10-07", "Quick, Cal", "K Jones"), ("2000-10-14", None, None)],
          str(pairs(d, "caught_behind")))
    check("counts: 11 stumpings, 2 catches, 2 caught behind, 15 in all, 4 with no bowler recorded",
          d.get("counts") == {"catch": 2, "caught_behind": 2, "stumping": 11, "total": 15, "unpaired": 4}, str(d.get("counts")))
    check("a bowled wicket and a caught-and-bowled have no fielder, so neither is listed",
          not any(r.get("batter_name") in ("Q Stump", "R Lee") for r in of(d)))

    print("\n-- THE SUMMARY BY BOWLER --")
    ben, cal, dan = line(d, "Bowler, Ben"), line(d, "Quick, Cal"), line(d, "Spin, Dan")
    check("Ben: 2 stumpings + 2 catches = 4, first 7 Oct, last 2 Dec",
          (ben.get("stumping"), ben.get("catch"), ben.get("caught_behind"), ben.get("total")) == (2, 2, 0, 4)
          and ben.get("first_played_at", "")[:10] == "2000-10-07" and ben.get("last_played_at", "")[:10] == "2000-12-02",
          str(ben))
    check("Cal: 2 stumpings + 1 caught behind = 3, last 16 Dec",
          (cal.get("stumping"), cal.get("catch"), cal.get("caught_behind"), cal.get("total")) == (2, 0, 1, 3)
          and cal.get("last_played_at", "")[:10] == "2000-12-16", str(cal))
    check("Dan: 2 stumpings, first 5 Feb", (dan.get("stumping"), dan.get("total")) == (2, 2)
          and dan.get("first_played_at", "")[:10] == "2000-02-05", str(dan))
    order = [g.get("bowler_name") for g in d.get("by_bowler") or []]
    check("most dismissals first (Ben 4, Cal 3, Dan 2, Lee 1), then the not-recorded and hidden lines last",
          order[:4] == ["Bowler, Ben", "Quick, Cal", "Spin, Dan", "Late, Lee"] and order[4:] == [None, None], str(order))
    check("the summary adds up to the list",
          sum(g.get("total", 0) for g in d.get("by_bowler") or []) == len(of(d)) == 15,
          str(sum(g.get("total", 0) for g in d.get("by_bowler") or [])))

    print("\n-- HAND-ENTERED AND SYNCED CARDS ARE NEVER COUNTED TWICE --")
    check("M3 is paired to G1 and the synced card wins: its stumping off Ben is not listed",
          not any(r.get("batter_name") == "Double Count" for r in of(d)))
    check("... though it IS on the table (so the check can fail)",
          await raw_count("SELECT count(*) FROM manual_bowler_wickets WHERE batter_name = 'Double Count'") == 1)
    check("G8's club card was chosen: the shown stumping is M4's, not the synced twin's",
          any(r.get("batter_name") == "Chosen Card" for r in of(d)) and not any(r.get("batter_name") == "Synced Twin" for r in of(d)))
    check("... and the synced twin IS on the table",
          await raw_count("SELECT count(*) FROM bowler_wickets WHERE batter_name = 'Synced Twin'") == 1)
    check("a hand-entered game with no grade is listed (it is not dropped by a grade join)",
          ("2000-12-02", "Bowler, Ben", "U Manual") in stumps)
    m2 = next((r for r in of(d, "stumping") if r.get("batter_name") == "U Manual"), {})
    check("and a hand-entered game with blank sides is named from the club and its opposition",
          (m2.get("home_team"), m2.get("away_team")) == (CLUB_NAME, "Rival"), str((m2.get("home_team"), m2.get("away_team"))))

    print("\n-- ONLY THIS CLUB'S GAMES AND PEOPLE --")
    check("another club's game carrying Carmody's name is not his stumping",
          not any(r.get("batter_name") == "Not Our Game" for r in of(d)))
    check("... the row IS in the table for him (so the check can fail)",
          await raw_count("SELECT count(*) FROM v_effective_bowler_wickets WHERE batter_name = 'Not Our Game' AND fielder_id = :p", p=RYAN) == 1)
    check("a Rival CC bowler on a Carmody row is not listed as his bowler",
          not any(r.get("bowler_name") == "Bowler, Rival" for r in of(d)))
    check("... the row IS in the view for him (so the check can fail)",
          await raw_count("SELECT count(*) FROM v_effective_bowler_wickets WHERE batter_name = 'Cross Club' AND fielder_id = :p", p=RYAN) == 1)
    rk = await route(RIVAL_KEEPER)
    check("the other club's keeper has his own stumping from the shared game, off their bowler",
          pairs(rk, "stumping") == [("2000-10-07", "Bowler, Rival", "Our Opener")], str(pairs(rk, "stumping")))
    check("and none of Carmody's rows from the same game", len(of(rk)) == 1, str(len(of(rk))))

    print("\n-- A BOWLER THE CLUB HAS HIDDEN IS NEVER NAMED TO THE PUBLIC --")
    hidden_rows = [r for r in of(d) if r.get("batter_name") == "N Hall"]
    check("the stumping stays on the keeper's list, with the bowler unnamed",
          len(hidden_rows) == 1 and hidden_rows[0].get("bowler_name") is None and hidden_rows[0].get("bowler_id") is None
          and hidden_rows[0].get("bowler_hidden") is True, str(hidden_rows))
    check("Harry's name and id appear nowhere in the public payload",
          "Hidden, Harry" not in repr(d) and str(HARRY) not in repr(d))
    hl = next((g for g in d.get("by_bowler") or [] if g.get("bowler_hidden")), {})
    check("the summary holds him as one unnamed line, still counted", hl.get("total") == 1 and hl.get("bowler_name") is None, str(hl))
    async with Session() as s:
        admin = await s.get(User, ADMIN)
    da = await route(RYAN, viewer=admin)
    check("a signed-in club admin sees Harry named",
          any(r.get("bowler_name") == "Hidden, Harry" for r in of(da)) and not any(r.get("bowler_hidden") for r in of(da)))
    check("the admin's list is otherwise the same fifteen", len(of(da)) == 15, str(len(of(da))))

    print("\n-- WHERE CA'S TEXT NAMES NOBODY, THE FIELDING ROW STILL COUNTS --")
    nb = [r for r in of(d) if r.get("bowler_unknown")]
    by_game = {}
    for r in nb:
        by_game.setdefault(r["game_id"], []).append(r["kind"])
    check("G9 (no pairing rows) adds its 2 stumpings and 1 keeper catch, with no bowler or batter",
          sorted(by_game.get(str(G9), [])) == ["caught_behind", "stumping", "stumping"]
          and all(r["bowler_name"] is None and r["batter_name"] is None for r in nb if r["game_id"] == str(G9)), str(by_game))
    check("G10 (one of two paired) adds only the one missing stumping", by_game.get(str(G10)) == ["stumping"], str(by_game.get(str(G10))))
    check("G10's paired stumping is still there, named, off Lee",
          ("2000-10-28", "Late, Lee", "Z Partial") in stumps)
    check("G1 (fielding row equals its pairings) adds nothing", str(G1) not in by_game, str(by_game.get(str(G1))))
    check("G11 (his own caught-and-bowled counted as a catch) adds nothing, and is not shown as a catch",
          str(G11) not in by_game and not any(r.get("batter_name") == "Own Bowling" for r in of(d)), str(by_game.get(str(G11))))
    check("another club's game (G13) adds nothing, though its fielding row names him",
          str(G13) not in by_game)
    check("... that fielding row IS his and IS in the view (so the check can fail)",
          await raw_count("SELECT COALESCE(SUM(stumpings),0) FROM v_effective_fielding_stats WHERE game_id = :g AND player_id = :p", g=G13, p=RYAN) == 1)
    check("the junior game's fielding row (G12) is out under the club default",
          str(G12) not in by_game)
    ub = next((g for g in d.get("by_bowler") or [] if g.get("bowler_unknown")), {})
    check("the summary holds them as one 'no bowler recorded' line, 3 stumpings 1 keeper catch, no name or id",
          (ub.get("total"), ub.get("stumping"), ub.get("caught_behind")) == (4, 3, 1)
          and ub.get("bowler_name") is None and ub.get("bowler_id") is None, str(ub))
    ordered = [(r.get("played_at") or "", r["game_id"]) for r in of(d)]
    check("the added rows sit in date order among the paired ones", ordered == sorted(ordered), str(ordered[:6]))

    print("\n-- THE PAGE'S OWN FILTERS --")
    dj = await route(RYAN, categories="all")
    check("juniors are out under the club default and in when 'all' is picked",
          not any(r.get("batter_name") == "Junior Opp" for r in of(d)) and any(r.get("batter_name") == "Junior Opp" for r in of(dj))
          and str(G12) in {r["game_id"] for r in of(dj) if r.get("bowler_unknown")},
          str(pairs(dj, "stumping")))
    check("all grade types: 13 stumpings, 17 in all (the junior pairing and the junior fielding row)",
          (dj.get("counts") or {}).get("stumping") == 13 and (dj.get("counts") or {}).get("total") == 17
          and (dj.get("counts") or {}).get("unpaired") == 5, str(dj.get("counts")))
    dt = await route(RYAN, formats="t20")
    check("a T20 pick leaves only G2's two stumpings",
          pairs(dt, "stumping") and {x[2] for x in pairs(dt)} == {"M Green", "N Hall"} and len(of(dt)) == 2, str(pairs(dt)))
    ds = await route(RYAN, season_id=str(S1))
    check("a season pick drops the 1999/00 stumping (10 left; Dan 1)",
          (ds.get("counts") or {}).get("stumping") == 10 and line(ds, "Spin, Dan").get("total") == 1, str(ds.get("counts")))

    print("\n-- A PLAYER WITH NOTHING, AND A BAD ID --")
    de = await route(BEN)
    check("a player who never took a catch or stumping gets an empty list, not an error",
          de.get("rows") == [] and de.get("by_bowler") == [] and (de.get("counts") or {}).get("total") == 0, str(de.get("counts")))
    for label, pid in (("an unknown player", uuid.uuid4()), ("a malformed id", "not-a-uuid")):
        try:
            await route(pid)
            ok, status = False, None
        except HTTPException as e:
            ok, status = e.status_code == 404, e.status_code
        check(f"{label} is a 404", ok, str(status))

    print(f"\n{b.PASS} passed, {b.FAIL} failed")
    await b.engine.dispose()
    sys.exit(1 if b.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
