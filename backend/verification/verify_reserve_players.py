"""A 12th man who did not play stops counting, against a real Postgres and the production views.

Reported by Applecross: Jack Barendse reads 214 matches, CA reads 213. The game is one where he
was 12th man: named on the team sheet, never on the batting card, no bowling, no catch. The audit
(`app.scripts.audit_twelfth_man`, `verify_twelfth_man_audit.py`) found the shape and tested it on two
clubs; the owner decided a reserve who did not play is not a match played, for the profile, for fees,
and even where Cricket Australia's own total counts the game.

`game_appearances.is_reserve` carries the call. This suite reads every figure twice on the same data:
first with the flag NULL (not judged, which is exactly what the app did before: the control, and it
must show the reported numbers), then with the flags the sync and the backfill write.

What CA's total does with a reserve varies, and the correction must not subtract blindly:
  JACK       CA already left the reserve game out (3 of 4 held)            -> 3, not 2
  CASTLEY    CA counted it (11 of 11 held)                                  -> 10, below CA
  SULWAY     two reserves, CA counted one (14 of 15 held)                   -> 13
  STACKPOLE  CA above what we hold (17 against 16): a scorecard is missing  -> 16
  BAET       his only game was a reserve and CA left it out                 -> 0
  SHAN       CA below what we hold for another reason (15 against 17)       -> 16 (the raise stays)
  FIELDER    flagged, but with a fielding row of their own: they played     -> unchanged
  WASH       a reserve in an abandoned game: the washout rule already takes it -> not taken twice
  NULLP      named only, never judged                                        -> unchanged
  BIGSHEET   slot 13 of 14, CA left it out                                  -> 3
  INSIDEXI   off the card but 8th of 12: not a reserve                       -> unchanged

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \\
  python verification/verify_reserve_players.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from verify_board_games_match_profile import build_schema
from app.models.db import GameAppearance
from app.routers.leaderboard import batting_leaderboard
from app.routers.players import get_player_stats
from app.scripts import backfill_reserve_flags as backfill
from app.services import grassroots_scores_client as gr
from app.services import reserve_players, superseded_ddl
from app.services.aggregations import get_player_team_breakdown, get_season_by_season
from app.services.game_status import appearance_counts_as_match

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
OUR_TEAM, THEIR_TEAM = str(uuid.uuid4()), str(uuid.uuid4())
P = {k: uuid.uuid4() for k in ("JACK", "CASTLEY", "SULWAY", "STACKPOLE", "BAET", "SHAN", "FIELDER",
                               "WASH", "NULLP", "BIGSHEET", "INSIDEXI")}
NAMES = {"JACK": "Barendse, Jack", "CASTLEY": "Castley, Gibson", "SULWAY": "Sulway, Richard",
         "STACKPOLE": "Stackpole, Vince", "BAET": "Baetsen, Burt", "SHAN": "Shanmuganathan, Antonio",
         "FIELDER": "Fielder, Flagged", "WASH": "Wash, Out", "NULLP": "Null, Player", "BIGSHEET": "Big, Sheet", "INSIDEXI": "Inside, Eleven"}
CARDS: dict[uuid.UUID, dict | None] = {}   # what the CA stub serves for the backfill
FETCHES: list[str] = []
_day = 0
RESERVE_GAMES: dict[str, list[uuid.UUID]] = {}   # player -> the games flagged TRUE
JUDGED: list[tuple[str, uuid.UUID, bool | None, int | None]] = []   # (player, game, flag, slot): what the sync/backfill writes


async def _stub(match_id: str, *, force: bool = False):
    FETCHES.append(match_id)
    return CARDS.get(uuid.UUID(match_id))


gr.get_match_scorecard = _stub


def filler(n: int) -> list[str]:
    return [str(uuid.uuid4()) for _ in range(n)]


def card(sheet: list[str], on_card, *, status: str = "COMPLETED") -> dict:
    """A CA-shaped card. `on_card` is our batting card as (participantId, dismissalType, id); None = we never batted."""
    innings = []
    if on_card is not None:
        innings.append({"battingTeamId": OUR_TEAM, "inningsOrder": 1,
                        "batting": [{"participantId": p, "dismissalType": t, "dismissalTypeId": i} for p, t, i in on_card],
                        "bowling": [], "fielding": []})
    innings.append({"battingTeamId": THEIR_TEAM, "inningsOrder": 2,
                    "batting": [{"participantId": g, "dismissalType": "Bowled", "dismissalTypeId": 2} for g in filler(11)],
                    "bowling": [], "fielding": []})
    return {"status": status,
            "teams": [{"id": OUR_TEAM, "players": [{"participantId": g, "roles": []} for g in sheet]},
                      {"id": THEIR_TEAM, "players": [{"participantId": g, "roles": []} for g in filler(11)]}],
            "innings": innings}


def sheet_with(player: uuid.UUID, slot: int, size: int) -> list[str]:
    others = filler(size - 1)
    others.insert(slot - 1, str(player))
    return others


def off_card(sheet: list[str], who: uuid.UUID) -> list[tuple[str, str, int]]:
    return [(g, "Bowled", 2) for g in sheet if g != str(who)]


async def seed() -> None:
    global _day
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        for oid, nm, slug in ((ORG, "Reserve Club", "reserve"), (OPP, "Opposition CC", "opp")):
            await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)", i=oid, n=nm, s=slug)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2016/17', 2016)", i=SEASON, o=ORG)
        await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                 "VALUES (:i, :s, '8th Grade', :g, 'senior', ARRAY['senior'])", i=GRADE, s=SEASON, g=str(GRADE))
        for k, pid in P.items():
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                     "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=ORG, n=NAMES[k], g=str(pid))

        async def new_game(*, status="COMPLETED") -> uuid.UUID:
            global _day
            _day += 7
            gid = uuid.uuid4()
            # `innings_totals` is what the sync writes; without a scored innings a game reads as unplayed.
            await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, match_format, status, "
                     " innings_totals) VALUES (:i, :g, :d, 'WIN', :o, :x, 'Two Day', :st, "
                     " jsonb_build_array(jsonb_build_object('runs_scored', 146, 'wickets', 9)))",
                     i=gid, g=GRADE, d=date(2016, 10, 1) + timedelta(days=_day), o=ORG, x=OPP, st=status)
            return gid

        async def real(player: uuid.UUID, n: int) -> None:
            """n games with a real batting row (and the team-sheet entry the sync writes beside it)."""
            for _ in range(n):
                gid = await new_game()
                await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=gid, p=player)
                await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, sixes, not_out, "
                         " dismissal_type, did_not_bat) VALUES (:g, :p, 1, 20, 25, 1, 0, false, 'caught', false)", g=gid, p=player)

        async def named(key: str, *, slot: int, size: int, shape: str, status="COMPLETED", fielding=False) -> uuid.UUID:
            """A game the player is only NAMED in. `shape` says what CA's card looks like and so what the judgement is."""
            gid = await new_game(status=status)
            pl = P[key]
            await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=gid, p=pl)
            sh = sheet_with(pl, slot, size)
            if shape == "reserve":          # the side batted, the player is nowhere on the card
                CARDS[gid] = card(sh, off_card(sh, pl))
                JUDGED.append((key, gid, True, slot))
                RESERVE_GAMES.setdefault(key, []).append(gid)
            elif shape == "dnb":            # on the card as Did Not Bat (CA id 0, which sync never stores)
                CARDS[gid] = card(sh, off_card(sh, pl) + [(str(pl), "Did Not Bat", 0)])
                JUDGED.append((key, gid, False, slot))
            elif shape == "inside":         # the side batted and the player is off the card, but in slots 1 to 11
                CARDS[gid] = card(sh, off_card(sh, pl))
                JUDGED.append((key, gid, False, slot))
            elif shape == "rain":           # the side never batted
                CARDS[gid] = card(sh, None)
                JUDGED.append((key, gid, False, slot))
            elif shape == "nocard":         # CA returns nothing
                CARDS[gid] = None
            if fielding:
                await ex("INSERT INTO fielding_stats (game_id, player_id, catches, catches_wk, run_outs, stumpings) "
                         "VALUES (:g, :p, 1, 0, 0, 0)", g=gid, p=pl)
            return gid

        async def ca(key: str, matches: int) -> None:
            await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, not_outs, wickets, "
                     " catches, source) VALUES (:p, :s, :m, 0, 0, 0, 0, 0, 'api')", p=P[key], s=SEASON, m=matches)

        # JACK: one real game, a DNB on the card, a rained-off game, and the 12th-man Grand Final. CA left the last out.
        await real(P["JACK"], 1)
        await named("JACK", slot=7, size=12, shape="dnb")
        await named("JACK", slot=4, size=13, shape="rain")
        await named("JACK", slot=12, size=12, shape="reserve")
        await ca("JACK", 3)
        # CASTLEY: 10 real games and a 12th man game CA counted. CA's per-grade claim counts it too.
        await real(P["CASTLEY"], 10)
        await named("CASTLEY", slot=13, size=14, shape="reserve")
        await ca("CASTLEY", 11)
        await ex("INSERT INTO player_season_grade_stats (player_id, season_id, grade_id, matches) VALUES (:p, :s, :g, 11)",
                 p=P["CASTLEY"], s=SEASON, g=GRADE)
        # SULWAY: 13 real, two 12th man games, CA counted one of them.
        await real(P["SULWAY"], 13)
        await named("SULWAY", slot=12, size=12, shape="reserve")
        await named("SULWAY", slot=12, size=12, shape="reserve")
        await ca("SULWAY", 14)
        # STACKPOLE: 15 real, a 12th man game, and CA counts 17: one of its games is a scorecard we do not hold.
        await real(P["STACKPOLE"], 15)
        await named("STACKPOLE", slot=12, size=12, shape="reserve")
        await ca("STACKPOLE", 17)
        # BAET: his only game was a 12th man game. CA left it out.
        await named("BAET", slot=12, size=12, shape="reserve")
        await ca("BAET", 0)
        # SHAN: 16 real and a 12th man game. CA is at 15 for some other reason.
        await real(P["SHAN"], 16)
        await named("SHAN", slot=12, size=12, shape="reserve")
        await ca("SHAN", 15)
        # FIELDER: flagged a reserve, but took a catch: a row of their own, so they played.
        await real(P["FIELDER"], 5)
        fgid = await named("FIELDER", slot=12, size=12, shape="none", fielding=True)
        JUDGED.append(("FIELDER", fgid, True, 12))
        RESERVE_GAMES.setdefault("FIELDER", []).append(fgid)
        await ca("FIELDER", 6)
        # WASH: a flagged reserve in an abandoned game, plus 4 real games. The washout rule already takes it off CA's 5.
        await real(P["WASH"], 4)
        wgid = await named("WASH", slot=12, size=12, shape="none", status="ABANDONED")
        JUDGED.append(("WASH", wgid, True, 12))
        RESERVE_GAMES.setdefault("WASH", []).append(wgid)
        await ca("WASH", 5)
        # NULLP: 4 real and a named-only game CA has no card for: never judged.
        await real(P["NULLP"], 4)
        await named("NULLP", slot=12, size=12, shape="nocard")
        await ca("NULLP", 5)
        # BIGSHEET: three real games and 13th of 14. CA left it out.
        await real(P["BIGSHEET"], 3)
        await named("BIGSHEET", slot=13, size=14, shape="reserve")
        await ca("BIGSHEET", 3)
        # INSIDEXI: off the card but 8th of 12, so inside the XI. CA counted it; so do we.
        await real(P["INSIDEXI"], 5)
        await named("INSIDEXI", slot=8, size=12, shape="inside")
        await ca("INSIDEXI", 6)
        await s.commit()


async def set_flags() -> None:
    """What the sync writes for a new game and the backfill writes for an old one."""
    async with Session() as s:
        for key, gid, flag, slot in JUDGED:
            await s.execute(text("UPDATE game_appearances SET is_reserve = :f, sheet_slot = :sl "
                                 "WHERE game_id = :g AND player_id = :p"), {"f": flag, "sl": slot, "g": gid, "p": P[key]})
        await s.commit()


async def clear_flags() -> None:
    async with Session() as s:
        await s.execute(text("UPDATE game_appearances SET is_reserve = NULL, sheet_slot = NULL"))
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


async def grid(key: str) -> int:
    async with Session() as s:
        d = await get_player_team_breakdown(s, str(P[key]), str(ORG), None)
    return d["grid_matches"]


async def board(key: str) -> int | None:
    async with Session() as s:
        rows = await batting_leaderboard(db=s, viewer=None, org_id=str(ORG), season_id=None, grade_id=None, grade_name=None,
                                         limit=50, finals_only=None, captain_only=None, gender=None, overseas=None,
                                         categories=None, formats=None, competitions=None, sort_by="total_runs",
                                         min_runs=0, min_rate_innings=0)
    row = next((r for r in rows if str(r["player_id"]) == str(P[key])), None)
    return None if row is None else row.get("games")


# What each player's figure reads WITHOUT the flags (the control: the old behaviour) and WITH them.
BEFORE = {"JACK": 4, "CASTLEY": 11, "SULWAY": 15, "STACKPOLE": 17, "BAET": 1, "SHAN": 17, "FIELDER": 6,
          "WASH": 4, "NULLP": 5, "BIGSHEET": 4, "INSIDEXI": 6}
AFTER = {"JACK": 3, "CASTLEY": 10, "SULWAY": 13, "STACKPOLE": 16, "BAET": 0, "SHAN": 16, "FIELDER": 6,
         "WASH": 4, "NULLP": 5, "BIGSHEET": 3, "INSIDEXI": 6}


async def main() -> None:
    await build_schema()
    async with engine.begin() as conn:
        for stmt in superseded_ddl.STATEMENTS:        # the lifespan re-applies these: production reads THESE views
            await conn.execute(text(stmt))
        ok = await superseded_ddl.verify(conn)
    check("the production source-aware views are the ones under test", all(ok.values()), str(ok))
    async with engine.begin() as conn:
        # `audit_logs` is created inline in main.py's lifespan, so create_all never makes it: the
        # same columns, copied, as the repair script's own suite does.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY, created_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL, user_id UUID,
                action TEXT NOT NULL, target_type TEXT, target_id TEXT, details JSONB DEFAULT '{}')"""))
    await seed()

    print("\n-- CONTROL: NOTHING JUDGED YET, AND THE APP READS WHAT IT READ BEFORE --")
    for k, want in BEFORE.items():
        got = await header(k)
        check(f"{NAMES[k]}: the header reads {want} (the reported over-count)", got == want, str(got))
    check("Jack reads 4 beside CA's 3: the reported one-game gap", await header("JACK") == 4 and await season_row("JACK") == 3)

    await set_flags()

    print("\n-- THE PROFILE HEADER, WITH THE FLAGS --")
    for k, want in AFTER.items():
        got = await header(k)
        check(f"{NAMES[k]}: the header reads {want}", got == want, f"{got} (was {BEFORE[k]})")

    print("\n-- WHERE CA'S OWN TOTAL ALREADY LEFT THE GAME OUT, IT IS NOT TAKEN OFF TWICE --")
    check("Jack: CA 3, the reserve was never in it, so 3 and not 2", await header("JACK") == 3 and await season_row("JACK") == 3)
    check("Baetsen: CA 0 stays 0 and does not go negative", await header("BAET") == 0 and await season_row("BAET") == 0)

    print("\n-- WHERE CA COUNTED THE GAME, BETTERCRICKET HOLDS THE MORE ACCURATE FIGURE (BELOW CA) --")
    check("Castley: CA says 11, the season row says 10", await season_row("CASTLEY") == 10, str(await season_row("CASTLEY")))
    check("Sulway: CA says 14 with two reserves, the season row says 13", await season_row("SULWAY") == 13)
    check("Big sheet (13 of 14): CA says 3 and the row stays 3", await season_row("BIGSHEET") == 3)

    print("\n-- WHERE WE ARE MISSING A SCORECARD OR CA IS LOWER FOR ANOTHER REASON, THE RAISE STILL HOLDS --")
    check("Stackpole: CA 17 beside 15 real games; one of the extra two was the reserve, so 16",
          await header("STACKPOLE") == 16 and await season_row("STACKPOLE") == 16)
    check("Shanmuganathan: CA is below the games we hold, the reserve comes off the held side, so 16",
          await header("SHAN") == 16)

    print("\n-- A RESERVE WITH A ROW OF THEIR OWN PLAYED --")
    check("a flagged player with a catch keeps the match", await header("FIELDER") == 6 and await season_row("FIELDER") == 6)
    print("\n-- A GAME NOBODY PLAYED IS TAKEN ONCE --")
    check("a reserve in an abandoned game: the washout rule takes the one game, not two", await header("WASH") == 4)
    print("\n-- NOT JUDGED IS READ AS PLAYED --")
    check("a named-only game with no card is left alone", await header("NULLP") == 5)

    print("\n-- EVERY SURFACE READS THE SAME FIGURE --")
    check("by-grade grid total: Castley 10 (CA's per-grade claim of 11 counted the reserve)", await grid("CASTLEY") == 10, str(await grid("CASTLEY")))
    check("by-grade grid total: Jack 3", await grid("JACK") == 3, str(await grid("JACK")))
    check("the batting board agrees with the profile: Castley 10", await board("CASTLEY") == 10, str(await board("CASTLEY")))
    check("the batting board agrees with the profile: Jack 3", await board("JACK") == 3, str(await board("JACK")))
    check("the batting board never reads below the held games: Stackpole 16", await board("STACKPOLE") == 16, str(await board("STACKPOLE")))

    print("\n-- FEES: THE SAME PREDICATE DECIDES WHO IS CHARGED A MATCH DAY --")
    async with Session() as s:
        # exactly the call fees.recompute_fee_match_days makes
        rows = (await s.execute(select(GameAppearance).where(text(appearance_counts_as_match("game_appearances"))))).scalars().all()
    charged = {(a.game_id, a.player_id) for a in rows}
    reserve_pairs = {(g, P[k]) for k, gs in RESERVE_GAMES.items() for g in gs if k not in ("FIELDER", "WASH")}
    check("no 12th man who did not play is charged a match day", not (reserve_pairs & charged), str(reserve_pairs & charged))
    check("a 12th man with a catch is still charged", any(p == P["FIELDER"] and g == RESERVE_GAMES["FIELDER"][0] for g, p in charged))
    dnb = next(g for k, g, f, sl in JUDGED if k == "JACK" and f is False and sl == 7)
    check("a Did Not Bat on the card is still charged", (dnb, P["JACK"]) in charged)
    rain = next(g for k, g, f, sl in JUDGED if k == "JACK" and sl == 4)
    check("a player named in a game our side never batted in is still charged", (rain, P["JACK"]) in charged)
    check("an appearance never judged is still charged",
          any(p == P["NULLP"] for g, p in charged))

    print("\n-- THE SYNC WRITES THE FLAG, ONLY ONCE THE GAME IS OVER --")
    sh = sheet_with(P["JACK"], 12, 12)
    done = card(sh, off_card(sh, P["JACK"]))
    team = done["teams"][0]
    flags = reserve_players.sync_flags(done, team)
    f = flags[str(P["JACK"])]
    check("a completed game flags the 12th man, slot 12", f == {"slot": 12, "is_reserve": True}, str(f))
    check("and the player on the card is not a reserve", flags[sh[0]]["is_reserve"] is False)
    check("a game still LIVE writes nothing: no batting yet would read as 'never batted'",
          reserve_players.sync_flags({**done, "status": "LIVE"}, team) == {})
    check("an UPCOMING fixture writes nothing", reserve_players.sync_flags({**done, "status": "UPCOMING"}, team) == {})
    check("no card writes nothing", reserve_players.sync_flags(None, team) == {} and reserve_players.sync_flags(done, None) == {})
    rain_card = card(sheet_with(P["JACK"], 4, 13), None)
    check("a side that never batted flags nobody", not any(v["is_reserve"] for v in reserve_players.sync_flags(rain_card, rain_card["teams"][0]).values()))

    print("\n-- THE BACKFILL: DRY RUN, APPLY, RESTORE --")
    await clear_flags()
    from argparse import Namespace
    args = Namespace(year=None, pace=0.0, timeout=120, list=40, max_games=500)

    async def planned(budget=500):
        FETCHES.clear()
        return await backfill.plan(str(ORG), args, [budget])

    rows_, left = await planned()
    reserves = [r for r in rows_ if r["is_reserve"]]
    want_reserve = {(str(g), str(P[k])) for k, g, f, sl in JUDGED if f is True and k not in ("FIELDER", "WASH")}
    check("the plan flags exactly the 12th-man games", {(r["game_id"], r["player_id"]) for r in reserves} == want_reserve,
          f"{len(reserves)} planned, {len(want_reserve)} expected")
    check("it judges the DNB, the rained-off and the inside-XI shapes FALSE (present in the plan, not flagged)",
          sum(1 for r in rows_ if not r["is_reserve"]) == 3, str(sum(1 for r in rows_ if not r["is_reserve"])))
    check("a game CA has no card for is left NULL, not guessed", any("no card" in k for k in left), str(dict(left)))
    check("a reserve with a catch and a washout are never candidates (they have rows or were not played)",
          not any(r["player_id"] in (str(P["FIELDER"]), str(P["WASH"])) for r in rows_))
    async with Session() as s:
        n_set = (await s.execute(text("SELECT COUNT(*) FROM game_appearances WHERE is_reserve IS NOT NULL"))).scalar()
    check("the dry run writes nothing", n_set == 0, str(n_set))
    check("one scorecard request per game", len(FETCHES) == len(set(FETCHES)))

    try:
        await backfill.apply(str(ORG), rows_, len(rows_) + 1, "Test Admin")
        check("a wrong --expect is refused", False, "it applied")
    except SystemExit:
        check("a wrong --expect is refused", True)
    try:
        await backfill.apply(str(ORG), rows_, len(rows_), None)
        check("a missing --by is refused", False, "it applied")
    except SystemExit:
        check("a missing --by is refused", True)
    await backfill.apply(str(ORG), rows_, len(rows_), "Test Admin")
    async with Session() as s:
        flagged = (await s.execute(text("SELECT COUNT(*) FROM game_appearances WHERE is_reserve IS TRUE"))).scalar()
        judged_false = (await s.execute(text("SELECT COUNT(*) FROM game_appearances WHERE is_reserve IS FALSE"))).scalar()
        audit = (await s.execute(text("SELECT id, details FROM audit_logs WHERE action = 'backfill_reserve_flags'"))).mappings().all()
    check("the flags are written", flagged == len(reserves) and judged_false == len(rows_) - len(reserves), f"{flagged}/{judged_false}")
    check("one audit entry holds every row written", len(audit) == 1 and len(audit[0]["details"]["changes"]) == len(rows_))
    check("after the backfill Jack reads 3 and Castley 10, as the sync's own flags give",
          await header("JACK") == 3 and await header("CASTLEY") == 10)

    rows2, _ = await planned()
    check("a second run judges nothing new", rows2 == [], f"{len(rows2)} rows")
    check("and asks CA only about the one game it holds no card for (left NULL, so tried again: one request)",
          len(FETCHES) == 1 and uuid.UUID(FETCHES[0]) not in {g for _, g, _, _ in JUDGED}, str(FETCHES))

    await backfill.restore(audit[0]["id"], "Test Admin")
    async with Session() as s:
        n_set = (await s.execute(text("SELECT COUNT(*) FROM game_appearances WHERE is_reserve IS NOT NULL"))).scalar()
        a2 = (await s.execute(text("SELECT details FROM audit_logs WHERE id = :i"), {"i": audit[0]["id"]})).scalar()
    check("--restore puts every row back to NULL", n_set == 0, str(n_set))
    check("and the app reads the old figure again (Jack 4): nothing was lost", await header("JACK") == 4)
    check("the entry records it was restored", bool(a2.get("restored_at")))
    try:
        await backfill.restore(audit[0]["id"], "Test Admin")
        check("an entry restores once", False, "restored twice")
    except SystemExit:
        check("an entry restores once", True)

    print("\n-- A FLAG A PERSON SET IS NEVER REPLACED --")
    async with Session() as s:
        gid = next(g for k, g, f, sl in JUDGED if k == "CASTLEY")
        await s.execute(text("UPDATE game_appearances SET is_reserve = FALSE WHERE game_id = :g AND player_id = :p"), {"g": gid, "p": P["CASTLEY"]})
        await s.commit()
    rows3, _ = await planned()
    check("a row already judged (here set by hand to 'played') is not read or changed",
          not any(r["player_id"] == str(P["CASTLEY"]) for r in rows3))
    check("and Castley keeps counting that game", await header("CASTLEY") == 11)

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
