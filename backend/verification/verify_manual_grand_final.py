"""A hand-entered or imported game marked as the grand final earns the club's automatic premierships. Real Postgres.

Reported by Shoalwater Bay (Oct 2026): their C grade (1999/00) and D grade (2004/05) premiership
scorecards are in BetterCricket, as hand-entered games, and the automatic premierships never saw
them. They read Cricket Australia's synced games only, and say "grand final" from CA's round name,
which a typed-in game does not have.

`manual_games.is_grand_final` is a person's statement that a match was the decider, set (a) by a
column in the CSV import, (b) by a tick on the Manual Games form, or (c) later, on a game already
stored, by the match-details edit (which never touches the scorecard). The premierships then read
those games the way they read a synced grand final: our side won it (winner or result line), the
squad is the players its card records, and the honours link to the game.

Drives the SHIPPED route bodies and `services/premierships` against a real Postgres.

  S1 C grade 2000  imported, column says yes, winner "Shoalwater Bay", result WIN  -> honours for the card
  S2 D grade 2005  created on the form with the tick                                -> honours for the card
  S3 lost final    marked, the opposition won                                       -> nothing
  S4 no winner     marked, no winner and no result                                  -> nothing, said why
  S5 disagree      marked, winner is us, result line says Lost                      -> nothing, said why
  S6 semi final    a final, not marked as the grand final                           -> nothing
  S7 no grade      marked, but the game has no grade                                -> nothing, said why
  S8 later         imported unmarked; the details edit sets, clears and undoes it   -> honours follow; scorecard untouched
  S9 paired        marked, but IS a synced game that is itself a counted final      -> counted once, from the synced game

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/gf_verify?host=/tmp&port=5439 \\
  python verification/verify_manual_grand_final.py

Control run: check out the previous commit and run it again. It REPORTS the missing parts rather
than crashing on the first absent name.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import select, text

import verify_manual_side_names as h          # its engine, schema and CSV helpers; main() is guarded
from app.models.db import ManualEditLog, ManualGame, Organisation, User
from app.routers import manual_entries as me
from app.services import premierships

check, Session = h.check, h.Session

CLUB = "Shoalwater Bay Cricket Club"
PLAYERS = ["Alpha, Anne", "Bravo, Beth", "Charlie, Cath", "Delta, Dana"]
ORG, USER = h.ORG, h.USER


def is_marked(game) -> bool:
    """The flag, read presence-safely so a run against code without the column reports instead of crashing."""
    return bool(getattr(game, "is_grand_final", False))


def absent(name: str):
    print(f"  (absent: {name})")
    return None


async def build() -> dict:
    """The club, its seasons and grades, and a roster. Returns {label: id}."""
    await h.setup()
    ids: dict = {}
    async with h.engine.begin() as conn:
        # The honours tables, column for column as the lifespan makes them (rule 24). h.setup() creates a
        # stub `player_achievements` that is too small for this path, so it is replaced.
        await conn.execute(text("DROP TABLE IF EXISTS player_achievements"))
        await conn.execute(text("""
            CREATE TABLE player_achievements (
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
            CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)"""))
        # games.innings_totals is lifespan DDL, not on the ORM model, so create_all omits it.
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        from app.services.premierships_ddl import STATEMENTS as PREM_DDL
        for stmt in PREM_DDL:
            await conn.execute(text(stmt))
        try:
            from app.services.manual_grand_final_ddl import STATEMENTS as GF_DDL
        except ImportError:        # the control commit has no such column
            GF_DDL = []
        for stmt in GF_DDL:
            await conn.execute(text(stmt))
        await conn.execute(text("UPDATE organisations SET name = :n, slug = 'shoalwater' WHERE id = :o"),
                           {"n": CLUB, "o": ORG})
        await conn.execute(text("DELETE FROM players WHERE organisation_id = :o"), {"o": ORG})
        await conn.execute(text("DELETE FROM grades WHERE season_id IN (SELECT id FROM seasons WHERE organisation_id = :o)"), {"o": ORG})
        await conn.execute(text("DELETE FROM seasons WHERE organisation_id = :o"), {"o": ORG})

    # label -> (start year, [grades]). A season's `year` is the year it STARTS, as on production
    # ("Summer 2025/26" is 2025), which is what a typed "1999_00" flag is matched against.
    seasons = {
        "1999/00": (1999, ["C grade"]),
        "Summer 2004/05": (2004, ["D grade"]),
        "Summer 2010/11": (2010, ["A grade", "B grade", "E grade", "F grade"]),
        "Summer 2012/13": (2012, ["A grade"]),
        "Summer 2013/14": (2013, ["A grade"]),
    }
    async with Session() as s:
        for name in PLAYERS:
            pid = uuid.uuid4()
            ids["p:" + name] = pid
            await s.execute(text("INSERT INTO players (id, organisation_id, name, status) VALUES (:i, :o, :n, 'active')"),
                            {"i": pid, "o": ORG, "n": name})
        for label, (year, grades) in seasons.items():
            sid = uuid.uuid4()
            ids["s:" + label] = sid
            await s.execute(text("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, :n, :y)"),
                            {"i": sid, "o": ORG, "n": label, "y": year})
            for g in grades:
                gid = uuid.uuid4()
                ids[f"g:{label}:{g}"] = gid
                await s.execute(text("INSERT INTO grades (id, season_id, name, category, categories) "
                                     "VALUES (:i, :s, :n, 'senior', ARRAY['senior'])"), {"i": gid, "s": sid, "n": g})
        await s.commit()
    return ids


def sheet(key: str, played: str, season: str, grade: str, *, grand_final=None, winner="Shoalwater Bay",
          result="WIN", is_final=None) -> list[dict]:
    """A scorebook match: our four players, with a fall of wickets and an opposition innings."""
    base = {"game_key": key, "played_at": played, "opposition": "Rival", "season_name": season,
            "grade_name": grade, "winning_team": winner, "result": result,
            "innings_number": 1, "opp_innings_number": 2}
    if grand_final is not None:
        base["is_grand_final"] = grand_final
    if is_final is not None:
        base["is_final"] = is_final
    rows = []
    for i, name in enumerate(PLAYERS, 1):
        r = {**base, "player_name": name, "batting_position": i, "batting_runs": 10 + i,
             "bowling_overs": 4, "bowling_runs": 15 + i, "bowling_wickets": i % 2,
             "fow_wicket": i, "fow_score": 12 * i}
        if i == 1:
            r.update({"innings_total": 62, "innings_wickets": 4, "opp_total": 55, "opp_wickets": 10})
        rows.append(r)
    return rows


async def import_sheet(rows: list[dict], *, mode: str = "skip"):
    """Preview, resolve and commit through the shipped wizard routes. Returns (resolved, committed, error)."""
    async with Session() as s:
        c, u = await s.get(Organisation, ORG), await s.get(User, USER)
        prev = await me.preview_manual_games(file=h.FakeUpload(h.csv_of(rows)), current_user=u, club=c, db=s)
        req = me.GameResolveRequest(token=prev.get("token"), rows=prev.get("rows") or [], duplicate_mode=mode)
        resolved = await me.resolve_manual_games(req=req, current_user=u, club=c, db=s)
        try:
            return resolved, await me.commit_manual_games(req=req, current_user=u, club=c, db=s), None
        except Exception as e:  # noqa: BLE001 - reported, not raised
            return resolved, None, f"{type(e).__name__}: {getattr(e, 'detail', e)}"


async def game_on(played: str):
    async with Session() as s:
        return (await s.execute(select(ManualGame).where(
            ManualGame.organisation_id == ORG, ManualGame.played_at == date.fromisoformat(played)))).scalars().first()


async def honours_for(game_id) -> list[dict]:
    if game_id is None:
        return []
    async with Session() as s:
        rows = (await s.execute(text(
            "SELECT player_id, player_name, subcategory, season, auto_created, detail FROM player_achievements "
            "WHERE category = 'Premiership' AND linked_game_id = CAST(:g AS UUID) ORDER BY player_name"),
            {"g": str(game_id)})).mappings().all()
    return [dict(r) for r in rows]


async def all_premiership_rows() -> int:
    async with Session() as s:
        return (await s.execute(text("SELECT count(*) FROM player_achievements WHERE category = 'Premiership'"))).scalar()


async def unresolved_reasons() -> dict:
    """{game id: reason} the premierships could not decide, as the dry run reports them."""
    async with Session() as s:
        club = await s.get(Organisation, ORG)
        _wins, unresolved = await premierships.grand_final_wins(s, club)
    return {u["game_id"]: u.get("reason") for u in unresolved}


async def children(game_id) -> tuple:
    """What the scorecard holds, for 'the edit did not touch it'."""
    async with Session() as s:
        q = lambda t: text(f"SELECT count(*) FROM {t} WHERE manual_game_id = :g")
        return tuple([(await s.execute(q(t), {"g": game_id})).scalar() for t in
                      ("manual_batting_innings", "manual_bowling_spells", "manual_innings", "manual_fall_of_wickets")])


async def create_on_form(ids, *, season, grade, played, grand_final, winner="Shoalwater Bay", result="WIN"):
    async with Session() as s:
        c, u = await s.get(Organisation, ORG), await s.get(User, USER)
        payload = dict(
            season_id=str(ids["s:" + season]), grade_id=str(ids[f"g:{season}:{grade}"]) if grade else None,
            played_at=played, opposition="Rival", winning_team=winner, result=result,
            is_grand_final=grand_final,
            batting_innings=[me.ManualBattingIn(player_id=str(ids["p:" + n]), innings_number=1, runs=10 + i)
                             for i, n in enumerate(PLAYERS, 1)])
        return await me.create_manual_game(data=me.ManualGameIn(**payload), current_user=u, club=c, db=s)


async def main() -> None:
    ids = await build()
    details = getattr(me, "update_manual_game_details", None) or absent("update_manual_game_details")
    Details = getattr(me, "ManualGameDetailsIn", None)

    print("\n-- THE COLUMN --")
    check("the CSV template carries an is_grand_final column", "is_grand_final" in me.GAME_CSV_COLUMNS)
    check("a heading written 'Grand Final' lands on it",
          getattr(me, "_GAME_HEADER_BY_CANON", {}).get(me._canon_header("Grand Final")) == "is_grand_final")

    print("\n-- S1: THE CLUB'S C GRADE (1999/00), IMPORTED --")
    # The club's own typed flag for one player, as their CSV upload would leave it: it must be linked to the
    # card, never doubled by an automatic one.
    async with Session() as s:
        await s.execute(text(
            "INSERT INTO player_achievements (org_id, player_id, player_name, season, category, subcategory, "
            "achievement, auto_created) VALUES (:o, :p, :n, '1999_00', 'Premiership', 'C grade', 'Premiership', FALSE)"),
            {"o": ORG, "p": ids["p:Alpha, Anne"], "n": "Alpha, Anne"})
        await s.commit()
    resolved, out, err = await import_sheet(sheet("C1", "2000-03-25", "1999/00", "C grade", grand_final="yes"))
    check("it imports", err is None and (out or {}).get("games_created") == 1, str(err or out))
    g1 = await game_on("2000-03-25")
    check("the game is stored as the grand final, and so as a final",
          bool(getattr(g1, "is_grand_final", False)) and bool(g1 and g1.is_final))
    rows = await honours_for(g1.id if g1 else None)
    check("every player on the card has the premiership, linked to the game", len(rows) == len(PLAYERS), str(len(rows)))
    check("the club's own typed flag for Alpha is linked, not doubled",
          [r["auto_created"] for r in rows if r["player_name"] == "Alpha, Anne"] == [False], str(rows[:1]))
    check("the other three are automatic, filed under the grade",
          sorted(r["auto_created"] for r in rows) == [False, True, True, True]
          and {r["subcategory"] for r in rows} == {"C grade"}, str(rows))
    check("and the commit says one grand final was written", (out or {}).get("grand_finals") == 1, str(out))
    scorecard_kept = await children(g1.id) if g1 else None

    print("\n-- S2: THE D GRADE (2004/05), TICKED ON THE FORM --")
    created = await create_on_form(ids, season="Summer 2004/05", grade="D grade", played="2005-03-19", grand_final=True)
    g2 = await game_on("2005-03-19")
    rows = await honours_for(g2.id if g2 else None)
    check("the form stores the tick", bool(created.get("is_grand_final")) and bool(created.get("is_final")), str(created))
    check("the whole card has the premiership", len(rows) == len(PLAYERS) and all(r["auto_created"] for r in rows),
          str(len(rows)))
    async with Session() as s:
        banner = await premierships.game_premiership_info(s, g2.id) if g2 else []
    check("the scorecard banner finds the club's premiership on the manual game",
          len(banner) == 1 and banner[0]["players"] == len(PLAYERS), str(banner))
    if g2:
        from app.routers.honours import get_premierships
        async with Session() as s:
            page = await get_premierships(ORG, s)
        cards = [p for p in page["premierships"] if p.get("game_id") == str(g2.id)]
        check("the Premierships page links the flag to the scorecard, with the opponent",
              len(cards) == 1 and (cards[0].get("game") or {}).get("opponent") == "Rival"
              and (cards[0].get("game") or {}).get("round_name") == "Grand Final", str(cards[:1]))

    print("\n-- THE GUARDS: NOTHING IS GUESSED --")
    _r, out3, err3 = await import_sheet(sheet("A1", "2011-03-12", "Summer 2010/11", "A grade", grand_final="yes",
                                              winner="Rival", result="Lost by 5 runs"))
    _r, out4, err4 = await import_sheet(sheet("B1", "2011-03-19", "Summer 2010/11", "B grade", grand_final="yes",
                                              winner="", result=""))
    resolved5, out5, err5 = await import_sheet(sheet("E1", "2011-03-26", "Summer 2010/11", "E grade",
                                                     grand_final="yes", winner="Shoalwater Bay", result="Lost by 5 runs"))
    _r, out6, err6 = await import_sheet(sheet("F1", "2011-03-05", "Summer 2010/11", "F grade", is_final="true"))
    g_lost, g_none, g_clash, g_semi = [await game_on(d) for d in ("2011-03-12", "2011-03-19", "2011-03-26", "2011-03-05")]
    check("all four imported", all(e is None for e in (err3, err4, err5, err6)), str((err3, err4, err5, err6)))
    check("a grand final the opposition won earns nothing", await honours_for(g_lost.id if g_lost else None) == [])
    check("a marked game that names no winner earns nothing", await honours_for(g_none.id if g_none else None) == [])
    check("a winner that contradicts the result line earns nothing", await honours_for(g_clash.id if g_clash else None) == [])
    check("a semi final (a final, not marked as the decider) earns nothing", await honours_for(g_semi.id if g_semi else None) == [])
    why = await unresolved_reasons()
    check("the game with no winner is reported, with the reason in words",
          why.get(str(g_none.id) if g_none else "") == "no winner recorded", str(why))
    check("so is the contradiction",
          "disagree" in (why.get(str(g_clash.id) if g_clash else "") or ""), str(why))
    check("a lost final is not reported as unresolved (we know who won)",
          str(g_lost.id if g_lost else "") not in why)
    check("the import warns about the marked game that does not say who won, and still imports it",
          any("do not say who won" in w for w in (resolved5 or {}).get("warnings", []))
          if resolved5 else False, str((resolved5 or {}).get("warnings")))

    print("\n-- S7: MARKED, BUT NO GRADE --")
    await create_on_form(ids, season="Summer 2012/13", grade=None, played="2013-03-09", grand_final=True)
    g7 = await game_on("2013-03-09")
    why = await unresolved_reasons()
    check("it is held back, and the reason names the missing grade",
          await honours_for(g7.id if g7 else None) == [] and "no grade" in (why.get(str(g7.id) if g7 else "") or ""),
          str(why))

    print("\n-- WHAT THE PERSON IS TOLD WHEN THEY SAVE --")
    check("a won grand final says how many players get the premiership",
          (created.get("grand_final") or {}).get("state") == "won" and created["grand_final"].get("players") == len(PLAYERS),
          str(created.get("grand_final")))
    if details and Details:
        statuses = {}
        for label, g in (("lost", g_lost), ("none", g_none), ("clash", g_clash), ("nograde", g7)):
            async with Session() as s:
                c, u = await s.get(Organisation, ORG), await s.get(User, USER)
                r = await details(game_id=str(g.id), data=Details(notes="checked"), current_user=u, club=c, db=s)
            statuses[label] = r.get("grand_final") or {}
        check("a final we lost says so, and writes nothing", statuses["lost"].get("state") == "lost", str(statuses["lost"]))
        check("a final that names no winner says why nothing was written",
              statuses["none"].get("state") == "undecided" and statuses["none"].get("reason") == "no winner recorded",
              str(statuses["none"]))
        check("a contradiction says so", statuses["clash"].get("state") == "undecided"
              and "disagree" in statuses["clash"].get("reason", ""), str(statuses["clash"]))
        check("a game with no grade says that", statuses["nograde"].get("state") == "no_grade", str(statuses["nograde"]))
    else:
        check("the match-details edit exists to report a status", False)

    print("\n-- S8: SET LATER, ON A GAME THAT IS ALREADY STORED (the match-details edit) --")
    _r, out8, err8 = await import_sheet(sheet("A13", "2013-03-16", "Summer 2012/13", "A grade",
                                              result="Won by 7 runs"))
    g8 = await game_on("2013-03-16")
    check("an ordinary imported game starts without the flag and without honours",
          err8 is None and g8 is not None and not getattr(g8, "is_grand_final", False)
          and await honours_for(g8.id) == [])
    before_children = await children(g8.id) if g8 else None
    if details and Details and g8:
        async with Session() as s:
            c, u = await s.get(Organisation, ORG), await s.get(User, USER)
            r1 = await details(game_id=str(g8.id), data=Details(is_grand_final=True), current_user=u, club=c, db=s)
        rows = await honours_for(g8.id)
        check("setting the flag earns the honours at once", len(rows) == len(PLAYERS), str(len(rows)))
        check("it says what changed: the flag, and the final it implies",
              sorted(r1.get("changed") or []) == ["is_final", "is_grand_final"], str(r1.get("changed")))
        check("the scorecard (batting, bowling, innings, fall of wickets) is exactly as it was",
              await children(g8.id) == before_children, f"{await children(g8.id)} vs {before_children}")
        check("the other fields were left alone (an absent key is not a clear)",
              r1.get("opposition") == "Rival" and r1.get("winning_team") == "Shoalwater Bay"
              and r1.get("result") == "Won by 7 runs", str(r1))
        async with Session() as s:
            c, u = await s.get(Organisation, ORG), await s.get(User, USER)
            r2 = await details(game_id=str(g8.id), data=Details(venue="Shoalwater Oval"), current_user=u, club=c, db=s)
        check("editing another field alone leaves the flag set", r2.get("venue") == "Shoalwater Oval"
              and bool(r2.get("is_grand_final")) and len(await honours_for(g8.id)) == len(PLAYERS))
        async with Session() as s:
            c, u = await s.get(Organisation, ORG), await s.get(User, USER)
            await details(game_id=str(g8.id), data=Details(is_grand_final=False), current_user=u, club=c, db=s)
        check("clearing the flag takes the automatic honours back", await honours_for(g8.id) == [])
        async with Session() as s:
            logs = (await s.execute(select(ManualEditLog).where(
                ManualEditLog.target_id == str(g8.id)).order_by(ManualEditLog.id))).scalars().all()
        details_logs = [lg for lg in logs if lg.action == "update_details"]
        check("each edit is logged on its own, holding only what changed",
              len(details_logs) == 3 and details_logs[1].before_json == {"venue": None}
              and details_logs[1].after_json == {"venue": "Shoalwater Oval"},
              str([(lg.action, lg.before_json) for lg in logs]))
        undo = getattr(me, "undo_edit", None)
        if undo and len(details_logs) == 3:
            async with Session() as s:
                c, u = await s.get(Organisation, ORG), await s.get(User, USER)
                await undo(log_id=details_logs[2].id, current_user=u, club=c, db=s)
            check("undoing the clear puts the flag and the honours back", len(await honours_for(g8.id)) == len(PLAYERS))
            async with Session() as s:
                c, u = await s.get(Organisation, ORG), await s.get(User, USER)
                await undo(log_id=details_logs[0].id, current_user=u, club=c, db=s)
            check("undoing the first edit clears them again", await honours_for(g8.id) == [])
            check("and the scorecard still holds everything it held", await children(g8.id) == before_children,
                  f"{await children(g8.id)} vs {before_children}")
            g8b = await game_on("2013-03-16")
            check("the venue edit, not undone, is still there", g8b.venue == "Shoalwater Oval")
        # leave it marked, for the full-edit and delete checks below
        async with Session() as s:
            c, u = await s.get(Organisation, ORG), await s.get(User, USER)
            await details(game_id=str(g8.id), data=Details(is_grand_final=True), current_user=u, club=c, db=s)
    else:
        check("the match-details edit exists", False)

    print("\n-- THE FULL EDIT: AN ABSENT FLAG IS NOT A CLEAR --")
    if g2:
        def full(**extra):
            return me.ManualGameIn(
                season_id=str(ids["s:Summer 2004/05"]), grade_id=str(ids["g:Summer 2004/05:D grade"]),
                played_at="2005-03-19", opposition="Rival", winning_team="Shoalwater Bay", result="WIN",
                is_final=True,
                batting_innings=[me.ManualBattingIn(player_id=str(ids["p:" + n]), innings_number=1, runs=20 + i)
                                 for i, n in enumerate(PLAYERS, 1)], **extra)
        async with Session() as s:
            c, u = await s.get(Organisation, ORG), await s.get(User, USER)
            await me.update_manual_game(game_id=str(g2.id), data=full(), current_user=u, club=c, db=s)
        check("a form that does not send the flag leaves it set, and the honours stand",
              is_marked(await game_on("2005-03-19")) and len(await honours_for(g2.id)) == len(PLAYERS))
        async with Session() as s:
            c, u = await s.get(Organisation, ORG), await s.get(User, USER)
            await me.update_manual_game(game_id=str(g2.id), data=full(is_grand_final=False),
                                        current_user=u, club=c, db=s)
        check("an explicit false clears it, and the automatic honours go",
              not is_marked(await game_on("2005-03-19")) and await honours_for(g2.id) == [])
        async with Session() as s:
            c, u = await s.get(Organisation, ORG), await s.get(User, USER)
            await me.update_manual_game(game_id=str(g2.id), data=full(is_grand_final=True),
                                        current_user=u, club=c, db=s)
        check("ticking it again brings them back", len(await honours_for(g2.id)) == len(PLAYERS))

    print("\n-- AN OVERWRITE IMPORT WITH A BLANK CELL KEEPS THE FLAG --")
    if g1:
        _r, outo, erro = await import_sheet(sheet("C1", "2000-03-25", "1999/00", "C grade"), mode="overwrite")
        g1b = await game_on("2000-03-25")
        check("a re-import that replaces the game, with no is_grand_final cell, keeps it marked",
              erro is None and g1b is not None and is_marked(g1b), str(erro or outo))
        check("and the honours are on the replacement game (a new id)",
              g1b is not None and len(await honours_for(g1b.id)) == len(PLAYERS)
              and await honours_for(g1.id) == [], f"{await honours_for(g1b.id if g1b else None)}")
        _r, outo, erro = await import_sheet(sheet("C1", "2000-03-25", "1999/00", "C grade", grand_final="no"),
                                            mode="overwrite")
        g1c = await game_on("2000-03-25")
        check("an explicit 'no' on the sheet is a decision, and clears it",
              erro is None and g1c is not None and not is_marked(g1c))

    print("\n-- S9: A MARKED IMPORT THAT IS A SYNCED GAME COUNTS ONCE --")
    async with Session() as s:
        twin, home, away = uuid.uuid4(), "SBCC A Grade", "Rival A"
        await s.execute(text(
            "INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_org_id, result, winning_team, "
            "is_final, round_name, status) VALUES (:i, :g, '2014-03-15', :h, :a, :o, 'WIN', :h, TRUE, 'Grand Final', "
            "'COMPLETED')"), {"i": twin, "g": ids["g:Summer 2013/14:A grade"], "h": home, "a": away, "o": ORG})
        for n in PLAYERS[:2]:
            await s.execute(text("INSERT INTO game_appearances (game_id, player_id, team_name) VALUES (:g, :p, :t)"),
                            {"g": twin, "p": ids["p:" + n], "t": home})
        await s.commit()
    created9 = await create_on_form(ids, season="Summer 2013/14", grade="A grade", played="2014-03-15", grand_final=True)
    async with Session() as s:
        await s.execute(text("UPDATE manual_games SET superseded_by_game_id = :t, pair_prefers_import = TRUE "
                             "WHERE id = CAST(:m AS UUID)"), {"t": twin, "m": created9["id"]})
        await s.commit()
    async with Session() as s:
        rec = await premierships.reconcile(s, ORG, apply=True)
    from_twin, from_manual = await honours_for(twin), await honours_for(created9["id"])
    check("the premiership is written from the synced game", len(from_twin) == 2, str(len(from_twin)))
    check("and not a second time from the imported stand-in for it", from_manual == [], str(len(from_manual)))

    print("\n-- RECONCILE IS STABLE, AND A DELETED GAME TAKES ITS AUTOMATIC HONOURS WITH IT --")
    before = await all_premiership_rows()
    async with Session() as s:
        await premierships.reconcile(s, ORG, apply=True)
    check("running it again adds and removes nothing", await all_premiership_rows() == before)
    if g8:
        async with Session() as s:
            c, u = await s.get(Organisation, ORG), await s.get(User, USER)
            await me.delete_manual_game(game_id=str(g8.id), current_user=u, club=c, db=s)
        check("deleting the marked game removes the honours it earned", await honours_for(g8.id) == [])

    print(f"\n{h.PASS} passed, {h.FAIL} failed")
    await h.engine.dispose()
    sys.exit(1 if h.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
