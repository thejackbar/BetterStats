"""BetterIQ: an opposition player's record AGAINST US (the "Against us" tab).

Asked for by a club scouting a Western Suburbs batter they had met twice in a
year: the profile showed overview, batting and bowling, but nothing on how the
player had fared against them, who had got them out, who had caught them, or
which of their batters the player had dismissed.

Runs the SHIPPED `opposition_player_vs_us` route body under the shipped
`apply_grade_scope` dependency, with the real `_our_games_vs` read over the
real `v_effective_*` views on a real Postgres, and the real background build
and cache. Only the Cricket Australia scorecard fetch is stubbed (no network).

    VERIFY_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/verify_iq_vs_us \\
      python -m verification.verify_iq_player_vs_us

Control run: against the previous commit the route does not exist, so every
check reports the record as absent (read through presence-safe accessors).
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

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/verify_iq_vs_us",
)
os.environ["DATABASE_URL"] = DB_URL

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from _view_ddl import view_statements  # noqa: E402
from app.models.db import Base, Organisation  # noqa: E402
from app.routers import iq as iq_router  # noqa: E402
from app.services import grassroots_scores_client as gr_client  # noqa: E402

engine = create_async_engine(DB_URL, echo=False)
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


US = uuid.uuid4()                 # Applecross (us)
THEM = str(uuid.uuid4())          # Western Suburbs' CA org GUID (not a synced club)
OTHER = str(uuid.uuid4())         # a third club
S_US = uuid.uuid4()
G_OD4, G_OD1 = uuid.uuid4(), uuid.uuid4()

# Our players: DB id and raw CA GUID differ (per-club ids, rule 3).
OUR = {
    "smith": (uuid.uuid4(), str(uuid.uuid4()), "Tom Smith", "T Smith"),
    "jones": (uuid.uuid4(), str(uuid.uuid4()), "Ryan Jones", "R Jones"),
    "white": (uuid.uuid4(), str(uuid.uuid4()), "Pat White", "P White"),
    "brown": (uuid.uuid4(), str(uuid.uuid4()), "Ben Brown", "B Brown"),
    "lee": (uuid.uuid4(), str(uuid.uuid4()), "Sam Lee", "S Lee"),
}
BARWOOD = str(uuid.uuid4())       # the scouted player
BARWOOD_ALT = str(uuid.uuid4())   # the same player under another CA GUID on one card
MATE = str(uuid.uuid4())          # a teammate of theirs
GAMES: dict[str, dict] = {}       # game id -> scorecard


def team(tid, org, name, players):
    return {"id": tid, "displayName": name, "owningOrganisation": {"id": org, "name": name},
            "players": [{"participantId": p, "displayName": dn, "playerShortName": sn} for p, dn, sn in players]}


def our_team():
    return team("t-us", str(US), "Applecross 6th XI",
                [(g, full, short) for (_id, g, full, short) in OUR.values()])


def their_team(barwood_id=BARWOOD, with_barwood=True, org=THEM, name="Western Suburbs 4th XI"):
    ps = [(MATE, "Max Mate", "M Mate")]
    if with_barwood:
        ps.append((barwood_id, "Adam Barwood", "A Barwood"))
    return team("t-them", org, name, ps)


def bat(pid, runs, balls, dtype, dtext, dt_id=2):
    return {"participantId": pid, "runsScored": runs, "ballsFaced": balls, "dismissalTypeId": dt_id,
            "dismissalType": dtype, "dismissalText": dtext}


def bowlr(pid, short, overs, runs, wkts):
    return {"participantId": pid, "playerShortName": short, "oversBowled": overs,
            "runsConceded": runs, "wicketsTaken": wkts, "maidensBowled": 0}


def fld(pid, short, ct=0, wk=0, st=0, ro=0):
    return {"participantId": pid, "playerShortName": short, "totalCatches": ct + wk,
            "wicketKeeperCatches": wk, "stumpings": st, "runOuts": ro}


def card(on, teams, innings):
    return {"matchSchedule": [{"startDateTime": f"{on.isoformat()}T10:00:00"}], "teams": teams, "innings": innings}


def g(k):
    return OUR[k][1]


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)"""))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)"""))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, 'Applecross CC', 'applecross-v', true)", i=US)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2025/26', 2025)", i=S_US, o=US)
        for gid, nm in ((G_OD4, "One Day Grade 4"), (G_OD1, "One Day Grade 1")):
            await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                     "VALUES (:i, :s, :n, :g, 'senior', ARRAY['senior'])", i=gid, s=S_US, n=nm, g=str(gid))
        for pid, guid, full, _short in OUR.values():
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                     "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=US, n=full, g=guid)

        async def game(on, opp_org, opp_name, sc, grade=G_OD4):
            gid = uuid.uuid4()
            await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, "
                     " opp_org_id, opp_club_name, match_format, status) "
                     "VALUES (:i, :g, :d, 'WIN', :h, NULL, :oo, :on, 'One Day', 'COMPLETED')",
                     i=gid, g=grade, d=on, h=US, oo=opp_org, on=opp_name)
            GAMES[str(gid)] = sc

        ws = "Western Suburbs CC"
        # Game 1: Barwood caught behind off Smith (Jones keeping). Barwood bowls Brown
        # and catches Lee.
        d1 = date(2026, 1, 17)
        await game(d1, THEM, ws, card(d1, [our_team(), their_team()], [
            {"batting": [bat(BARWOOD, 19, 23, "Caught", "c: R Jones b: T Smith"),
                         bat(MATE, 30, 40, "Bowled", "b: P White")],
             "bowling": [bowlr(g("smith"), "T Smith", 8, 30, 1), bowlr(g("white"), "P White", 6, 20, 1)],
             "fielding": [fld(g("jones"), "R Jones", wk=1)]},
            {"batting": [bat(g("brown"), 4, 9, "Bowled", "b: A Barwood"),
                         bat(g("lee"), 12, 20, "Caught", "c: A Barwood b: M Mate"),
                         bat(g("smith"), 22, 30, "Not Out", "not out", dt_id=1)],
             "bowling": [bowlr(BARWOOD, "A Barwood", 7, 25, 1), bowlr(MATE, "M Mate", 5, 18, 1)],
             "fielding": [fld(BARWOOD, "A Barwood", ct=1)]},
        ]))
        # Game 2: Barwood bowled by Smith. Barwood traps Brown lbw.
        d2 = date(2026, 3, 7)
        await game(d2, THEM, ws, card(d2, [our_team(), their_team()], [
            {"batting": [bat(BARWOOD, 2, 6, "Bowled", "b: T Smith")],
             "bowling": [bowlr(g("smith"), "T Smith", 8, 22, 1)], "fielding": []},
            {"batting": [bat(g("brown"), 0, 3, "LBW", "lbw b: A Barwood")],
             "bowling": [bowlr(BARWOOD, "A Barwood", 6, 14, 1)], "fielding": []},
        ]))
        # Game 3: Barwood under a different GUID on this card (found by name), caught
        # by Jones in the outfield off White; runs Lee out.
        d3 = date(2026, 10, 31)
        await game(d3, THEM, ws, card(d3, [our_team(), their_team(barwood_id=BARWOOD_ALT)], [
            {"batting": [bat(BARWOOD_ALT, 40, 52, "Caught", "c: R Jones b: P White")],
             "bowling": [bowlr(g("white"), "P White", 8, 35, 1)],
             "fielding": [fld(g("jones"), "R Jones", ct=1)]},
            {"batting": [bat(g("lee"), 7, 11, "Run Out", "run out (A Barwood)")],
             "bowling": [bowlr(MATE, "M Mate", 8, 40, 0)],
             "fielding": [fld(BARWOOD_ALT, "A Barwood", ro=1)]},
        ], ), grade=G_OD4)
        # Game 4: against them, but Barwood sat it out.
        d4 = date(2025, 12, 6)
        await game(d4, THEM, ws, card(d4, [our_team(), their_team(with_barwood=False)], [
            {"batting": [bat(MATE, 50, 60, "Bowled", "b: T Smith")],
             "bowling": [bowlr(g("smith"), "T Smith", 8, 30, 1)], "fielding": []},
        ]))
        # Game 5: against them, hand-entered, no CA scorecard.
        await game(date(2025, 11, 1), THEM, ws, None)
        # Game 6: against ANOTHER club; a player of theirs with Barwood's GUID must not count.
        d6 = date(2026, 2, 14)
        await game(d6, OTHER, "Other CC", card(d6, [our_team(), their_team(org=OTHER, name="Other CC")], [
            {"batting": [bat(BARWOOD, 99, 80, "Caught", "c: R Jones b: T Smith")],
             "bowling": [bowlr(g("smith"), "T Smith", 8, 30, 1)], "fielding": [fld(g("jones"), "R Jones", ct=1)]},
        ]))
        await s.commit()


async def _fake_scorecard(match_id, *_a, **_k):
    return GAMES.get(str(match_id))


async def vs_us(player: str, player_name: str | None = None, opponent: str = THEM) -> dict:
    route = getattr(iq_router, "opposition_player_vs_us", None)
    if route is None:
        return {}
    async with Session() as s:
        club = (await s.execute(select(Organisation).where(Organisation.id == US))).scalar_one()
        gen = iq_router.apply_grade_scope(categories=None, formats=None, competitions=None, db=s, club=club)
        await gen.__anext__()
        try:
            res: dict = {}
            for _ in range(150):
                res = await route(opponent=opponent, player=player, player_name=player_name,
                                  club_name="Western Suburbs CC", db=s, club=club)
                if res.get("status") != "building":
                    break
                await asyncio.sleep(0.1)
            return res
        finally:
            await gen.aclose()


def row(rows, name):
    return next((r for r in (rows or []) if r.get("name") == name), None)


async def main() -> int:
    gr_client.get_match_scorecard = _fake_scorecard
    await build_schema()
    await seed()

    print("\n-- Barwood against Applecross --")
    d = await vs_us(BARWOOD, "Adam Barwood")
    check("the record is built (status ready)", d.get("status") == "ready", str(d.get("status")))
    check("5 games against Western Suburbs on record, 4 with a scorecard",
          d.get("games_total") == 5 and d.get("games_checked") == 4, f"{d.get('games_total')}/{d.get('games_checked')}")
    check("Barwood appeared in 3 (one card under another GUID, found by name)",
          d.get("games_played") == 3, str(d.get("games_played")))
    b = d.get("batting") or {}
    check("batting against us: 3 innings, 61 runs, average 20.33",
          (b.get("innings"), b.get("runs"), b.get("average")) == (3, 61, 20.33), str(b))
    check("the 99 against another club is not counted", b.get("high_score") == "40", str(b.get("high_score")))
    got = d.get("got_them_out") or []
    sm = row(got, "Tom Smith")
    check("Tom Smith has dismissed them twice (caught behind, bowled)",
          sm is not None and sm.get("count") == 2
          and {m["type"] for m in sm.get("methods") or []} == {"caught behind", "bowled"}, str(got))
    check("Tom Smith links to our player id, not the CA GUID",
          sm is not None and sm.get("player_id") == str(OUR["smith"][0]), str(sm))
    check("Pat White has dismissed them once", (row(got, "Pat White") or {}).get("count") == 1, str(got))
    jn = row(d.get("fielded_them"), "Ryan Jones")
    check("Ryan Jones has caught them twice", jn is not None and jn.get("catches") == 2, str(d.get("fielded_them")))
    vic = d.get("victims") or []
    br = row(vic, "Ben Brown")
    check("Barwood has dismissed Ben Brown twice (bowled, lbw)",
          br is not None and br.get("count") == 2
          and {m["type"] for m in br.get("methods") or []} == {"bowled", "lbw"}, str(vic))
    check("Sam Lee was not a bowling victim (caught off another bowler, run out)", row(vic, "Sam Lee") is None, str(vic))
    lee = row(d.get("their_fielding"), "Sam Lee")
    check("Barwood caught Sam Lee once and ran Lee out once",
          lee is not None and lee.get("catches") == 1 and lee.get("run_outs") == 1, str(d.get("their_fielding")))
    bw = d.get("bowling") or {}
    check("bowling against us: 2 wickets, best 1/14", (bw.get("wickets"), bw.get("best")) == (2, "1/14"), str(bw))
    lines = " ".join(d.get("lines") or [])
    check("the read names the bowler who has their number", "Tom Smith has dismissed them 2 times" in lines, lines)
    check("the read names the catcher", "Ryan Jones has caught them 2 times" in lines, lines)
    check("the read names our batter they have dismissed", "Ben Brown has fallen to them 2 times" in lines, lines)
    check("no gendered pronouns in the read",
          not any(w in f" {lines.lower()} " for w in (" he ", " him ", " his ", " she ", " her ")), lines)
    check("the manual game is explained", any("no Cricket Australia scorecard" in n for n in d.get("notes") or []),
          str(d.get("notes")))
    check("games are newest first", [x.get("date") for x in d.get("games") or []] == ["2026-10-31", "2026-03-07", "2026-01-17"],
          str([x.get("date") for x in d.get("games") or []]))

    print("\n-- control: the same reads CAN come back empty --")
    d2 = await vs_us(MATE, "Max Mate")
    check("the teammate's one bowling victim is Sam Lee (not Brown, who fell to Barwood)",
          [r.get("name") for r in d2.get("victims") or []] == ["Sam Lee"], str(d2.get("victims")))
    check("but Smith got the teammate out (games where Barwood sat out count for them)",
          (row(d2.get("got_them_out"), "Tom Smith") or {}).get("count") == 1, str(d2.get("got_them_out")))
    d3 = await vs_us(BARWOOD, "Adam Barwood", opponent=str(uuid.uuid4()))
    check("a club we have never played: ready, zero games, and it says nothing",
          d3.get("status") == "ready" and d3.get("games_total") == 0 and not d3.get("lines"),
          f"{d3.get('status')} {d3.get('games_total')} {d3.get('lines')}")

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
