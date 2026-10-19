"""Card review: a match stored twice (synced Cricket Australia card + the club's own card) is
compared, grouped, switched between three ways, copied into, undone and bulk-switched, all
against a real Postgres through the shipped services.

Run:  DATABASE_URL=postgresql+asyncpg://root@/pl_verify?host=/var/run/postgresql \
      python verification/verify_card_review.py

Mutations (each must make the suite FAIL, which is what proves the checks bite):
  MUTATE=balls   the combined copy also copies balls faced where the batter's runs differ
  MUTATE=hand    the bulk switch ignores a choice a person made by hand
  MUTATE=undo    undo puts the flags back but leaves the copied rows behind
  MUTATE=lock    a choice does not lock the pairing
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
    from app.models.db import Base, engine, async_session_maker
    from app.services import card_review as cr
    from app.services import card_review_actions as act
    from app.services import card_review_hybrid as hy
    from app.services.card_review_ddl import STATEMENTS as REVIEW_DDL
    from app.services.superseded_ddl import STATEMENTS as SUPERSEDED_DDL
    from app.services.competition_ddl import STATEMENTS as COMP_DDL
    from _view_ddl import view_statements
    from verify_merge_carry import EXTRA_DDL

    mutate = os.environ.get("MUTATE", "")
    if mutate == "balls":
        real_plan = hy.plan_hybrid

        async def plan_balls(db, org_id, mid):
            plan = await real_plan(db, org_id, mid)
            # also copy balls for every club row with no balls, whatever the runs
            rows = (await db.execute(text(
                "SELECT mb.id, bi.balls FROM manual_batting_innings mb "
                "JOIN manual_games mg ON mg.id = mb.manual_game_id "
                "JOIN batting_innings bi ON bi.game_id = mg.superseded_by_game_id AND bi.player_id = mb.player_id "
                "WHERE mb.manual_game_id = CAST(:m AS UUID) AND mb.balls IS NULL AND bi.balls > 0"),
                {"m": str(mid)})).all()
            plan["balls"] = [(r[0], r[1]) for r in rows]
            return plan
        hy.plan_hybrid = plan_balls
    if mutate == "hand":
        cr_cand = act.bulk_candidates
        act.bulk_candidates = lambda rows: [r for r in rows if r["group"] == "agree" and r["current"] != "ca"]
    if mutate == "lock":
        real_set = act.set_choice

        async def set_nolock(db, org_id, mid, choice, user_id, **kw):
            res = await real_set(db, org_id, mid, choice, user_id, **kw)
            await db.execute(text("UPDATE manual_games SET pairing_locked = FALSE WHERE id = CAST(:m AS UUID)"),
                             {"m": str(mid)})
            await db.commit()
            return res
        act.set_choice = set_nolock
    if mutate == "undo":
        async def no_revert(db, mid):
            return {}
        act._revert_inserted = no_revert

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        for stmt in COMP_DDL:
            await conn.execute(text(stmt))
        for stmt in EXTRA_DDL:
            await conn.execute(text(stmt))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_manual_games_superseded_by_game "
            "ON manual_games (superseded_by_game_id) WHERE superseded_by_game_id IS NOT NULL"))
        for stmt in REVIEW_DDL:
            await conn.execute(text(stmt))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)"""))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)"""))
        for tbl, col in (await conn.execute(text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND data_type = 'json'"))).all():
            await conn.execute(text(f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb '
                                    f'USING "{col}"::text::jsonb'))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))
        for stmt in SUPERSEDED_DDL:
            await conn.execute(text(stmt))

    ORG, OPP, SEASON, GRADE, USER, USER2 = u(), u(), u(), u(), u(), u()
    ours = {k: u() for k in ("Ortega", "Raman", "Karim", "Wen", "Pike", "Tran", "Cole", "Park",
                             "Quinn", "Reid", "Soto", "SmithR", "SmithRG")}
    theirs = {k: u() for k in ("Hale", "Shaw", "Moss", "Dunn", "Nair", "Rowe")}
    given = {"Ortega": "Sam", "Raman": "Dev", "Karim": "Ali", "Wen": "Chris", "Pike": "Jordan",
             "Tran": "Lee", "Cole": "Hal", "Park": "Mal", "Quinn": "Quin", "Reid": "Rex", "Soto": "Sid",
             "SmithR": "Reuben", "SmithRG": "RG"}

    async def ex(sql, **kw):
        async with async_session_maker() as s:
            res = await s.execute(text(sql), kw)
            await s.commit()
            return res

    async def q(sql, **kw):
        async with async_session_maker() as s:
            return (await s.execute(text(sql), kw)).all()

    async with async_session_maker() as s:
        await s.execute(text("INSERT INTO organisations (id, name, slug, is_active) VALUES "
                             "(:a, 'Payneham', 'pay', true), (:b, 'Eastlake', 'east', true)"), {"a": ORG, "b": OPP})
        await s.execute(text("INSERT INTO seasons (id, organisation_id, name, year) VALUES "
                             "(:i, :o, 'Summer 2025/26', 2025)"), {"i": SEASON, "o": ORG})
        await s.execute(text("INSERT INTO grades (id, season_id, name) VALUES (:i, :s, '1st XI')"),
                        {"i": GRADE, "s": SEASON})
        for k, pid in ours.items():
            nm = f"Smith, {given[k]}" if k.startswith("Smith") else f"{k}, {given[k]}"
            await s.execute(text("INSERT INTO players (id, organisation_id, name, grassroots_id) "
                                 "VALUES (:i, :o, :n, :g)"), {"i": pid, "o": ORG, "n": nm, "g": str(pid)})
        for k, pid in theirs.items():
            await s.execute(text("INSERT INTO players (id, organisation_id, name, grassroots_id) "
                                 "VALUES (:i, :o, :n, :g)"), {"i": pid, "o": OPP, "n": f"{k}, {k[0]}", "g": str(pid)})
        for uid, name in ((USER, "neil"), (USER2, "jack")):
            await s.execute(text("INSERT INTO users (id, username, password_hash, failed_login_count) "
                                 "VALUES (:i, :n, 'x', 0)"), {"i": uid, "n": name})
        await s.commit()

    ids: dict = {}

    async def make(key, *, day=date(2026, 3, 21), g_day=None, club_bat, ca_bat, club_bowl=(), ca_bowl=(),
                   club_result="WIN", ca_winner="Payneham", totals=None, club_inn=None, club_only=False):
        """One match stored twice. `club_bat` / `ca_bat`: (player, runs, pos, how_out, balls, innings)."""
        gid, mid = u(), u()
        ids[key] = (mid, gid)
        async with async_session_maker() as s:
            await s.execute(text("""
                INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_org_id, away_org_id,
                                   opp_club_name, status, result, winning_team, innings_totals)
                VALUES (:g, :gr, :d, 'Payneham', 'Eastlake', :o, :x, 'Eastlake', 'COMPLETED', 'WIN', :w,
                        CAST(:t AS JSONB))"""),
                {"g": gid, "gr": GRADE, "d": g_day or day, "o": ORG, "x": OPP, "w": ca_winner,
                 "t": __import__("json").dumps(totals) if totals else None})
            await s.execute(text("""
                INSERT INTO manual_games (id, organisation_id, season_id, grade_id, played_at, opposition,
                                          result, superseded_by_game_id, pair_prefers_import, pairing_locked)
                VALUES (:m, :o, :s, :gr, :d, 'Eastlake', :r, :g, TRUE, TRUE)"""),
                {"m": mid, "o": ORG, "s": SEASON, "gr": GRADE, "d": day, "r": club_result, "g": gid})
            for who, runs, pos, how, balls, inn in club_bat:
                await s.execute(text("""
                    INSERT INTO manual_batting_innings (manual_game_id, player_id, innings_number, batting_position,
                        runs, balls, dismissal_type, not_out, did_not_bat)
                    VALUES (:m, :p, :i, :pos, :r, :b, :h, :no, FALSE)"""),
                    {"m": mid, "p": ours[who], "i": inn, "pos": pos, "r": runs, "b": balls, "h": how,
                     "no": how == "not out"})
            for who, runs, pos, how, balls, inn in ca_bat:
                await s.execute(text("""
                    INSERT INTO batting_innings (game_id, player_id, innings_number, batting_position, runs, balls,
                        fours, sixes, dismissal_type, not_out, did_not_bat)
                    VALUES (:g, :p, :i, :pos, :r, :b, 1, 0, :h, :no, FALSE)"""),
                    {"g": gid, "p": ours[who], "i": inn, "pos": pos, "r": runs, "b": balls, "h": how,
                     "no": how == "not out"})
            for who, wk, rc, inn in club_bowl:
                await s.execute(text("INSERT INTO manual_bowling_spells (manual_game_id, player_id, innings_number, "
                                     "overs, runs, wickets) VALUES (:m, :p, :i, 8, :r, :w)"),
                                {"m": mid, "p": ours[who], "i": inn, "r": rc, "w": wk})
            for who, wk, rc, inn in ca_bowl:
                await s.execute(text("INSERT INTO bowling_spells (game_id, player_id, innings_number, overs, "
                                     "runs, wickets) VALUES (:g, :p, :i, 8, :r, :w)"),
                                {"g": gid, "p": ours[who], "i": inn, "r": rc, "w": wk})
            if club_inn:
                for n, side, total, extras in club_inn:
                    await s.execute(text("INSERT INTO manual_innings (manual_game_id, innings_number, batting_side, "
                                         "total_runs, extras_total) VALUES (:m, :n, :s, :t, :e)"),
                                    {"m": mid, "n": n, "s": side, "t": total, "e": extras})
            await s.commit()
        return mid, gid

    six = [("Ortega", 28, 1, "c", None, 1), ("Raman", 2, 2, "b", None, 1), ("Karim", 13, 3, "c", None, 1),
           ("Wen", 15, 4, "lbw", None, 1), ("Pike", 35, 5, "c", None, 1), ("Tran", 3, 6, "run out", None, 1)]
    six_ca = [(w, r, p, h, 10 + i * 7, i_) for i, (w, r, p, h, _b, i_) in enumerate(six)]
    caps = [("Ortega", "caught"), ("Raman", "bowled"), ("Karim", "caught"), ("Wen", "lbw"),
            ("Pike", "caught"), ("Tran", "run out")]
    six_ca = [(w, r, p, hd, b, i_) for (w, r, p, _h, b, i_), (_, hd) in zip(six_ca, caps)]

    # --- the matches ------------------------------------------------------------------------
    await make("agree", club_bat=six, ca_bat=six_ca, club_bowl=[("Cole", 3, 40, 2)], ca_bowl=[("Cole", 3, 40, 2)])
    await make("small_date", day=date(2026, 3, 14), g_day=date(2026, 3, 15), club_bat=six, ca_bat=six_ca)
    await make("small_bowl", day=date(2026, 3, 7), club_bat=six, ca_bat=six_ca,
               club_bowl=[("Cole", 3, 40, 2)], ca_bowl=[("Cole", 2, 40, 2)])
    pike36 = [(w, 36 if w == "Pike" else r, p, h, b, i_) for (w, r, p, h, b, i_) in six_ca]
    await make("differ", day=date(2026, 2, 28), club_bat=six, ca_bat=pike36)
    await make("flip", day=date(2026, 2, 21), club_bat=six, ca_bat=six_ca, club_result="LOSS")
    other = [(w, r + 40, p, h, b, i_) for (w, r, p, h, b, i_) in six_ca]
    await make("pairing", day=date(2026, 2, 14), club_bat=six, ca_bat=other)
    await make("nocard", day=date(2026, 2, 7), club_bat=six, ca_bat=[])
    # a match with enough detail to test the combined copy
    totals = [{"innings_number": 1, "runs_scored": 111, "wickets": 6, "extras": 5},
              {"innings_number": 2, "runs_scored": 160, "wickets": 8, "extras": 9}]
    await make("hybrid", day=date(2026, 1, 31), club_bat=six, ca_bat=pike36, totals=totals,
               club_bowl=[("Cole", 3, 60, 2), ("Park", 3, 40, 2)],
               ca_bowl=[("Cole", 3, 60, 2), ("Park", 2, 40, 2)])
    # CA detail rows for the hybrid match
    _, hg = ids["hybrid"]
    async with async_session_maker() as s:
        for k, (who, kind, bw, fl) in enumerate([("Hale", "caught", "Cole", "Park"), ("Shaw", "bowled", "Cole", None),
                                                  ("Moss", "lbw", "Cole", None), ("Dunn", "caught", "Park", "Cole"),
                                                  ("Nair", "bowled", "Park", None)]):
            await s.execute(text("""INSERT INTO bowler_wickets (game_id, innings_number, bowler_id, fielder_id,
                batter_name, batter_position, batter_runs, dismissal_type, caught_behind)
                VALUES (:g, 2, :b, :f, :n, :pos, 10, :t, FALSE)"""),
                {"g": hg, "b": ours[bw], "f": ours[fl] if fl else None, "n": who, "pos": k + 1, "t": kind})
        for w, sc in ((1, 20), (2, 30), (3, 55), (4, 70), (5, 90)):
            await s.execute(text("INSERT INTO fall_of_wickets (game_id, innings_number, wicket_number, score_at_fall, "
                                 "batter_name) VALUES (:g, 1, :w, :s, 'x')"), {"g": hg, "w": w, "s": sc})
            await s.execute(text("INSERT INTO fall_of_wickets (game_id, innings_number, wicket_number, score_at_fall, "
                                 "batter_name) VALUES (:g, 2, :w, :s, 'y')"), {"g": hg, "w": w, "s": sc + 5})
            await s.execute(text("INSERT INTO partnerships (game_id, innings_number, wicket_number, runs, "
                                 "is_club_innings) VALUES (:g, 2, :w, 20, FALSE)"), {"g": hg, "w": w})
        await s.commit()
    # the live card Cricket Australia would give for the hybrid match (stubbed: no network here)
    live_card = {
        "batting": [{"innings_number": 1, "player_id": str(ours["Ortega"]), "dismissal_type": "c R Hale b K Moss"},
                    {"innings_number": 1, "player_id": str(ours["Pike"]), "dismissal_type": "c R Hale b M Park"},
                    {"innings_number": 1, "player_id": str(ours["Raman"]), "dismissal_type": "b"}],
        "opp_batting": [{"innings_number": 2, "player_name": "R Hale", "runs": 31, "balls": 49,
                         "dismissal_type": "c S Ortega b A Nair", "not_out": False, "did_not_bat": False,
                         "batting_position": 1}],
        "opp_bowling": [{"innings_number": 1, "player_name": "K Moss", "overs": 8, "maidens": 1, "runs": 30,
                         "wickets": 2}],
        "innings_totals": {"1": {"runs": 106, "wickets": 6, "extras": 5},
                           "2": {"runs": 151, "wickets": 8, "extras": 9, "batting_team": "Eastlake"}},
    }
    live_state = {"card": live_card}

    async def fake_card(db, gid):
        return live_state["card"]
    hy._ca_card = fake_card

    async def review():
        async with async_session_maker() as s:
            return {r["match_id"]: r for r in await cr.review_rows(s, ORG)}

    # --- grouping -----------------------------------------------------------------------------
    print("\n-- every paired match lands in one group, with its differences listed --")
    rows = await review()
    g = {k: rows[str(ids[k][0])] for k in ids}
    check("identical cards agree", g["agree"]["group"], "agree")
    check("a date a day apart is a small difference", (g["small_date"]["group"], g["small_date"]["headline"]),
          ("small", "Date 2026-03-15 v 2026-03-14"))
    check("a bowler's wickets differing is small, because the batting agrees", g["small_bowl"]["group"], "small")
    check("one batter's runs differing needs a decision", g["differ"]["group"], "differ")
    check("and says which batter and what each card has",
          g["differ"]["headline"], "Pike, Jordan, runs 36 v 35")
    check("a win on one card and a loss on the other needs a decision", g["flip"]["group"], "differ")
    check("cards sharing too few scores are a pairing problem", g["pairing"]["group"], "pairing")
    check("no Cricket Australia card of ours means nothing to compare", g["nocard"]["group"], "nocard")
    check("how a dismissal is spelled is not a difference (caught against c)",
          [i for i in g["agree"]["items"] if i["kind"] == "how_out"], [])
    check("an agreeing match suggests Cricket Australia", g["agree"]["suggested"], "ca")
    check("a small difference suggests Cricket Australia too", g["small_bowl"]["suggested"], "ca")
    check("a match with a pairing problem suggests nothing", g["pairing"]["suggested"], None)
    check("every match starts showing the club card", {r["current"] for r in rows.values()}, {"club"})
    ov = cr.overview(list(rows.values()))
    check("the overview counts each group",
          ov["groups"], {"agree": 1, "small": 2, "differ": 3, "pairing": 1, "nocard": 1})
    check("a club scorecard with no recorded file says where it came from",
          g["agree"]["source"]["kind"], "typed")

    # --- the three-way choice -----------------------------------------------------------------
    print("\n-- the choice: Cricket Australia, club card, or club card with Cricket Australia detail --")
    mid_a, gid_a = ids["agree"]
    async with async_session_maker() as s:
        res = await act.set_choice(s, ORG, mid_a, "ca", USER, note="scores match")
    st = (await q("SELECT pair_prefers_import, review_choice, review_source, pairing_locked, review_note "
                  "FROM manual_games WHERE id = :m", m=mid_a))[0]
    check("choosing Cricket Australia makes the site show the synced card",
          (st[0], st[1], st[2], st[4]), (False, "ca", "hand", "scores match"))
    check("a choice locks the pairing so a sync cannot flip it back", st[3], True)
    eff = {r[0] for r in await q("SELECT id::text FROM v_effective_games WHERE id IN (:m, :g)", m=mid_a, g=gid_a)}
    check("the effective views now serve the synced game and hide the club card", eff, {str(gid_a)})
    async with async_session_maker() as s:
        await act.set_choice(s, ORG, mid_a, "club", USER)
    eff = {r[0] for r in await q("SELECT id::text FROM v_effective_games WHERE id IN (:m, :g)", m=mid_a, g=gid_a)}
    check("switching back serves the club card again", eff, {str(mid_a)})
    async with async_session_maker() as s:
        hist = await act.history(s, ORG, mid_a)
    check("every change is in the history, newest first", [(h["from_choice"], h["to_choice"]) for h in hist],
          [("ca", "club"), ("club", "ca")])
    async with async_session_maker() as s:
        await act.undo_last(s, ORG, mid_a, USER)
    st = (await q("SELECT pair_prefers_import, review_choice FROM manual_games WHERE id = :m", m=mid_a))[0]
    check("undo puts back the state before the last change", (st[0], st[1]), (False, "ca"))
    async with async_session_maker() as s:
        await act.undo_last(s, ORG, mid_a, USER)
    st = (await q("SELECT pair_prefers_import, review_choice, review_source, pairing_locked, review_note "
                  "FROM manual_games WHERE id = :m", m=mid_a))[0]
    check("undoing again returns the match to never having been reviewed",
          (st[0], st[1], st[2], st[4]), (True, None, None, None))
    async with async_session_maker() as s:
        try:
            await act.undo_last(s, ORG, mid_a, USER)
            msg = "no error"
        except act.ReviewError as e:
            msg = str(e)
    check("with nothing left to undo it says so", msg, "There is nothing to undo for this match.")

    # --- the combined choice --------------------------------------------------------------------
    print("\n-- club numbers with Cricket Australia detail --")
    mid_h, gid_h = ids["hybrid"]
    before_runs = await q("SELECT player_id::text, runs, innings_number FROM manual_batting_innings "
                          "WHERE manual_game_id = :m ORDER BY player_id, innings_number", m=mid_h)
    async with async_session_maker() as s:
        plan = await hy.plan_hybrid(s, ORG, mid_h)
    check("a preview writes nothing", (await q("SELECT count(*) FROM manual_fall_of_wickets "
                                               "WHERE manual_game_id = :m", m=mid_h))[0][0], 0)
    check("the preview lists what would come over", any("Balls faced" in b for b in plan["brought"]), True)
    check("and what would be left out, naming the batter",
          any("Pike, Jordan" in x and "36 runs" in x and "35" in x for x in plan["left_out"]), True)
    async with async_session_maker() as s:
        res = await act.set_choice(s, ORG, mid_h, "hybrid", USER)
    balls = {r[0]: r[1] for r in await q("SELECT p.name, mb.balls FROM manual_batting_innings mb "
                                         "JOIN players p ON p.id = mb.player_id WHERE mb.manual_game_id = :m", m=mid_h)}
    check("balls faced come over for batters whose runs agree", balls["Ortega, Sam"], 10)
    check("but NOT for the batter whose runs differ", balls["Pike, Jordan"], None)
    check("the club's own runs are never touched",
          await q("SELECT player_id::text, runs, innings_number FROM manual_batting_innings "
                  "WHERE manual_game_id = :m ORDER BY player_id, innings_number", m=mid_h), before_runs)
    credits = await q("SELECT p.name, count(*) FROM manual_bowler_wickets w JOIN players p ON p.id = w.bowler_id "
                      "WHERE w.manual_game_id = :m GROUP BY 1 ORDER BY 1", m=mid_h)
    check("who took the wicket comes over for a bowler whose wicket count agrees", credits, [("Cole, Hal", 3)])
    check("and the bowler whose count differs is listed as left out",
          any("Park" in x or "Mal" in x for x in res["left_out"]), True)
    fow = {r[0] for r in await q("SELECT innings_number FROM manual_fall_of_wickets WHERE manual_game_id = :m", m=mid_h)}
    check("fall of wickets are NOT copied for our innings whose batters' runs differ", 1 not in fow, True)
    check("but are copied for the opposition innings, whose totals do not conflict", 2 in fow, True)
    detail = (await q("SELECT review_detail FROM manual_games WHERE id = :m", m=mid_h))[0][0]
    check("our dismissal text is kept for a batter whose runs agree",
          [d["text"] for d in detail["our_dismissals"]], ["c R Hale b K Moss"])
    check("and not for the batter whose runs differ or a bare 'b'",
          any(d["player_id"] == str(ours["Pike"]) for d in detail["our_dismissals"]), False)
    check("the opposition's cards come over", (len(detail["opp_batting"]), len(detail["opp_bowling"])), (1, 1))
    check("they sit on the club card's own innings numbers",
          (detail["opp_batting"][0]["innings_number"], detail["opp_bowling"][0]["innings_number"]), (2, 1))
    from app.routers.games import get_scorecard
    async with async_session_maker() as s:
        page = await get_scorecard(str(mid_h), db=s, viewer=None, org_param=None)
    check("the match page draws the opposition's card from it",
          [r["player_name"] for r in page["opp_batting"]], ["R Hale"])
    check("and the bowler and fielder on our dismissal",
          {r["player_name"]: r["dismissal_type"] for r in page["batting"]}.get("Ortega, Sam")
          or next((r["dismissal_type"] for r in page["batting"] if "Ortega" in (r["player_name"] or "")), None),
          "c R Hale b K Moss")
    log = (await q("SELECT detail FROM card_review_log WHERE manual_game_id = :m AND action = 'choice' "
                   "ORDER BY id DESC LIMIT 1", m=mid_h))[0][0]
    check("the history keeps the id of every row the copy wrote",
          sorted(log["inserted"]), ["balls", "bw", "detail", "fow", "part"])
    async with async_session_maker() as s:
        await act.set_choice(s, ORG, mid_h, "ca", USER)
    left = (await q("SELECT (SELECT count(*) FROM manual_fall_of_wickets WHERE manual_game_id = :m), "
                    "(SELECT count(*) FROM manual_bowler_wickets WHERE manual_game_id = :m), "
                    "(SELECT count(*) FROM manual_batting_innings WHERE manual_game_id = :m AND balls IS NOT NULL), "
                    "(SELECT review_detail IS NULL FROM manual_games WHERE id = :m)", m=mid_h))[0]
    check("leaving the combined choice takes back exactly what it copied", tuple(left), (0, 0, 0, True))
    check("and the club's runs are still exactly as they were",
          await q("SELECT player_id::text, runs, innings_number FROM manual_batting_innings "
                  "WHERE manual_game_id = :m ORDER BY player_id, innings_number", m=mid_h), before_runs)
    async with async_session_maker() as s:
        await act.undo_last(s, ORG, mid_h, USER)
    check("undoing that leave puts the combined choice back, copy and all",
          (await q("SELECT count(*) FROM manual_batting_innings WHERE manual_game_id = :m AND balls IS NOT NULL",
                   m=mid_h))[0][0] > 0, True)
    # Cricket Australia corrects its card; refresh re-copies
    await ex("UPDATE batting_innings SET balls = 99 WHERE game_id = :g AND player_id = :p", g=gid_h, p=ours["Ortega"])
    async with async_session_maker() as s:
        await act.refresh_detail(s, ORG, mid_h, USER)
    check("refreshing picks up Cricket Australia's correction",
          (await q("SELECT balls FROM manual_batting_innings WHERE manual_game_id = :m AND player_id = :p",
                   m=mid_h, p=ours["Ortega"]))[0][0], 99)
    async with async_session_maker() as s:
        try:
            await act.refresh_detail(s, ORG, ids["agree"][0], USER)
            msg = "no error"
        except act.ReviewError as e:
            msg = str(e)
    check("refresh is refused on a match not showing the combined choice", msg.startswith("Detail can only be"), True)
    # a person's own correction to a copied balls figure survives leaving the combined choice
    await ex("UPDATE manual_batting_innings SET balls = 55 WHERE manual_game_id = :m AND player_id = :p",
             m=mid_h, p=ours["Ortega"])
    async with async_session_maker() as s:
        await act.set_choice(s, ORG, mid_h, "club", USER)
    check("a balls figure a person has corrected since is theirs, so it stays",
          (await q("SELECT balls FROM manual_batting_innings WHERE manual_game_id = :m AND player_id = :p",
                   m=mid_h, p=ours["Ortega"]))[0][0], 55)
    live_state["card"] = None
    async with async_session_maker() as s:
        plan = await hy.plan_hybrid(s, ORG, ids["agree"][0])
    check("if Cricket Australia cannot be reached the rest still comes and the plan says what was left out",
          (plan["ok"], any("could not be reached" in x for x in plan["left_out"])), (True, True))
    live_state["card"] = live_card

    # --- a match nobody can combine ------------------------------------------------------------------
    async with async_session_maker() as s:
        try:
            await act.set_choice(s, ORG, ids["nocard"][0], "hybrid", USER)
            msg = "no error"
        except act.ReviewError as e:
            msg = str(e)
    check("a match with no Cricket Australia card of ours cannot be combined",
          msg, "Cricket Australia has no card of ours for this match.")

    # --- the bulk switch ------------------------------------------------------------------------------
    print("\n-- the bulk switch for matches whose cards agree --")
    for i in range(4):
        await make(f"bulk{i}", day=date(2026, 1, 3 + i), club_bat=six, ca_bat=six_ca)
    # a person chose the club card for one agreeing match by hand
    async with async_session_maker() as s:
        await act.set_choice(s, ORG, ids["bulk0"][0], "club", USER2, note="keep ours")
    rows_now = list((await review()).values())
    prev = act.bulk_preview(rows_now)
    agree_now = [r for r in rows_now if r["group"] == "agree"]
    check("the preview counts agreeing matches nobody has chosen for",
          prev["matches"], len([r for r in agree_now if not r["decided_by_hand"] and r["current"] != "ca"]))
    check("it does not count the match a person chose by hand",
          str(ids["bulk0"][0]) in {r["match_id"] for r in prev["sample"]}, False)
    check("it gives a sample to spot-check", 0 < len(prev["sample"]) <= 10, True)
    async with async_session_maker() as s:
        res = await act.bulk_apply(s, ORG, USER)
    check("the bulk switch changes only those matches", res["switched"], prev["matches"])
    check("a match chosen by hand is left exactly as the person set it",
          (await q("SELECT review_choice, review_source FROM manual_games WHERE id = :m", m=ids["bulk0"][0]))[0],
          ("club", "hand"))
    check("a match that does not agree is never switched in bulk",
          (await q("SELECT review_choice FROM manual_games WHERE id = :m", m=ids["differ"][0]))[0][0], None)
    sw = await q("SELECT count(*) FROM manual_games WHERE review_source = 'bulk' AND NOT pair_prefers_import")
    check("every bulk switch is a logged change of its own", (sw[0][0],
          (await q("SELECT count(*) FROM card_review_log WHERE batch_id = CAST(:b AS UUID)", b=res["batch_id"]))[0][0]),
          (res["switched"], res["switched"]))
    check("the batch is in the audit log", (await q(
        "SELECT count(*) FROM audit_logs WHERE action = 'card_review_bulk' AND target_id = :b",
        b=res["batch_id"]))[0][0], 1)
    # a person changes one bulk match afterwards: undoing the batch must leave that one alone
    changed_mid = next(r["match_id"] for r in (await review()).values()
                       if r["decided_source"] == "bulk")
    async with async_session_maker() as s:
        await act.set_choice(s, ORG, changed_mid, "hybrid", USER2)
    async with async_session_maker() as s:
        undone = await act.bulk_undo(s, ORG, USER, res["batch_id"])
    check("undoing the batch puts back every match a person has not touched since",
          undone["undone"], res["switched"] - 1)
    check("and names the one it left alone", undone["left_alone"], [changed_mid])
    check("the left-alone match still shows what its person chose",
          (await q("SELECT review_choice, review_source FROM manual_games WHERE id = CAST(:m AS UUID)",
                   m=changed_mid))[0], ("hybrid", "hand"))

    # --- pairing ------------------------------------------------------------------------------------------
    print("\n-- fixing a pairing --")
    mid_p, gid_p = ids["pairing"]
    async with async_session_maker() as s:
        await act.mark_pair_ok(s, ORG, mid_p, USER)
    rows = await review()
    check("saying the cards are the same match moves it out of 'pairing looks wrong'",
          rows[str(mid_p)]["group"], "differ")
    async with async_session_maker() as s:
        await act.undo_last(s, ORG, mid_p, USER)
    check("and that can be undone", (await review())[str(mid_p)]["group"], "pairing")
    mid_n, gid_n = ids["nocard"]
    async with async_session_maker() as s:
        try:
            await act.relink(s, ORG, mid_p, gid_a, USER)
            msg = "no error"
        except act.ReviewError as e:
            msg = str(e)
    check("re-linking to a card another match already holds is refused", msg.startswith("Another club scorecard"), True)
    async with async_session_maker() as s:
        await act.unlink(s, ORG, mid_p, USER)
    check("unlinking says these are two different matches",
          (await q("SELECT superseded_by_game_id FROM manual_games WHERE id = :m", m=mid_p))[0][0], None)
    async with async_session_maker() as s:
        await act.undo_last(s, ORG, mid_p, USER)
    check("and undo links them again",
          str((await q("SELECT superseded_by_game_id FROM manual_games WHERE id = :m", m=mid_p))[0][0]), str(gid_p))
    async with async_session_maker() as s:
        try:
            await act.set_choice(s, ORG, u(), "ca", USER)
            msg = "no error"
        except act.ReviewError as e:
            msg = str(e)
    check("a match that is not this club's is refused", msg, "That match was not found for this club.")

    # --- a sync must not flip a person's choice back ---------------------------------------------------
    print("\n-- the pairing step a sync runs leaves a choice alone --")
    from app.services import match_pairing
    mid_c, gid_c = await make("cs", day=date(2025, 12, 6), club_bat=six, ca_bat=six_ca)
    await ex("UPDATE manual_games SET cricketstatz_import_id = gen_random_uuid(), cricketstatz_match_id = 'cs-1', "
             "pairing_locked = FALSE, pair_prefers_import = FALSE WHERE id = :m", m=mid_c)
    async with async_session_maker() as s:
        await act.set_choice(s, ORG, mid_c, "club", USER, note="ours is right")
    async with async_session_maker() as s:
        await match_pairing.reconcile_org(s, ORG)
    st = (await q("SELECT pair_prefers_import, review_choice, pairing_locked FROM manual_games WHERE id = :m",
                  m=mid_c))[0]
    check("a CricketStatz-paired match a person chose keeps showing the club card after the sweep",
          tuple(st), (True, "club", True))

    # --- the routes ----------------------------------------------------------------------------------------
    print("\n-- the API a reviewer's screens use --")
    import csv as _csv
    import io as _io
    from fastapi import HTTPException
    from app.models.db import Organisation, User
    from app.routers import card_review as route

    async with async_session_maker() as s:
        club, user = await s.get(Organisation, ORG), await s.get(User, USER)
        n_paired = (await q("SELECT count(*) FROM manual_games WHERE superseded_by_game_id IS NOT NULL"))[0][0]
        route._CACHE.clear()
        ov = await route.card_review_overview(club=club, db=s)
        check("the overview counts every paired match once", (ov["total"], sum(ov["groups"].values())),
              (n_paired, n_paired))
        lst = await route.card_review_matches(group="differ", season=None, decided=None, source_file=None,
                                              recent_seasons=None, limit=2, offset=0, club=club, db=s)
        check("a list answers one group, with the total and a page of it",
              ({r["group"] for r in lst["rows"]}, lst["total"] >= 3, len(lst["rows"])), ({"differ"}, True, 2))
        page2 = await route.card_review_matches(group="differ", season=None, decided=None, source_file=None,
                                                recent_seasons=None, limit=2, offset=2, club=club, db=s)
        check("the next page continues where the first stopped",
              {r["match_id"] for r in lst["rows"]} & {r["match_id"] for r in page2["rows"]}, set())
        row = lst["rows"][0]
        check("each line carries its headline, its count and its full difference list",
              (bool(row["headline"]), row["item_count"], len(row["items"])), (True, len(row["items"]), len(row["items"])))
        try:
            await route.card_review_matches(group="nonsense", season=None, decided=None, source_file=None,
                                            recent_seasons=None, limit=5, offset=0, club=club, db=s)
            code = None
        except HTTPException as e:
            code = e.status_code
        check("an unknown group is refused", code, 422)
        yes = await route.card_review_matches(group=None, season=None, decided="yes", source_file=None,
                                              recent_seasons=None, limit=50, offset=0, club=club, db=s)
        check("the list can show only matches chosen by hand", all(r["decided_by_hand"] for r in yes["rows"]), True)

        det = await route.card_review_match(str(ids["differ"][0]), club=club, db=s)
        pike = next(l for inn in det["innings"] for l in inn["batting"] if l["name"].startswith("Pike"))
        check("the compare screen marks the cell that differs and gives both values",
              (pike["differs"], pike["ca"]["runs"], pike["club"]["runs"]), (True, 36, 35))
        ortega = next(l for inn in det["innings"] for l in inn["batting"] if l["name"].startswith("Ortega"))
        check("and leaves a matching row unmarked", ortega["differs"], False)
        check("it names where the club card came from and both ids",
              (det["source"]["kind"], det["match_id"] == str(ids["differ"][0]), det["game_id"] == str(ids["differ"][1])),
              ("typed", True, True))
        try:
            await route.card_review_match(str(u()), club=club, db=s)
            code = None
        except HTTPException as e:
            code = e.status_code
        check("a match that is not this club's is a 404", code, 404)

        by_match = await route.card_review_for_game(str(ids["differ"][0]), club=club, db=s)
        by_game = await route.card_review_for_game(str(ids["differ"][1]), club=club, db=s)
        check("the match page finds the pair from either of its two ids", by_match["match_id"], by_game["match_id"])
        check("an id that is not part of a pair says so", (await route.card_review_for_game(str(u()), club=club, db=s)),
              {"paired": False})

        prev = await route.card_review_preview(str(ids["hybrid"][0]), club=club, db=s)
        check("the combined choice's preview comes from its own route",
              (prev["ok"], bool(prev["brought"]), bool(prev["left_out"])), (True, True, True))
        nopreview = await route.card_review_preview(str(ids["nocard"][0]), club=club, db=s)
        check("and says why a match cannot be combined", (nopreview["ok"], bool(nopreview["reason"])), (False, True))

    # a Cricket Australia game close in date whose card matches the club's
    cg = u()
    await ex("INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_org_id, away_org_id, "
             "opp_club_name, status, result, winning_team) VALUES (:g, :gr, :d, 'Payneham', 'Eastlake', :o, :x, "
             "'Eastlake', 'COMPLETED', 'WIN', 'Payneham')",
             g=cg, gr=GRADE, d=date(2026, 2, 14), o=ORG, x=OPP)
    for who, runs, pos, how, balls, inn in six_ca:
        await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, batting_position, runs, balls, "
                 "dismissal_type, not_out, did_not_bat) VALUES (:g, :p, 1, :pos, :r, :b, :h, FALSE, FALSE)",
                 g=cg, p=ours[who], pos=pos, r=runs, b=balls, h=how)
    async with async_session_maker() as s:
        club, user = await s.get(Organisation, ORG), await s.get(User, USER)
        cands = await route.card_review_candidates(str(ids["pairing"][0]), club=club, db=s)
        check("a pairing problem is offered the games whose scorecards actually match, and which are taken",
              [(c["game_id"], c["shared"], bool(c["taken_by"])) for c in cands["candidates"]],
              [(str(cg), 6, False), (str(ids["flip"][1]), 6, True)])
        await route.card_review_relink(str(ids["pairing"][0]), RelinkIn := route.RelinkIn(game_id=str(cg)),
                                       user=user, club=club, db=s)
        check("re-linking to it makes the match agree",
              (await review())[str(ids["pairing"][0])]["group"], "agree")
        # accept the suggestion for three matches, one of which has none
        route._CACHE.clear()
        acc = await route.card_review_accept(route.AcceptIn(match_ids=[str(ids["agree"][0]), str(ids["small_bowl"][0]),
                                                                       str(ids["flip"][0])]),
                                             user=user, club=club, db=s)
        check("accepting suggestions switches the matches that have one and skips the rest",
              (acc["switched"], [x["match_id"] for x in acc["skipped"]]), (2, [str(ids["flip"][0])]))
        check("an accepted suggestion is the person's choice, with the note saying so",
              (await q("SELECT review_choice, review_source, review_note FROM manual_games WHERE id = :m",
                       m=ids["agree"][0]))[0], ("ca", "hand", "Accepted the suggestion"))
        route._CACHE.clear()
        bp = await route.card_review_bulk_preview(club=club, db=s)
        check("the bulk preview offers the agreeing matches not yet switched or chosen", bp["matches"] >= 1, True)
        applied = await route.card_review_bulk_apply(route.BulkIn(limit=1), user=user, club=club, db=s)
        check("the bulk switch can be limited to a first handful", applied["switched"], 1)
        batches = await route.card_review_batches(club=club, db=s)
        check("each batch is listed with how many are still switched",
              (batches["batches"][0]["batch_id"], batches["batches"][0]["still_switched"]), (applied["batch_id"], 1))
        undone = await route.card_review_bulk_undo(route.BulkUndoIn(batch_id=applied["batch_id"]),
                                                    user=user, club=club, db=s)
        check("and a batch can be undone from the list", undone["undone"], 1)
        try:
            await route.card_review_bulk_undo(route.BulkUndoIn(batch_id="not-a-uuid"), user=user, club=club, db=s)
            code = None
        except HTTPException as e:
            code = e.status_code
        check("a batch id that is not an id is refused", code, 422)
        route._CACHE.clear()
        resp = await route.card_review_export(club=club, db=s)
        body = "".join([chunk if isinstance(chunk, str) else chunk.decode() async for chunk in resp.body_iterator])
    parsed = list(_csv.reader(_io.StringIO(body.lstrip("\ufeff"))))
    check("the spreadsheet has the agreed columns, the last two blank for the reviewer",
          (parsed[0], parsed[0][-2:]), (cr.EXPORT_HEADERS, ["Your choice", "Notes"]))
    check("it lists only matches with a discrepancy",
          {r[5] for r in parsed[1:]} <= {"Scores differ", "Small differences", "Pairing looks wrong"}, True)
    check("it leaves out matches that agree or have no Cricket Australia card",
          {r[0] for r in parsed[1:]} & {str(ids["agree"][0]), str(ids["nocard"][0])}, set())
    check("scores that differ come first", parsed[1][5], "Scores differ")
    check("each row carries every difference, a review link and empty reviewer columns",
          (all(r[8] for r in parsed[1:]), parsed[1][15].startswith("https://betterat.cricket/admin/card-review/match/"),
           parsed[1][16], parsed[1][17]), (True, True, "", ""))
    check("the file name says which club and day", resp.headers["content-disposition"].startswith(
        'attachment; filename="card-review-pay-'), True)

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
