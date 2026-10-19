"""The 12th-man audit flags exactly the right games, against a real Postgres. Read only.

Reported by Applecross: Jack Barendse reads 214 matches, CA reads 213. The one game is a Grand
Final where he was 12th man: on the team sheet, never on the batting card, no bowling, no catch.
`appearance_counts_as_match` counts any named player, so the profile counts it and CA does not.

`app.scripts.audit_twelfth_man` tests a rule for the shape: the side batted, the player is not on
its card, has no bowling or fielding, and sits beyond slot 11. The user's constraint is that the
rule must NOT reach a game like 8a5f61d3 (rained off, nobody from Applecross batted) nor a game
where the player is on the card as Did Not Bat. This suite seeds each shape through the real
query paths (`v_effective_*`, `game_appearances`, `player_season_stats`) with CA-shaped
scorecards, and checks both directions: the games the rule must flag ARE flagged, and the games
it must leave alone are present in the audit and NOT flagged.

Control: the seed reproduces the reported behaviour first. The profile header reads one game
above CA's own season total, and it is the game this audit goes on to flag.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \\
  python verification/verify_twelfth_man_audit.py
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

# The schema the board suite builds (create_all, the late ALTERs, the views out of the
# migrations): one copy, so this suite cannot drift from what the app runs.
from verify_board_games_match_profile import build_schema
from app.routers.players import get_player_stats
from app.scripts import audit_twelfth_man as audit
from app.services import superseded_ddl
from app.services import grassroots_scores_client as gr

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
OUR_TEAM, THEIR_TEAM = str(uuid.uuid4()), str(uuid.uuid4())
S_1617, G_8TH = uuid.uuid4(), uuid.uuid4()

JACK, BAET, MON, ELTON, OVER, MISSED, DRIFT = (uuid.uuid4() for _ in range(7))
PLAYERS = {JACK: "Barendse, Jack", BAET: "Baetsen, Burt", MON: "Monument, Darren", ELTON: "Barendse, Elton",
           OVER: "Over, Flagged", MISSED: "Missed, Gap", DRIFT: "Drift, Stats"}


def filler(n: int) -> list[str]:
    return [str(uuid.uuid4()) for _ in range(n)]


def card(sheet: list[str], on_card: list[tuple[str, str, int]] | None, *, bowl=(), field=()) -> dict:
    """A CA-shaped scorecard. `sheet` is OUR team list in slot order. `on_card` is our batting
    card as (participantId, dismissalType, dismissalTypeId); None means our side never batted."""
    innings = []
    if on_card is not None:
        innings.append({"battingTeamId": OUR_TEAM, "inningsOrder": 1,
                        "batting": [{"participantId": p, "dismissalType": t, "dismissalTypeId": i}
                                    for p, t, i in on_card],
                        "bowling": [], "fielding": []})
    innings.append({"battingTeamId": THEIR_TEAM, "inningsOrder": 2,
                    "batting": [{"participantId": g, "dismissalType": "Bowled", "dismissalTypeId": 2}
                                for g in filler(11)],
                    "bowling": [{"participantId": str(p)} for p in bowl],
                    "fielding": [{"participantId": str(p)} for p in field]})
    return {"status": "COMPLETED",
            "teams": [{"id": OUR_TEAM, "players": [{"participantId": g, "roles": []} for g in sheet]},
                      {"id": THEIR_TEAM, "players": [{"participantId": g, "roles": []} for g in filler(11)]}],
            "innings": innings}


def batters(sheet: list[str], skip: set[str]) -> list[tuple[str, str, int]]:
    """Everyone on the sheet bats except `skip`: the card as a scorer leaves it."""
    return [(g, "Bowled", 2) for g in sheet if g not in skip]


GAMES: dict[uuid.UUID, dict] = {}   # game id -> the scorecard the stub serves
FETCHES: list[str] = []


async def _stub_scorecard(match_id: str, *, force: bool = False):
    FETCHES.append(match_id)
    return GAMES.get(uuid.UUID(match_id))


gr.get_match_scorecard = _stub_scorecard

G = {k: uuid.uuid4() for k in (
    "stats", "dnb", "rain", "twelfth", "twelfth_b", "mid", "mid_stats", "wash", "over", "miss_stats",
    "miss_dnb", "drift", "elton_other")}


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        for oid, nm, slug in ((ORG, "Audit Club", "audit"), (OPP, "Opposition CC", "opp")):
            await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)",
                     i=oid, n=nm, s=slug)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2016/17', 2016)",
                 i=S_1617, o=ORG)
        await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                 "VALUES (:i, :s, '8th Grade', :g, 'senior', ARRAY['senior'])", i=G_8TH, s=S_1617, g=str(G_8TH))
        for pid, nm in PLAYERS.items():
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                     "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=ORG, n=nm, g=str(pid))

        day = 0

        async def game(key, *, status="COMPLETED", players=(), rows=(), sheet=None, on_card=None, **cardkw):
            """One game. `players` are named on the sheet (a game_appearances row each);
            `rows` get a real batting row. `sheet` is the full CA team list, in slot order."""
            nonlocal day
            day += 7
            gid = G[key]
            # `innings_totals` is what the sync writes from CA's innings[]; without a scored innings
            # a game reads as "nothing was played" (`looks_unplayed_sql`) and no named player counts it.
            await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, "
                     " match_format, status, innings_totals) "
                     "VALUES (:i, :g, :d, 'WIN', :o, :x, 'Two Day', :st, CAST(:it AS JSONB))",
                     i=gid, g=G_8TH, d=date(2016, 10, 1) + timedelta(days=day), o=ORG, x=OPP, st=status,
                     it='[{"runs_scored": 146, "wickets": 9}, {"runs_scored": 118, "wickets": 10}]')
            for p in players:
                await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=gid, p=p)
            for p in rows:
                await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, "
                         " sixes, not_out, dismissal_type, did_not_bat) "
                         "VALUES (:g, :p, 1, 20, 25, 1, 0, false, 'caught', false)", g=gid, p=p)
            if sheet is not None:
                GAMES[gid] = card(sheet, on_card, **cardkw)

        def sheet_with(player, slot, size):
            """A team list of `size` with `player` at 1-based `slot`."""
            others = filler(size - 1)
            others.insert(slot - 1, str(player))
            return others

        # JACK: his four named-only shapes plus one real game, as in the reported season.
        await game("stats", players=[JACK], rows=[JACK], sheet=sheet_with(JACK, 3, 11),
                   on_card=[(str(JACK), "Bowled", 2)])
        sh = sheet_with(JACK, 7, 12)
        await game("dnb", players=[JACK], sheet=sh,                                  # 59a24d84: on the card, DNB id 0
                   on_card=batters(sh, {str(JACK)}) + [(str(JACK), "Did Not Bat", 0)])
        sh = sheet_with(JACK, 4, 13); sh[11] = str(ELTON)                            # 8a5f61d3: rained off
        await game("rain", players=[JACK, ELTON], sheet=sh, on_card=None)
        sh = sheet_with(JACK, 12, 12)                                                # 651d4d5a: the 12th man
        await game("twelfth", players=[JACK], sheet=sh, on_card=batters(sh, {str(JACK)}))
        await game("wash", status="ABANDONED", players=[JACK], sheet=sheet_with(JACK, 12, 12),
                   on_card=batters(sheet_with(JACK, 12, 12), {str(JACK)}))           # called off: never a match

        # BAET: only game that season is a 12th-man game; CA counts none.
        sh = sheet_with(BAET, 12, 12)
        await game("twelfth_b", players=[BAET], sheet=sh, on_card=batters(sh, {str(BAET)}))
        # MON: off the card but slot 8 of 12, so inside the XI; CA counts it.
        sh = sheet_with(MON, 8, 12)
        await game("mid", players=[MON], sheet=sh, on_card=batters(sh, {str(MON)}))
        await game("mid_stats", players=[MON], rows=[MON], sheet=sheet_with(MON, 2, 11),
                   on_card=[(str(MON), "Bowled", 2)])
        # ELTON: slot 12 of 13 in the rained-off game ('rain'), his only game; CA counts it.
        # OVER: looks like a 12th man, but CA counts the game: the rule is WRONG here.
        sh = sheet_with(OVER, 12, 12)
        await game("over", players=[OVER], sheet=sh, on_card=batters(sh, {str(OVER)}))
        # MISSED: a Did-Not-Bat game on the card and CA is one short: another cause.
        await game("miss_stats", players=[MISSED], rows=[MISSED], sheet=sheet_with(MISSED, 2, 11),
                   on_card=[(str(MISSED), "Bowled", 2)])
        sh = sheet_with(MISSED, 9, 12)
        await game("miss_dnb", players=[MISSED], sheet=sh,
                   on_card=batters(sh, {str(MISSED)}) + [(str(MISSED), "Did Not Bat", 0)])
        # DRIFT: no row of ours, but the card carries a catch for them.
        sh = sheet_with(DRIFT, 12, 12)
        await game("drift", players=[DRIFT], sheet=sh, on_card=batters(sh, {str(DRIFT)}), field=[DRIFT])

        async def ca(player, matches):
            await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, "
                     " not_outs, wickets, catches, source) VALUES (:p, :s, :m, 0, 0, 0, 0, 0, 'api')",
                     p=player, s=S_1617, m=matches)

        await ca(JACK, 3)      # holds 4 (stats, dnb, rain, twelfth): CA is one lower
        await ca(BAET, 0)
        await ca(MON, 2)
        await ca(ELTON, 1)
        await ca(OVER, 1)
        await ca(MISSED, 1)    # holds 2, CA says 1
        await ca(DRIFT, 1)
        await s.commit()


async def table_counts() -> dict:
    async with Session() as s:
        out = {}
        for t in ("games", "game_appearances", "batting_innings", "bowling_spells", "fielding_stats",
                  "player_season_stats", "players", "seasons", "grades"):
            out[t] = (await s.execute(text(f"SELECT COUNT(*) FROM {t}"))).scalar()
        return out


async def profile_games(player) -> int:
    async with Session() as s:
        d = await get_player_stats(
            player_id=str(player), db=s, season_id=None, grade_id=None, last_n_games=None,
            start_date=None, end_date=None, categories=None, formats=None, competitions=None, grades=None)
    return (d["career_batting"] or {}).get("games")


def by(rows, player, game):
    return next((r for r in rows if r["player_id"] == str(player) and r["game_id"] == str(G[game])), None)


async def apply_production_views() -> None:
    """The lifespan re-applies `superseded_ddl` on every boot, so production reads THESE views, not
    the migrations'. The audit first read them per row and took 38s on 40,000 appearances here
    against 0.4s on the migration versions: a suite on the wrong views cannot see that."""
    async with engine.begin() as conn:
        for stmt in superseded_ddl.STATEMENTS:
            await conn.execute(text(stmt))
        ok = await superseded_ddl.verify(conn)
    check("the production source-aware views are the ones under test", all(ok.values()), str(ok))


async def main() -> None:
    await build_schema()
    await apply_production_views()
    await seed()
    args = Namespace(year=None, pace=0.0, list=40, csv=None, max_games=500, timeout=120)

    print("\n-- CONTROL: THE SEED REPRODUCES THE REPORTED BEHAVIOUR --")
    jack_profile = await profile_games(JACK)
    check("Jack's header reads 4 games while CA's season total says 3 (the reported one-game gap)",
          jack_profile == 4, str(jack_profile))
    check("BetterCricket's two answers for Baetsen differ: header 1, CA 0",
          await profile_games(BAET) == 1)

    before = await table_counts()
    FETCHES.clear()
    rows = await audit.audit_club(str(ORG), "Audit Club", args, [args.max_games])
    after = await table_counts()

    print("\n-- WHICH NAMED-ONLY APPEARANCES THE AUDIT SEES --")
    check("the called-off game never becomes a candidate (it was not a match)", by(rows, JACK, "wash") is None)
    check("a game with a real row is not a candidate", by(rows, JACK, "stats") is None
          and by(rows, MON, "mid_stats") is None)
    check("every named-only game is present, so each can be shown to be left alone",
          all(by(rows, p, g) is not None for p, g in (
              (JACK, "dnb"), (JACK, "rain"), (ELTON, "rain"), (JACK, "twelfth"), (BAET, "twelfth_b"),
              (MON, "mid"), (OVER, "over"), (MISSED, "miss_dnb"), (DRIFT, "drift"))))

    print("\n-- THE FIVE-CONDITION RULE FLAGS THE 12TH MAN AND NOTHING ELSE --")
    flagged = {(r["player_id"], r["game_id"]) for r in rows if r["code"] == audit.TWELFTH_MAN}
    want = {(str(JACK), str(G["twelfth"])), (str(BAET), str(G["twelfth_b"])), (str(OVER), str(G["over"]))}
    check("flags Jack's 12th-man game, Baetsen's and the look-alike (OVER), exactly", flagged == want,
          str(sorted(flagged)))
    r = by(rows, JACK, "twelfth")
    check("Jack's 12th-man game reads slot 12 of 12", (r["slot"], r["sheet"]) == (12, 12), str(r))
    r = by(rows, JACK, "rain")
    check("the rained-off game (nobody on our side batted) is NOT flagged", r["code"] == "SIDE_DID_NOT_BAT", r["code"])
    r = by(rows, ELTON, "rain")
    check("...even for a player listed 12th of 13 in it", r["code"] == "SIDE_DID_NOT_BAT" and r["slot"] == 12,
          f"{r['code']} slot {r['slot']}")
    r = by(rows, JACK, "dnb")
    check("a Did Not Bat on the card (CA id 0, which sync never stores) is NOT flagged", r["code"] == "ON_CARD_DNB", r["code"])
    r = by(rows, MON, "mid")
    check("off the card at slot 8 of 12 is NOT flagged", r["code"] == "INSIDE_XI" and r["slot"] == 8, f"{r['code']} {r['slot']}")
    r = by(rows, DRIFT, "drift")
    check("a card row our tables lack (a catch) is NOT flagged", r["code"] == "HAS_STATS", r["code"])

    print("\n-- AGAINST CA'S OWN SEASON TOTAL --")
    check("Jack: held 4, CA 3, one flagged: the rule explains the whole gap",
          by(rows, JACK, "twelfth")["verdict"] == "EXPLAINED", by(rows, JACK, "twelfth")["verdict"])
    check("Jack's other named-only games carry the same season verdict (one line per player-season)",
          by(rows, JACK, "rain")["verdict"] == "EXPLAINED" and by(rows, JACK, "dnb")["verdict"] == "EXPLAINED")
    check("Baetsen: held 1, CA 0: explained", by(rows, BAET, "twelfth_b")["verdict"] == "EXPLAINED")
    check("Monument: CA counts the off-card slot-8 game, nothing flagged: AGREES",
          by(rows, MON, "mid")["verdict"] == "AGREES", by(rows, MON, "mid")["verdict"])
    check("Elton (12th of 13, rained off): CA counts it, nothing flagged: AGREES",
          by(rows, ELTON, "rain")["verdict"] == "AGREES")
    check("OVER: the rule flags a game CA counts, and the audit says so (OVER_FLAGS)",
          by(rows, OVER, "over")["verdict"] == "OVER_FLAGS", by(rows, OVER, "over")["verdict"])
    check("MISSED: CA is one lower and nothing was flagged: MISSED",
          by(rows, MISSED, "miss_dnb")["verdict"] == "MISSED", by(rows, MISSED, "miss_dnb")["verdict"])

    print("\n-- IT WRITES NOTHING AND ASKS CA ONCE PER GAME --")
    check("no table changed", before == after, f"{before} -> {after}")
    named_games = {r["game_id"] for r in rows}
    check("one scorecard request per named-only game, however many players share it",
          len(FETCHES) == len(set(FETCHES)) == len(named_games), f"{len(FETCHES)} fetches, {len(named_games)} games")
    check("the shared rained-off game (two players) was asked for once", FETCHES.count(str(G["rain"])) == 1)

    FETCHES.clear()
    capped = await audit.audit_club(str(ORG), "Audit Club", Namespace(year=None, pace=0.0, list=5, csv=None, max_games=3, timeout=120),
                                    [3])
    check("a --max-games allowance of 3 stops at 3 requests", len(FETCHES) == 3, str(len(FETCHES)))
    check("and games beyond it are left unjudged, not guessed",
          len(capped) < len(rows) and all(r["code"] for r in capped))

    print("\n-- THE PURE RULE, EDGE BY EDGE --")
    me = "aaaaaaaa-0000-0000-0000-000000000001"
    cd = card([*filler(11), me], [(g, "Bowled", 2) for g in filler(11)])
    check("12th of 12, side batted, off the card: TWELFTH_MAN", audit.classify(cd, {me})["code"] == "TWELFTH_MAN")
    cd = card([*filler(10), me, *filler(1)], [(g, "Bowled", 2) for g in filler(11)])
    check("11th of 12: INSIDE_XI (slot 11 is the last place in the XI)", audit.classify(cd, {me})["code"] == "INSIDE_XI")
    check("a merged-away id is honoured: the card carries the old id",
          audit.classify(cd, {"zz", str(cd['teams'][0]['players'][10]['participantId'])})["code"] == "INSIDE_XI")
    check("no card at all: NO_CARD", audit.classify(None, {me})["code"] == "NO_CARD")
    check("a player on neither sheet: NOT_ON_SHEET", audit.classify(cd, {"nobody"})["code"] == "NOT_ON_SHEET")
    cd = card([*filler(11), me], [(g, "Bowled", 2) for g in filler(11)], bowl=[me])
    check("a bowling row on the card: HAS_STATS, never flagged", audit.classify(cd, {me})["code"] == "HAS_STATS")
    cd = card([*filler(11), me], [(g, "Bowled", 2) for g in filler(11)] + [(me, "Absent", 5)])
    check("an Absent row on the card: ON_CARD_DNB, never flagged", audit.classify(cd, {me})["code"] == "ON_CARD_DNB")
    print("\n-- CHECK THE CHECKS: the rule can flag, and verdict() reaches every branch --")
    check("verdict EXPLAINED", audit.verdict(4, 3, 1) == "EXPLAINED")
    check("verdict OVER_FLAGS", audit.verdict(1, 1, 1) == "OVER_FLAGS")
    check("verdict PARTLY", audit.verdict(5, 3, 1) == "PARTLY")
    check("verdict MISSED", audit.verdict(2, 1, 0) == "MISSED")
    check("verdict AGREES", audit.verdict(2, 2, 0) == "AGREES")
    check("verdict NO_CA_TOTAL", audit.verdict(2, None, 0) == "NO_CA_TOTAL")

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
