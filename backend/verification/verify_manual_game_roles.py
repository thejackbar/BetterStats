"""Captain and wicket keeper on a hand-entered or imported game, and the script that adds them to matches
already imported. Real Postgres.

Reported by Shoalwater Bay (Oct 2026): the captain and wicket keeper they entered in CSFW for each match are
missing from BetterCricket, and a hand-entered or imported match had nowhere to hold either. The converter now
reads both flags out of the CSFW files (proved on the club's own archive, see docs/csfw-data-extraction.md), and:

  (a) the scorecard CSV carries `is_captain` and `is_wicketkeeper` columns, so a club that has not imported yet
      brings them in with the match;
  (b) a club that HAS imported runs `app.scripts.apply_game_roles` over the converter's `manual_game_roles.csv`,
      which adds the roles to the matches already there, finding each match as the importer does and each
      player among those on that match's card;
  (c) an admin can set or change them on any hand-entered or imported match, from the full form or from the
      match-details edit, which never touches the scorecard.

Drives the SHIPPED route bodies and the shipped script against a real Postgres.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/roles_verify?host=/tmp&port=5439 \\
  python verification/verify_manual_game_roles.py

Control run: check out the previous commit and run it again. It REPORTS the missing parts rather than
crashing on the first absent name.
"""
from __future__ import annotations

import asyncio
import csv
import importlib
import io
import os
import sys
import tempfile
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from sqlalchemy import select, text

import verify_manual_grand_final as g          # its schema, club, sheets and helpers; main() is guarded
import verify_manual_side_names as h
from app.models.db import ManualEditLog, Organisation, User
from app.routers import manual_entries as me

check, Session = h.check, h.Session
ORG, USER = h.ORG, h.USER
PLAYERS = g.PLAYERS
ALPHA, BRAVO, CHARLIE, DELTA = PLAYERS


def load(name):
    try:
        return importlib.import_module(name)
    except Exception as e:  # noqa: BLE001 - reported, not raised
        print(f"  (absent: {name}: {e})")
        return None


def role_sheet(key, played, season, grade, *, captain=None, keepers=(), **kw) -> list[dict]:
    rows = g.sheet(key, played, season, grade, **kw)
    for r in rows:
        r["is_captain"] = "true" if r["player_name"] == captain else ""
        r["is_wicketkeeper"] = "true" if r["player_name"] in keepers else ""
    return rows


async def import_text(csv_text: str, mode: str = "skip"):
    async with Session() as s:
        c, u = await s.get(Organisation, ORG), await s.get(User, USER)
        up = h.FakeUpload(csv_text)
        prev = await me.preview_manual_games(file=up, current_user=u, club=c, db=s)
        req = me.GameResolveRequest(token=prev.get("token"), rows=prev.get("rows") or [], duplicate_mode=mode)
        await me.resolve_manual_games(req=req, current_user=u, club=c, db=s)
        try:
            return await me.commit_manual_games(req=req, current_user=u, club=c, db=s), None
        except Exception as e:  # noqa: BLE001
            return None, f"{type(e).__name__}: {getattr(e, 'detail', e)}"


def csv_with_headings(rows: list[dict], rename: dict) -> str:
    cols = [c for c in me.GAME_CSV_COLUMNS if c not in ("is_captain", "is_wicketkeeper")] + ["is_captain", "is_wicketkeeper"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=[rename.get(c, c) for c in cols], restval="")
    w.writeheader()
    for r in rows:
        w.writerow({rename.get(c, c): r.get(c, "") for c in cols})
    return buf.getvalue()


async def roles_of(game_id) -> dict:
    """{player name: 'C', 'K' or 'CK'} stored for a game; {} where the table is absent (the control)."""
    if game_id is None:
        return {}
    async with Session() as s:
        try:
            rows = (await s.execute(text(
                "SELECT p.name, r.is_captain, r.is_wicket_keeper FROM manual_game_roles r "
                "JOIN players p ON p.id = r.player_id WHERE r.manual_game_id = CAST(:g AS UUID) ORDER BY r.id"),
                {"g": str(game_id)})).all()
        except Exception:
            await s.rollback()
            return {}
    return {n: ("C" if c else "") + ("K" if k else "") for n, c, k in rows}


async def pid(name: str) -> str:
    async with Session() as s:
        return str((await s.execute(text("SELECT id FROM players WHERE organisation_id = :o AND name = :n"),
                                    {"o": ORG, "n": name})).scalar())


async def route(fn, **kw):
    async with Session() as s:
        c, u = await s.get(Organisation, ORG), await s.get(User, USER)
        return await fn(current_user=u, club=c, db=s, **kw)


async def main() -> None:
    ids = await g.build()
    async with h.engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY, created_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL, user_id UUID,
                action TEXT NOT NULL, target_type TEXT, target_id TEXT, details JSONB DEFAULT '{}')"""))
        try:
            from app.services.manual_game_roles_ddl import STATEMENTS as ROLES_DDL
        except ImportError:      # the control commit has no such table
            ROLES_DDL = []
        for stmt in ROLES_DDL:
            await conn.execute(text(stmt))
    P = {n: await pid(n) for n in PLAYERS}
    Details = getattr(me, "ManualGameDetailsIn", None)
    details = getattr(me, "update_manual_game_details", None)

    print("\n-- THE COLUMNS --")
    check("the scorecard CSV carries is_captain and is_wicketkeeper",
          {"is_captain", "is_wicketkeeper"} <= set(me.GAME_CSV_COLUMNS))
    canon = getattr(me, "_GAME_HEADER_BY_CANON", {})
    check("headings 'Captain' and 'Wicket Keeper' land on them",
          canon.get(me._canon_header("Captain")) == "is_captain"
          and canon.get(me._canon_header("Wicket Keeper")) == "is_wicketkeeper")

    print("\n-- AN IMPORT NAMES THE CAPTAIN AND THE KEEPERS --")
    out, err = await import_text(h.csv_of(role_sheet("R1", "2011-03-12", "Summer 2010/11", "A grade",
                                                      captain=BRAVO, keepers=(DELTA,))))
    g1 = await g.game_on("2011-03-12")
    check("it imports, and says one captain and one keeper were named",
          err is None and (out or {}).get("captains_named") == 1 and (out or {}).get("keepers_named") == 1,
          str(err or out))
    check("Bravo is the captain and Delta the keeper", await roles_of(g1.id if g1 else None)
          == {BRAVO: "C", DELTA: "K"}, str(await roles_of(g1.id if g1 else None)))
    out, err = await import_text(h.csv_of(role_sheet("R2", "2011-03-19", "Summer 2010/11", "B grade",
                                                      captain=ALPHA, keepers=(CHARLIE, DELTA))))
    g2 = await g.game_on("2011-03-19")
    check("two keepers in one match (a change mid-match) are both kept",
          await roles_of(g2.id if g2 else None) == {ALPHA: "C", CHARLIE: "K", DELTA: "K"},
          str(await roles_of(g2.id if g2 else None)))
    check("the captain who is also the keeper holds both roles",
          (lambda r: r == {ALPHA: "CK"})(await roles_of((await _import_one(role_sheet(
              "R3", "2011-03-26", "Summer 2010/11", "E grade", captain=ALPHA, keepers=(ALPHA,)), "2011-03-26")))))
    got = await route(me.get_manual_game, game_id=str(g1.id)) if g1 else {}
    check("GET returns the roles as player ids",
          (got.get("roles") or {}) == {"captain_player_ids": [P[BRAVO]], "wicket_keeper_player_ids": [P[DELTA]]},
          str(got.get("roles")))

    print("\n-- OTHER HEADINGS, AND A SHEET THAT SAYS NOTHING --")
    out, err = await import_text(csv_with_headings(role_sheet("R4", "2011-04-02", "Summer 2010/11", "F grade",
                                                              captain=CHARLIE, keepers=(BRAVO,)),
                                                   {"is_captain": "Captain", "is_wicketkeeper": "Wicket Keeper"}))
    g4 = await g.game_on("2011-04-02")
    check("a sheet headed 'Captain' and 'Wicket Keeper' is read the same",
          err is None and await roles_of(g4.id if g4 else None) == {CHARLIE: "C", BRAVO: "K"}, str(err))
    out, err = await import_text(h.csv_of(g.sheet("R5", "2012-03-03", "Summer 2012/13", "A grade")))
    g5 = await g.game_on("2012-03-03")
    check("a sheet with no role cells stores no roles (and says none were named)",
          err is None and await roles_of(g5.id if g5 else None) == {} and (out or {}).get("captains_named") == 0, str(out))

    print("\n-- AN OVERWRITE IMPORT KEEPS ROLES THE SHEET DOES NOT MENTION --")
    out, err = await import_text(h.csv_of(g.sheet("R1", "2011-03-12", "Summer 2010/11", "A grade")), mode="overwrite")
    g1b = await g.game_on("2011-03-12")
    check("replacing a game with a sheet that names no roles keeps its captain and keeper",
          err is None and g1b is not None and await roles_of(g1b.id) == {BRAVO: "C", DELTA: "K"},
          str(err or await roles_of(g1b.id if g1b else None)))
    out, err = await import_text(h.csv_of(role_sheet("R1", "2011-03-12", "Summer 2010/11", "A grade",
                                                      captain=CHARLIE, keepers=(ALPHA,))), mode="overwrite")
    g1c = await g.game_on("2011-03-12")
    check("a sheet that names them replaces them",
          g1c is not None and await roles_of(g1c.id) == {CHARLIE: "C", ALPHA: "K"}, str(await roles_of(g1c.id if g1c else None)))

    print("\n-- THE FORM: SET, LEAVE ALONE, CLEAR --")
    created = await g.create_on_form(ids, season="Summer 2004/05", grade="D grade", played="2005-03-19", grand_final=False)
    gf = await g.game_on("2005-03-19")

    async def edit(**extra):
        return await route(me.update_manual_game, game_id=str(gf.id), data=me.ManualGameIn(
            season_id=str(ids["s:Summer 2004/05"]), grade_id=str(ids["g:Summer 2004/05:D grade"]),
            played_at="2005-03-19", opposition="Rival", winning_team="Shoalwater Bay", result="WIN",
            batting_innings=[me.ManualBattingIn(player_id=str(ids["p:" + n]), innings_number=1, runs=10 + i)
                             for i, n in enumerate(PLAYERS, 1)], **extra))
    await edit(captain_player_ids=[P[ALPHA]], wicket_keeper_player_ids=[P[BRAVO]])
    check("the form sets a captain and a keeper", await roles_of(gf.id) == {ALPHA: "C", BRAVO: "K"}, str(await roles_of(gf.id)))
    await edit()
    check("an edit that does not send them leaves them (an absent key is not a clear)",
          await roles_of(gf.id) == {ALPHA: "C", BRAVO: "K"}, str(await roles_of(gf.id)))
    await edit(captain_player_ids=[P[CHARLIE]])
    check("sending only the captain changes only the captain",
          await roles_of(gf.id) == {CHARLIE: "C", BRAVO: "K"}, str(await roles_of(gf.id)))
    await edit(wicket_keeper_player_ids=None)
    check("an explicit null clears that role and leaves the other",
          await roles_of(gf.id) == {CHARLIE: "C"}, str(await roles_of(gf.id)))
    await edit(captain_player_ids=[])
    check("an empty list clears it too, and a player with no role has no row", await roles_of(gf.id) == {})
    outsider = uuid.uuid4()
    async with Session() as s:
        await s.execute(text("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, 'Other CC', 'other-cc', true)"), {"i": uuid.uuid4()})
        oid = (await s.execute(text("SELECT id FROM organisations WHERE slug = 'other-cc'"))).scalar()
        await s.execute(text("INSERT INTO players (id, organisation_id, name, status) VALUES (:i, :o, 'Outsider, Olly', 'active')"),
                        {"i": outsider, "o": oid})
        await s.commit()
    try:
        await edit(captain_player_ids=[str(outsider)])
        refused = False
    except HTTPException as e:
        refused = e.status_code == 404
    check("another club's player cannot be made captain", refused and await roles_of(gf.id) == {})

    print("\n-- THE MATCH-DETAILS EDIT: ROLES WITHOUT TOUCHING THE SCORECARD --")
    if details and Details:
        before_children = await g.children(g5.id)
        r1 = await route(details, game_id=str(g5.id), data=Details(
            captain_player_ids=[P[DELTA]], wicket_keeper_player_ids=[P[ALPHA]]))
        check("sets them on an imported match", await roles_of(g5.id) == {DELTA: "C", ALPHA: "K"}, str(await roles_of(g5.id)))
        check("and says so, without claiming any other field changed",
              sorted(r1.get("changed") or []) == ["captain", "wicket_keeper"], str(r1.get("changed")))
        check("the scorecard is exactly as it was", await g.children(g5.id) == before_children,
              f"{await g.children(g5.id)} vs {before_children}")
        r2 = await route(details, game_id=str(g5.id), data=Details(venue="Shoalwater Oval"))
        check("editing another field leaves the roles", await roles_of(g5.id) == {DELTA: "C", ALPHA: "K"}
              and r2.get("venue") == "Shoalwater Oval")
        r3 = await route(details, game_id=str(g5.id), data=Details(captain_player_ids=[P[DELTA]]))
        check("sending what is already there changes nothing and logs nothing",
              r3.get("changed") == [], str(r3.get("changed")))
        async with Session() as s:
            logs = (await s.execute(select(ManualEditLog).where(ManualEditLog.target_id == str(g5.id))
                                    .order_by(ManualEditLog.id))).scalars().all()
        dl = [lg for lg in logs if lg.action == "update_details"]
        check("two edits are logged, the first holding the role lists it changed",
              len(dl) == 2 and dl[0].before_json == {"captain_player_ids": [], "wicket_keeper_player_ids": []}
              and dl[0].after_json == {"captain_player_ids": [P[DELTA]], "wicket_keeper_player_ids": [P[ALPHA]]},
              str([(lg.action, lg.before_json) for lg in logs]))
        undo = getattr(me, "undo_edit", None)
        if undo and dl:
            await route(undo, log_id=dl[0].id)
            check("undoing it puts the roles back as they were (none)", await roles_of(g5.id) == {})
            check("and the scorecard is untouched", await g.children(g5.id) == before_children)
    else:
        check("the match-details edit takes captain and wicket keeper", False)

    print("\n-- A DELETED GAME'S ROLES COME BACK WITH IT --")
    gid4 = g4.id if g4 else None
    if gid4:
        async with Session() as s:
            c, u = await s.get(Organisation, ORG), await s.get(User, USER)
            await me.delete_manual_game(game_id=str(gid4), current_user=u, club=c, db=s)
        check("deleting the game takes its roles with it", await roles_of(gid4) == {})
        async with Session() as s:
            log = (await s.execute(select(ManualEditLog).where(
                ManualEditLog.target_id == str(gid4), ManualEditLog.action == "delete"))).scalars().first()
        await route(me.undo_edit, log_id=log.id)
        check("undoing the delete restores the captain and the keeper",
              await roles_of(gid4) == {CHARLIE: "C", BRAVO: "K"}, str(await roles_of(gid4)))

    print("\n-- THE PREMIERSHIP CAPTAIN --")
    out, err = await import_text(h.csv_of(role_sheet("GF", "2000-03-25", "1999/00", "C grade", grand_final="yes",
                                                      captain=ALPHA, keepers=(DELTA,))))
    gg = await g.game_on("2000-03-25")
    hon = await g.honours_for(gg.id if gg else None)
    check("every player on a marked grand final the club won has the premiership", len(hon) == len(PLAYERS), str(len(hon)))
    check("the captain's honour carries the 'Captain' detail, and nobody else's does",
          {r["player_name"]: r["detail"] for r in hon} == {ALPHA: "Captain", BRAVO: None, CHARLIE: None, DELTA: None},
          str({r["player_name"]: r["detail"] for r in hon}))

    print("\n-- A PLAYER MERGE CARRIES THE ROLE --")
    carry = load("app.services.merge_carry")
    check("the roles table is on merge_carry.CARRIED",
          bool(carry) and any(t[0] == "manual_game_roles" for t in carry.CARRIED))
    cleanup = load("app.services.import_cleanup")
    check("and a player holding a role cannot be deleted as 'empty'",
          bool(cleanup) and any(t[1] == "manual_game_roles" for t in cleanup.BLOCKING_REFS))

    print("\n-- THE SCRIPT: ROLES ONTO MATCHES ALREADY IMPORTED --")
    script = load("app.scripts.apply_game_roles")
    if script is None:
        check("app.scripts.apply_game_roles exists", False)
    else:
        # Matches imported WITHOUT roles, the state Shoalwater Bay is in.
        await import_text(h.csv_of(g.sheet("X1", "2012-03-10", "Summer 2012/13", "A grade")))
        await import_text(h.csv_of(role_sheet("X2", "2012-03-17", "Summer 2012/13", "A grade", captain=BRAVO)))
        await import_text(h.csv_of(g.sheet("X4", "2012-03-24", "Summer 2012/13", "A grade")))
        x1, x2, x4 = [await g.game_on(d) for d in ("2012-03-10", "2012-03-17", "2012-03-24")]
        # A Cricket Australia game on one more date: its roles come from the team sheet.
        async with Session() as s:
            ca = uuid.uuid4()
            await s.execute(text(
                "INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_org_id, status) VALUES "
                "(:i, :g, '2012-03-31', 'SBCC A Grade', 'Rival A', :o, 'COMPLETED')"),
                {"i": ca, "g": ids["g:Summer 2012/13:A grade"], "o": ORG})
            await s.commit()

        def rows_for(key, played, who, flag):
            return [dict(game_key=key, season_name="Summer 2012/13", grade_name="A grade", played_at=played,
                         opposition="Rival", player_name=n, is_captain="true" if flag == "C" else "",
                         is_wicketkeeper="true" if flag == "K" else "") for n in who]
        cols = ["game_key", "season_name", "grade_name", "played_at", "opposition", "player_name",
                "is_captain", "is_wicketkeeper"]
        allrows = (rows_for("X1", "2012-03-10", ["Anne Alpha"], "C")            # a name written the other way round
                   + rows_for("X1", "2012-03-10", [BRAVO], "K")
                   + rows_for("X2", "2012-03-17", [DELTA], "C")                 # X2 already has a captain
                   + rows_for("X2", "2012-03-17", [CHARLIE], "K")
                   + rows_for("X3", "2012-04-07", [ALPHA], "C")                 # no such match
                   + rows_for("X4", "2012-03-24", ["Zed, Nobody"], "C")         # not on the card
                   + rows_for("X4", "2012-03-24", [ALPHA], "K")
                   + rows_for("X5", "2012-03-31", [ALPHA], "C"))                # a Cricket Australia game
        tmp = Path(tempfile.mkdtemp()) / "manual_game_roles.csv"
        with tmp.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(allrows)

        games = script.read_roles(tmp)
        check("the file is read: five matches and the names on each", len(games) == 5 and games["X1"]["captains"] == ["Anne Alpha"])
        # Name matching on a card: exact first, then the same surname with a first name that agrees.
        def card_of(*names):
            return [dict(id=f"id-{i}", name=n, display_name_override=None) for i, n in enumerate(names)]
        seen = script.Counter()
        def resolve_full(nm, *card):
            try:
                return script._resolve(nm, card_of(*card), seen)
            except TypeError:               # the control commit's _resolve takes no variants tally
                return script._resolve(nm, card_of(*card))
        res = lambda nm, *card: resolve_full(nm, *card)[0]
        check("Ken is Kenneth, Rod is Rodney, Steve is Steven (a short form)",
              res("Staines, Ken", "Staines, Kenneth", "Hind, Darren") == "id-0"
              and res("Cribbs, Rod", "Cribbs, Michael", "Cribbs, Rodney") == "id-1"
              and res("Salter, Steve", "Salter, Steven") == "id-0")
        check("Mick is Michael and Andy is Andrew (listed nicknames)",
              res("Winter, Mick", "Winter, Michael") == "id-0" and res("Lawler, Andy", "Lawler, Andrew") == "id-0")
        check("a one-letter typo and a middle name left off agree",
              res("Puntigam, Dayman", "Puntigam, Daymon") == "id-0" and res("Baldwin, Julian Andrew", "Baldwin, Julian") == "id-0"
              and res("Trigg, Griffen", "Trigg, Griff") == "id-0")
        check("an exact spelling wins over a variant", res("Staines, Josh", "Staines, Kenneth", "Staines, Josh") == "id-1")
        check("the absent player is not replaced by a relative (Mick absent, Adam and Mark on the card)",
              res("Winter, Mick", "Winter, Adam", "Winter, Mark") is None)
        check("a different surname never matches", res("Staines, Ken", "Stains, Kenneth", "Hind, Ken") is None)
        check("two people who both fit is listed, not guessed",
              res("Cribbs, Rod", "Cribbs, Rodney", "Cribbs, Rodger") is None
              and "more than one" in str(resolve_full("Cribbs, Rod", "Cribbs, Rodney", "Cribbs, Rodger")[1]))
        check("every variant pairing is tallied for the plan to show",
              ("Staines, Ken", "Staines, Kenneth") in seen and ("Winter, Mick", "Winter, Michael") in seen, str(dict(seen)))
        rows, left, unplaced = await script.plan(str(ORG), games)
        by_date = {r["date"]: r for r in rows}
        check("the plan changes three matches: X1, X2 (keeper only) and X4 (keeper only)",
              sorted(by_date) == ["2012-03-10", "2012-03-17", "2012-03-24"], str(sorted(by_date)))
        check("X1's captain is found though the file writes the name the other way round",
              by_date.get("2012-03-10", {}).get("add_captains") == [P[ALPHA]]
              and by_date["2012-03-10"]["add_keepers"] == [P[BRAVO]])
        check("X2 keeps the captain it already has, and gains the keeper",
              by_date.get("2012-03-17", {}).get("add_captains") == [] and by_date["2012-03-17"]["add_keepers"] == [P[CHARLIE]])
        check("X4 gains its keeper; the name that is not on its card is listed, not guessed",
              by_date.get("2012-03-24", {}).get("add_captains") == []
              and [u["name"] for u in unplaced] == ["Zed, Nobody"], str(unplaced))
        why = " | ".join(left)
        check("the match with no counterpart, the Cricket Australia game and the held captain are each listed",
              "no match in BetterCricket" in why and "Cricket Australia game" in why and "already has a captain" in why, why)
        check("a dry run writes nothing", await roles_of(x1.id) == {} and await roles_of(x4.id) == {})

        for label, kw in (("a wrong --expect", dict(expect=9, by="t")), ("a missing --by", dict(expect=len(rows)))):
            try:
                await script.apply(str(ORG), rows, kw.get("expect"), kw.get("by"))
                refused = False
            except SystemExit:
                refused = True
            check(f"refuses {label}", refused and await roles_of(x1.id) == {})
        await script.apply(str(ORG), rows, len(rows), "tester")
        check("apply adds the roles", await roles_of(x1.id) == {ALPHA: "C", BRAVO: "K"}
              and await roles_of(x4.id) == {ALPHA: "K"}, f"{await roles_of(x1.id)} {await roles_of(x4.id)}")
        check("X2 has the captain it always had, plus the keeper",
              await roles_of(x2.id) == {BRAVO: "C", CHARLIE: "K"}, str(await roles_of(x2.id)))
        async with Session() as s:
            audits = (await s.execute(text("SELECT id, details FROM audit_logs WHERE action = :a"),
                                      {"a": script.ACTION})).all()
        check("one audit entry holds every match written", len(audits) == 1 and len(audits[0][1]["changes"]) == 3, str(audits))
        rows2, left2, _u = await script.plan(str(ORG), games)
        check("running it again has nothing to change", rows2 == [], str(rows2))
        await script.restore(audits[0][0], "tester")
        check("restore takes exactly what the run added back off",
              await roles_of(x1.id) == {} and await roles_of(x4.id) == {})
        check("and leaves the captain somebody had already set", await roles_of(x2.id) == {BRAVO: "C"},
              str(await roles_of(x2.id)))
        try:
            await script.restore(audits[0][0], "tester")
            again = False
        except SystemExit:
            again = True
        check("an entry restores once", again)

    print("\n-- THE TABLE'S OWN DDL (the migration and the lifespan run this list) --")
    if ROLES_DDL:
        keep = g1c.id if g1c else None
        async with h.engine.begin() as conn:
            await conn.execute(text("DROP TABLE manual_game_roles"))
            for stmt in ROLES_DDL:
                await conn.execute(text(stmt))
            for stmt in ROLES_DDL:           # the lifespan re-runs it every boot
                await conn.execute(text(stmt))
        async with Session() as s:
            await s.execute(text("INSERT INTO manual_game_roles (manual_game_id, player_id, is_captain) "
                                 "VALUES (:g, :p, TRUE)"), {"g": keep, "p": P[ALPHA]})
            await s.commit()
        try:
            async with Session() as s:
                await s.execute(text("INSERT INTO manual_game_roles (manual_game_id, player_id) VALUES (:g, :p)"),
                                {"g": keep, "p": P[ALPHA]})
                await s.commit()
            dup = False
        except Exception:
            dup = True
        check("created from the shared list, re-runnable, one row per game and player", dup)
        async with Session() as s:
            await s.execute(text("DELETE FROM manual_games WHERE id = :g"), {"g": keep})
            await s.commit()
            left_rows = (await s.execute(text("SELECT count(*) FROM manual_game_roles WHERE manual_game_id = :g"),
                                         {"g": keep})).scalar()
        check("deleting the game deletes its roles (ON DELETE CASCADE)", left_rows == 0)
    else:
        check("services/manual_game_roles_ddl exists", False)

    print(f"\n{h.PASS} passed, {h.FAIL} failed")
    await h.engine.dispose()
    sys.exit(1 if h.FAIL else 0)


async def _import_one(rows, played):
    await import_text(h.csv_of(rows))
    gm = await g.game_on(played)
    return gm.id if gm else None


if __name__ == "__main__":
    asyncio.run(main())
