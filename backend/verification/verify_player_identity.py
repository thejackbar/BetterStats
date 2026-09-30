"""Matching a hand-made player to their PlayCricket profile, against a real
Postgres, through the SHIPPED service and route bodies.

Reported off a club setting up Fantasy: five players who have come across from
other clubs were created by hand, and nobody could say whether their stats
would sync. They would not. A player created by hand has no ``grassroots_id``,
so their first game finds no row for their participant GUID and the sync mints a
SECOND player. The hand-made record, the one a squad or a Fantasy pick points
at, scores nothing all season.

What is asserted:
  * the search reads the identity it must: "Green, Spencer" searched as
    "Spencer Green", a second page fetched only when the first is full, results
    cached briefly so a keystroke is not an upstream call, and a person marked
    when they are already registered at this club or already in its roster (a
    legacy raw-GUID player included), never another club's;
  * an identity has one holder: a second attempt is a 409 naming the first, and
    no second player row is created;
  * every creation route that takes an identity stores it as ``grassroots_id``
    and leaves the player's own id alone, and a route given none behaves as it
    always did;
  * linking an existing player is idempotent, refuses a different profile,
    refuses an identity somebody else holds, and cannot reach another club's
    player;
  * the sync ties a first-seen participant to the one record-free hand-made
    player of that name, refuses when two fit, when the feed names two people the
    same, or when the player already holds any record, and mints exactly as it
    did before when given nothing to adopt;
  * a previous-club record is priced through the SAME baseline as the club's own
    players, inside the same window, and the club build is cached under its own
    key so it cannot collide with BetterIQ's ten-year one.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/var/run/postgresql \
  python verification/verify_player_identity.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import (
    Base, FantasyPoolPlayer, FantasySeason, Organisation, Player, PlayerSeasonStats, Season,
)

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []
MISSING: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


def load(what, fn):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 — a control run must survive this
        MISSING.append(f"{what}: {e}")
        return None


pi = load("services/player_identity.py", lambda: __import__("app.services.player_identity", fromlist=["x"]))
pi_router = load("routers/player_identity.py", lambda: __import__("app.routers.player_identity", fromlist=["x"]))
club_admin = load("routers/club_admin.py", lambda: __import__("app.routers.club_admin", fromlist=["x"]))
fantasy_router = load("routers/fantasy.py", lambda: __import__("app.routers.fantasy", fromlist=["x"]))
fe = load("services/fantasy_engine.py", lambda: __import__("app.services.fantasy_engine", fromlist=["x"]))
sync = load("services/sync.py", lambda: __import__("app.services.sync", fromlist=["x"]))
live = load("services/scout_live_search.py", lambda: __import__("app.services.scout_live_search", fromlist=["x"]))
iq_scout = load("services/iq_scout.py", lambda: __import__("app.services.iq_scout", fromlist=["x"]))

APP = Path(__file__).resolve().parent.parent / "app"

ORG = uuid.UUID("11111111-1111-4111-8111-111111111111")
OTHER = uuid.UUID("22222222-2222-4222-8222-222222222222")
PREV_CLUB = "33333333-3333-4333-8333-333333333333"

SPENCER = "9292cde6-36c5-40a4-b843-0c530951ede8"
TODD = "aaaaaaaa-0000-4000-8000-000000000001"
LEGACY = "bbbbbbbb-0000-4000-8000-000000000002"   # a legacy raw-GUID player
NEWBIE = "cccccccc-0000-4000-8000-000000000003"
FAT = "dddddddd-0000-4000-8000-000000000004"


class _User:
    id = uuid.uuid4()
    username = "verify"
    role = "club_admin"


USER = _User()


class Club:
    def __init__(self, oid):
        self.id = oid


CLUB = Club(ORG)
OTHER_CLUB = Club(OTHER)

# ── the upstream search, stubbed ────────────────────────────────────────────────
CALLS: list[tuple] = []
CANNED: dict[str, list[list[dict]]] = {}


async def fake_search(term, *, types=("PLAYCOMM_CLUB", "PLAYCOMM_PLAYER"), size=20, page=0):
    CALLS.append((term, page))
    pages = CANNED.get(term.lower(), [])
    return {"clubs": [], "players": pages[page] if page < len(pages) else []}


def person(pid, name, org_ids):
    return {"id": pid, "name": name, "organisations": [{"id": o, "name": f"Club {o[:4]}"} for o in org_ids]}


async def build_schema():
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)


async def seed():
    async with Session() as s:
        s.add(Organisation(id=ORG, name="Scarborough CC", slug="scarb"))
        s.add(Organisation(id=OTHER, name="Other CC", slug="other"))
        s.add(Player(id=uuid.UUID(LEGACY), name="Legacy, Larry", organisation_id=ORG, grassroots_id=LEGACY))
        s.add(Player(id=uuid.uuid4(), name="Gill, Todd", organisation_id=ORG, grassroots_id=TODD))
        # ANOTHER club's player holding Spencer's identity must never read as ours.
        s.add(Player(id=uuid.uuid4(), name="Green, Spencer", organisation_id=OTHER, grassroots_id=SPENCER))
        await s.commit()


async def raises(coro, code=None):
    try:
        await coro
    except HTTPException as e:
        d = e.detail
        return e.status_code, (d.get("code") if isinstance(d, dict) else None), d
    return None, None, None


async def count_players(org=ORG):
    async with Session() as s:
        return (await s.execute(select(func.count()).select_from(Player).where(Player.organisation_id == org))).scalar()


async def main():
    await build_schema()
    await seed()
    if pi is None or pi_router is None:
        print("\nFEATURE ABSENT: " + "; ".join(MISSING))
        check("the identity service and router exist", False, "; ".join(MISSING))
        return
    live.search_playcommunity = fake_search  # the service calls it through the module

    print("-- the id and the term")
    check("a blank id is no identity", pi.clean_participant_id("  ") is None and pi.clean_participant_id(None) is None)
    check("an id is lower-cased", pi.clean_participant_id(SPENCER.upper()) == SPENCER)
    st, _, _ = await raises(_wrap(pi.clean_participant_id, "not-a-guid"))
    check("junk is refused (400), never stored", st == 400)
    check("'Green, Spencer' is searched as 'Spencer Green'", pi.search_term("Green, Spencer") == "Spencer Green")
    check("a plain name is left alone", pi.search_term("  Spencer   Green ") == "Spencer Green")

    print("-- search")
    CANNED["spencer green"] = [[
        person("eeeeeeee-0000-4000-8000-000000000009", "Spencer Greene", ["44444444-0000-4000-8000-000000000001"]),
        person(TODD, "Todd Gill", [PREV_CLUB]),
        person(SPENCER, "Spencer Green", [PREV_CLUB, str(ORG)]),
        person(LEGACY, "Larry Legacy", [PREV_CLUB]),
    ]]
    CALLS.clear()
    r = await _search(CLUB, "Green, Spencer")
    cands = r["candidates"]
    by = {c["participant_id"]: c for c in cands}
    check("the comma name reached the upstream search as First Last", CALLS and CALLS[0][0] == "Spencer Green", str(CALLS))
    check("four people come back", len(cands) == 4)
    check("someone already registered at this club is marked and listed first",
          cands[0]["participant_id"] == SPENCER and cands[0]["at_this_club"] is True)
    check("another club's player row is NOT this club's existing player",
          by[SPENCER]["existing_player"] is None)
    check("a player this club already holds is marked, with who",
          by[TODD]["existing_player"] is not None and by[TODD]["existing_player"]["name"] == "Gill, Todd")
    check("a legacy raw-GUID player (id == the participant id) is found too",
          by[LEGACY]["existing_player"] is not None and by[LEGACY]["existing_player"]["name"] == "Legacy, Larry")
    check("held players sort ahead of strangers", [c["participant_id"] for c in cands[1:3]] == [TODD, LEGACY])
    check("each result carries the clubs to choose between", len(by[SPENCER]["clubs"]) == 2)
    CALLS.clear()
    await _search(CLUB, "spencer green")
    check("the same search a moment later is served from the cache", CALLS == [], str(CALLS))
    other = await _search(OTHER_CLUB, "spencer green")
    check("the other club sees its OWN player as existing",
          {c["participant_id"]: c for c in other["candidates"]}[SPENCER]["existing_player"] is not None)
    tiny = await _search(CLUB, "Sp")
    check("under three characters asks nobody", tiny["candidates"] == [])

    CANNED["michael simpson"] = [
        [person(f"00000000-0000-4000-8000-{i:012d}", f"Michael Simpson {i}", []) for i in range(20)],
        [person(f"00000000-0000-4000-8000-{i:012d}", f"Michael Simpson {i}", []) for i in range(20, 23)],
    ]
    CALLS.clear()
    big = await _search(CLUB, "Michael Simpson")
    check("a full first page fetches a second", [c[1] for c in CALLS] == [0, 1] and len(big["candidates"]) == 23)
    check("an unfilled second page is not reported as capped", big["capped"] is False)
    CANNED["ben harris"] = [
        [person(f"10000000-0000-4000-8000-{i:012d}", f"Ben Harris {i}", []) for i in range(20)],
        [person(f"10000000-0000-4000-8000-{i:012d}", f"Ben Harris {i}", []) for i in range(20, 40)],
    ]
    capped = await _search(CLUB, "Ben Harris")
    check("two full pages are reported as capped, so the screen can ask for a club", capped["capped"] is True)

    print("-- an identity has one holder")
    async with Session() as s:
        g = await pi.assert_identity_free(s, CLUB, SPENCER)
    check("a free identity is returned cleaned", g == SPENCER)
    async with Session() as s:
        st, code, d = await raises(pi.assert_identity_free(s, CLUB, TODD))
    check("a held identity is a 409 naming the holder", st == 409 and code == "identity_in_use" and d.get("name") == "Gill, Todd", str(d))
    async with Session() as s:
        todd_id = (await s.execute(select(Player.id).where(Player.grassroots_id == TODD, Player.organisation_id == ORG))).scalar()
        ok = await pi.assert_identity_free(s, CLUB, TODD, exclude_player_id=todd_id)
    check("the holder itself is not in its own way", ok == TODD)

    print("-- Add player takes an identity")
    before = await count_players()
    async with Session() as s:
        made = await club_admin.create_player(
            club_admin.PlayerCreate(first_name="Spencer", last_name="Green", participant_id=SPENCER), USER, CLUB, s)
    check("the identity is stored as grassroots_id", await _gid(made["id"]) == SPENCER)
    check("the route says it linked", made.get("identity_linked") is True)
    check("the player's own id is a fresh id, not the participant id", made["id"] != SPENCER)
    async with Session() as s:
        st, code, _ = await raises(club_admin.create_player(
            club_admin.PlayerCreate(first_name="Spencer", last_name="Green", participant_id=SPENCER), USER, CLUB, s))
    check("adding the same person twice is a 409", st == 409 and code == "identity_in_use")
    check("and no second row was minted", await count_players() == before + 1)
    async with Session() as s:
        plain = await club_admin.create_player(club_admin.PlayerCreate(first_name="Jo", last_name="Bloggs"), USER, CLUB, s)
    check("with no identity a player is created exactly as before", await _gid(plain["id"]) is None and plain.get("identity_linked") is False)
    async with Session() as s:
        legacy_field = await club_admin.create_player(
            club_admin.PlayerCreate(first_name="Pat", last_name="Legacy", playhq_id="abc-123"), USER, CLUB, s)
    check("the old Player ID box still writes playhq_id and does not link", await _gid(legacy_field["id"]) is None)
    async with Session() as s:
        st, _, _ = await raises(club_admin.create_player(
            club_admin.PlayerCreate(first_name="X", last_name="Y", participant_id="nope"), USER, CLUB, s))
    check("a junk participant id is refused", st == 400)

    print("-- Fantasy new player takes an identity")
    fs_id = uuid.uuid4()
    async with Session() as s:
        s.add(FantasySeason(id=fs_id, organisation_id=ORG, season_year=2026, name="Fantasy 2026", status="setup",
                            rules={"price_window_years": 3}))
        await s.commit()
    async with Session() as s:
        r = await fantasy_router.add_new_player(
            str(fs_id), fantasy_router.NewPlayer(name="Newbie Nine", role="batter", price=6.5, participant_id=NEWBIE),
            CLUB, s, None)
    check("the player is created linked and in the pool", r["identity_linked"] is True and await _gid(r["player_id"]) == NEWBIE)
    async with Session() as s:
        pool = (await s.execute(select(FantasyPoolPlayer).where(FantasyPoolPlayer.player_id == uuid.UUID(r["player_id"])))).scalar_one_or_none()
    check("the pool row holds the price the admin set", pool is not None and float(pool.current_price) == 6.5)
    n = await count_players()
    async with Session() as s:
        st, code, _ = await raises(fantasy_router.add_new_player(
            str(fs_id), fantasy_router.NewPlayer(name="Newbie Nine", participant_id=NEWBIE), CLUB, s, None))
    check("the same person cannot be created twice for Fantasy", st == 409 and await count_players() == n)
    async with Session() as s:
        r2 = await fantasy_router.add_new_player(str(fs_id), fantasy_router.NewPlayer(name="No Profile"), CLUB, s, None)
    check("a player who is not on PlayCricket yet is created unlinked, as before",
          r2["identity_linked"] is False and await _gid(r2["player_id"]) is None)

    print("-- linking a player who already exists")
    async with Session() as s:
        hm = Player(id=uuid.uuid4(), name="Fat, Fred", organisation_id=ORG)
        s.add(hm)
        await s.commit()
        hm_id = hm.id
    async with Session() as s:
        res = await pi_router.link(pi_router.LinkBody(player_id=str(hm_id), participant_id=FAT.upper()), CLUB, USER, s)
    check("link stores the identity", res["linked"] and res["changed"] and await _gid(str(hm_id)) == FAT)
    async with Session() as s:
        res = await pi_router.link(pi_router.LinkBody(player_id=str(hm_id), participant_id=FAT), CLUB, USER, s)
    check("linking twice is a no-op", res["changed"] is False)
    async with Session() as s:
        st, code, _ = await raises(pi_router.link(pi_router.LinkBody(player_id=str(hm_id), participant_id=SPENCER + ""), CLUB, USER, s))
    check("a player linked to one profile cannot be pointed at another",
          st == 409 and code in ("already_linked", "identity_in_use"))
    async with Session() as s:
        other = Player(id=uuid.uuid4(), name="Extra, Eddie", organisation_id=ORG)
        s.add(other); await s.commit(); oid = other.id
    async with Session() as s:
        st, code, _ = await raises(pi_router.link(pi_router.LinkBody(player_id=str(oid), participant_id=FAT), CLUB, USER, s))
    check("an identity another player holds is a duplicate to merge, not a link", st == 409 and code == "identity_in_use")
    async with Session() as s:
        st, _, _ = await raises(pi_router.link(pi_router.LinkBody(player_id=str(oid), participant_id=FAT), OTHER_CLUB, USER, s))
    check("another club's player cannot be linked from here", st == 404)
    async with Session() as s:
        st, _, _ = await raises(pi_router.link(pi_router.LinkBody(player_id="not-a-uuid", participant_id=FAT), CLUB, USER, s))
    check("a malformed player id is a 404", st == 404)
    async with Session() as s:
        st, _, _ = await raises(pi_router.link(pi_router.LinkBody(player_id=str(oid), participant_id="junk"), CLUB, USER, s))
    check("a malformed participant id is a 400", st == 400)

    print("-- the sync ties a first-seen participant to a hand-made player")
    if sync is None:
        check("the sync module loads", False, "; ".join(MISSING))
    else:
        await sync_section()

    print("-- pricing from a previous club")
    await pricing_section()

    print("-- wiring")
    src = (APP / "services" / "sync.py").read_text()
    check("the sync loads candidates once and passes them to the resolver",
          "load_unlinked_candidates" in src and "adopt_candidates=_adopt_here" in src)
    check("only a recent season may adopt", "year >= datetime.now(timezone.utc).year - 1" in src)
    check("the adoption update is guarded on the player still being unlinked", "Player.grassroots_id.is_(None)" in src)
    check("the candidate query names every table that could hold a record",
          all(t in (APP / "services" / "player_identity.py").read_text() for t in (
              "player_season_stats", "batting_innings", "bowling_spells", "game_appearances",
              "imported_stats", "manual_batting_innings", "manual_bowling_spells")))
    check("the router is mounted", "app.include_router(player_identity.router)" in (APP / "main.py").read_text())
    check("the search is rate limited per user", "rate_limit.enforce" in (APP / "routers" / "player_identity.py").read_text())


async def _wrap(fn, *a):
    return fn(*a)


async def _search(club, term):
    async with Session() as s:
        return await pi.search_candidates(s, club, term)


async def _gid(pid):
    async with Session() as s:
        return (await s.execute(select(Player.grassroots_id).where(Player.id == uuid.UUID(str(pid))))).scalar()


async def sync_section():
    from app.services.player_aliases import normalise_name_key as nk
    # A fresh club so earlier sections do not colour it.
    adopt_org = uuid.UUID("55555555-5555-4555-8555-555555555555")
    async with Session() as s:
        s.add(Organisation(id=adopt_org, name="Adopt CC", slug="adopt"))
        await s.commit()
        made = {}
        for label, name, kw in (
            ("plain", "Green, Spencer", {}),
            ("dupe1", "Twin, Sam", {}), ("dupe2", "Twin, Sam", {}),
            ("fathers", "Smith, Jack", {}),
            ("hasphq", "Phq, Pat", {"playhq_id": "x1"}),
            ("linked", "Linked, Lee", {"grassroots_id": "77777777-0000-4000-8000-000000000001"}),
            ("hasstats", "Stats, Stan", {}),
            ("override", "Someone, Else", {"display_name_override": "Nick Name"}),
        ):
            p = Player(id=uuid.uuid4(), name=name, organisation_id=adopt_org, **kw)
            s.add(p); made[label] = p.id
        s.add(Season(id=uuid.uuid4(), organisation_id=adopt_org, name="Summer 2026/27", year=2026))
        await s.commit()
        sid = (await s.execute(select(Season.id).where(Season.organisation_id == adopt_org))).scalar()
        s.add(PlayerSeasonStats(player_id=made["hasstats"], season_id=sid, matches=3))
        await s.commit()

    async with Session() as s:
        cands = await pi.load_unlinked_candidates(s, adopt_org)
    flat = {i for v in cands.values() for i in v}
    check("a record-free hand-made player is a candidate", made["plain"] in flat)
    check("a player with a PlayHQ id is not", made["hasphq"] not in flat)
    check("a player already linked is not", made["linked"] not in flat)
    check("a player holding season stats is not", made["hasstats"] not in flat)
    check("a display-name override is a second key", cands.get(nk("Nick Name")) == [made["override"]])
    check("'Green, Spencer' and 'Spencer Green' are one key", nk("Green, Spencer") == nk("Spencer Green") and nk("Spencer Green") in cands)

    G1, G2, G3, G4 = (f"66666666-0000-4000-8000-00000000000{i}" for i in range(1, 5))
    omap: dict = {}
    adopted: list = []
    counts = {nk("Green, Spencer"): 1}
    async with Session() as s:
        got = await sync._resolve_org_player(s, adopt_org, omap, G1, "Green, Spencer", {},
                                             adopt_candidates=cands, feed_name_counts=counts, adopted=adopted)
        await s.commit()
    check("the participant resolves to the EXISTING hand-made player", got == made["plain"], str(got))
    check("the map now points the participant at it", omap.get(G1) == made["plain"])
    check("the identity was stored on it", await _gid(made["plain"]) == G1)
    check("the adoption is reported", adopted == [(str(made["plain"]), "Green, Spencer")])
    check("no second player was minted", await count_players(adopt_org) == 8, str(await count_players(adopt_org)))
    check("it cannot be adopted a second time", made["plain"] not in {i for v in cands.values() for i in v})
    async with Session() as s:
        rows = (await s.execute(select(Player.id, Player.grassroots_id).where(Player.organisation_id == adopt_org))).all()
    pid_by_guid = {g: pid for pid, g in rows if g}
    check("the game-level map (grassroots_id -> id) attaches scorecard rows to the hand-made player",
          pid_by_guid.get(G1) == made["plain"])

    async with Session() as s:
        got = await sync._resolve_org_player(s, adopt_org, {}, G2, "Twin, Sam", {},
                                             adopt_candidates=cands, feed_name_counts={nk("Twin, Sam"): 1}, adopted=[])
        await s.commit()
    check("two hand-made players of one name: refused, a new player is minted", got not in (made["dupe1"], made["dupe2"]))
    async with Session() as s:
        got = await sync._resolve_org_player(s, adopt_org, {}, G3, "Smith, Jack", {},
                                             adopt_candidates=cands, feed_name_counts={nk("Smith, Jack"): 2}, adopted=[])
        await s.commit()
    check("the feed naming two people alike: refused (a father and son)", got != made["fathers"])
    async with Session() as s:
        got = await sync._resolve_org_player(s, adopt_org, {}, G4, "Stats, Stan", {},
                                             adopt_candidates=cands, feed_name_counts={nk("Stats, Stan"): 1}, adopted=[])
        await s.commit()
    check("a player who already holds a record is never adopted", got != made["hasstats"])
    async with Session() as s:
        legacy = await sync._resolve_org_player(s, adopt_org, {}, "88888888-0000-4000-8000-000000000001", "Brand, New", {})
        await s.commit()
    check("called the old way (no candidates) it mints exactly as before", str(legacy) == "88888888-0000-4000-8000-000000000001")
    async with Session() as s:
        again = await sync._resolve_org_player(s, adopt_org, {}, "88888888-0000-4000-8000-000000000002", "Twin, Sam", {},
                                               adopt_candidates=None, feed_name_counts=None)
        await s.commit()
    check("with adoption switched off a same-name participant is minted, not adopted", again not in (made["dupe1"], made["dupe2"]))

    # An already-known participant is returned from the map, never re-adopted.
    omap2 = {G1: made["plain"]}
    async with Session() as s:
        same = await sync._resolve_org_player(s, adopt_org, omap2, G1, "Green, Spencer", {},
                                              adopt_candidates=cands, feed_name_counts=counts, adopted=[])
    check("a participant the club already knows resolves from the map", same == made["plain"])


def _fs(year=2026, window=3):
    class F:
        season_year = year
        rules = {"price_window_years": window}
    return F()


async def pricing_section():
    if fe is None or not hasattr(fe, "suggest_from_career"):
        check("the pricing helper exists", False, "; ".join(MISSING))
        return
    fs = _fs()

    def season(year, **k):
        base = dict(year=year, matches=0, innings=0, runs=0, fifties=0, hundreds=0, wickets=0,
                    maidens=0, five_fors=0, catches=0, catches_wk=0, stumpings=0, run_outs=0, bowling_balls=0)
        base.update(k)
        return base

    bat = {"seasons": [season(2026, matches=14, innings=14, runs=620, fifties=4, hundreds=1, catches=6),
                       season(2025, matches=16, innings=15, runs=540, fifties=3, catches=5)]}
    r = fe.suggest_from_career(bat, fs)
    check("a run-scorer is priced as a batter", r and r["role"] == "batter", str(r))
    row = {"r_matches": 30, "r_runs": 1160, "r_fours": 0, "r_sixes": 0, "r_fifties": 7, "r_hundreds": 1,
           "r_wickets": 0, "r_maidens": 0, "r_fivefor": 0, "r_catches": 11, "r_catches_wk": 0, "r_stumpings": 0, "r_run_outs": 0}
    check("the price is the club's own baseline for the same record", r and r["price"] == fe._baseline_price(row, "batter"), str(r))
    check("the basis names what it was priced on", r["basis"]["matches"] == 30 and r["basis"]["runs"] == 1160 and r["basis"]["years"] == [2026, 2025])

    bowl = {"seasons": [season(2026, matches=15, innings=3, runs=40, wickets=28, maidens=9, bowling_balls=560),
                        season(2025, matches=14, innings=2, runs=30, wickets=22, bowling_balls=480)]}
    rb = fe.suggest_from_career(bowl, fs)
    check("a wicket-taker is priced as a bowler", rb and rb["role"] == "bowler", str(rb))
    keeper = {"seasons": [season(2026, matches=12, innings=12, runs=250, catches=14, catches_wk=11, stumpings=3)]}
    check("a keeper is recognised", fe.suggest_from_career(keeper, fs)["role"] == "keeper")
    star = {"seasons": [season(2026, matches=14, innings=14, runs=1100, fifties=8, hundreds=4)]}
    check("a better record prices higher", fe.suggest_from_career(star, fs)["price"] > r["price"])
    check("nothing inside the window means no suggestion, never a made-up price",
          fe.suggest_from_career({"seasons": [season(2019, matches=20, runs=900)]}, fs) is None)
    check("no record at all means no suggestion", fe.suggest_from_career(None, fs) is None and fe.suggest_from_career({"seasons": []}, fs) is None)
    narrow = fe.suggest_from_career(bat, _fs(window=1))
    check("the club's own pricing window is honoured", narrow["basis"]["years"] == [2026] and narrow["basis"]["matches"] == 14)

    if iq_scout is None:
        check("the scout stack loads for prior_record", False, "; ".join(MISSING))
        return
    seen = {}

    async def stub_get(session, our_org_id, key, version, build, *, name=None, force=False):
        seen["key"] = key
        seen["build"] = build
        return seen["result"]

    async def stub_build(org_guid, club_name=None, years=10):
        seen["years"] = years
        return {}

    orig_get, orig_build = iq_scout._get_or_start, iq_scout._build_career
    iq_scout._get_or_start, iq_scout._build_career = stub_get, stub_build
    try:
        seen["result"] = {"status": "building"}
        r = await fe.prior_record(None, fs, str(ORG), PREV_CLUB, "Prev CC", SPENCER)
        check("a club still being read answers 'building'", r == {"status": "building"}, str(r))
        check("the cache key carries the pricing window, so it cannot collide with BetterIQ's ten-year build",
              seen["key"] == f"career3y::{PREV_CLUB}" and seen["key"] != iq_scout._career_key(PREV_CLUB), seen["key"])
        await seen["build"]()
        check("the build reads only the pricing window, not a decade", seen["years"] == 3, str(seen.get("years")))
        seen["result"] = {"status": "ready", "players": [{"player_id": SPENCER.upper(), **bat}]}
        r = await fe.prior_record(None, fs, str(ORG), PREV_CLUB, "Prev CC", SPENCER)
        check("a ready club with the person prices them (ids compared case-insensitively)",
              r["status"] == "ready" and r["found"] and r["suggestion"]["role"] == "batter", str(r))
        seen["result"] = {"status": "ready", "players": [{"player_id": TODD, **bat}]}
        r = await fe.prior_record(None, fs, str(ORG), PREV_CLUB, "Prev CC", SPENCER)
        check("a ready club without them says so rather than inventing a record",
              r["status"] == "ready" and r["found"] is False and r["suggestion"] is None, str(r))
        r = await fe.prior_record(None, fs, str(ORG), "not-a-guid", None, SPENCER)
        check("a club with no Cricket Australia id is unavailable", r["status"] == "unavailable")
        wide = await fe.prior_record(None, _fs(window=9), str(ORG), PREV_CLUB, None, SPENCER)
        check("a very wide window is capped at five years for the build", seen["key"] == f"career5y::{PREV_CLUB}")
    finally:
        iq_scout._get_or_start, iq_scout._build_career = orig_get, orig_build


if __name__ == "__main__":
    asyncio.run(main())
    print(f"\n{PASS} passed, {FAIL} failed")
    if MISSING:
        print("REPORTED MISSING: " + "; ".join(MISSING))
    for f in FAILURES:
        print("  - " + f)
    sys.exit(1 if FAIL else 0)
