"""A club types the fall of wickets Cricket Australia is missing, and it sticks. Real Postgres.

Reported off a club card: six wickets fell, Cricket Australia held four fall-of-wicket rows
(1, 3, 4 and 5), so the innings gave no partnerships. The club has the rest in its scorebook.

This drives the SHIPPED route bodies (`routers/game_fow.py`), the shipped `fow_overrides`
service, the shipped `participant_relink.attach_innings_detail` (the code sync and the re-read
run) and the shipped records route over a real Postgres:

  * a short card now gives the stands its figures settle (1st, 4th, 5th) with no club typing;
  * the editor opens on the club's own innings only, says what is missing and why;
  * saving all six wickets gives six stands (73, 77, 181, 25, 25, 19), replaces the synced
    rows for that innings, reaches the records board, and writes one audit row;
  * every refusal 422s and leaves the stored rows exactly as they were;
  * an opposition innings, an uploaded card and a game from another club are refused;
  * a Full Rebuild (the game deleted and stored again) loses the synced rows but the typed
    wickets are applied again: the club's typing outlives it;
  * a stand another club holds in the same innings survives a save;
  * Reset puts Cricket Australia's rows and stands back.

Run:  DATABASE_URL=postgresql+asyncpg://root@/fowedit?host=/var/run/postgresql \
      python verification/verify_fow_overrides.py
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
from sqlalchemy import select, text

import verify_club_records as base   # its engine, schema and views; main() is guarded
from app.models.db import Organisation, User
from app.routers.records import get_records

Session, engine = base.Session, base.engine
OURS, THEIRS = base.OURS, base.THEIRS
check = base.check

MISSING: list[str] = []
try:
    from app.routers import game_fow
    from app.services import fow_overrides as fo
    from app.services import grassroots_scores_client as gr
    from app.services import participant_relink as relink
    from app.services.fow_override_ddl import STATEMENTS as FOW_DDL
except Exception as exc:  # control run against the previous commit
    MISSING.append(str(exc))

S = uuid.uuid4(); G = uuid.uuid4()
T_US, T_OPP = uuid.uuid4(), uuid.uuid4()
NAMES = ["Payne", "Hall", "Bivens", "Sweet", "Cox", "Menezes", "Ito", "Lee"]
GUIDS = {n: uuid.uuid4() for n in NAMES}
PIDS = {n: uuid.uuid4() for n in NAMES}
OPP_GUIDS = {n: uuid.uuid4() for n in ("O1", "O2", "O3")}
GAME, MANUAL_GAME, OTHER_GAME = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
USER = uuid.uuid4()
RUNS = {"Payne": 40, "Hall": 33, "Bivens": 160, "Sweet": 12, "Cox": 60, "Menezes": 14, "Ito": 20, "Lee": 5}
OUT = {"Payne", "Hall", "Bivens", "Sweet", "Menezes", "Cox"}   # six wickets; Ito and Lee not out


def card(fow_ours: list[tuple]) -> dict:
    def bat(n, order):
        out = n in OUT
        return {"participantId": str(GUIDS[n]), "batOrder": order, "runsScored": RUNS[n],
                "dismissalTypeId": 3 if out else 1, "dismissalType": "Bowled" if out else "Not Out",
                "playerShortName": f"{n[0]} {n}"}
    opp = [{"participantId": str(g), "batOrder": i, "runsScored": 20, "dismissalTypeId": 3,
            "dismissalType": "Bowled", "playerShortName": f"{k}"} for i, (k, g) in enumerate(OPP_GUIDS.items(), 1)]
    return {
        "teams": [
            {"id": str(T_US), "owningOrganisation": {"id": str(OURS)},
             "players": [{"participantId": str(g)} for g in GUIDS.values()]},
            {"id": str(T_OPP), "owningOrganisation": {"id": str(THEIRS)},
             "players": [{"participantId": str(g)} for g in OPP_GUIDS.values()]},
        ],
        "innings": [
            {"inningsOrder": 1, "battingTeamId": str(T_US),
             "batting": [bat(n, i) for i, n in enumerate(NAMES, 1)],
             "fallOfWickets": [{"order": o, "runs": r, "participantId": str(GUIDS[n]), "playerShortName": f"{n[0]} {n}"}
                               for o, r, n in fow_ours]},
            {"inningsOrder": 2, "battingTeamId": str(T_OPP), "batting": opp,
             "fallOfWickets": [{"order": 1, "runs": 20, "participantId": str(OPP_GUIDS["O1"]), "playerShortName": "O1"},
                               {"order": 2, "runs": 41, "participantId": str(OPP_GUIDS["O2"]), "playerShortName": "O2"}]},
        ],
    }


CA_FOW = [(1, 73, "Payne"), (3, 331, "Bivens"), (4, 356, "Sweet"), (5, 381, "Menezes")]
CARD = card(CA_FOW)


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)
        await ex("INSERT INTO organisations (id, name, is_active, slug) VALUES (:i, 'Our Club', true, 'our-club')", i=OURS)
        await ex("INSERT INTO organisations (id, name, is_active) VALUES (:i, 'Their Club', true)", i=THEIRS)
        await ex("INSERT INTO users (id, username, display_name, failed_login_count) VALUES (:i, 'scorer', 'The Scorer', 0)", i=USER)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2025/26', 2025)", i=S, o=OURS)
        await ex("INSERT INTO grades (id, season_id, name, category) VALUES (:i, :s, 'Grade A', 'senior')", i=G, s=S)
        for n in NAMES:
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id) VALUES (:i, :o, :n, :g)",
                     i=PIDS[n], o=OURS, n=f"{n[0]} {n}", g=str(GUIDS[n]))
        await ex("INSERT INTO players (id, organisation_id, name, grassroots_id) VALUES (:i, :o, 'T Their', :g)",
                 i=base.P_THEIRS[0], o=THEIRS, g=str(uuid.uuid4()))
        S_T, G_T = uuid.uuid4(), uuid.uuid4()
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2025/26', 2025)", i=S_T, o=THEIRS)
        await ex("INSERT INTO grades (id, season_id, name, category) VALUES (:i, :s, 'Grade A', 'senior')", i=G_T, s=S_T)
        for gid, home, away, grade in ((GAME, OURS, None, G), (OTHER_GAME, THEIRS, None, G_T)):
            await ex(
                "INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_club, away_club, "
                " opp_club_name, result, home_org_id, away_org_id, venue, match_format, is_final) "
                "VALUES (:i, :g, :d, 'Our Club', 'Opp', 'Our Club', 'Opp', 'Opp', 'WIN', :ho, NULL, 'Oval', "
                " 'One Day', false)", i=gid, g=grade, d=date(2025, 12, 13), ho=home)
        await s.commit()


async def store_game_rows() -> None:
    """What sync stores for the game: batting rows and CA's own fall of wickets and stands."""
    async with Session() as s:
        by_guid, merged, _ = await relink._org_maps(s, OURS)
        await relink.attach_innings_detail(
            s, OURS, GAME, CARD, lambda g: relink._known(g, by_guid, merged) if g else None)
        await s.commit()


class _Club:   # the club a request resolves to: only `.id` is read
    id = OURS


async def as_scorer():
    async with Session() as s:
        return (await s.execute(select(User).where(User.id == USER))).scalar_one()


def fake_fetch(card_by_game):
    async def fetch(match_id: str, *, force: bool = False):
        return card_by_game.get(match_id)
    return fetch


async def rows(sql: str, **kw):
    async with Session() as s:
        return (await s.execute(text(sql), kw)).all()


async def fow_rows() -> list[tuple]:
    return [tuple(r) for r in await rows(
        "SELECT wicket_number, score_at_fall FROM fall_of_wickets WHERE game_id = :g AND innings_number = 1 "
        "ORDER BY wicket_number", g=GAME)]


async def stands() -> list[tuple]:
    return [tuple(r) for r in await rows(
        "SELECT wicket_number, runs FROM partnerships WHERE game_id = :g AND innings_number = 1 "
        "ORDER BY wicket_number", g=GAME)]


async def board() -> set:
    async with Session() as s:
        p = await get_records(
            str(OURS), season_id=None, grade_id=None, grade_name=None, finals_only=False,
            captain_only=False, gender=None, categories="all", formats=None, competitions=None,
            debug_timing=False, db=s, viewer=None)
    return {r["runs"] for r in p["partnerships"]["top_partnerships"]}


async def call(fn, **kw):
    """Run a route body on its own session; returns (result, None) or (None, HTTPException)."""
    async with Session() as s:
        try:
            return await fn(db=s, **kw), None
        except HTTPException as e:
            await s.rollback()
            return None, e


ROWS6 = [(1, 73, "Payne"), (2, 150, "Hall"), (3, 331, "Bivens"), (4, 356, "Sweet"),
         (5, 381, "Menezes"), (6, 400, "Cox")]


def body(rs):
    return game_fow.FowEditIn(rows=[game_fow.FowRowIn(
        wicket_number=w, score_at_fall=sc, participant_id=str(GUIDS[n]) if n else None) for w, sc, n in rs])


async def main() -> None:
    if MISSING:
        print(f"  MISSING: {MISSING[0]}")
        check("the fall-of-wickets editor exists", False, MISSING[0])
        base.report() if hasattr(base, "report") else None
        sys.exit(1)
    await base.build_schema()
    async with engine.begin() as conn:
        from sqlalchemy import text as t
        for stmt in FOW_DDL:
            await conn.execute(t(stmt))
        from app.services.audit_ddl import STATEMENTS as AUDIT
        for stmt in AUDIT:
            await conn.execute(t(stmt))
        await conn.execute(t("""CREATE TABLE IF NOT EXISTS merge_logs (
            id SERIAL PRIMARY KEY, org_id UUID, keep_player_id UUID, removed_player_id UUID, undone_at TIMESTAMPTZ)"""))
    await seed()
    user = await as_scorer()
    gr.get_match_scorecard = fake_fetch({str(GAME): CARD, str(OTHER_GAME): CARD})

    club = Organisation(id=OURS)
    kw = dict(current_user=user, club=club)

    print("A short card, no club typing")
    await store_game_rows()
    check("synced rows: Cricket Australia's four wickets", await fow_rows() == [(1, 73), (3, 331), (4, 356), (5, 381)],
          str(await fow_rows()))
    check("the stands its figures settle: 1st, 4th and 5th", await stands() == [(1, 73), (4, 25), (5, 25)],
          str(await stands()))
    check("the 73 reaches the club's records", 73 in await board(), str(await board()))
    check("the 181 is not on the board yet", 181 not in await board())

    print("The editor")
    res, err = await call(game_fow.fow_editor, game_id=str(GAME), **kw)
    inn = (res or {}).get("innings", [])
    check("opens on the club's own innings only", [i["innings_number"] for i in inn] == [1], str(res))
    if inn:
        i1 = inn[0]
        check("six wickets on the card, four recorded", i1["wickets"] == 6 and len(i1["fow"]) == 4, str(i1["wickets"]))
        check("lists the six batters who were out, in batting order",
              [b["name"] for b in i1["batters"]] == [f"{n[0]} {n}" for n in NAMES if n in OUT], str(i1["batters"]))
        check("says why wickets 2, 3 and 6 have no stand",
              sorted(i1["missing"]) == [2, 3, 6] and "wicket 2" in i1["missing"][3], str(i1["missing"]))
        check("not edited yet", i1["edited"] is False)
    check("a game another club owns is not found",
          (await call(game_fow.fow_editor, game_id=str(OTHER_GAME), **kw))[1] is not None)
    e = (await call(game_fow.fow_editor, game_id=str(OTHER_GAME), **kw))[1]
    check("  (404)", e is not None and e.status_code == 404, str(e and e.status_code))

    print("Refusals leave everything as it was")
    before_fow, before_stands = await fow_rows(), await stands()
    bad_cases = {
        "a wicket entered twice": [(1, 73, "Payne"), (1, 80, "Hall")],
        "a score going backwards": [(1, 73, "Payne"), (3, 60, "Bivens")],
        "a batter who was not out": [(1, 73, "Payne"), (3, 331, "Ito")],
        "a batter out at two wickets": [(1, 73, "Payne"), (3, 331, "Payne")],
        "a wicket past ten": [(11, 400, None)],
        "a row with neither score nor batter": [(1, None, None)],
        "every wicket entered but one has no batter": [(1, 73, "Payne"), (2, 150, "Hall"), (3, 331, "Bivens"),
                                                      (4, 356, "Sweet"), (5, 381, "Menezes"), (6, 400, None)],
    }
    for label, rs in bad_cases.items():
        res, err = await call(game_fow.save_fow, game_id=str(GAME), innings_number=1, data=body(rs), **kw)
        check(f"{label}: 422", err is not None and err.status_code == 422, str(err and err.status_code))
    res, err = await call(game_fow.save_fow, game_id=str(GAME), innings_number=1, data=game_fow.FowEditIn(rows=[]), **kw)
    check("no wickets at all: 422, points at Reset", err is not None and err.status_code == 422 and "Reset" in err.detail)
    res, err = await call(game_fow.save_fow, game_id=str(GAME), innings_number=2, data=body([(1, 20, None)]), **kw)
    check("the opposition's innings: 404", err is not None and err.status_code == 404, str(err and err.status_code))
    check("nothing was written by any refusal",
          await fow_rows() == before_fow and await stands() == before_stands
          and (await rows("SELECT count(*) FROM fow_overrides"))[0][0] == 0
          and (await rows("SELECT count(*) FROM audit_events"))[0][0] == 0)

    print("A stand another club holds in the same innings")
    async with Session() as s:
        await s.execute(text(
            "INSERT INTO partnerships (game_id, innings_number, wicket_number, batter1_id, batter2_id, runs, is_club_innings) "
            "VALUES (:g, 1, 9, :a, :b, 5, true)"), {"g": GAME, "a": base.P_THEIRS[0], "b": PIDS["Lee"]})
        await s.commit()

    print("Saving all six wickets")
    res, err = await call(game_fow.save_fow, game_id=str(GAME), innings_number=1, data=body(ROWS6), **kw)
    check("saves", err is None and res is not None, str(err and err.detail))
    check("the six wickets replace the synced four",
          await fow_rows() == [(1, 73), (2, 150), (3, 331), (4, 356), (5, 381), (6, 400)], str(await fow_rows()))
    got = [s for s in await stands() if s[0] != 9]
    check("six stands: 73, 77, 181, 25, 25, 19", got == [(1, 73), (2, 77), (3, 181), (4, 25), (5, 25), (6, 19)], str(got))
    check("the other club's stand in that innings survives",
          (9, 5) in await stands(), str(await stands()))
    check("the 181 now reaches the club's records", 181 in await board(), str(await board()))
    check("the response names the result", res and "6 of 6 wickets" in res["summary"] and res["innings"]["edited"] is True,
          str(res and res["summary"]))
    check("nothing left missing", res and res["innings"]["missing"] == {}, str(res and res["innings"]["missing"]))
    check("one audit row, with the figures before and after",
          (await rows("SELECT count(*) FROM audit_events WHERE action = 'fow_edit' AND area = 'scorecard'"))[0][0] == 1)
    check("the typed rows are stored apart from the synced ones",
          (await rows("SELECT count(*) FROM fow_overrides WHERE game_id = :g", g=GAME))[0][0] == 6)
    check("the opposition's fall of wickets is untouched",
          [tuple(r) for r in await rows(
              "SELECT wicket_number, score_at_fall FROM fall_of_wickets WHERE game_id = :g AND innings_number = 2 "
              "ORDER BY wicket_number", g=GAME)] == [(1, 20), (2, 41)])

    print("Saving the same thing again changes nothing and adds no rows")
    res, err = await call(game_fow.save_fow, game_id=str(GAME), innings_number=1, data=body(ROWS6), **kw)
    check("idempotent", err is None and
          len([s for s in await stands() if s[0] != 9]) == 6 and len(await fow_rows()) == 6,
          str(await stands()))

    print("A Full Rebuild: the game is deleted and stored again")
    async with Session() as s:
        await s.execute(text("DELETE FROM games WHERE id = :g"), {"g": GAME})
        await s.execute(text(
            "INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_club, away_club, opp_club_name, "
            " result, home_org_id, away_org_id, venue, match_format, is_final) VALUES (:i, :g, :d, 'Our Club', 'Opp', "
            " 'Our Club', 'Opp', 'Opp', 'WIN', :ho, NULL, 'Oval', 'One Day', false)"),
            {"i": GAME, "g": G, "d": date(2025, 12, 13), "ho": OURS})
        await s.commit()
    check("the synced rows went with the game", await fow_rows() == [] and await stands() == [])
    async with Session() as s:   # the other club's own sync writes its stand again
        await s.execute(text(
            "INSERT INTO partnerships (game_id, innings_number, wicket_number, batter1_id, batter2_id, runs, is_club_innings) "
            "VALUES (:g, 1, 9, :a, :b, 5, true)"), {"g": GAME, "a": base.P_THEIRS[0], "b": PIDS["Lee"]})
        await s.commit()
    check("the typed wickets are still there", (await rows(
        "SELECT count(*) FROM fow_overrides WHERE game_id = :g", g=GAME))[0][0] == 6)
    await store_game_rows()    # sync stores Cricket Australia's short card again
    check("sync stores the short card again", await fow_rows() == [(1, 73), (3, 331), (4, 356), (5, 381)],
          str(await fow_rows()))
    async with Session() as s:
        by_guid, merged, _ = await relink._org_maps(s, OURS)
        n = await fo.apply_in_sync(s, OURS, GAME, CARD, lambda g: relink._known(g, by_guid, merged) if g else None)
        await s.commit()
    check("and the club's wickets are applied over it",
          await fow_rows() == [(1, 73), (2, 150), (3, 331), (4, 356), (5, 381), (6, 400)], str(await fow_rows()))
    check("with all six stands", [s for s in await stands() if s[0] != 9] ==
          [(1, 73), (2, 77), (3, 181), (4, 25), (5, 25), (6, 19)], str(await stands()))

    print("Reset")
    res, err = await call(game_fow.reset_fow, game_id=str(GAME), innings_number=1, **kw)
    check("resets", err is None and res is not None, str(err and err.detail))
    check("Cricket Australia's four wickets are back", await fow_rows() == [(1, 73), (3, 331), (4, 356), (5, 381)],
          str(await fow_rows()))
    check("with the stands they settle", [s for s in await stands() if s[0] != 9] == [(1, 73), (4, 25), (5, 25)],
          str(await stands()))
    check("the typed rows are gone", (await rows("SELECT count(*) FROM fow_overrides"))[0][0] == 0)
    check("the other club's stand still survives", (9, 5) in await stands())
    check("a reset is audited too",
          (await rows("SELECT count(*) FROM audit_events WHERE action = 'fow_reset'"))[0][0] == 1)
    res, err = await call(game_fow.reset_fow, game_id=str(GAME), innings_number=1, **kw)
    check("resetting an innings with nothing typed: 409", err is not None and err.status_code == 409, str(err and err.status_code))

    print("A short list with a batter left blank still gives the stands the card settles")
    rs = [(1, 73, "Payne"), (2, 150, None), (3, 331, "Bivens"), (4, 356, "Sweet"), (5, 381, "Menezes")]
    res, err = await call(game_fow.save_fow, game_id=str(GAME), innings_number=1, data=body(rs), **kw)
    got = [s for s in await stands() if s[0] != 9]
    check("saves five of six wickets", err is None, str(err and err.detail))
    check("the 2nd and 3rd stands come out as well (150 is the 2nd wicket's score)",
          got == [(1, 73), (2, 77), (3, 181), (4, 25), (5, 25)], str(got))

    print()
    print(f"{base.PASS} passed, {base.FAIL} failed")
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
