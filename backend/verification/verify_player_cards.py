"""Player Cards, against a real Postgres, through the shipped services and route bodies.

What is asserted:

* a club WITHOUT BetterSelect has a player page: the landing, the PIN, `/me` and the profile all
  answer, with no availability section; a club WITH it still needs its self-service switch;
* the card pool: hidden (`is_public` false), club-hidden, junior-only (until the club switches
  juniors on) and no-match players are out, and every "out" check is paired with the same player
  being in once the switch is flipped;
* the six card figures, and a rarity rating from 1 to 99 that orders strong players above weak;
* packs: starter, weekly (a week ends Monday 00:00 club time and an old weekly pack expires),
  milestone (one per 25 runs, 2 wickets, 2 dismissals in the CURRENT season only) and duck (only
  ducks after launch); grants are add-only and idempotent, and a figure corrected downwards takes
  no pack away;
* opening: five cards, one Rare or better, no repeat in a pack, recorded copies, a pack cannot be
  opened twice or by somebody else, and the odds are the odds (over many draws);
* special cards: a century, a half century, a five-for, a debut, a games milestone, a hat-trick and
  a club award each make exactly one card, a re-run makes none, the player is gifted a copy, and
  duplicates stack as a count;
* the collection always holds the player's own card, and a card of a player who later leaves the
  pool is not shown;
* a player merge moves the packs and cards and deletes none (apart from the same pack twice).

Run on its own database:
  DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/verify_cards python verification/verify_player_cards.py

CONTROL: run the same file against the commit before the change. The cards modules are read through
find_spec, so the control reports the missing behaviour as failed checks instead of crashing.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from jose import jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from _view_ddl import view_statements
from app.config.settings import settings as app_settings
from app.models.db import Base, Organisation, Player, User
from app.routers import public_availability as pa
from app.services.superseded_ddl import STATEMENTS as SUPERSEDED_DDL
from app.services import player_dashboard
from app.services.junior_hiding_ddl import STATEMENTS as JUNIOR_DDL

HAVE = importlib.util.find_spec("app.services.player_cards") is not None
if HAVE:
    from app.services import player_cards as cards, merge_carry
    from app.services.player_cards_ddl import STATEMENTS as CARD_DDL
    from app.routers import public_player_cards as pc_routes, player_cards_admin as admin_routes
else:  # the control run
    cards = merge_carry = pc_routes = admin_routes = None
    CARD_DDL = []
HAVE_SWAPS = importlib.util.find_spec("app.services.player_card_swaps") is not None
if HAVE_SWAPS:
    from app.services import player_card_swaps as swaps
    from app.services.player_card_swaps_ddl import STATEMENTS as SWAP_DDL
else:
    swaps = None
    SWAP_DDL = []

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


YEAR = date.today().year
ORG, ORG_SELECT = uuid.uuid4(), uuid.uuid4()
TOKEN, TOKEN_SELECT = "tok-" + uuid.uuid4().hex, "tok-" + uuid.uuid4().hex
S_NOW, S_OLD = uuid.uuid4(), uuid.uuid4()
GR_SENIOR, GR_JUNIOR, GR_OLD = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
COMP_JUNIOR = uuid.uuid4()
(ALPHA, BRAVO, CHARLIE, DELTA, ECHO, FOXTROT, GOLF, HOTEL, INDIA) = (uuid.uuid4() for _ in range(9))
SEL_PLAYER = uuid.uuid4()
NAMES = {ALPHA: "Alpha, A", BRAVO: "Bravo, B", CHARLIE: "Charlie, C", DELTA: "Delta, D", ECHO: "Echo, E",
         FOXTROT: "Foxtrot, F", GOLF: "Golf, G", HOTEL: "Hotel, H", INDIA: "India, I"}


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
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
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS amalgamate_seasons BOOLEAN NOT NULL DEFAULT false"))
        # Copied from main.py's lifespan: the achievements table and the audit trail.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_achievements (
                id SERIAL PRIMARY KEY, org_id UUID NOT NULL, player_id UUID, player_name TEXT NOT NULL,
                season TEXT, category TEXT NOT NULL, subcategory TEXT, achievement TEXT NOT NULL,
                detail TEXT, created_at TIMESTAMPTZ DEFAULT NOW())"""))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY, org_id UUID, user_id UUID, action TEXT, target_type TEXT,
                target_id TEXT, details JSONB, created_at TIMESTAMPTZ DEFAULT NOW())"""))
        for stmt in JUNIOR_DDL:
            await conn.execute(text(stmt))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))
        for stmt in SUPERSEDED_DDL:
            await conn.execute(text(stmt))
        for stmt in CARD_DDL + SWAP_DDL:
            await conn.execute(text(stmt))


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        await ex("INSERT INTO organisations (id, name, slug, is_active, availability_link_token, "
                 "availability_self_service_enabled, availability_require_pin, module_overrides) "
                 "VALUES (:i, 'Cards CC', 'cards-cc', true, :t, false, false, CAST('[]' AS JSONB))", i=ORG, t=TOKEN)
        await ex("INSERT INTO organisations (id, name, slug, is_active, availability_link_token, "
                 "availability_self_service_enabled, availability_require_pin, module_overrides) "
                 "VALUES (:i, 'Select CC', 'select-cc', true, :t, false, false, CAST('[\"select\"]' AS JSONB))",
                 i=ORG_SELECT, t=TOKEN_SELECT)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES "
                 "(:a, :o, :na, :ya), (:b, :o, 'Summer 2015/16', 2015)",
                 a=S_NOW, b=S_OLD, o=ORG, na=f"Summer {YEAR}/{str(YEAR + 1)[2:]}", ya=YEAR)
        await ex("INSERT INTO club_competitions (id, organisation_id, name, is_junior) VALUES (:c, :o, 'Juniors', true)",
                 c=COMP_JUNIOR, o=ORG)
        for gid, sid, name, cats, comp in (
            (GR_SENIOR, S_NOW, "A Grade", ["senior"], None),
            (GR_JUNIOR, S_NOW, "Under 13s", ["junior"], COMP_JUNIOR),
            (GR_OLD, S_OLD, "A Grade", ["senior"], None),
        ):
            await ex("INSERT INTO grades (id, season_id, name, category, categories, competition_id) "
                     "VALUES (:i, :s, :n, :c, :cs, :comp)", i=gid, s=sid, n=name, c=cats[0], cs=cats, comp=comp)
        for pid, name in NAMES.items():
            await ex("INSERT INTO players (id, organisation_id, name, is_player, status, is_public) "
                     "VALUES (:i, :o, :n, true, 'active', :pub)", i=pid, o=ORG, n=name, pub=(pid != GOLF))
        await ex("INSERT INTO players (id, organisation_id, name, is_player, status) VALUES (:i, :o, 'Sel, S', true, 'active')",
                 i=SEL_PLAYER, o=ORG_SELECT)

        async def pss(pid, sid, **kw):
            cols = {"matches": 0, "runs": 0, "wickets": 0, "catches": 0, "batting_innings": 0, "not_outs": 0,
                    "runs_conceded": 0, "run_outs": 0, "stumpings": 0}
            cols.update(kw)
            await ex(f"INSERT INTO player_season_stats (player_id, season_id, {', '.join(cols)}) "
                     f"VALUES (:p, :s, {', '.join(':' + k for k in cols)})", p=pid, s=sid, **cols)

        # Career = old season + current season. The CURRENT season is what milestone packs count.
        await pss(ALPHA, S_OLD, matches=100, runs=2870, batting_innings=90, not_outs=8)
        await pss(ALPHA, S_NOW, matches=20, runs=130, batting_innings=10, not_outs=2)      # 5 runs packs
        await pss(BRAVO, S_OLD, matches=140, wickets=243, runs_conceded=5000)
        await pss(BRAVO, S_NOW, matches=10, wickets=7, runs_conceded=200)                  # 3 wickets packs
        await pss(CHARLIE, S_OLD, matches=90, catches=140, stumpings=38)
        await pss(CHARLIE, S_NOW, matches=10, catches=5, stumpings=2)                      # 7 dismissals, 3 packs
        await pss(DELTA, S_NOW, matches=5, runs=40, batting_innings=5)
        await pss(ECHO, S_NOW, matches=8, runs=100, batting_innings=8)
        await pss(GOLF, S_NOW, matches=30, runs=900, batting_innings=30)
        await pss(HOTEL, S_NOW, matches=12, runs=300, batting_innings=12)
        await pss(INDIA, S_OLD, matches=15, runs=200, batting_innings=15)                  # played only in an old season

        games = {}

        async def game(key, gid, days_ago):
            g = uuid.uuid4()
            games[key] = g
            await ex("INSERT INTO games (id, grade_id, played_at, home_team, away_team, status) "
                     "VALUES (:i, :g, :d, 'Us', 'Them', 'COMPLETED')", i=g, g=gid, d=date.today() - timedelta(days=days_ago))

        await game("senior_recent", GR_SENIOR, 5)
        await game("senior_old", GR_SENIOR, 60)
        await game("junior", GR_JUNIOR, 20)
        await game("pre_launch", GR_SENIOR, 90)

        async def bat(pid, key, runs, not_out=False, inn=1):
            await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, not_out, did_not_bat) "
                     "VALUES (:g, :p, :n, :r, :no, false)", g=games[key], p=pid, n=inn, r=runs, no=not_out)
            await ex("INSERT INTO game_appearances (game_id, player_id, team_name) VALUES (:g, :p, 'Us') ON CONFLICT DO NOTHING",
                     g=games[key], p=pid)

        await bat(ALPHA, "senior_old", 112, not_out=True)      # a century
        await bat(ALPHA, "senior_recent", 0)                   # a duck AFTER launch
        await bat(ALPHA, "pre_launch", 0)                      # a duck BEFORE launch
        await bat(DELTA, "senior_old", 52)                     # a half century
        await bat(ECHO, "junior", 30)
        await ex("INSERT INTO bowling_spells (game_id, player_id, innings_number, overs, maidens, runs, wickets) "
                 "VALUES (:g, :p, 1, 10, 2, 30, 5)", g=games["senior_old"], p=BRAVO)
        await ex("INSERT INTO game_appearances (game_id, player_id, team_name) VALUES (:g, :p, 'Us') ON CONFLICT DO NOTHING",
                 g=games["senior_old"], p=BRAVO)
        await ex("INSERT INTO player_achievements (org_id, player_id, player_name, season, category, subcategory, achievement) "
                 "VALUES (:o, :p, 'Charlie, C', '2025', 'Statistics', 'Hat Tricks', 'Hat trick v Rovers')", o=ORG, p=CHARLIE)
        await ex("INSERT INTO player_achievements (org_id, player_id, player_name, season, category, subcategory, achievement) "
                 "VALUES (:o, :p, 'Bravo, B', '2025', 'Club Award', '1st XI', 'Best & Fairest')", o=ORG, p=BRAVO)
        # Cards launched a month ago: a duck before then earns no pack.
        if HAVE:
            await ex("INSERT INTO club_card_settings (organisation_id, launched_at, weekly_packs) "
                     "VALUES (:o, NOW() - INTERVAL '30 days', 1)", o=ORG)
        await s.commit()


def request_for(player_id, club_id) -> Request:
    token = jwt.encode({"club": str(club_id), "pid": str(player_id), "typ": "avail",
                        "exp": datetime.now(timezone.utc) + timedelta(days=1)},
                       app_settings.secret_key, algorithm=app_settings.algorithm)
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [(b"cookie", f"bs_avail={token}".encode())],
                    "client": ("127.0.0.1", 1), "query_string": b""})


def main_src_swaps() -> str:
    return (Path(__file__).resolve().parent.parent / "app" / "main.py").read_text()


async def status_of(coro):
    try:
        await coro
        return 200
    except HTTPException as exc:
        return exc.status_code


async def main() -> None:
    await build_schema()
    await seed()

    # ── A club without BetterSelect has a player page ────────────────────────
    print("\nplayer page without BetterSelect")
    async with Session() as db:
        landing = None
        try:
            landing = await pa.get_landing(TOKEN, db)
        except HTTPException as exc:
            landing = {"status": exc.status_code}
        check("a club without BetterSelect: the landing answers", "players" in landing, str(landing)[:80])
        check("...and lists the club's players for the name step", len(landing.get("players", [])) >= 5)
        select_status = await status_of(pa.get_landing(TOKEN_SELECT, db))
        check("a BetterSelect club with self-service OFF still 404s (its own switch is kept)", select_status == 404)
        me = None
        try:
            me = await pa.get_me(TOKEN, request_for(ALPHA, ORG), None, db)
        except HTTPException as exc:
            me = {"status": exc.status_code}
        check("/me works with no BetterSelect and says there is no availability",
              me.get("has_availability") is False and me.get("dates") == [], str(me)[:100])
        check("set_me (the availability answer) stays refused without BetterSelect",
              await status_of(pa.set_me(TOKEN, pa.SetBody(date=date.today(), status="AVAILABLE"), request_for(ALPHA, ORG), db)) == 404)

    async with Session() as db:
        club = await db.get(Organisation, ORG)
        club.player_dashboard_modules = player_dashboard.store(["cards"])
        await db.commit()
        default_no_select = player_dashboard.enabled_modules(Organisation(id=uuid.uuid4(), name="x", slug="x", module_overrides=[]))
        default_select = player_dashboard.enabled_modules(Organisation(id=uuid.uuid4(), name="x", slug="x", module_overrides=["select"]))
        check("a club without BetterSelect opens on cards, not squads", default_no_select[:1] == ["cards"] and "squad" not in default_no_select,
              str(default_no_select))
        check("a BetterSelect club keeps its modules and gains cards", "squad" in default_select and "cards" in default_select)
        check("squad modules are blocked for a club without BetterSelect",
              player_dashboard.blocked_reason(club, "squad") is not None and player_dashboard.blocked_reason(club, "cards") is None)

    if not HAVE:
        print("\n(control run: the cards modules do not exist on this commit)")
        for label in ("card pool", "figures and rarity", "pack grants", "weekly reset", "opening", "odds",
                      "special cards", "collection", "merge", "admin", "routes"):
            check(f"{label}: Player Cards exist", False, "app.services.player_cards missing")
        return

    # ── The pool ─────────────────────────────────────────────────────────────
    print("\nthe card pool")
    async with Session() as db:
        club = await db.get(Organisation, ORG)
        await cards.set_hidden(db, ORG, HOTEL, True, "test")
        await db.commit()
        cards.forget(ORG)
        snap = await cards.club_snapshot(db, club, fresh=True)
        people = set(snap["people"])
        check("players with matches and no flag are in", {str(ALPHA), str(BRAVO), str(CHARLIE), str(DELTA)} <= people)
        check("a hidden player (is_public false) is out", str(GOLF) not in people)
        check("a player the club hid from cards is out", str(HOTEL) not in people)
        check("a junior-only player is out by default", str(ECHO) not in people)
        check("a player with no match is in (own card) but not in the draw pool",
              str(FOXTROT) in people and all(str(FOXTROT) not in v for v in snap["pool"].values()))
        await cards.save_settings(db, ORG, {"include_juniors": True})
        await db.commit()
        snap2 = await cards.club_snapshot(db, club, fresh=True)
        check("switching juniors on brings the junior in (the same player, so the exclusion was real)", str(ECHO) in snap2["people"])
        await cards.set_hidden(db, ORG, HOTEL, False, "test")
        cards.forget(ORG)
        snap3 = await cards.club_snapshot(db, club, fresh=True)
        check("un-hiding a player puts them back", str(HOTEL) in snap3["people"])
        await cards.save_settings(db, ORG, {"include_juniors": False})
        await cards.set_hidden(db, ORG, HOTEL, True, "test")
        await db.commit()
        cards.forget(ORG)

    # ── Figures and rarity ───────────────────────────────────────────────────
    print("\nfigures and rarity")
    async with Session() as db:
        club = await db.get(Organisation, ORG)
        snap = await cards.club_snapshot(db, club, fresh=True)
        a = cards.regular_card(snap, str(ALPHA))
        check("matches are the career total across seasons", a["matches"] == 120, str(a["matches"]))
        check("runs are the career total", a["runs"] == 3000)
        check("batting average is runs over innings less not-outs", abs(a["bat_avg"] - round(3000 / (100 - 10), 2)) < 0.01, str(a["bat_avg"]))
        b = cards.regular_card(snap, str(BRAVO))
        check("bowling average is runs conceded over wickets", abs(b["bowl_avg"] - round(5200 / 250, 2)) < 0.01, str(b["bowl_avg"]))
        c = cards.regular_card(snap, str(CHARLIE))
        check("dismissals are catches, run outs and stumpings together", c["dismissals"] == 145 + 40 - 0 or c["dismissals"] == 185, str(c["dismissals"]))
        d = cards.regular_card(snap, str(DELTA))
        check("no bowling at all reads None, not 0", d["bowl_avg"] is None and d["wickets"] == 0)
        check("rarity is 1 to 99 for everyone",
              all(1 <= r["score"] <= 99 for r in snap["rating"].values()), str(snap["rating"]))
        check("a strong player outranks a weak one", a["rarity"] > d["rarity"] and b["rarity"] > d["rarity"], f'{a["rarity"]} {b["rarity"]} {d["rarity"]}')
        check("a player with no matches is 1, Common", snap["rating"][str(FOXTROT)] == {"score": 1, "tier": "common"})
        check("tier follows the score", cards.tier_for(90) == "legendary" and cards.tier_for(75) == "epic"
              and cards.tier_for(55) == "rare" and cards.tier_for(54) == "common")
        check("the pool lists a player under their own tier", str(ALPHA) in snap["pool"][a["tier"]])

    # ── Week boundaries ──────────────────────────────────────────────────────
    print("\nthe weekly reset")
    st = cards.default_settings()
    sunday_late = datetime(2026, 10, 25, 15, 59, tzinfo=timezone.utc)    # Sun 23:59 in Perth
    monday_start = datetime(2026, 10, 25, 16, 0, tzinfo=timezone.utc)    # Mon 00:00 in Perth
    check("Sunday 23:59 club time is still the old week", cards.week_key(st, sunday_late) == "2026-W43", cards.week_key(st, sunday_late))
    check("Monday 00:00 club time is a new week", cards.week_key(st, monday_start) == "2026-W44", cards.week_key(st, monday_start))
    st_syd = {**st, "timezone": "Australia/Sydney"}
    check("the reset follows the club's own timezone", cards.week_key(st_syd, datetime(2026, 10, 25, 13, 0, tzinfo=timezone.utc)) == "2026-W44")

    # ── Grants ───────────────────────────────────────────────────────────────
    print("\npack grants")
    async with Session() as db:
        club = await db.get(Organisation, ORG)
        snap = await cards.club_snapshot(db, club, fresh=True)
        check("the club's current season is the one of its newest game", snap["current_season_ids"] == [str(S_NOW)], str(snap["current_season_ids"]))

        async def packs_of(pid):
            rows = await db.execute(text("SELECT source, count(*) FROM player_card_packs WHERE player_id = :p GROUP BY source"), {"p": pid})
            return {r[0]: r[1] for r in rows.fetchall()}

        await cards.ensure_grants(db, club, str(ALPHA), snap)
        await db.commit()
        got = await packs_of(ALPHA)
        check("two starter packs", got.get("starter") == 2, str(got))
        check("one weekly pack", got.get("weekly") == 1, str(got))
        check("one runs pack per 25 runs THIS season (130 runs = 5, not the career 3000)", got.get("runs") == 5, str(got))
        check("ducks count only after launch (two in history, one after)", got.get("duck") == 1, str(got))
        before = await packs_of(ALPHA)
        added = await cards.ensure_grants(db, club, str(ALPHA), snap)
        await db.commit()
        check("a second look grants nothing", await packs_of(ALPHA) == before and sum(added.values()) == 0, str(added))

        await db.execute(text("UPDATE player_season_stats SET runs = 20 WHERE player_id = :p AND season_id = :s"), {"p": ALPHA, "s": S_NOW})
        await db.commit()
        await cards.ensure_grants(db, club, str(ALPHA), snap)
        await db.commit()
        check("a figure corrected downwards takes no pack away", (await packs_of(ALPHA)).get("runs") == 5)
        await db.execute(text("UPDATE player_season_stats SET runs = 130 WHERE player_id = :p AND season_id = :s"), {"p": ALPHA, "s": S_NOW})
        await db.commit()

        await cards.ensure_grants(db, club, str(BRAVO), snap)
        await cards.ensure_grants(db, club, str(CHARLIE), snap)
        await db.commit()
        check("one wickets pack per 2 wickets (7 = 3)", (await packs_of(BRAVO)).get("wickets") == 3, str(await packs_of(BRAVO)))
        check("one dismissals pack per 2 (5 catches + 2 stumpings = 3)", (await packs_of(CHARLIE)).get("dismissals") == 3, str(await packs_of(CHARLIE)))
        check("a batter with no wickets earns no wickets pack", (await packs_of(ALPHA)).get("wickets") is None)

        await db.execute(text("INSERT INTO player_card_packs (organisation_id, player_id, source, ref_key) VALUES (:o, :p, 'weekly', '2001-W01:1')"),
                         {"o": ORG, "p": ALPHA})
        await db.commit()
        avail = await cards.available_packs(db, str(ALPHA), snap)
        check("last week's weekly pack has expired", not any(p["source"] == "weekly" for p in avail) is False and
              sum(1 for p in avail if p["source"] == "weekly") == 1, str(Counter(p["source"] for p in avail)))
        check("every other pack banks (starter, runs, duck all still there)",
              Counter(p["source"] for p in avail)["starter"] == 2 and Counter(p["source"] for p in avail)["runs"] == 5)

        # a club-wide weekly count is applied
        await cards.save_settings(db, ORG, {"weekly_packs": 3})
        await db.commit()
        cards.forget(ORG)
        snap_w = await cards.club_snapshot(db, club, fresh=True)
        await cards.ensure_grants(db, club, str(DELTA), snap_w)
        await db.commit()
        check("the club's weekly count is honoured", (await packs_of(DELTA)).get("weekly") == 3, str(await packs_of(DELTA)))
        await cards.save_settings(db, ORG, {"weekly_packs": 1})
        await db.commit()
        cards.forget(ORG)

    # ── Odds (pure) ──────────────────────────────────────────────────────────
    print("\nthe odds")
    pool = {"common": [f"c{i}" for i in range(40)], "rare": [f"r{i}" for i in range(15)],
            "epic": [f"e{i}" for i in range(6)], "legendary": ["l0", "l1", "l2"]}
    tiers = Counter()
    n_packs, specials_seen, dup_packs, no_rare = 4000, 0, 0, 0
    specials = [f"sp{i}" for i in range(20)]
    for _ in range(n_packs):
        picks = cards.draw_cards(pool, specials)
        for p in picks:
            tiers[p["tier"]] += 1
        if len(picks) != cards.PACK_SIZE:
            dup_packs += 1
        if len({(p["kind"], p["id"]) for p in picks}) != len(picks):
            dup_packs += 1
        if all(p["tier"] == "common" for p in picks):
            no_rare += 1
    total = sum(tiers.values())
    share = {k: v / total for k, v in tiers.items()}
    check("every pack holds five cards", dup_packs == 0)
    check("every pack has at least one Rare or better", no_rare == 0, str(no_rare))
    check("special cards turn up around 5% of the time", 0.03 < share["special"] < 0.09, str(share))
    check("Common is the bulk (about 60% of regular draws, a little less after the guarantee)", 0.45 < share["common"] < 0.65, str(share))
    check("Legendary is rare but possible", 0.004 < share["legendary"] < 0.05, str(share))
    thin = {"common": ["c0", "c1", "c2", "c3", "c4", "c5"], "rare": ["r0"], "epic": [], "legendary": []}
    check("the guarantee still holds when only one Rare exists", all(
        any(p["tier"] != "common" for p in cards.draw_cards(thin, [])) for _ in range(300)))
    tiny = cards.draw_cards({"common": ["only"], "rare": [], "epic": [], "legendary": []}, [])
    check("a club too small to fill a pack still gets what it can, without repeats", 1 <= len(tiny) <= cards.PACK_SIZE and len({p['id'] for p in tiny}) == len(tiny))
    check("an empty club draws nothing and does not crash", cards.draw_cards({t: [] for t in cards.TIERS}, []) == [])

    # ── Opening ──────────────────────────────────────────────────────────────
    print("\nopening a pack")
    async with Session() as db:
        club, alpha = await db.get(Organisation, ORG), await db.get(Player, ALPHA)
        bravo = await db.get(Player, BRAVO)
        snap = await cards.club_snapshot(db, club, fresh=True)
        avail = await cards.available_packs(db, str(ALPHA), snap)
        pack = avail[0]["id"]
        got = await cards.open_pack(db, club, alpha, pack, snap)
        await db.commit()
        check("opening yields cards", got is not None and 1 <= len(got) <= cards.PACK_SIZE, str(got and len(got)))
        n_copies = (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE owner_player_id = :p AND source = 'pack'"), {"p": ALPHA})).scalar()
        check("each card is recorded as a copy the player owns", n_copies == len(got), f"{n_copies} vs {len(got)}")
        again = await cards.open_pack(db, club, alpha, pack, snap)
        await db.commit()
        check("a pack cannot be opened twice", again is None)
        check("nor by somebody else", await cards.open_pack(db, club, bravo, avail[1]["id"], snap) is None)
        await db.commit()
        check("the pack is marked open and leaves the list",
              pack not in [p["id"] for p in await cards.available_packs(db, str(ALPHA), snap)])
        check("no card from a hidden or junior player ever comes out",
              all(c["player_id"] in snap["people"] for c in got))

        summary = await cards.open_many(db, club, alpha, snap)
        await db.commit()
        check("open-all opens what is ready and reports a summary", summary["opened"] > 3 and summary["total"] >= summary["opened"], str(summary)[:120])
        left = await cards.available_packs(db, str(ALPHA), snap)
        check("open-all leaves nothing open", len(left) == 0)

    # ── Special cards ────────────────────────────────────────────────────────
    print("\nspecial cards")
    async with Session() as db:
        club = await db.get(Organisation, ORG)
        snap = await cards.club_snapshot(db, club, fresh=True)
        made = await cards.refresh_specials(db, club, force=True)
        await db.commit()

        async def specials_of(pid, kind=None):
            q = "SELECT kind, detail, occurred_on FROM player_special_cards WHERE player_id = :p"
            if kind:
                q += " AND kind = :k"
            return (await db.execute(text(q), {"p": pid, "k": kind})).mappings().all()

        cent = await specials_of(ALPHA, "century")
        check("a century makes one card", len(cent) == 1 and cent[0]["detail"]["runs"] == 112 and cent[0]["detail"]["not_out"] is True, str(cent))
        check("...with the opposition read from the other side of the game", cent and cent[0]["detail"].get("opposition") == "Them", str(cent))
        check("a 52 is a half century, and not a century", len(await specials_of(DELTA, "fifty")) == 1 and not await specials_of(DELTA, "century"))
        check("a five-for makes a card", len(await specials_of(BRAVO, "five_for")) == 1)
        check("a hat-trick the club recorded makes a card", len(await specials_of(CHARLIE, "hat_trick")) == 1)
        check("a club award makes a card", len(await specials_of(BRAVO, "award")) == 1)
        debuts = [len(await specials_of(p, "debut")) for p in (ALPHA, BRAVO, CHARLIE, DELTA)]
        check("everyone with a match has a debut card", debuts == [1, 1, 1, 1], str(debuts))
        gm = {r["detail"]["games"] for r in await specials_of(ALPHA, "games")}
        check("a games milestone for each one reached (120 matches: 10, 50, 100)", gm == {10, 50, 100}, str(gm))
        check("a milestone nobody has reached is not made", 150 not in gm)
        total_before = (await db.execute(text("SELECT count(*) FROM player_special_cards WHERE organisation_id = :o"), {"o": ORG})).scalar()
        await cards.refresh_specials(db, club, force=True)
        await db.commit()
        total_after = (await db.execute(text("SELECT count(*) FROM player_special_cards WHERE organisation_id = :o"), {"o": ORG})).scalar()
        check("a second look makes no new card", total_before == total_after and total_before > 8, f"{total_before} {total_after}")
        gifts = (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE source = 'gift' AND organisation_id = :o"), {"o": ORG})).scalar()
        check("every player is gifted the cards that commemorate them (one copy each)", gifts == total_after, f"{gifts} vs {total_after}")
        await db.execute(text("UPDATE batting_innings SET runs = 98 WHERE player_id = :p AND runs = 112"), {"p": ALPHA})
        await db.commit()
        await cards.refresh_specials(db, club, force=True)
        await db.commit()
        check("a score corrected down later keeps the card (add-only: it commemorates the moment)", len(await specials_of(ALPHA, "century")) == 1)
        await db.execute(text("UPDATE batting_innings SET runs = 112 WHERE player_id = :p AND runs = 98"), {"p": ALPHA})
        await db.commit()

    # ── The collection ───────────────────────────────────────────────────────
    print("\nthe collection")
    async with Session() as db:
        club, alpha = await db.get(Organisation, ORG), await db.get(Player, ALPHA)
        snap = await cards.club_snapshot(db, club, fresh=True)
        col = await cards.collection(db, club, alpha, snap)
        keys = {c["key"] for c in col["cards"]}
        check("the player's own card is always in it", f"p:{ALPHA}" in keys)
        own = next(c for c in col["cards"] if c["key"] == f"p:{ALPHA}")
        check("...marked as theirs", own["mine"] is True)
        check("the gifted special cards are in it", any(c["kind"] == "special" and c["special_kind"] == "century" for c in col["cards"]))
        check("totals count the club's set (the five players in the pool)", col["totals"]["regular_total"] == 5 and col["totals"]["regular_owned"] >= 1, str(col["totals"]))
        # a duplicate stacks as a count
        sub = str(BRAVO)
        held_before = next((c["copies"] for c in col["cards"] if c["key"] == f"p:{sub}"), 0)
        for _ in range(3):
            await db.execute(text("INSERT INTO player_card_copies (organisation_id, owner_player_id, subject_player_id, source) "
                                  "VALUES (:o, :p, :s, 'pack')"), {"o": ORG, "p": ALPHA, "s": sub})
        await db.commit()
        col = await cards.collection(db, club, alpha, snap)
        bravo_card = next((c for c in col["cards"] if c["key"] == f"p:{sub}"), None)
        check("duplicates stack as a count, one entry", bravo_card is not None and bravo_card["copies"] == held_before + 3, str(bravo_card and bravo_card["copies"]))
        await cards.set_hidden(db, ORG, BRAVO, True, "test")
        await db.commit()
        snap_h = await cards.club_snapshot(db, club, fresh=True)
        col_h = await cards.collection(db, club, alpha, snap_h)
        check("a card of a player who leaves the pool is no longer shown", not any(c["key"] == f"p:{sub}" for c in col_h["cards"]))
        check("...and the copies are still held (they come back if the player does)",
              (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE owner_player_id = :p AND subject_player_id = :s"), {"p": ALPHA, "s": BRAVO})).scalar() >= held_before + 3)
        await cards.set_hidden(db, ORG, BRAVO, False, "test")
        await db.commit()
        cards.forget(ORG)
        foxtrot = await db.get(Player, FOXTROT)
        snap = await cards.club_snapshot(db, club, fresh=True)
        col_f = await cards.collection(db, club, foxtrot, snap)
        check("a player with no match still holds their own card", [c["key"] for c in col_f["cards"]] == [f"p:{FOXTROT}"])

    # ── Swaps ────────────────────────────────────────────────────────────────────────────────────────────────
    print("\nswaps")
    if not HAVE_SWAPS:
        for label in ("spare copies", "who has doubles", "asking", "answering", "a stale accept", "expiry", "routes"):
            check(f"{label}: swaps exist", False, "app.services.player_card_swaps missing")
    else:
        check("a player keeps one of every card they hold (3 copies = 2 spare, 1 copy = none)", swaps.spare("o", ("x", None), 3) == 2 and swaps.spare("o", ("x", None), 1) == 0)
        check("...but their own card is theirs without a row, so every pulled copy is spare", swaps.spare("o", ("o", None), 1) == 1 and swaps.spare("o", ("o", None), 0) == 0)
        async with Session() as db:
            club = await db.get(Organisation, ORG)
            await db.execute(text("DELETE FROM player_card_copies WHERE source IN ('pack', 'swap') AND organisation_id = :o"), {"o": ORG})
            await db.commit()

            async def give(owner, subject, n, special=None, source="pack"):
                for _ in range(n):
                    await db.execute(text("INSERT INTO player_card_copies (organisation_id, owner_player_id, subject_player_id, special_id, source) "
                                          "VALUES (:o, :ow, :s, :sp, :src)"), {"o": ORG, "ow": owner, "s": subject, "sp": special, "src": source})
                await db.commit()

            async def held(owner, subject, special=None):
                return (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE owner_player_id = :o AND subject_player_id = :s "
                                              "AND special_id IS NOT DISTINCT FROM :sp"), {"o": owner, "s": subject, "sp": special})).scalar()

            await give(ALPHA, CHARLIE, 2)       # two of Charlie: one spare
            await give(DELTA, BRAVO, 2)         # two of Bravo: one spare
            await give(DELTA, ALPHA, 1)         # one of Alpha: none spare
            await give(HOTEL, BRAVO, 3)         # Hotel is hidden from the pool
            cards.forget(ORG)
            snap = await cards.club_snapshot(db, club, fresh=True)
            a, d = str(ALPHA), str(DELTA)
            mine = await swaps.spare_cards(db, club, snap, a)
            check("a player's doubles are listed with how many are spare", [c["key"] for c in mine if c["kind"] == "player"] == [f"p:{CHARLIE}"] and mine[0]["spare"] == 1, str([(c["key"], c["spare"]) for c in mine]))
            check("a card held once is not offered", f"p:{BRAVO}" not in {c["key"] for c in mine})
            people = await swaps.swap_people(db, club, snap, a)
            names = {p["player_id"]: p["spare"] for p in people}
            check("who has doubles to offer: Delta does, with one spare", names.get(d) == 1, str(people))
            check("...not the asker, and not a player taken out of the pool", a not in names and str(HOTEL) not in names)
            check("another player's doubles show only the spare card, never their whole collection",
                  [c["key"] for c in await swaps.spare_cards(db, club, snap, d)] == [f"p:{BRAVO}"])

            async def refused(coro, status=None):
                try:
                    await coro
                    return None
                except swaps.SwapError as exc:
                    await db.commit()   # nothing was written; this only releases any row locks (a rollback would expire the club)
                    return exc.status if status is None else (exc.status == status)

            check("asking someone out of the pool is a 404", await refused(swaps.create_swap(db, club, snap, a, str(HOTEL), f"p:{CHARLIE}", f"p:{BRAVO}")) == 404)
            check("asking yourself is refused", await refused(swaps.create_swap(db, club, snap, a, a, f"p:{CHARLIE}", f"p:{BRAVO}")) == 404)
            check("offering a card you hold once is refused", (await refused(swaps.create_swap(db, club, snap, a, d, f"p:{DELTA}", f"p:{BRAVO}"))) == 409)
            check("asking for a card they hold once is refused", (await refused(swaps.create_swap(db, club, snap, a, d, f"p:{CHARLIE}", f"p:{ALPHA}"))) == 409)
            check("the same card both ways is refused", (await refused(swaps.create_swap(db, club, snap, a, d, f"p:{CHARLIE}", f"p:{CHARLIE}"))) == 422)
            check("a made-up card is refused", (await refused(swaps.create_swap(db, club, snap, a, d, "p:not-a-uuid", f"p:{BRAVO}"))) == 422)
            gift_special = (await db.execute(text("SELECT id::text FROM player_special_cards WHERE player_id = :p AND kind = 'century'"), {"p": ALPHA})).scalar()
            check("a gifted special held once cannot be given away", (await refused(swaps.create_swap(db, club, snap, a, d, f"s:{gift_special}", f"p:{BRAVO}"))) == 409)

            sid = await swaps.create_swap(db, club, snap, a, d, f"p:{CHARLIE}", f"p:{BRAVO}")
            await db.commit()
            check("a swap request is made", bool(sid))
            check("asking again for the same swap is refused", (await refused(swaps.create_swap(db, club, snap, a, d, f"p:{CHARLIE}", f"p:{BRAVO}"))) == 409)
            check("nothing has moved yet", await held(ALPHA, CHARLIE) == 2 and await held(DELTA, BRAVO) == 2)
            li = await swaps.list_swaps(db, club, snap, d)
            lo = await swaps.list_swaps(db, club, snap, a)
            check("the person asked sees it coming in, with both cards", len(li["incoming"]) == 1 and li["incoming"][0]["give"]["player_id"] == str(CHARLIE) and li["incoming"][0]["want"]["player_id"] == str(BRAVO), str(li)[:200])
            check("the person who asked sees it going out", len(lo["outgoing"]) == 1 and not lo["incoming"])
            check("a third player sees nothing of it", not (await swaps.list_swaps(db, club, snap, str(CHARLIE)))["incoming"])
            check("the dashboard counts requests waiting", await swaps.waiting_count(db, d) == 1 and await swaps.waiting_count(db, a) == 0)
            summary = await cards.dashboard_summary(db, club, await db.get(Player, DELTA))
            await db.commit()
            check("...and its summary carries the count", summary["swaps_waiting"] == 1, str(summary))

            check("the asker cannot accept their own request", (await refused(swaps.respond(db, club, snap, a, sid, "accept"))) == 403)
            check("the person asked cannot cancel it", (await refused(swaps.respond(db, club, snap, d, sid, "cancel"))) == 403)
            check("a stranger cannot touch it (404)", (await refused(swaps.respond(db, club, snap, str(CHARLIE), sid, "accept"))) == 404)
            check("nothing moved from those refusals", await held(ALPHA, CHARLIE) == 2 and await held(DELTA, BRAVO) == 2)

            # a second request offering the SAME spare Charlie, so the first accept makes it stale
            sid2 = await swaps.create_swap(db, club, snap, a, d, f"p:{CHARLIE}", f"p:{BRAVO}") if False else None
            await db.execute(text("INSERT INTO player_card_swaps (organisation_id, from_player_id, to_player_id, give_subject_player_id, want_subject_player_id) "
                                  "VALUES (:o, :a, :d, :c, :b)"), {"o": ORG, "a": ALPHA, "d": DELTA, "c": CHARLIE, "b": BRAVO})
            await db.commit()
            total_before = (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE organisation_id = :o"), {"o": ORG})).scalar()
            res = await swaps.respond(db, club, snap, d, sid, "accept")
            await db.commit()
            check("accepting makes the swap", res == "accepted")
            check("Alpha gave Charlie's card and got Bravo's", await held(ALPHA, CHARLIE) == 1 and await held(ALPHA, BRAVO) == 1, f"{await held(ALPHA, CHARLIE)} {await held(ALPHA, BRAVO)}")
            check("Delta gave Bravo's card and got Charlie's", await held(DELTA, BRAVO) == 1 and await held(DELTA, CHARLIE) == 1)
            check("no card was made or lost", (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE organisation_id = :o"), {"o": ORG})).scalar() == total_before)
            check("both people still hold a copy of what they gave", await held(ALPHA, CHARLIE) >= 1 and await held(DELTA, BRAVO) >= 1)
            check("a swapped card is marked as swapped", (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE source = 'swap' AND organisation_id = :o"), {"o": ORG})).scalar() == 2)
            check("a settled swap cannot be accepted again", (await refused(swaps.respond(db, club, snap, d, sid, "accept"))) == 409)
            check("it shows in the recent list for both", len((await swaps.list_swaps(db, club, snap, a))["recent"]) == 1 and len((await swaps.list_swaps(db, club, snap, d))["recent"]) == 1)

            stale = (await db.execute(text("SELECT id::text FROM player_card_swaps WHERE status = 'pending' AND organisation_id = :o"), {"o": ORG})).scalar()
            check("the second request, offering a card that is no longer a double, cannot go ahead (409)", (await refused(swaps.respond(db, club, snap, d, stale, "accept"))) == 409)
            check("...and moved nothing", await held(ALPHA, CHARLIE) == 1 and await held(DELTA, BRAVO) == 1)
            check("it can still be declined", await swaps.respond(db, club, snap, d, stale, "decline") == "declined")
            await db.commit()

            # cancel, and expiry
            await give(DELTA, BRAVO, 1)
            await give(ALPHA, CHARLIE, 1)
            s3 = await swaps.create_swap(db, club, snap, a, d, f"p:{CHARLIE}", f"p:{BRAVO}")
            await db.commit()
            check("the asker can cancel", await swaps.respond(db, club, snap, a, s3, "cancel") == "cancelled")
            await db.commit()
            s4 = await swaps.create_swap(db, club, snap, a, d, f"p:{CHARLIE}", f"p:{BRAVO}")
            await db.execute(text("UPDATE player_card_swaps SET created_at = NOW() - INTERVAL '20 days' WHERE id = CAST(:i AS UUID)"), {"i": s4})
            await db.commit()
            check("an old request has expired and is not offered", not (await swaps.list_swaps(db, club, snap, d))["incoming"] and await swaps.waiting_count(db, d) == 0)
            check("...and cannot be accepted", (await refused(swaps.respond(db, club, snap, d, s4, "accept"))) == 409)

            # the cap on open requests
            old_cap = swaps.MAX_OUTGOING
            swaps.MAX_OUTGOING = 1
            await give(ALPHA, DELTA, 2)
            await give(DELTA, ALPHA, 1)
            first = await swaps.create_swap(db, club, snap, a, d, f"p:{CHARLIE}", f"p:{BRAVO}")
            await db.commit()
            check("the number of open requests is capped", (await refused(swaps.create_swap(db, club, snap, a, d, f"p:{DELTA}", f"p:{ALPHA}"))) == 409)
            swaps.MAX_OUTGOING = old_cap
            await swaps.respond(db, club, snap, a, first, "cancel")
            await db.commit()

    # ── What the admin can see ───────────────────────────────────────────────────────────────────────────────
    print("\nadmin insight")
    if not HAVE_SWAPS or not hasattr(admin_routes, "overview"):
        for label in ("overview", "activity", "catalogue", "one player", "swap audit"):
            check(f"{label}: the admin views exist", False, "player_cards_admin has no such route")
    else:
        async with Session() as db:
            club = await db.get(Organisation, ORG)
            user = User(id=uuid.uuid4(), email="admin@example.com")
            cards.forget(ORG)
            ov = await admin_routes.overview(db, club, user)
            rows = {r["id"]: r for r in ov["players"]}
            t = ov["totals"]
            check("the overview counts the pool and a row per player the club holds", t["pool"] == 5 and len(rows) >= 9, str(t))
            check("a player who opened packs shows how many, and when first and last", rows[str(ALPHA)]["packs_opened"] > 0 and rows[str(ALPHA)]["first_opened_at"] and rows[str(ALPHA)]["last_opened_at"], str(rows[str(ALPHA)]))
            check("a player who never opened one says so (and is counted)", rows[str(CHARLIE)]["packs_opened"] == 0 and t["players_never_opened"] >= 1 and t["players_opened"] >= 1)
            check("every opened pack is counted across the club", t["packs_opened"] == sum(r["packs_opened"] for r in rows.values()), str(t))
            check("collected is cards held over the club's set", 0 < rows[str(ALPHA)]["collected_pct"] <= 100 and rows[str(ALPHA)]["cards"] >= 1)
            check("a player out of the pool is listed, marked out, and not credited their own card", rows[str(GOLF)]["in_pool"] is False and rows[str(GOLF)]["cards"] == 0)
            check("accepted swaps are counted per player and in total", t["swaps_done"] >= 1 and rows[str(ALPHA)]["swaps_done"] >= 1 and rows[str(DELTA)]["swaps_done"] >= 1, str(t))

            act = await admin_routes.activity(db, club, user)
            check("recent special cards come newest first with the player and what is held", act["recent_specials"] and act["recent_specials"][0]["player"] and "held" in act["recent_specials"][0])
            added = [r["added_at"] for r in act["recent_specials"]]
            check("...in date order", added == sorted(added, reverse=True))
            check("recent cards say where they came from and whether they were new to the player", {c["source"] for c in act["recent_cards"]} <= {"pack", "swap"} and all("new_to_owner" in c for c in act["recent_cards"]) and act["recent_cards"])
            check("recent openings name the player, the pack and the best card", act["recent_openings"] and act["recent_openings"][0]["player"] and act["recent_openings"][0]["source"])
            check("a card pulled for the first time is marked new, and a repeat is not",
                  any(c["new_to_owner"] for c in act["recent_cards"]) and any(not c["new_to_owner"] for c in act["recent_cards"]), str([c["new_to_owner"] for c in act["recent_cards"]][:12]))
            check("a fortnight of daily counts, today's special cards among them", len(act["daily"]) == 14 and act["daily"][-1]["specials_added"] > 0 and sum(d["packs_opened"] for d in act["daily"]) > 0)

            cat = await admin_routes.catalogue("all", None, "", "rarity", 60, 0, db, club, user)
            check("the catalogue lists every drawable player card (5) and the specials", cat["counts"]["player"] == 5 and cat["counts"]["special"] > 5, str(cat["counts"]))
            check("a player outside the pool has no card in it", all(i["player_id"] != str(GOLF) for i in cat["items"]))
            check("it shows copies held and owners for each card", all("held" in i and "owners" in i for i in cat["items"]))
            own = await admin_routes.catalogue("player", None, "alpha", "name", 60, 0, db, club, user)
            check("search finds a player by name", len(own["items"]) == 1 and own["items"][0]["player_id"] == str(ALPHA) and own["items"][0]["held"] >= 1 and own["items"][0]["owners"] >= 1, str(own["items"][:1]))
            sp = await admin_routes.catalogue("special", "century", "", "recent", 60, 0, db, club, user)
            check("it filters to one kind of special", sp["items"] and all(i["special_kind"] == "century" for i in sp["items"]))
            page1 = await admin_routes.catalogue("special", None, "", "name", 5, 0, db, club, user)
            page2 = await admin_routes.catalogue("special", None, "", "name", 5, 5, db, club, user)
            check("it pages, with no card on two pages", len(page1["items"]) == 5 and not ({i["key"] for i in page1["items"]} & {i["key"] for i in page2["items"]}) and page1["total"] == page2["total"])
            by_held = await admin_routes.catalogue("player", None, "", "held", 60, 0, db, club, user)
            check("sorting by copies held puts the scarcest first", by_held["items"][0]["held"] <= by_held["items"][-1]["held"])

            one = await admin_routes.player_detail(str(ALPHA), db, club, user)
            keys = {c["key"] for c in one["cards"]}
            check("a player's page holds their whole collection, their own card among it", f"p:{ALPHA}" in keys and one["totals"]["copies"] >= 1)
            check("...their packs by kind and recent ones", one["packs"]["by_source"] and one["packs"]["recent"])
            check("...what they got lately and their swaps", one["recent_cards"] and one["swaps"] and one["swaps"][0]["from"]["name"])
            check("another club's player is a 404, not a 403", await status_of(admin_routes.player_detail(str(SEL_PLAYER), db, club, user)) == 404)
            check("a made-up id is a 404", await status_of(admin_routes.player_detail("nope", db, club, user)) == 404)

            aud = await admin_routes.swap_audit("all", "", 50, 0, db, club, user)
            counts = aud["counts"]
            check("the audit counts every kind of ending", counts["accepted"] >= 1 and counts["declined"] >= 1 and counts["cancelled"] >= 1 and counts["expired"] >= 1, str(counts))
            check("each row names who asked, who was asked and both cards", all(r["from"]["name"] and r["to"]["name"] and r["give"]["player"] and r["want"]["player"] for r in aud["swaps"]), str(aud["swaps"][:1]))
            done = await admin_routes.swap_audit("accepted", "", 50, 0, db, club, user)
            check("it filters to one outcome", done["swaps"] and all(r["status"] == "accepted" for r in done["swaps"]))
            exp = await admin_routes.swap_audit("expired", "", 50, 0, db, club, user)
            check("an old unanswered request shows as expired", exp["swaps"] and all(r["status"] == "expired" for r in exp["swaps"]))
            who = await admin_routes.swap_audit("all", "delta", 50, 0, db, club, user)
            check("it searches by player", who["swaps"] and all("Delta" in (r["from"]["name"] or "") + (r["to"]["name"] or "") or "Delta" in r["give"]["player"] + r["want"]["player"] for r in who["swaps"]))
            check("nothing in the audit was written to by reading it", (await db.execute(text("SELECT count(*) FROM player_card_swaps WHERE status = 'expired'"))).scalar() == 0)

    # ── Route bodies ─────────────────────────────────────────────────────────
    print("\nroute bodies")
    async with Session() as db:
        out = await pc_routes.get_my_cards(TOKEN, request_for(DELTA, ORG), db)
        check("GET my cards answers with packs and a collection", "packs" in out and out["cards"] and "week_resets_at" in out, str(out.keys()))
        check("...DELTA has packs to open", len(out["packs"]) > 0)
        opened = await pc_routes.open_my_pack(TOKEN, out["packs"][0]["id"], request_for(DELTA, ORG), db)
        check("POST open returns the cards and what is left", opened["cards"] and opened["packs_left"] == len(out["packs"]) - 1)
        check("another player's pack id is refused (409), not opened",
              await status_of(pc_routes.open_my_pack(TOKEN, out["packs"][1]["id"], request_for(ALPHA, ORG), db)) == 409)
        check("a player outside the pool has no cards (404)", await status_of(pc_routes.get_my_cards(TOKEN, request_for(GOLF, ORG), db)) == 404)
        check("no cookie, no cards (401)", await status_of(pc_routes.get_my_cards(TOKEN, Request({"type": "http", "method": "GET", "path": "/", "headers": [], "client": ("1.1.1.1", 1)}), db)) == 401)
        check("a cookie for ANOTHER club does not work here (401)", await status_of(pc_routes.get_my_cards(TOKEN, request_for(DELTA, ORG_SELECT), db)) == 401)
        allr = await pc_routes.open_all_my_packs(TOKEN, request_for(DELTA, ORG), db)
        check("open-all returns a summary, not hundreds of cards", "by_tier" in allr and "cards" not in allr and allr["packs_left"] == 0)
        if HAVE_SWAPS:
            from app.routers import public_player_cards as pcr
            await db.execute(text("INSERT INTO player_card_copies (organisation_id, owner_player_id, subject_player_id, source) VALUES (:o, :a, :c, 'pack'), (:o, :d, :b, 'pack')"),
                             {"o": ORG, "a": ALPHA, "c": CHARLIE, "d": DELTA, "b": BRAVO})
            await db.commit()
            board = await pcr.get_my_swaps(TOKEN, request_for(ALPHA, ORG), db)
            check("GET swaps answers with requests, my doubles and who has doubles", {"incoming", "outgoing", "recent", "mine", "people"} <= set(board), str(board.keys()))
            other = await pcr.get_swap_player(TOKEN, str(DELTA), request_for(ALPHA, ORG), db)
            check("GET a player's doubles answers with only spare cards", other["player"]["player_id"] == str(DELTA) and all(c["spare"] >= 1 for c in other["cards"]))
            check("GET the doubles of a player outside the pool is a 404", await status_of(pcr.get_swap_player(TOKEN, str(HOTEL), request_for(ALPHA, ORG), db)) == 404)
            made = await pcr.ask_for_swap(TOKEN, pcr.SwapBody(to_player_id=str(DELTA), give_key=f"p:{CHARLIE}", want_key=f"p:{BRAVO}"), request_for(ALPHA, ORG), db)
            check("POST a swap request", made["status"] == "pending")
            check("POST the same again is a 409", await status_of(pcr.ask_for_swap(TOKEN, pcr.SwapBody(to_player_id=str(DELTA), give_key=f"p:{CHARLIE}", want_key=f"p:{BRAVO}"), request_for(ALPHA, ORG), db)) == 409)
            check("the asker accepting their own is a 403", await status_of(pcr.answer_swap(TOKEN, made["id"], "accept", request_for(ALPHA, ORG), db)) == 403)
            done = await pcr.answer_swap(TOKEN, made["id"], "accept", request_for(DELTA, ORG), db)
            check("POST accept as the person asked", done["status"] == "accepted")
            check("no cookie, no swaps (401)", await status_of(pcr.get_my_swaps(TOKEN, Request({"type": "http", "method": "GET", "path": "/", "headers": [], "client": ("1.1.1.1", 1)}), db)) == 401)
        prof = await pa.get_my_profile(TOKEN, request_for(ALPHA, ORG), None, db)
        check("the profile carries the cards line and no availability", prof["cards"] is not None and prof["has_availability"] is False and "cards" in prof["modules"], str(prof.get("modules")))
        await cards.save_settings(db, ORG, {"enabled": False})
        await db.commit()
        cards.forget(ORG)
        prof_off = await pa.get_my_profile(TOKEN, request_for(ALPHA, ORG), None, db)
        check("a club that switches cards off drops the module", "cards" not in prof_off["modules"] and prof_off["cards"] is None)
        check("...and the card routes answer 404", await status_of(pc_routes.get_my_cards(TOKEN, request_for(ALPHA, ORG), db)) == 404)
        await cards.save_settings(db, ORG, {"enabled": True})
        await db.commit()
        cards.forget(ORG)

    # ── Settings and admin ───────────────────────────────────────────────────
    print("\nsettings and admin")
    async with Session() as db:
        club = await db.get(Organisation, ORG)
        await cards.save_settings(db, ORG, {"weekly_packs": 2, "timezone": "Australia/Sydney"})
        await cards.save_settings(db, ORG, {"include_juniors": True})
        s = await cards.load_settings(db, ORG)
        check("a key that is not sent leaves its setting alone", s["weekly_packs"] == 2 and s["timezone"] == "Australia/Sydney" and s["include_juniors"] is True, str(s))
        await cards.save_settings(db, ORG, {"timezone": None})
        s = await cards.load_settings(db, ORG)
        check("an explicit null clears the timezone", s["timezone"] is None and s["weekly_packs"] == 2)
        try:
            await cards.save_settings(db, ORG, {"timezone": "Mars/Olympus"})
            bad = False
        except ValueError:
            bad = True
        await db.rollback()
        club = await db.get(Organisation, ORG)
        check("a timezone nobody knows is refused", bad)
        await cards.save_settings(db, ORG, {"weekly_packs": 99})
        check("the weekly count is capped", (await cards.load_settings(db, ORG))["weekly_packs"] == cards.MAX_WEEKLY_PACKS)
        await cards.save_settings(db, ORG, {"weekly_packs": 1, "include_juniors": False})
        await db.commit()
        cards.forget(ORG)
        user = User(id=uuid.uuid4(), email="admin@example.com")
        payload = await admin_routes._payload(db, club)
        check("the admin payload lists every player with why they are out",
              {r["id"]: r["excluded"] for r in payload["players"]}.get(str(GOLF)) == "private"
              and {r["id"]: r["excluded"] for r in payload["players"]}.get(str(ECHO)) == "junior", str({r["display_name"]: r["excluded"] for r in payload["players"]}))
        check("...and the link to the player page", payload["link"]["path"] == f"/avail/{TOKEN}")
        gone = await status_of(admin_routes.hide_player(str(SEL_PLAYER), admin_routes.HiddenBody(hidden=True), db, club, user))
        check("hiding another club's player is a 404, not a 403", gone == 404)

    # ── Merge ────────────────────────────────────────────────────────────────
    print("\nplayer merge")
    async with Session() as db:
        keep, drop = INDIA, FOXTROT
        await db.execute(text("INSERT INTO player_card_packs (organisation_id, player_id, source, ref_key) VALUES "
                              "(:o, :k, 'weekly', '2026-W44:1'), (:o, :d, 'weekly', '2026-W44:1'), (:o, :d, 'starter', '1')"), {"o": ORG, "k": keep, "d": drop})
        await db.execute(text("INSERT INTO player_card_copies (organisation_id, owner_player_id, subject_player_id, source) VALUES "
                              "(:o, :d, :k, 'pack'), (:o, :k, :d, 'pack')"), {"o": ORG, "k": keep, "d": drop})
        await db.execute(text("INSERT INTO player_special_cards (organisation_id, player_id, kind, event_key, title) VALUES (:o, :d, 'century', 'century:merge-test', 'Century')"),
                         {"o": ORG, "d": drop})
        await db.commit()
        if HAVE_SWAPS:
            await db.execute(text("INSERT INTO player_card_swaps (organisation_id, from_player_id, to_player_id, give_subject_player_id, want_subject_player_id) "
                                  "VALUES (:o, :d, :a, :d, :a), (:o, :a, :d, :a, :d)"), {"o": ORG, "d": drop, "a": ALPHA})
            await db.commit()
        moved = await merge_carry.carry_rows(db, keep, drop, ORG)
        await db.commit()
        left = (await db.execute(text("SELECT count(*) FROM player_card_packs WHERE player_id = :d"), {"d": drop})).scalar()
        check("the removed player's packs move to the keeper", left == 0 and "player_card_packs.player_id" in moved, str(moved.keys()))
        check("the same pack twice (same person, same week) is kept once, not doubled",
              (await db.execute(text("SELECT count(*) FROM player_card_packs WHERE player_id = :k AND source = 'weekly' AND ref_key = '2026-W44:1'"), {"k": keep})).scalar() == 1)
        check("a pack only the removed player had arrives",
              (await db.execute(text("SELECT count(*) FROM player_card_packs WHERE player_id = :k AND source = 'starter' AND ref_key = '1'"), {"k": keep})).scalar() == 1)
        check("cards they held and cards OF them both move",
              (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE owner_player_id = :d OR subject_player_id = :d"), {"d": drop})).scalar() == 0
              and (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE owner_player_id = :k AND subject_player_id = :k AND source = 'pack'"), {"k": keep})).scalar() == 2)
        if HAVE_SWAPS:
            check("swap requests move with the person, in both directions and on both cards",
                  (await db.execute(text("SELECT count(*) FROM player_card_swaps WHERE :d IN (from_player_id, to_player_id, give_subject_player_id, want_subject_player_id)"), {"d": drop})).scalar() == 0
                  and (await db.execute(text("SELECT count(*) FROM player_card_swaps WHERE :k IN (from_player_id, to_player_id)"), {"k": keep})).scalar() >= 2)
        check("special cards of the removed player move to the keeper",
              (await db.execute(text("SELECT count(*) FROM player_special_cards WHERE player_id = :k AND event_key = 'century:merge-test'"), {"k": keep})).scalar() == 1)

    # ── The migration and its mirror ─────────────────────────────────────────
    print("\nmigration")
    async with engine.begin() as conn:
        for stmt in CARD_DDL:
            await conn.execute(text(stmt))
    check("the DDL runs a second time without error (the lifespan re-runs it on every boot)", True)
    mig = (Path(__file__).resolve().parent.parent / "alembic" / "versions" / "363_player_cards.py").read_text()
    check("the migration runs the shared DDL list (one copy)", "from app.services.player_cards_ddl import STATEMENTS" in mig)
    if HAVE_SWAPS:
        mig2 = (Path(__file__).resolve().parent.parent / "alembic" / "versions" / "364_player_card_swaps.py").read_text()
        check("the swaps migration follows 363 and runs its own shared list", "down_revision = \"363\"" in mig2 and "player_card_swaps_ddl import STATEMENTS" in mig2 and "player_card_swaps_ddl import STATEMENTS" in main_src_swaps())
    main_src = (Path(__file__).resolve().parent.parent / "app" / "main.py").read_text()
    check("the lifespan mirrors the same list", "from app.services.player_cards_ddl import STATEMENTS" in main_src)

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("FAILED:\n  " + "\n  ".join(FAILURES))
        sys.exit(1)


async def _run() -> None:
    try:
        await main()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_run())
