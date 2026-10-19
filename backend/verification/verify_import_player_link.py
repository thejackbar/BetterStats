"""Initial-only players an import created are joined to the synced player they are,
on paired-match evidence and nothing else. Real Postgres, the shipped service and the
club's own merge.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/pl_verify?host=/var/run/postgresql \
      python verification/verify_import_player_link.py

Controls (each must FAIL the checks it is named for):
  CONTROL=1   the behaviour before this change: nothing joins an import player.
  MUTATE=1    the evidence ignores runs and batting position, so any same-label
              player in a paired match counts.
  MUTATE=bowl the unique-figures guard on bowling spells is removed.
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

from sqlalchemy import text  # noqa: E402

PASS = FAIL = 0


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


def u():
    return uuid.uuid4()


async def main():
    from app.models.db import (
        Base, BattingInnings, Game, Grade, ManualBattingInnings, ManualGame, Organisation,
        Player, Season, engine, async_session_maker,
        BowlingSpell, ManualBowlingSpell, BowlerWicket,
    )
    from app.services import import_player_link as ipl
    from app.routers.admin import undo_merge, UndoMergeRequest
    from verify_merge_carry import EXTRA_DDL

    if os.environ.get("CONTROL"):
        async def _nothing(org_id, *, apply=False, min_evidence=1, limit=None):
            return {"initial_only": 0, "found": 0, "merged": 0, "failed": 0, "pairs": [], "held": []}
        ipl.link_players = _nothing
    if os.environ.get("MUTATE") == "bowl":
        # the unique-figures guard on bowling spells removed
        ipl._EVIDENCE_SQL = ipl._EVIDENCE_SQL.replace(") = 1", ") >= 1")
    elif os.environ.get("MUTATE"):
        ipl._EVIDENCE_SQL = ipl._EVIDENCE_SQL.replace(
            "AND bi.runs = mbi.runs\n              AND bi.batting_position IS NOT DISTINCT FROM mbi.batting_position",
            "AND TRUE")

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        for stmt in EXTRA_DDL:
            await conn.execute(text(stmt))
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS merge_pair_ignores (
            id SERIAL PRIMARY KEY, org_id UUID NOT NULL, player_a_id UUID NOT NULL,
            player_b_id UUID NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (org_id, player_a_id, player_b_id))"""))

    org, other = u(), u()
    season, grade = u(), u()
    P: dict = {}

    def pid(k):
        return P.setdefault(k, u())

    async with async_session_maker() as db:
        db.add_all([Organisation(id=org, name="Payneham", slug="pay-v", is_active=True),
                    Organisation(id=other, name="Elsewhere", slug="else-v", is_active=True),
                    Season(id=season, organisation_id=org, name="Summer 2010/11", year=2010,
                           import_authoritative=True)])
        await db.flush()
        db.add(Grade(id=grade, season_id=season, name="1st XI"))
        await db.flush()

        def synced(k, name, o=None):
            db.add(Player(id=pid(k), organisation_id=o or org, name=name, grassroots_id=str(pid(k))))

        def imported(k, name, **kw):
            db.add(Player(id=pid(k), organisation_id=org, name=name, **kw))

        synced("Ysol", "Milne, Solomon"); imported("Xsol", "Milne, SA")
        synced("Yand", "Belsak, Andrew"); imported("Xand", "Belsak, AJ")
        synced("Yjohn", "Smith, John"); synced("Yjames", "Smith, James"); imported("Xsmith", "Smith, J")
        synced("Yrob", "Westley, Robert"); imported("Xw1", "Westley, R"); imported("Xw2", "Westley, RHJ")
        synced("Ycam", "Young, Cameron"); synced("Ycoo", "Young, Cooper"); imported("Xyoung", "Young, CS")
        imported("Xnone", "Nobody, Q")
        synced("Yother", "Different, Dan"); imported("Xname", "Nameless, A")
        synced("Ynob", "Nobody, Quinn"); synced("Ypos", "Posn, Pat"); imported("Xpos", "Posn, P")
        imported("Xhq", "Hq, H", playhq_id="phq-1"); synced("Yhq", "Hq, Harry")
        synced("Yforeign", "Foreign, Fred", o=other); imported("Xforeign", "Foreign, F")
        synced("Yign", "Ignored, Ian"); imported("Xign", "Ignored, I")
        synced("Ysing", "Single, Sam"); imported("Xsing", "Single, S")
        synced("Yunp", "Unpaired, Ulf"); imported("Xunp", "Unpaired, U")
        synced("Ydnb", "Dnb, Dee"); imported("Xdnb", "Dnb, D")
        synced("Yzap", "Zappia, Matthew"); imported("Xzap", "Zappia, MA")
        # bowlers: players a batting line can never prove
        synced("Ybow", "Bowler, Paul"); imported("Xbow", "Bowler, P")
        synced("Ytwa", "Twina, Alan"); imported("Xtwa", "Twina, A")
        synced("Ytwb", "Twinb, Bob"); imported("Xtwb", "Twinb, B")
        synced("Ybad", "Badfig, Bill"); imported("Xbad", "Badfig, B")
        synced("Ybun", "Bowlunp, Bert"); imported("Xbun", "Bowlunp, B")
        # label clashes: initials that cannot be one man, and initials that could
        synced("Ycr", "Crou, Angus"); imported("Xag", "Crou, AG"); imported("Xad", "Crou, AD")
        synced("Ypr", "Pref, Angus"); imported("Xpa", "Pref, AG"); imported("Xpb", "Pref, A")
        # the wickets as proof: a bowler whose figures differ by a run on the two cards
        synced("Yb1", "Batter, One"); synced("Yb2", "Batter, Two"); synced("Yo", "Other, Olly")
        synced("Yel", "Elim, Eric"); imported("Xel", "Elim, E")
        await db.flush()

        n = [0]

        def pair(rows, paired=True):
            """One synced game and one manual game. rows: (X key, Y key, runs, pos,
            manual runs, manual pos, manual did_not_bat)."""
            n[0] += 1
            g, m = u(), u()
            db.add(Game(id=g, grade_id=grade, played_at=date(2010, 10, n[0]), home_team="A",
                        away_team="B", status="COMPLETED"))
            return g, m

        async def match(rows, *, paired=True):
            g, m = pair(rows, paired)
            await db.flush()
            db.add(ManualGame(id=m, organisation_id=org, season_id=season, grade_id=grade,
                              played_at=date(2010, 10, n[0]), opposition="Opp",
                              superseded_by_game_id=g if paired else None,
                              pair_prefers_import=paired, pairing_locked=paired))
            await db.flush()
            for xk, yk, runs, pos, mruns, mpos, dnb in rows:
                db.add(BattingInnings(game_id=g, player_id=P[yk], innings_number=1, runs=runs,
                                      batting_position=pos, not_out=False, did_not_bat=False))
                db.add(ManualBattingInnings(manual_game_id=m, player_id=P[xk], innings_number=1,
                                            runs=mruns, batting_position=mpos, did_not_bat=dnb))
            await db.flush()
            return m

        # A: two players line up in one match; the third match for Xsol repeats it
        await match([("Xsol", "Ysol", 42, 3, 42, 3, False), ("Xand", "Yand", 7, 5, 7, 5, False)])
        await match([("Xsol", "Ysol", 15, 4, 15, 4, False)])
        # Smith, J is John in the evidence, but the club also has a James Smith
        await match([("Xsmith", "Yjohn", 30, 2, 30, 2, False)])
        # Westley under two labels, one synced man
        await match([("Xw1", "Yrob", 12, 6, 12, 6, False)])
        await match([("Xw2", "Yrob", 80, 1, 80, 1, False)])
        # Young, CS lines up with Cameron in one match and Cooper in another
        await match([("Xyoung", "Ycam", 5, 7, 5, 7, False)])
        await match([("Xyoung", "Ycoo", 9, 8, 9, 8, False)])
        # same runs and position but a different surname: not the same label
        await match([("Xname", "Yother", 11, 9, 11, 9, False)])
        # runs disagree: no evidence
        await match([("Xnone", "Ynob", 20, 10, 21, 10, False)])
        # runs agree but the batting position does not: no evidence
        await match([("Xpos", "Ypos", 40, 3, 40, 4, False)])
        # a record with a PlayHQ id is not an import's
        await match([("Xhq", "Yhq", 33, 2, 33, 2, False)])
        # the synced twin belongs to another club
        await match([("Xforeign", "Yforeign", 18, 3, 18, 3, False)])
        # the club said these two are different people
        await match([("Xign", "Yign", 25, 4, 25, 4, False)])
        # one agreeing match only
        m_single = await match([("Xsing", "Ysing", 61, 1, 61, 1, False)])
        # the import's match is not paired: no evidence
        await match([("Xunp", "Yunp", 14, 2, 14, 2, False)], paired=False)
        # the import row is a did-not-bat: no evidence
        await match([("Xdnb", "Ydnb", 0, None, 0, None, True)])
        # two initials
        await match([("Xzap", "Yzap", 52, 1, 52, 1, False)])

        async def spells(m, rows, synced_rows=None):
            g = (await db.get(ManualGame, m)).superseded_by_game_id
            for xk, yk, ov, ru, wk in rows:
                db.add(ManualBowlingSpell(manual_game_id=m, player_id=P[xk], innings_number=1,
                                          overs=ov, runs=ru, wickets=wk))
            for xk, yk, ov, ru, wk in (synced_rows or rows):
                db.add(BowlingSpell(game_id=g, player_id=P[yk], innings_number=1,
                                    overs=ov, runs=ru, wickets=wk))
            await db.flush()

        # a bowler who never batted: one spell with the same figures on both cards
        await spells(await match([]), [("Xbow", "Ybow", 5.0, 20, 2)])
        # two of our bowlers with identical figures: whose is whose is a coin toss
        await spells(await match([]), [("Xtwa", "Ytwa", 4.0, 20, 1), ("Xtwb", "Ytwb", 4.0, 20, 1)])
        # the figures differ by a run: not the same spell
        await spells(await match([]), [("Xbad", "Ybad", 4.0, 20, 1)],
                     [("Xbad", "Ybad", 4.0, 21, 1)])
        # a bowling match the import did not pair
        await spells(await match([], paired=False), [("Xbun", "Ybun", 6.0, 30, 3)])
        # the SAME match proved by a batting line and a spell counts once
        await spells(m_single, [("Xsing", "Ysing", 3.0, 12, 0)])
        # THE POINT OF ALL THIS: an import match the override never paired because
        # its players were not the synced players. Four batters on one card, the
        # opposition spelt two ways, the dates four days apart.
        mu, gu = u(), u()
        db.add(Game(id=gu, grade_id=grade, played_at=date(2010, 11, 20), home_team="Payneham",
                    away_team="PAOC", opp_club_name="PAOC", status="COMPLETED"))
        await db.flush()
        db.add(ManualGame(id=mu, organisation_id=org, season_id=season, grade_id=grade,
                          played_at=date(2010, 11, 16), opposition="P A O C"))
        await db.flush()
        for xk, yk, runs, pos in (("Xsol", "Ysol", 71, 1), ("Xand", "Yand", 33, 2),
                                  ("Xw1", "Yrob", 19, 3), ("Xzap", "Yzap", 8, 4)):
            db.add(BattingInnings(game_id=gu, player_id=P[yk], innings_number=1, runs=runs,
                                  batting_position=pos, not_out=False, did_not_bat=False))
            db.add(ManualBattingInnings(manual_game_id=mu, player_id=P[xk], innings_number=1,
                                        runs=runs, batting_position=pos, did_not_bat=False))
        # initials that cannot be one man do not make the label shared; ones that could do
        await match([("Xag", "Ycr", 36, 2, 36, 2, False)])
        await match([("Xpa", "Ypr", 44, 3, 44, 3, False)])
        # the wickets prove it: batters agree (so the pair is confirmed), every bowler's
        # figures agree except Elim's, whose runs differ by one between the cards
        m_el = await match([("Yb1", "Yb1", 21, 1, 21, 1, False), ("Yb2", "Yb2", 14, 2, 14, 2, False)])
        await spells(m_el, [("Xel", "Yel", 3.0, 15, 1), ("Yo", "Yo", 4.0, 20, 2)],
                     [("Xel", "Yel", 3.0, 16, 1), ("Yo", "Yo", 4.0, 20, 2)])
        g_el = (await db.get(ManualGame, m_el)).superseded_by_game_id
        for who, kind in (("Yel", "bowled"), ("Yo", "caught"), ("Yo", "lbw")):
            db.add(BowlerWicket(game_id=g_el, innings_number=2, bowler_id=P[who],
                                batter_name="Opp", dismissal_type=kind))
        await db.flush()
        await db.execute(text("""INSERT INTO manual_edit_logs
            (organisation_id, action, target_table, target_id, after_json)
            VALUES (:o, 'import', 'manual_games', 'x', CAST(:j AS JSONB))"""),
            {"o": org, "j": '{"created_game_ids": ["%s"]}' % m_el})
        await db.execute(text("""INSERT INTO manual_edit_logs
            (organisation_id, action, target_table, target_id, after_json)
            VALUES (:o, 'import', 'manual_games', 'x', CAST(:j AS JSONB))"""),
            {"o": org, "j": '{"created_game_ids": ["%s"]}' % mu})
        await db.commit()
        await db.execute(text("INSERT INTO merge_pair_ignores (org_id, player_a_id, player_b_id) "
                              "VALUES (:o, :a, :b)"), {"o": org, "a": P["Xign"], "b": P["Yign"]})
        await db.commit()

    async def one(sql, **kw):
        async with async_session_maker() as db:
            return (await db.execute(text(sql), kw)).scalar()

    async def exists(k):
        return bool(await one("SELECT count(*) FROM players WHERE id = :p", p=P[k]))

    # ── the plan, from the database, with nothing written ────────────────────
    dry = await ipl.link_players(org, apply=False)
    want_merge = {"Xsol": "Ysol", "Xand": "Yand", "Xw1": "Yrob", "Xw2": "Yrob",
                  "Xsing": "Ysing", "Xzap": "Yzap", "Xbow": "Ybow",
                  "Xag": "Ycr", "Xel": "Yel"}
    got_merge = {p["remove"]: p["keep"] for p in dry["pairs"]}
    check("a dry run lists exactly the pairs the evidence proves",
          got_merge, {str(P[k]): str(P[v]) for k, v in want_merge.items()})
    check("a dry run changes nothing",
          [await exists(k) for k in want_merge], [True] * len(want_merge))
    check("the evidence count is the number of agreeing matches (the unpaired match is not one)",
          {p["remove_name"]: p["matches"] for p in dry["pairs"]}.get("Milne, SA"), 2)
    held = {h["remove_name"]: h["why"] for h in dry["held"]}
    check("a label another club player shares is held, not merged",
          held.get("Smith, J"), ipl.SHARED_NAME)
    check("a record lining up with two synced players is held",
          held.get("Young, CS"), ipl.MANY_CANDIDATES)
    check("a different surname is no evidence", held.get("Nameless, A"), ipl.NO_EVIDENCE)
    check("different runs are no evidence", held.get("Nobody, Q"), ipl.NO_EVIDENCE)
    check("a different batting position is no evidence", held.get("Posn, P"), ipl.NO_EVIDENCE)
    check("a match the import did not pair is no evidence", held.get("Unpaired, U"), ipl.NO_EVIDENCE)
    check("a did-not-bat row is no evidence", held.get("Dnb, D"), ipl.NO_EVIDENCE)
    check("another club's player is never evidence", held.get("Foreign, F"), ipl.NO_EVIDENCE)
    check("a record with a PlayHQ id is not a candidate",
          "Hq, H" not in held and str(P["Xhq"]) not in got_merge)
    check("a pair the club chose to keep apart is not merged", str(P["Xign"]) not in got_merge)
    check("initials that cannot be one man ('Crou, AD' beside 'Crou, AG') do not block the join",
          got_merge.get(str(P["Xag"])), str(P["Ycr"]))
    check("the other record is left, with no evidence of its own", held.get("Crou, AD"), ipl.NO_EVIDENCE)
    check("initials that could be one man ('Pref, A' beside 'Pref, AG') still make the label shared",
          held.get("Pref, AG"), ipl.SHARED_NAME)
    check("a bowler whose figures differ by a run is joined on the wickets: everything else on "
          "the card agreed and one credited bowler and one import bowler were left",
          got_merge.get(str(P["Xel"])), str(P["Yel"]))
    check("a player who only ever bowled is joined on his bowling figures",
          got_merge.get(str(P["Xbow"])), str(P["Ybow"]))
    check("two bowlers with identical figures in one match are not evidence for either",
          (held.get("Twina, A"), held.get("Twinb, B")), (ipl.NO_EVIDENCE, ipl.NO_EVIDENCE))
    check("figures that differ by a run are not the same spell", held.get("Badfig, B"), ipl.NO_EVIDENCE)
    check("a bowling match the import did not pair is not evidence", held.get("Bowlunp, B"), ipl.NO_EVIDENCE)

    one_only = await ipl.link_players(org, apply=False, min_evidence=2)
    check("asking for two agreeing matches holds the single-match player",
          ({p["remove_name"] for p in one_only["pairs"]} >= {"Milne, SA"},
           "Single, S" in {p["remove_name"] for p in one_only["pairs"]}), (True, False))

    from app.scripts import repair_overwrite_pairs as rop

    async def repair_dry():
        async with async_session_maker() as db:
            return await rop.repair_org(db, org, apply=False)

    before = await repair_dry()
    check("before the join, the pairing script cannot see the unpaired import match",
          (before["candidates"], before["paired"]), (1, 0))

    # a thin sibling label joining the same man does not block the strong one
    pl = [dict(id="y", name="Ansell, Chris", removable=False, synced=True),
          dict(id="x1", name="Ansell, C", removable=True, synced=False),
          dict(id="x2", name="Ansell, CI", removable=True, synced=False)]
    ev = [dict(x_id="x1", y_id="y", matches=1), dict(x_id="x2", y_id="y", matches=93)]
    sib = ipl.plan_from(pl, ev, set(), min_evidence=3)
    check("a sibling label with thin evidence joining the same man does not block the strong one",
          ([m["remove"] for m in sib["merge"]], [(h["remove"], h["why"]) for h in sib["held"]]),
          (["x2"], [("x1", ipl.TOO_FEW)]))
    two = ipl.plan_from(pl, ev, set(), min_evidence=1)
    check("with no minimum both labels join", sorted(m["remove"] for m in two["merge"]), ["x1", "x2"])

    # ── apply ────────────────────────────────────────────────────────────────
    res = await ipl.link_players(org, apply=True)
    check("apply merges every proven pair", (res["merged"], res["failed"]), (len(want_merge), 0))
    check("each removed record is gone and the synced one kept",
          [(await exists(k), await exists(v)) for k, v in want_merge.items()],
          [(False, True)] * len(want_merge))
    check("their manual innings followed the person onto the synced record",
          await one("SELECT count(*) FROM manual_batting_innings WHERE player_id = :p", p=P["Ysol"]), 3)
    check("nothing is left on the removed record",
          await one("SELECT count(*) FROM manual_batting_innings WHERE player_id = :p", p=P["Xsol"]), 0)
    check("two labels of one man both land on the one synced record",
          await one("SELECT count(*) FROM manual_batting_innings WHERE player_id = :p", p=P["Yrob"]), 3)
    check("every merge is in the merge log, not undone",
          await one("SELECT count(*) FROM merge_logs WHERE org_id = :o AND undone_at IS NULL", o=org),
          len(want_merge))
    check("each merge has an audit entry saying why",
          await one("SELECT count(*) FROM audit_logs WHERE org_id = :o AND action = 'auto_merge_import_player'",
                    o=org), len(want_merge))
    for k in ("Xsmith", "Xyoung", "Xname", "Xnone", "Xpos", "Xhq", "Xforeign", "Xign", "Xunp", "Xdnb"):
        check(f"left alone: {k}", await exists(k), True)
    check("a synced record of another club is untouched", await exists("Yforeign"), True)
    check("the synced games' own innings are untouched",
          await one("SELECT count(*) FROM batting_innings WHERE player_id = :p", p=P["Ysol"]), 3)
    after = await repair_dry()
    check("after the join, the same script pairs it on its scorecard",
          (after["candidates"], after["paired"], after["pairs"][0]["shared_scores"] if after["pairs"] else None),
          (1, 1, 4))
    # the pairing script can be told to leave a pair a person does not believe
    async def repair_skip(skip):
        async with async_session_maker() as db:
            return await rop.repair_org(db, org, apply=False, skip=skip)

    unpaired_id = after["pairs"][0]["manual_game_id"] if after["pairs"] else None
    sk = await repair_skip([str(unpaired_id)[:8]])
    check("--skip by the id the dry run prints leaves that pair unpaired and says so",
          (sk["paired"], len(sk["skipped"])), (0, 1))
    check("a skip shorter than six characters matches nothing",
          (await repair_skip([str(unpaired_id)[:3]]))["paired"], 1)

    again = await ipl.link_players(org, apply=True)
    check("a second run finds nothing to merge", (again["found"], again["merged"]), (0, 0))

    # ── undoable from the merge log ──────────────────────────────────────────
    log_id = await one("SELECT id FROM merge_logs WHERE org_id = :o AND removed_player_id = :r",
                       o=org, r=P["Xsol"])
    check("there is a merge to undo", log_id is not None)
    if log_id is not None:
        async with async_session_maker() as db:
            class _U:
                id = uuid.uuid4()
                username = "verifier"
            await undo_merge(UndoMergeRequest(merge_log_id=log_id, org_id=str(org)), db, _U())
    check("undo brings the import record back", await exists("Xsol"), True)
    check("undo puts its manual innings back on it",
          await one("SELECT count(*) FROM manual_batting_innings WHERE player_id = :p", p=P["Xsol"]), 3)

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
