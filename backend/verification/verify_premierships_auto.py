"""Verification for automatic premierships, against a real Postgres.

A club that wins a grand final should get the Premiership honour on every
player who played, a link from each honour to the scorecard, and the card on
its Premierships page, with nothing typed in. This runs the SHIPPED
``services/premierships`` (``plan`` / ``reconcile``), ``services/honours.premiership_squads``
and the shipped route bodies ``routers/honours.get_premierships`` /
``get_game_premierships`` and ``routers/achievements.list_achievements`` /
``update_achievement`` / ``delete_achievement`` over a club with:

  - a grand final won (captain, three players, a withdrawn 12th man, and an
    opposition player on the card), a semi final won, a grand final lost, a
    grand final with no winner, a preliminary final won,
  - a 2023/24 grand final won where the club had ALREADY typed the honour in
    for one player (it must be linked, not duplicated),
  - a grade that won two grand finals in one year (a hand-typed row cannot be
    matched to either),
  - the same grand final seen from the other club (a shared fixture).

Every "X is absent" check is paired with a check that X could be present
(rule 21).

CONTROL MODE. Run against the commit BEFORE this change, ``services/premierships``
does not exist: every check fails and nothing crashes, because it is read
through ``getattr`` on a module that may be missing.

Run:  DATABASE_URL=postgresql+asyncpg://root@/premierships_auto?host=/var/run/postgresql \
      python verification/verify_premierships_auto.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base, Organisation
from app.services.session_safety import rollback_keeping
from app.services import honours
from app.routers import achievements as ach_router
from app.routers import honours as honours_router

try:  # absent on the control commit
    from app.services import premierships as prem
except ImportError:
    prem = None

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  - ' + detail) if detail else ''}")


def u() -> uuid.UUID:
    return uuid.uuid4()


OURS, OTHER = u(), u()
S25, S23, SOTHER = u(), u(), u()
GR_F25, GR_H23, GR_B23, GR_ONE, GR_OTHER25 = u(), u(), u(), u(), u()
G_GF, G_SEMI, G_LOST, G_DRAW, G_PRELIM, G_GF23, G_SPRING, G_SUMMER, G_JUN = (u() for _ in range(9))
GR_U13, COMP_JUN = u(), u()
P = {n: u() for n in ("cap", "bob", "cat", "dan", "twelfth", "eve", "foe", "hist", "other1", "hidden", "kid1", "kid2")}
NAME = {"cap": "Caden Smith", "bob": "Bob Bell", "cat": "Cat Cole", "dan": "Dan Day",
        "twelfth": "Tim Twelfth", "eve": "Eve East", "foe": "Fred Foe", "hist": "Hal Hist",
        "other1": "Oscar Other", "hidden": "Hugh Hidden", "kid1": "Kit Kidd", "kid2": "Kip Kidd"}


async def seed(conn) -> None:
    for oid, name, slug in ((OURS, "Leederville Cricket Club", "leederville"),
                            (OTHER, "Rivals Cricket Club", "rivals")):
        await conn.execute(text("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i,:n,:s,true)"),
                           {"i": oid, "n": name, "s": slug})
    for sid, org, name, year in ((S25, OURS, "2025/26", 2025), (S23, OURS, "2023/24", 2023),
                                 (SOTHER, OTHER, "2025/26", 2025)):
        await conn.execute(text("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i,:o,:n,:y)"),
                           {"i": sid, "o": org, "n": name, "y": year})
    # The sponsor suffix on the 2025 grade shows the honour is named the way the club names it.
    for gid, sid, name in ((GR_F25, S25, "F Grade"), (GR_H23, S23, "H Grade"), (GR_B23, S23, "B Grade"),
                           (GR_ONE, S25, "A Grade"), (GR_OTHER25, SOTHER, "F Grade")):
        await conn.execute(text("INSERT INTO grades (id, season_id, name) VALUES (:i,:s,:n)"),
                           {"i": gid, "s": sid, "n": name})
    await conn.execute(text("INSERT INTO club_competitions (id, organisation_id, name, is_junior) "
                            "VALUES (:c, :o, 'Junior Cricket Association', true)"), {"c": COMP_JUN, "o": OURS})
    await conn.execute(text("INSERT INTO grades (id, season_id, name, competition_id) VALUES (:i,:s,'Under 13',:c)"),
                       {"i": GR_U13, "s": S25, "c": COMP_JUN})
    for k, org in (("cap", OURS), ("bob", OURS), ("cat", OURS), ("dan", OURS), ("twelfth", OURS),
                   ("eve", OURS), ("hist", OURS), ("foe", OTHER), ("other1", OTHER), ("hidden", OURS),
                 ("kid1", OURS), ("kid2", OURS)):
        await conn.execute(text("INSERT INTO players (id, name, organisation_id) VALUES (:i,:n,:o)"),
                           {"i": P[k], "n": NAME[k], "o": org})

    def game(gid, grade, d, rnd, ours_home, winner, final=True, status="COMPLETED"):
        return {"id": gid, "grade": grade, "d": d, "rnd": rnd, "final": final, "status": status,
                "home": "Leederville F" if ours_home else "Rivals F",
                "away": "Rivals F" if ours_home else "Leederville F",
                "ho": OURS if ours_home else OTHER, "ao": OTHER if ours_home else OURS,
                "winner": winner}
    games = [
        game(G_GF, GR_F25, date(2026, 3, 14), "Grand Final", True, "Leederville F"),
        game(G_JUN, GR_U13, date(2026, 3, 15), "Grand Final", True, "Leederville F"),
        game(G_SEMI, GR_F25, date(2026, 3, 1), "Semi Final", True, "Leederville F"),
        game(G_LOST, GR_ONE, date(2026, 3, 14), "Grand Final", True, "Rivals F"),
        game(G_DRAW, GR_ONE, date(2026, 3, 21), "Grand Final", True, None),
        game(G_PRELIM, GR_ONE, date(2026, 3, 7), "Preliminary Final", True, "Leederville F"),
        game(G_GF23, GR_H23, date(2024, 3, 16), "Grand Final", False, "Leederville F"),
        game(G_SPRING, GR_B23, date(2023, 11, 11), "Grand Final", True, "Leederville F"),
        game(G_SUMMER, GR_B23, date(2024, 3, 9), "Grand Final", True, "Leederville F"),
    ]
    for g in games:
        await conn.execute(text("""
            INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_org_id, away_org_id,
                               winning_team, is_final, status)
            VALUES (:id, :grade, :d, :home, :away, :ho, :ao, :winner, :final, :status)"""),
            {k: v for k, v in g.items() if k != "rnd"})
        # round_name is this change's column: on the control commit it does not exist, and the
        # game is still stored (is_final true), which is exactly what the club has today.
        if prem is not None:
            await conn.execute(text("UPDATE games SET round_name = :r WHERE id = :i"),
                               {"r": g["rnd"], "i": g["id"]})

    def app(gid, k, team, cap=False, reserve=None):
        return {"g": gid, "p": P[k], "t": team, "c": cap, "r": reserve}
    appearances = [
        app(G_GF, "cap", "Leederville F", cap=True), app(G_GF, "bob", "Leederville F"),
        app(G_GF, "cat", "Leederville F"), app(G_GF, "twelfth", "Leederville F", reserve=True),
        app(G_GF, "foe", "Rivals F"), app(G_GF, "other1", "Rivals F"),
        app(G_GF, "hidden", "Leederville F"),
        app(G_JUN, "kid1", "Leederville F", cap=True), app(G_JUN, "kid2", "Leederville F"),
        app(G_SEMI, "cap", "Leederville F"), app(G_LOST, "bob", "Leederville F"),
        app(G_DRAW, "bob", "Leederville F"), app(G_PRELIM, "bob", "Leederville F"),
        app(G_GF23, "cap", "Leederville F", cap=True), app(G_GF23, "dan", "Leederville F"),
        app(G_SPRING, "eve", "Leederville F"), app(G_SUMMER, "eve", "Leederville F"),
    ]
    for a in appearances:
        await conn.execute(text("""
            INSERT INTO game_appearances (game_id, player_id, team_name, is_captain, is_reserve)
            VALUES (:g,:p,:t,:c,:r)"""), a)

    await conn.execute(text("UPDATE players SET privacy_hidden_at = NOW() WHERE id = :i"), {"i": P["hidden"]})

    # What the club typed in itself, before any of this existed.
    hand = [
        # 2023/24 H Grade flag for the captain, typed with the season as a label.
        ("cap", "2023/24", "Premiership", "H Grade", "Premiership", "Captain"),
        # A captain award row, nothing to do with the automatic flag.
        ("cap", "2025/26", "Premiership", "F Grade", "Captain", None),
        # A flag in a grade that won two grand finals in 2023/24: cannot be matched to either.
        ("eve", "2023/24", "Premiership", "B Grade", "Premiership", None),
        # A flag the club typed for a year with no grand final in the data (a flag from long ago).
        ("hist", "1998/99", "Premiership", "A Grade", "Premiership", None),
    ]
    for k, season, cat, sub, ach, detail in hand:
        await conn.execute(text("""
            INSERT INTO player_achievements (org_id, player_id, player_name, season, category, subcategory,
                                             achievement, detail)
            VALUES (:o,:p,:n,:s,:c,:sub,:a,:d)"""),
            {"o": OURS, "p": P[k], "n": NAME[k], "s": season, "c": cat, "sub": sub, "a": ach, "d": detail})


async def _expect_err(prem, db, club, game, pid):
    from app.services.session_safety import rollback_keeping
    try:
        return await prem.edit_squad(db, club, game_id=game, action="add", player_id=pid, role="12th Man")
    except Exception as e:
        await rollback_keeping(db, club)
        return e


async def rows(db, org=None, **where) -> list[dict]:
    q = ("SELECT id, player_id, player_name, season, category, subcategory, achievement, detail, "
         "linked_game_id, auto_created FROM player_achievements WHERE org_id = :o AND category = 'Premiership'")
    res = await db.execute(text(q), {"o": org or OURS})
    out = [dict(r) for r in res.mappings().all()]
    for k, v in where.items():
        out = [r for r in out if r[k] == v]
    return out


def pids(rs) -> set:
    return {r["player_id"] for r in rs}


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        # The lifespan's own raw-SQL tables, column for column (rule 24).
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_achievements (
                id SERIAL PRIMARY KEY, org_id UUID NOT NULL, player_id UUID, player_name TEXT NOT NULL,
                season TEXT, category TEXT NOT NULL, subcategory TEXT, achievement TEXT NOT NULL,
                detail TEXT, created_at TIMESTAMPTZ DEFAULT NOW())"""))
        await conn.execute(text("ALTER TABLE player_achievements ADD COLUMN IF NOT EXISTS season_end TEXT"))
        await conn.execute(text("ALTER TABLE player_achievements ADD COLUMN IF NOT EXISTS import_batch_id UUID"))
        await conn.execute(text("ALTER TABLE player_achievements ADD COLUMN IF NOT EXISTS club_role_id UUID"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS org_award_definitions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                org_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                category TEXT NOT NULL, subcategory TEXT, achievement TEXT, display_name TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0, active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"""))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL,
                canonical_name TEXT NOT NULL, alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)"""))
        # This change's own DDL, applied the way the migration and the lifespan apply it.
        try:
            from app.services.premierships_ddl import STATEMENTS
        except ImportError:
            STATEMENTS = []
        for stmt in STATEMENTS:
            await conn.execute(text(stmt))
        from app.services.junior_hiding_ddl import STATEMENTS as JUNIOR_DDL
        for stmt in JUNIOR_DDL:
            await conn.execute(text(stmt))
        await seed(conn)

    # ── 1. what counts as a grand final ──────────────────────────────────
    print("\n1. Reading a round name")
    f = getattr(prem, "is_grand_final_round", lambda _n: None)
    for name, want in (("Grand Final", True), ("grand final", True), ("Grand Final - Day 2", True),
                       ("Grand-Final", True), ("Final", True), ("Semi Final", False),
                       ("Preliminary Final", False), ("Qualifying Final", False),
                       ("Elimination Final", False), ("Finals", False), ("Round 7", False),
                       ("", False), (None, False), ("Grand Final Qualifier", False)):
        check(f"{name!r} -> {want}", f(name) is want, f"got {f(name)!r}")

    async with Session() as db:
        if prem is None:
            # CONTROL: the club won the 2025 F Grade grand final and nothing recorded it.
            got = (await db.execute(text(
                "SELECT player_id FROM player_achievements WHERE org_id = :o AND category = 'Premiership' "
                "AND subcategory = 'F Grade'"), {"o": OURS})).all()
            check("a won grand final puts the Premiership honour on its players", len(got) >= 3,
                  f"{len(got)} rows: nothing is written from the scorecard")
            check("services.premierships exists", False, "control: module absent")
            await engine.dispose()
            print(f"\n{PASS} passed, {FAIL} failed")
            sys.exit(1)
        # ── 2. a dry run writes nothing, and says what it would do ───────
        print("\n2. Preview")
        club = (await db.execute(select(Organisation).where(Organisation.id == OURS))).scalar_one()
        before = await rows(db)
        rep = await prem.reconcile(db, OURS, apply=False)
        check("dry run writes nothing", len(await rows(db)) == len(before))
        check("dry run reports the grand finals won (2025 F + 2023 H + spring + summer + Under 13 = 5)",
              rep.get("wins") == 5, str(rep.get("wins")))
        check("a grand final with no winner is reported, not awarded",
              [x["grade_name"] for x in rep.get("unresolved", [])] == ["A Grade"], str(rep.get("unresolved")))

        # ── 3. apply ─────────────────────────────────────────────────────
        print("\n3. Apply")
        rep = await prem.reconcile(db, OURS, apply=True)
        gf = await rows(db, linked_game_id=G_GF)
        check("captain, two players on the 2025 F Grade flag", pids(gf) == {P["cap"], P["bob"], P["cat"]},
              str(pids(gf)))
        check("the withdrawn 12th man is not in the squad", P["twelfth"] not in pids(gf))
        check("an opposition player on the card is not in our squad",
              P["foe"] not in pids(gf) and P["other1"] not in pids(gf))
        check("every automatic row is marked auto_created", all(r["auto_created"] for r in gf))
        check("the captain carries 'Captain' and the others carry nothing",
              {r["player_id"]: r["detail"] for r in gf} == {P["cap"]: "Captain", P["bob"]: None, P["cat"]: None})
        check("subcategory is the grade as the club names it",
              {r["subcategory"] for r in gf} == {"F Grade"}, str({r["subcategory"] for r in gf}))
        check("the season is the club's own season id (what the Awards screen writes)",
              {r["season"] for r in gf} == {str(S25)}, str({r["season"] for r in gf}))
        check("achievement is the bare word the page already understands",
              {r["achievement"] for r in gf} == {"Premiership"})
        check("a semi final win earns nothing", await rows(db, linked_game_id=G_SEMI) == [])
        check("a preliminary final win earns nothing", await rows(db, linked_game_id=G_PRELIM) == [])
        check("a grand final lost earns nothing", await rows(db, linked_game_id=G_LOST) == [])
        check("a grand final with no winner earns nothing", await rows(db, linked_game_id=G_DRAW) == [])

        check("a player who asked to be removed gets no automatic honour",
              await rows(db, player_id=P["hidden"]) == [] and P["hidden"] not in pids(gf))

        # ── 4. what the club typed in is never touched ───────────────────
        print("\n4. Hand-typed rows")
        h23 = [r for r in await rows(db) if r["player_id"] == P["cap"] and r["subcategory"] == "H Grade"]
        check("the hand-typed 2023/24 flag is not duplicated", len(h23) == 1, str(len(h23)))
        check("it is linked to the grand final instead", h23 and h23[0]["linked_game_id"] == G_GF23)
        check("and is still the club's own row (not auto, text unchanged)",
              h23 and not h23[0]["auto_created"] and h23[0]["detail"] == "Captain" and h23[0]["season"] == "2023/24")
        dan = await rows(db, player_id=P["dan"])
        check("the other 2023/24 player, with no typed row, gets one", len(dan) == 1 and dan[0]["auto_created"])
        cap_award = await rows(db, player_id=P["cap"], achievement="Captain")
        check("a typed Captain award row is left alone",
              len(cap_award) == 1 and not cap_award[0]["auto_created"] and cap_award[0]["linked_game_id"] is None)
        eve = await rows(db, player_id=P["eve"])
        check("two grand finals in one year: the typed row is neither linked nor doubled",
              len(eve) == 1 and eve[0]["linked_game_id"] is None and not eve[0]["auto_created"], str(eve))
        hist = await rows(db, player_id=P["hist"])
        check("a typed flag with no grand final in the data survives",
              len(hist) == 1 and hist[0]["linked_game_id"] is None)

        # ── 5. idempotent ────────────────────────────────────────────────
        print("\n5. Second run")
        n = len(await rows(db))
        rep = await prem.reconcile(db, OURS, apply=True)
        check("nothing created", rep.get("create") == 0 and len(await rows(db)) == n, str(rep))
        check("nothing deleted", rep.get("delete") == 0)

        # ── 6. other clubs ───────────────────────────────────────────────
        print("\n6. The other side of a shared fixture")
        rep = await prem.reconcile(db, OTHER, apply=True)
        check("the loser's club gets nothing from the same game", await rows(db, org=OTHER) == [], str(rep))
        check("and our rows are untouched by it", len(await rows(db)) == n)

        # ── 7. the three surfaces ────────────────────────────────────────
        print("\n7. Premierships page, scorecard banner, player honours")
        links = await prem.achievement_game_links(db, OURS)
        data = await honours.premiership_squads(db, OURS, game_links=links)
        card = next((c for c in data["premierships"] if c["team"] == "F Grade"), {})
        check("the 2025 F Grade card exists with its three players", card.get("player_count") == 3, str(card))
        check("and carries its scorecard", card.get("game_id") == str(G_GF), str(card.get("game_id")))
        h = next((c for c in data["premierships"] if c["team"] == "H Grade" and c["year"] == 2023 and c["players"]
                  and any(p["name"] == "Dan Day" for p in c["players"])), {})
        check("the linked hand-typed flag joins the 2023/24 card, not a second one",
              h.get("player_count") == 2 and h.get("game_id") == str(G_GF23), str(h))
        old = await honours.premiership_squads(db, OURS)
        check("football's call (no links) is unchanged: no game_id key",
              all("game_id" not in c for c in old["premierships"]))
        body = await honours_router.get_premierships(OURS, db)
        c2 = next((c for c in body["premierships"] if c["team"] == "F Grade"), {})
        check("the route adds the game's date and opponent",
              (c2.get("game") or {}).get("opponent") == "Rivals F"
              and (c2.get("game") or {}).get("played_at") == "2026-03-14", str(c2.get("game")))
        banner = await honours_router.get_game_premierships(G_GF, db)
        check("the scorecard banner names the club, grade and squad size",
              [(b["slug"], b["team"], b["players"]) for b in banner["premierships"]] == [("leederville", "F Grade", 3)],
              str(banner))
        check("a game that was not a premiership has no banner",
              (await honours_router.get_game_premierships(G_SEMI, db))["premierships"] == [])
        listed = await ach_router.list_achievements(org_id=str(OURS), player_id=str(P["bob"]), season=None, db=db)
        bob = [r for r in listed if r["category"] == "Premiership"]
        check("the player's honours list carries game_id and auto_created",
              len(bob) == 1 and str(bob[0]["game_id"]) == str(G_GF) and bob[0]["auto_created"] is True, str(bob))

        # ── 8. a corrected result removes only what we wrote ─────────────
        print("\n8. Result corrected")
        await db.execute(text("UPDATE games SET winning_team = 'Rivals F' WHERE id = :g"), {"g": G_GF23})
        await db.commit()
        rep = await prem.reconcile(db, OURS, apply=True)
        check("the automatic row for the game we no longer won is gone", await rows(db, player_id=P["dan"]) == [])
        h23 = [r for r in await rows(db) if r["player_id"] == P["cap"] and r["subcategory"] == "H Grade"]
        check("the hand-typed row stays, with its link removed",
              len(h23) == 1 and h23[0]["linked_game_id"] is None and h23[0]["detail"] == "Captain", str(h23))
        check("the other grand final's honours are untouched", pids(await rows(db, linked_game_id=G_GF)) ==
              {P["cap"], P["bob"], P["cat"]})
        await db.execute(text("UPDATE games SET winning_team = 'Leederville F' WHERE id = :g"), {"g": G_GF23})
        await db.commit()
        await prem.reconcile(db, OURS, apply=True)
        check("restoring the result restores the honour and the link",
              len(await rows(db, player_id=P["dan"])) == 1
              and any(r["linked_game_id"] == G_GF23 for r in await rows(db, player_id=P["cap"])))

        # ── 9. a person's decisions are kept ─────────────────────────────
        print("\n9. Delete and edit")
        bob_row = (await rows(db, player_id=P["bob"]))[0]
        await ach_router.delete_achievement(bob_row["id"], org_id=str(OURS), db=db)
        check("the deleted honour is gone", await rows(db, player_id=P["bob"]) == [])
        await prem.reconcile(db, OURS, apply=True)
        check("and the next sync does not write it back", await rows(db, player_id=P["bob"]) == [])
        check("but a squad-mate's honour is still there", len(await rows(db, player_id=P["cat"])) == 1)

        cat_row = (await rows(db, player_id=P["cat"]))[0]
        body = ach_router.AchievementUpdate(detail="Player of the Grand Final")
        await ach_router.update_achievement(cat_row["id"], body, db)
        cat_row = (await rows(db, player_id=P["cat"]))[0]
        check("an edited honour is no longer automatic", cat_row["auto_created"] is False)
        await db.execute(text("UPDATE games SET winning_team = 'Rivals F' WHERE id = :g"), {"g": G_GF})
        await db.commit()
        rep = await prem.reconcile(db, OURS, apply=True)
        check("a result correction does not delete an honour a person edited",
              len(await rows(db, player_id=P["cat"])) == 1)
        check("while the untouched automatic captain row goes",
              [r for r in await rows(db, player_id=P["cap"]) if r["linked_game_id"] == G_GF] == [])
        await db.execute(text("UPDATE games SET winning_team = 'Leederville F' WHERE id = :g"), {"g": G_GF})
        await db.commit()

        # ── 9b. a club that hides its juniors gets no junior honours ─────
        print("\n9b. Junior programme hidden")
        from app.services import junior_hiding
        kids = lambda: pids([r for r in rows_cache[0] if r["linked_game_id"] == G_JUN])
        rows_cache = [await rows(db)]
        check("with juniors shown, the Under 13 grand final earns its honours",
              kids() == {P["kid1"], P["kid2"]}, str(kids()))
        await db.execute(text("UPDATE organisations SET hide_juniors = true WHERE id = :o"), {"o": OURS})
        await db.commit(); junior_hiding.forget(OURS)
        rep = await prem.reconcile(db, OURS, apply=True)
        rows_cache[0] = await rows(db)
        check("hide_juniors on: the junior honours are removed (they were ours)", kids() == set(), str(kids()))
        check("and the senior flag beside them is untouched",
              pids([r for r in rows_cache[0] if r["linked_game_id"] == G_GF]) == {P["cap"], P["cat"]},
              str(pids([r for r in rows_cache[0] if r["linked_game_id"] == G_GF])))
        check("the junior grand final is not counted among the wins", rep.get("wins") == 4, str(rep.get("wins")))
        await db.execute(text("UPDATE organisations SET hide_juniors = false WHERE id = :o"), {"o": OURS})
        await db.commit(); junior_hiding.forget(OURS)
        await prem.reconcile(db, OURS, apply=True)
        rows_cache[0] = await rows(db)
        check("switched back off: they return", kids() == {P["kid1"], P["kid2"]}, str(kids()))

        # ── 9c. flags typed by team and competition (Applecross) ──────────
        print("\n9c. Typed by team and competition: no duplicate card")
        S16, S21, S22 = u(), u(), u()
        GR2, GRPS, GRA, GRB = u(), u(), u(), u()
        G1, G2, G3A, G3B = u(), u(), u(), u()
        for sid, nm, yr in ((S16, "2016/17", 2016), (S21, "2021/22", 2021), (S22, "2022/23", 2022)):
            await db.execute(text("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i,:o,:n,:y)"),
                             {"i": sid, "o": OURS, "n": nm, "y": yr})
        for gid, sid, nm in ((GR2, S16, "2nd Grade"), (GRPS, S21, "PSWL South A"), (GRA, S22, "A Grade"), (GRB, S22, "B Grade")):
            await db.execute(text("INSERT INTO grades (id, season_id, name) VALUES (:i,:s,:n)"), {"i": gid, "s": sid, "n": nm})
        for gid, gr_, d in ((G1, GR2, date(2017, 3, 11)), (G2, GRPS, date(2022, 3, 12)),
                            (G3A, GRA, date(2023, 3, 11)), (G3B, GRB, date(2023, 3, 12))):
            await db.execute(text("""INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_org_id, away_org_id,
                                     winning_team, is_final, round_name, status)
                                     VALUES (:g,:gr,:d,'Leederville F','Rivals F',:o,:t,'Leederville F',true,'Grand Final','COMPLETED')"""),
                             {"g": gid, "gr": gr_, "d": d, "o": OURS, "t": OTHER})

        async def newp(label):
            pid = u()
            await db.execute(text("INSERT INTO players (id, name, organisation_id) VALUES (:i,:n,:o)"),
                             {"i": pid, "n": label, "o": OURS})
            return pid

        async def sheet(game, pid):
            await db.execute(text("INSERT INTO game_appearances (game_id, player_id, team_name) VALUES (:g,:p,'Leederville F')"),
                             {"g": game, "p": pid})

        async def typed(pid, name, season, sub, ach, detail=None):
            await db.execute(text("""INSERT INTO player_achievements (org_id, player_id, player_name, season, category, subcategory,
                                     achievement, detail) VALUES (:o,:p,:n,:s,'Premiership',:sub,:a,:d)"""),
                             {"o": OURS, "p": pid, "n": name, "s": season, "sub": sub, "a": ach, "d": detail})

        a1, a2, a3 = await newp("Ann One"), await newp("Ann Two"), await newp("Ann Three")
        crowd = [await newp(f"Crowd {i}") for i in range(8)]
        for pid in [a1, a2, a3, *crowd]:
            await sheet(G1, pid)
        b1, b2 = await newp("Bea One"), await newp("Bea Two")
        for pid in (b1, b2):
            await sheet(G2, pid)
        c1, c2 = await newp("Cy One"), await newp("Cy Two")
        for pid in (c1, c2):
            await sheet(G3A, pid); await sheet(G3B, pid)
        await db.commit()

        # The state production is in: the automatic rows exist FIRST, then the typed ones are seen.
        await prem.reconcile(db, OURS, apply=True)
        mine = lambda pid, **kw: [r for r in rows_cache9c[0] if r["player_id"] == pid and (not kw or all(r[k] == v for k, v in kw.items()))]
        rows_cache9c = [await rows(db)]
        check("before the typed flags are seen, every player has an automatic honour (two for a double winner)",
              all(len(mine(p_)) == 1 and mine(p_)[0]["auto_created"] for p_ in (a1, a2, a3, b1, b2, *crowd))
              and all(len(mine(p_)) == 2 and all(r["auto_created"] for r in mine(p_)) for p_ in (c1, c2)))

        await typed(a1, "Ann One", "2016/17", "1st XI", "2nd Grade One Day Premiership")
        await typed(a1, "Ann One", "2016/17", "1st XI", "2nd Grade Two Day Premiership")
        await typed(a2, "Ann Two", "2016/17", "1st XI", "2nd Grade One Day Premiership", "Captain / Player of the Match")
        for pid in crowd:
            await typed(pid, "Crowd", "2016/17", "1st XI", "2nd Grade Two Day Premiership")
        await typed(b1, "Bea One", "2021/22", "Womens A", "PSWL South Premiership")
        await typed(None, "Bea Two", "2021/22", "Womens A", "PSWL South Premiership")
        await typed(c1, "Cy One", "2022/23", "1st XI", "Premiership")
        await db.commit()
        n_typed = len(await rows(db, auto_created=False))
        rep = await prem.reconcile(db, OURS, apply=True)
        rows_cache9c[0] = await rows(db)

        check("two typed flags (One Day, Two Day) for one win: the automatic duplicate is gone, both typed stay",
              len(mine(a1)) == 2 and not any(r["auto_created"] for r in mine(a1)), str(mine(a1)))
        check("a typed flag naming the grade is linked to the scorecard, its wording untouched",
              len(mine(a2)) == 1 and mine(a2)[0]["linked_game_id"] == G1 and mine(a2)[0]["detail"] == "Captain / Player of the Match"
              and not mine(a2)[0]["auto_created"], str(mine(a2)))
        check("a player with no typed flag keeps the automatic honour", len(mine(a3)) == 1 and mine(a3)[0]["auto_created"])
        check("eight more typed players: all eight automatic duplicates go in one run (not held back as a damaged read)",
              all(len(mine(p_)) == 1 and not mine(p_)[0]["auto_created"] for p_ in crowd) and not rep.get("delete_blocked"),
              str({k: rep.get(k) for k in ("supersede", "delete_blocked")}))
        check("a competition named PSWL South matches the grade PSWL South A, one honour each",
              len(mine(b1)) == 1 and mine(b1)[0]["linked_game_id"] == G2 and not mine(b1)[0]["auto_created"], str(mine(b1)))
        bea2 = [r for r in rows_cache9c[0] if r["player_name"] == "Bea Two" and r["category"] == "Premiership"]
        check("a typed row with no player id is matched by name and linked",
              len(bea2) == 1 and bea2[0]["linked_game_id"] == G2 and not bea2[0]["auto_created"]
              and len(mine(b2)) == 0, str((bea2, mine(b2))))
        check("one typed flag against two wins it does not name: nothing is guessed (both automatic rows stay, the "
              "typed one is untouched and unlinked) and the run says it was ambiguous",
              len(mine(c1)) == 3 and [r["auto_created"] for r in mine(c1)].count(False) == 1
              and [r for r in mine(c1) if not r["auto_created"]][0]["linked_game_id"] is None
              and rep.get("ambiguous", 0) >= 2, f"{len(mine(c1))} rows, ambiguous={rep.get('ambiguous')}")
        check("a player with the same two wins and no typed flag gets both honours",
              len(mine(c2)) == 2 and all(r["auto_created"] for r in mine(c2)), str(mine(c2)))
        check("no typed row was deleted or edited", len(await rows(db, auto_created=False)) == n_typed)
        rep2 = await prem.reconcile(db, OURS, apply=True)
        check("a second run changes nothing", all(rep2.get(k) == 0 for k in ("create", "supersede", "link", "delete")), str(rep2))

        # ── 9d. the squad editor ──────────────────────────────────────────
        print("\n9d. Squad editor")
        S30, GRE, GE = u(), u(), u()
        await db.execute(text("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i,:o,'2030/31',2030)"), {"i": S30, "o": OURS})
        await db.execute(text("INSERT INTO grades (id, season_id, name) VALUES (:i,:s,'E Grade')"), {"i": GRE, "s": S30})
        await db.execute(text("""INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_org_id, away_org_id, winning_team,
                                 is_final, round_name, status) VALUES (:g,:gr,:d,'Leederville F','Rivals F',:o,:t,'Leederville F',true,
                                 'Grand Final','COMPLETED')"""), {"g": GE, "gr": GRE, "d": date(2031, 3, 15), "o": OURS, "t": OTHER})
        e1, e2, e3, e4, e5 = [await newp(f"Edie {i}") for i in range(1, 6)]
        foreign = u()
        await db.execute(text("INSERT INTO players (id, name, organisation_id) VALUES (:i,'Someone Else',:o)"), {"i": foreign, "o": OTHER})
        for pid in (e1, e2, e3):
            await sheet(GE, pid)
        await db.commit()
        await prem.reconcile(db, OURS, apply=True)
        club = (await db.execute(select(Organisation).where(Organisation.id == OURS))).scalar_one()

        async def card():
            links_ = await prem.achievement_game_links(db, OURS)
            data_ = await honours.premiership_squads(db, OURS, game_links=links_)
            cs = [c for c in data_["premierships"] if c.get("game_id") == str(GE)]
            return cs, ({p_["name"]: p_ for p_ in cs[0]["players"]} if cs else {})

        async def edit(**kw):
            try:
                return await prem.edit_squad(db, club, game_id=GE, **kw)
            except Exception as e:
                await rollback_keeping(db, club)   # rule 12: a rollback expires `club`
                return e
        SquadEditError = getattr(prem, "SquadEditError", ValueError)

        cs, byname = await card()
        check("the new grand final is one card of three", len(cs) == 1 and set(byname) == {"Edie 1", "Edie 2", "Edie 3"}, str(byname.keys()))
        r = await edit(action="role", player_id=e1, role="Player of the Match", on=True)
        cs, byname = await card()
        check("Player of the Match is marked on a player who played", byname["Edie 1"]["roles"] == ["Player of the Match"], str(byname["Edie 1"]))
        r = await edit(action="add", player_id=e4, role="12th Man")
        cs, byname = await card()
        check("a 12th Man is added to the card without a flag of their own",
              byname.get("Edie 4", {}).get("roles") == ["12th Man"] and len(await rows(db, player_id=e4, achievement="Premiership")) == 0,
              str(byname.get("Edie 4")))
        check("and the card is still ONE card, now of four", len(cs) == 1 and cs[0]["player_count"] == 4, str(cs[0]["player_count"]))
        await edit(action="add", player_id=e5)
        cs, byname = await card()
        check("somebody who played and was missed by the sheet is added as a squad member",
              "Edie 5" in byname and len(await rows(db, player_id=e5, achievement="Premiership")) == 1)

        check("Player of the Match for a 12th Man is refused (they did not play)",
              isinstance(await edit(action="role", player_id=e4, role="Player of the Match", on=True), SquadEditError))
        check("a player from another club is refused", isinstance(await edit(action="add", player_id=foreign, role="12th Man"), SquadEditError))
        check("an unknown role is refused", isinstance(await edit(action="role", player_id=e1, role="Man of Steel", on=True), SquadEditError))
        check("a game that is not a premiership card is refused",
              isinstance(await _expect_err(prem, db, club, G_SEMI, e1), SquadEditError))

        rep = await prem.reconcile(db, OURS, apply=True)
        cs, byname = await card()
        check("a sync after the edits removes nothing the club added and adds nothing twice",
              set(byname) == {"Edie 1", "Edie 2", "Edie 3", "Edie 4", "Edie 5"} and byname["Edie 1"]["roles"] == ["Player of the Match"]
              and byname["Edie 4"]["roles"] == ["12th Man"], str(byname.keys()))

        await edit(action="remove", player_id=e2)
        await prem.reconcile(db, OURS, apply=True)
        cs, byname = await card()
        check("a player taken off the card stays off after the next sync", "Edie 2" not in byname and "Edie 3" in byname)
        await edit(action="role", player_id=e1, role="Player of the Match", on=False)
        await edit(action="remove", player_id=e4)
        cs, byname = await card()
        check("a role can be unmarked, and a 12th Man removed entirely",
              byname["Edie 1"]["roles"] == [] and "Edie 4" not in byname)
        route = await honours_router.get_premierships(OURS, db)
        c = [x for x in route["premierships"] if x.get("game_id") == str(GE)]
        check("the public route shows the edited card with its scorecard link and opponent",
              len(c) == 1 and (c[0].get("game") or {}).get("opponent") == "Rivals F")

        # ── 10. a damaged read does not wipe a club ──────────────────────
        print("\n10. Mass-removal guard")
        for i in range(8):
            pid = u()
            await db.execute(text("INSERT INTO players (id, name, organisation_id) VALUES (:i,:n,:o)"),
                             {"i": pid, "n": f"Extra {i}", "o": OURS})
            await db.execute(text("INSERT INTO game_appearances (game_id, player_id, team_name) VALUES (:g,:p,'Leederville F')"),
                             {"g": G_GF, "p": pid})
        await db.commit()
        await prem.reconcile(db, OURS, apply=True)
        total_auto = len([r for r in await rows(db) if r["auto_created"]])
        # The home side's id is cleared, as a half-finished rebuild might leave it.
        await db.execute(text("UPDATE games SET home_org_id = NULL WHERE home_org_id = :o"), {"o": OURS})
        await db.commit()
        rep = await prem.reconcile(db, OURS, apply=True)
        check("a read that would remove most of the club's honours removes none",
              len([r for r in await rows(db) if r["auto_created"]]) == total_auto and rep.get("delete_blocked"),
              str(rep))

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
