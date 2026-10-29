"""A player CA drops from the final team sheet stops counting, against a real Postgres and the production views.

Reported by Applecross: Nuwani Jayaweera read 51 matches beside Cricket Australia's 50. The extra game is
one she was named for and pulled out of. The sync stored an appearance for her from the sheet it read
first, CA later took her off the sheet, and nothing ever removed the row, so the game counted for
somebody who never played it. Her NULL `is_reserve` read as played.

`withdrawn_appearances.mark_withdrawn` (the sync, recent games) and `backfill_reserve_flags` (history)
now mark such a row `is_reserve` TRUE with no `sheet_slot`. Every reader that skips a reserve skips it.

This suite reads every figure first with nothing marked (the CONTROL: it must show the reported numbers)
and then after the shipped code has run. On code without the change the "after" checks fail on exactly the
reported figure; nothing here crashes for want of the new modules.

What must NOT be taken off is as much the point as what is:
  NUWANI    named, not on the final sheet, no rows of her own        -> marked, 11 reads 10
  GRESELE   on the sheet under a NEW id with her full name           -> left alone, she played
  BATTER    off the sheet but with a batting row                     -> left alone, a row of her own
  HUMAN     a person set the flag to "played"                        -> left alone
  BACK      marked earlier, CA has put her back on the sheet         -> cleared, counts again
  RES12     a real 12th man (slot 12), on the sheet                  -> still a reserve, untouched
  MASS      4 stored, 3 off the sheet                                -> a damaged card, nothing marked
  UNSET     the card is still IN PROGRESS                            -> nothing marked
  EMPTYSIDE the other side's sheet is empty                          -> nothing marked
  INTERNAL  the club plays itself: a player on the OTHER side's sheet is not marked, one on neither is

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \\
  python verification/verify_withdrawn_appearances.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from argparse import Namespace
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from verify_board_games_match_profile import build_schema
from app.routers.players import get_player_stats
from app.scripts import backfill_reserve_flags as backfill
from app.services import grassroots_scores_client as gr
from app.services import reserve_players, superseded_ddl
from app.services.aggregations import get_season_by_season

try:                                    # absent on the code before the change: the control must not crash on it
    from app.services import withdrawn_appearances
except ImportError:
    withdrawn_appearances = None

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
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


ORG, OPP = uuid.uuid4(), uuid.uuid4()
SEASON, GRADE = uuid.uuid4(), uuid.uuid4()
OUR_TEAM, OUR_TEAM_B, THEIR_TEAM = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
NAMES = {"NUWANI": "Jayaweera, Nuwani", "GRESELE": "Gresele, Lily", "BATTER": "Batter, Has", "HUMAN": "Human, Said",
         "BACK": "Back, Again", "RES12": "Twelfth, Real", "MA": "Mass, Alpha", "MB": "Mass, Bravo", "MC": "Mass, Charlie",
         "MD": "Mass, Delta", "UNSET": "Unsettled, Card", "EMPTYSIDE": "Empty, Side", "INTW": "Internal, Withdrawn",
         "INTB": "Internal, OtherSide"}
P = {k: uuid.uuid4() for k in NAMES}
MATES = [uuid.uuid4() for _ in range(8)]
GUID_GRESELE_NEW = str(uuid.uuid4())      # the id CA's sheet carries for Gresele, which the club never stored
RESOLVE: dict[str, uuid.UUID] = {str(p): p for p in list(P.values()) + MATES}
RESOLVE[GUID_GRESELE_NEW] = P["GRESELE"]  # what the sync's full-name attach adds to its own lookup
CARDS: dict[uuid.UUID, dict | None] = {}
FETCHES: list[str] = []
GAMES: dict[str, uuid.UUID] = {}          # scenario -> the game it is about
_day = 0


async def _stub(match_id: str, *, force: bool = False):
    FETCHES.append(match_id)
    return CARDS.get(uuid.UUID(match_id))


gr.get_match_scorecard = _stub


def full(key_or_mate) -> str:
    n = NAMES[key_or_mate]
    last, first = [x.strip() for x in n.split(",")]
    return f"{first} {last}"


def entry(guid: str, name: str) -> dict:
    return {"participantId": guid, "playerShortName": name, "roles": []}


def filler(n: int) -> list[dict]:
    return [entry(str(uuid.uuid4()), f"Opp{i} Player{i}") for i in range(n)]


def make_card(our_sheet: list[dict], *, status: str = "COMPLETED", their_sheet: list[dict] | None = None,
              internal_b: list[dict] | None = None) -> dict:
    """A CA-shaped card. `internal_b` makes the club's own second side (a fixture between two sides of one club)."""
    their = filler(11) if their_sheet is None else their_sheet
    teams = [{"id": OUR_TEAM, "displayName": "Alpha - 8s", "owningOrganisation": {"id": str(ORG)}, "players": our_sheet}]
    if internal_b is not None:
        teams.append({"id": OUR_TEAM_B, "displayName": "Alpha B - 8s", "owningOrganisation": {"id": str(ORG)}, "players": internal_b})
    else:
        teams.append({"id": THEIR_TEAM, "displayName": "Opp - 8s", "owningOrganisation": {"id": str(OPP)}, "players": their})
    innings = [{"battingTeamId": OUR_TEAM, "inningsOrder": 1, "batting": [
                    {"participantId": p["participantId"], "dismissalType": "Bowled", "dismissalTypeId": 2} for p in our_sheet],
                "bowling": [], "fielding": []},
               {"battingTeamId": THEIR_TEAM if internal_b is None else OUR_TEAM_B, "inningsOrder": 2, "batting": [
                    {"participantId": p["participantId"], "dismissalType": "Bowled", "dismissalTypeId": 2}
                    for p in (their if internal_b is None else internal_b)], "bowling": [], "fielding": []}]
    return {"status": status, "teams": teams, "innings": innings}


async def seed() -> None:
    global _day
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        for oid, nm, slug in ((ORG, "Withdrawn Club", "withdrawn"), (OPP, "Opposition CC", "opp")):
            await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)", i=oid, n=nm, s=slug)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2026/27', 2026)", i=SEASON, o=ORG)
        await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                 "VALUES (:i, :s, 'PSWL South A', :g, 'senior', ARRAY['senior'])", i=GRADE, s=SEASON, g=str(GRADE))
        for k, pid in P.items():
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) VALUES (:i, :o, :n, :g, 'active')",
                     i=pid, o=ORG, n=NAMES[k], g=str(pid))
        for i, pid in enumerate(MATES):
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) VALUES (:i, :o, :n, :g, 'active')",
                     i=pid, o=ORG, n=f"Mate, Team{i}", g=str(pid))

        async def new_game() -> uuid.UUID:
            global _day
            _day += 7
            gid = uuid.uuid4()
            await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, match_format, status, innings_totals) "
                     "VALUES (:i, :g, :d, 'WIN', :o, :x, 'T20', 'COMPLETED', "
                     " jsonb_build_array(jsonb_build_object('runs_scored', 120, 'wickets', 7)))",
                     i=gid, g=GRADE, d=date(2026, 8, 1) + timedelta(days=_day), o=ORG, x=OPP)
            return gid

        async def real(player: uuid.UUID, n: int) -> None:
            for _ in range(n):
                gid = await new_game()
                await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=gid, p=player)
                await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, sixes, not_out, "
                         " dismissal_type, did_not_bat) VALUES (:g, :p, 1, 20, 25, 1, 0, false, 'caught', false)", g=gid, p=player)

        async def named_game(scenario: str, appear: list[str], sheet: list[str], *, mates: int = 8, flags: dict | None = None,
                             extra_sheet: list[dict] | None = None, **card_kw) -> uuid.UUID:
            """A game the `appear` players have an appearance row in, and CA's final sheet naming `sheet` (plus the mates)."""
            gid = await new_game()
            GAMES[scenario] = gid
            flags = flags or {}
            for k in appear:
                fl = flags.get(k)
                await ex("INSERT INTO game_appearances (game_id, player_id, is_reserve, sheet_slot) VALUES (:g, :p, :r, :sl)",
                         g=gid, p=P[k], r=(fl[0] if fl else None), sl=(fl[1] if fl else None))
            for m in MATES[:mates]:
                await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=gid, p=m)
            our_sheet = [entry(str(P[k]), full(k)) for k in sheet] + [entry(str(m), "Team Mate") for m in MATES[:mates]]
            our_sheet += extra_sheet or []
            CARDS[gid] = make_card(our_sheet, **card_kw)
            return gid

        async def ca(key: str, matches: int) -> None:
            await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, not_outs, wickets, "
                     " catches, source) VALUES (:p, :s, :m, 0, 0, 0, 0, 0, 'api')", p=P[key], s=SEASON, m=matches)

        # NUWANI: ten real games, and the one she was named for and pulled out of. CA says 10 (the reported 51 against 50).
        await real(P["NUWANI"], 10)
        await named_game("NUWANI", ["NUWANI"], [])
        await ca("NUWANI", 10)
        # GRESELE: five real games and one where CA's sheet has her full name under an id we never stored. She played it.
        await real(P["GRESELE"], 5)
        await named_game("GRESELE", ["GRESELE"], [], extra_sheet=[entry(GUID_GRESELE_NEW, "Lily Gresele")])
        await ca("GRESELE", 5)
        # BATTER: off the sheet but with a batting row in the game (a row of their own: they played).
        await real(P["BATTER"], 4)
        gb = await named_game("BATTER", ["BATTER"], [])
        await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, sixes, not_out, "
                 " dismissal_type, did_not_bat) VALUES (:g, :p, 1, 7, 9, 0, 0, false, 'bowled', false)", g=gb, p=P["BATTER"])
        await ca("BATTER", 5)
        # HUMAN: off the sheet, but a person decided "played" (is_reserve FALSE).
        await real(P["HUMAN"], 4)
        await named_game("HUMAN", ["HUMAN"], [], flags={"HUMAN": (False, None)})
        await ca("HUMAN", 5)
        # BACK: marked withdrawn earlier (TRUE, no slot); CA has put them back on the sheet.
        await real(P["BACK"], 3)
        await named_game("BACK", ["BACK"], ["BACK"], flags={"BACK": (True, None)})
        await ca("BACK", 4)
        # RES12: a real 12th man (slot 12), on the sheet. Not a withdrawal: untouched.
        await real(P["RES12"], 3)
        await named_game("RES12", ["RES12"], ["RES12"], flags={"RES12": (True, 12)})
        await ca("RES12", 3)
        # MASS: a card that names almost nobody we stored: four stored, three of them off the sheet.
        await named_game("MASS", ["MA", "MB", "MC", "MD"], ["MD"], mates=0, extra_sheet=filler(9))
        # UNSET: the card is still in play.
        await real(P["UNSET"], 2)
        await named_game("UNSET", ["UNSET"], [], status="IN PROGRESS")
        await ca("UNSET", 3)
        # EMPTYSIDE: CA has not filled in the other side's sheet.
        await real(P["EMPTYSIDE"], 2)
        await named_game("EMPTYSIDE", ["EMPTYSIDE"], [], their_sheet=[])
        await ca("EMPTYSIDE", 3)
        # INTERNAL: the club plays itself. INTW is on neither sheet; INTB is on the other side's.
        await named_game("INTERNAL", ["INTW", "INTB"], [], mates=4,
                         internal_b=[entry(str(P["INTB"]), full("INTB"))] + filler(7))
        await s.commit()


async def header(key: str) -> int | None:
    async with Session() as s:
        d = await get_player_stats(player_id=str(P[key]), db=s, season_id=None, grade_id=None, last_n_games=None,
                                   start_date=None, end_date=None, categories=None, formats=None, competitions=None, grades=None)
    return ((d["career_batting"] or {}).get("games"))


async def season_row(key: str) -> int | None:
    async with Session() as s:
        rows = await get_season_by_season(s, str(P[key]), include_prior=True)
    return next((r["matches"] for r in rows if str(r.get("season_id")) == str(SEASON)), None)


async def flag(scenario: str, key: str) -> tuple:
    async with Session() as s:
        r = (await s.execute(text("SELECT is_reserve, sheet_slot FROM game_appearances WHERE game_id = :g AND player_id = :p"),
                             {"g": GAMES[scenario], "p": P[key]})).first()
    return tuple(r) if r else (None, None)


async def audit_rows(action: str) -> list:
    async with Session() as s:
        return (await s.execute(text("SELECT id, details FROM audit_logs WHERE action = :a ORDER BY id"), {"a": action})).mappings().all()


def resolve(guid: str):
    return RESOLVE.get(str(guid).lower())


async def run_service(scenario: str):
    """What the sync does for one stored game it reads again: the shipped service, with the sync's own lookup."""
    if withdrawn_appearances is None:
        return None
    async with Session() as s:
        return await withdrawn_appearances.mark_withdrawn(s, ORG, GAMES[scenario], CARDS[GAMES[scenario]], resolve)


def unit_checks() -> None:
    print("\n-- THE CLASSIFIER, ON CARDS --")
    sheet = [entry(str(uuid.uuid4()), f"Team Mate{i}") for i in range(10)]
    done = make_card(sheet)
    nobody = {str(uuid.uuid4())}
    cw = getattr(reserve_players, "classify_withdrawal", None)
    check("classify_withdrawal exists", cw is not None)
    if cw is None:
        return
    check("a name on neither sheet, by id or by name, on a settled card: WITHDRAWN", cw(done, nobody, "Jayaweera, Nuwani")["code"] == "WITHDRAWN")
    check("the same card, the old classifier: still NOT_ON_SHEET (unchanged)", reserve_players.classify(done, nobody)["code"] == "NOT_ON_SHEET")
    named = make_card(sheet + [entry(str(uuid.uuid4()), "Lily Gresele")])
    check("her full name on the sheet under another id: SAME_NAME_ON_SHEET", cw(named, nobody, "Gresele, Lily")["code"] == "SAME_NAME_ON_SHEET")
    check("'Gresele, Lily' and 'Lily Gresele' are one key, either way round", cw(named, nobody, "Lily Gresele")["code"] == "SAME_NAME_ON_SHEET")
    check("a bare initial is not a name: 'L Gresele' on the sheet does not protect Lily", cw(make_card(sheet + [entry(str(uuid.uuid4()), "L Gresele")]), nobody, "Gresele, Lily")["code"] == "WITHDRAWN")
    check("a short name is never matched (no full name to compare)", cw(done, nobody, "Nuwani")["code"] == "WITHDRAWN")
    check("not COMPLETED: cannot rule anyone out", cw(make_card(sheet, status="IN PROGRESS"), nobody, "Jayaweera, Nuwani")["code"] == "NOT_ON_SHEET")
    check("the other side's sheet empty: cannot rule anyone out", cw(make_card(sheet, their_sheet=[]), nobody, "Jayaweera, Nuwani")["code"] == "NOT_ON_SHEET")
    check("nobody batted: cannot rule anyone out", cw({**done, "innings": [{"battingTeamId": OUR_TEAM, "batting": []}]}, nobody, "Jayaweera, Nuwani")["code"] == "NOT_ON_SHEET")
    on = {str(uuid.UUID(sheet[0]["participantId"]))}
    check("a player on the sheet is never WITHDRAWN", cw(done, on, "Team Mate0")["code"] != "WITHDRAWN")
    check("no card: NO_CARD, as before", cw(None, nobody, "Jayaweera, Nuwani")["code"] == "NO_CARD")


async def main() -> None:
    await build_schema()
    async with engine.begin() as conn:
        for stmt in superseded_ddl.STATEMENTS:
            await conn.execute(text(stmt))
        ok = await superseded_ddl.verify(conn)
    check("the production source-aware views are the ones under test", all(ok.values()), str(ok))
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY, created_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL, user_id UUID,
                action TEXT NOT NULL, target_type TEXT, target_id TEXT, details JSONB DEFAULT '{}')"""))
    await seed()
    unit_checks()

    print("\n-- CONTROL: BEFORE ANYTHING RUNS, THE APP READS THE REPORTED OVER-COUNT --")
    check("Nuwani: the header reads 11 beside CA's 10 (the reported 51 against 50)", await header("NUWANI") == 11 and await season_row("NUWANI") == 10,
          f"{await header('NUWANI')} / {await season_row('NUWANI')}")
    check("Gresele reads 6 (five real games and the one she played)", await header("GRESELE") == 6, str(await header("GRESELE")))
    check("Back reads 3: marked withdrawn, so the game is off", await header("BACK") == 3, str(await header("BACK")))

    print("\n-- THE SYNC CHECK, ON EACH STORED GAME --")
    res = {sc: await run_service(sc) for sc in GAMES}
    check("the service exists", withdrawn_appearances is not None)
    check("Nuwani's game: one appearance marked", (res["NUWANI"] or {}).get("marked") == 1, str(res["NUWANI"]))
    check("she is TRUE with NO slot (a withdrawal, not a 12th man)", await flag("NUWANI", "NUWANI") == (True, None), str(await flag("NUWANI", "NUWANI")))
    async with Session() as s:
        mates_marked = (await s.execute(text("SELECT COUNT(*) FROM game_appearances WHERE game_id = :g AND player_id = ANY(:m) AND is_reserve IS NOT NULL"),
                                        {"g": GAMES["NUWANI"], "m": MATES})).scalar()
    check("none of the eight team-mates is marked", mates_marked == 0, str(mates_marked))

    print("\n-- THE FIGURES AFTER --")
    check("Nuwani: the header reads 10, level with CA", await header("NUWANI") == 10 and await season_row("NUWANI") == 10,
          f"{await header('NUWANI')} / {await season_row('NUWANI')}")

    print("\n-- WHAT MUST NOT BE TAKEN OFF --")
    check("Gresele: on the sheet under a new id with her full name, so she played and keeps 6", await header("GRESELE") == 6, str(await header("GRESELE")))
    check("and her appearance is not marked", await flag("GRESELE", "GRESELE") == (None, None), str(await flag("GRESELE", "GRESELE")))
    check("Batter: off the sheet but with a batting row, keeps the game", await flag("BATTER", "BATTER") == (None, None) and await header("BATTER") == 5)
    check("Human: a person's 'played' stands", await flag("HUMAN", "HUMAN") == (False, None) and await header("HUMAN") == 5)
    check("RES12: a real 12th man keeps its slot and stays a reserve", await flag("RES12", "RES12") == (True, 12), str(await flag("RES12", "RES12")))
    mass = [await flag("MASS", k) for k in ("MA", "MB", "MC", "MD")]
    check("Mass: four stored, three off the sheet, is a damaged card and nothing is marked",
          all(f == (None, None) for f in mass) and res["MASS"] is None, str(mass))
    check("Unset: a card still IN PROGRESS rules nobody out", await flag("UNSET", "UNSET") == (None, None) and res["UNSET"] is None)
    check("Emptyside: the other side's sheet is empty, so nobody is ruled out", await flag("EMPTYSIDE", "EMPTYSIDE") == (None, None) and res["EMPTYSIDE"] is None)
    check("Internal: the player on neither sheet is marked", await flag("INTERNAL", "INTW") == (True, None), str(await flag("INTERNAL", "INTW")))
    check("Internal: the player on the club's OTHER side's sheet is not", await flag("INTERNAL", "INTB") == (None, None), str(await flag("INTERNAL", "INTB")))

    print("\n-- A PLAYER PUT BACK ON THE SHEET COUNTS AGAIN --")
    check("Back: the mark is cleared", (res["BACK"] or {}).get("cleared") == 1 and await flag("BACK", "BACK") == (None, None), str(await flag("BACK", "BACK")))
    check("Back: and the game counts again (4, CA's figure)", await header("BACK") == 4, str(await header("BACK")))

    print("\n-- THE AUDIT TRAIL AND RUNNING IT AGAIN --")
    audits = await audit_rows("sync_withdrawn_appearances")
    check("one audit entry per game that changed (Nuwani, Back, Internal)", len(audits) == 3, str(len(audits)))
    nu = next((a for a in audits if any(c["player_id"] == str(P["NUWANI"]) for c in a["details"].get("changes", []))), None)
    check("Nuwani's entry names the game and her", bool(nu) and nu["details"]["changes"][0]["game_id"] == str(GAMES["NUWANI"]))
    again = {sc: await run_service(sc) for sc in GAMES}
    check("a second run changes nothing and writes nothing", all(v is None for v in again.values()) and len(await audit_rows("sync_withdrawn_appearances")) == 3,
          str({k: v for k, v in again.items() if v}))

    print("\n-- THE BACKFILL, FOR HISTORY --")
    # Undo the sync's mark through the backfill's own --restore, which must accept the sync's entry.
    if nu:
        await backfill.restore(nu["id"], "Test Admin")
        check("--restore undoes a sync entry: Nuwani reads 11 again", await flag("NUWANI", "NUWANI") == (None, None) and await header("NUWANI") == 11,
              f"{await flag('NUWANI', 'NUWANI')} {await header('NUWANI')}")
    else:
        check("--restore undoes a sync entry", False, "no sync entry to restore")
    async with Session() as s:                       # the other marks the sync made: back to unjudged, as old history is
        await s.execute(text("UPDATE game_appearances SET is_reserve = NULL, sheet_slot = NULL WHERE game_id = :g AND player_id = :p"),
                        {"g": GAMES["INTERNAL"], "p": P["INTW"]})
        await s.commit()
    args = Namespace(year=None, pace=0.0, timeout=120, list=40, max_games=500)

    async def planned():
        FETCHES.clear()
        return await backfill.plan(str(ORG), args, [500])

    rows, left = await planned()
    withdrawn = {(r["game_id"], r["player_id"]) for r in rows if r["is_reserve"] and r["slot"] is None}
    check("the plan lists Nuwani and the internal fixture's player as withdrawn, and only them",
          withdrawn == {(str(GAMES["NUWANI"]), str(P["NUWANI"])), (str(GAMES["INTERNAL"]), str(P["INTW"]))}, str(withdrawn))
    check("Gresele is left NULL and named as a same-name case", not any(r["player_id"] == str(P["GRESELE"]) for r in rows)
          and any("SAME_NAME_ON_SHEET" in k for k in left), str(dict(left)))
    check("the damaged card is left alone and said so", not any(r["game_id"] == str(GAMES["MASS"]) and r["is_reserve"] for r in rows)
          and any("damaged card" in k for k in left), str(dict(left)))
    check("an IN PROGRESS card is left NULL (not COMPLETED)", not any(r["game_id"] == str(GAMES["UNSET"]) for r in rows))
    check("an empty other side is left NULL: the card cannot rule anyone out", not any(r["game_id"] == str(GAMES["EMPTYSIDE"]) and r["is_reserve"] for r in rows))
    check("a real reserve and a person's decision are not candidates", not any(r["player_id"] in (str(P["RES12"]), str(P["HUMAN"])) for r in rows))
    async with Session() as s:
        n_set = (await s.execute(text("SELECT COUNT(*) FROM game_appearances WHERE game_id = :g AND is_reserve IS NOT NULL"), {"g": GAMES["NUWANI"]})).scalar()
    check("the dry run writes nothing", n_set == 0, str(n_set))
    await backfill.apply(str(ORG), rows, len(rows), "Test Admin")
    check("--apply marks Nuwani as the sync would: TRUE, no slot", await flag("NUWANI", "NUWANI") == (True, None))
    check("and she reads 10 again", await header("NUWANI") == 10, str(await header("NUWANI")))
    bf = await audit_rows("backfill_reserve_flags")
    await backfill.restore(bf[0]["id"], "Test Admin")
    check("--restore puts it back", await flag("NUWANI", "NUWANI") == (None, None) and await header("NUWANI") == 11)

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
