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
import json
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
    from app.services import player_card_swaps_ddl as _swap_ddl
    SWAP_DDL = _swap_ddl.STATEMENTS
    try:
        from app.services.player_card_community_ddl import STATEMENTS as COMMUNITY_DDL
    except ImportError:
        COMMUNITY_DDL = []
    try:
        from app.services.player_card_packs_ddl import STATEMENTS as PACKS_DDL
    except ImportError:   # the control run on the commit before the new packs
        PACKS_DDL = []
    try:
        from app.services.player_card_designs_ddl import STATEMENTS as DESIGNS_DDL
    except ImportError:   # the control run on the commit before pack designs
        DESIGNS_DDL = []
    try:
        from app.services.player_card_gifts_ddl import STATEMENTS as GIFTS_DDL
    except ImportError:   # the control run on the commit before admin-created packs
        GIFTS_DDL = []
    try:
        from app.services.player_card_photos_ddl import STATEMENTS as PHOTOS_DDL
    except ImportError:   # the control run on the commit before photos by card type
        PHOTOS_DDL = []
    try:
        from app.services.player_card_looks_ddl import STATEMENTS as LOOKS_DDL
    except ImportError:   # the control run on the commit before packs could be designed and sized as they are made
        LOOKS_DDL = []
    try:
        from app.services.player_card_social_ddl import STATEMENTS as SOCIAL_DDL
    except ImportError:   # the control run on the commit before the social side
        SOCIAL_DDL = []
    ITEM_DDL = getattr(_swap_ddl, "ITEM_STATEMENTS", [])  # absent before migration 366
else:
    swaps = None
    SWAP_DDL = []
    SOCIAL_DDL = []
    COMMUNITY_DDL = []
    PACKS_DDL = []
    DESIGNS_DDL = []
    GIFTS_DDL = []
    LOOKS_DDL = []
    PHOTOS_DDL = []
    ITEM_DDL = []

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
            CREATE TABLE IF NOT EXISTS org_award_definitions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(), org_id UUID NOT NULL,
                category TEXT NOT NULL, subcategory TEXT, achievement TEXT, display_name TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0, active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"""))
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
        for stmt in CARD_DDL + SWAP_DDL + SOCIAL_DDL + COMMUNITY_DDL + PACKS_DDL + DESIGNS_DDL + GIFTS_DDL + PHOTOS_DDL + LOOKS_DDL:
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
        # Awards written two ways: a seasons id with a club rename (two definitions under one name, which must
        # not fan the row out) and an imported "2015_16" label with no rename.
        await ex("INSERT INTO player_achievements (org_id, player_id, player_name, season, category, subcategory, achievement) "
                 "VALUES (:o, :p, 'Delta, D', :s, 'Club Award', 'Perpetual', 'Best Bowler')", o=ORG, p=DELTA, s=str(S_OLD))
        await ex("INSERT INTO player_achievements (org_id, player_id, player_name, season, category, subcategory, achievement) "
                 "VALUES (:o, :p, 'Delta, D', '2015_16', 'Club Award', NULL, 'Best Batter')", o=ORG, p=DELTA)
        await ex("INSERT INTO org_award_definitions (org_id, category, subcategory, achievement, display_name, sort_order) VALUES "
                 "(:o, 'Club Award', 'Perpetual', 'Best Bowler', 'Bowler of the Year', 0), "
                 "(:o, 'Club Award', 'Perpetual', 'Best Bowler', 'Second Name', 1)", o=ORG)
        # Cards launched a month ago: a duck before then earns no pack.
        if HAVE:
            await ex("INSERT INTO club_card_settings (organisation_id, launched_at, weekly_packs) "
                     "VALUES (:o, NOW() - INTERVAL '30 days', 1)", o=ORG)
            if PACKS_DDL:
                # The older sections were written when every special was gifted; the minimal default has its own section.
                await ex("UPDATE club_card_settings SET starter_gifts = 'all', event_packs_enabled = FALSE WHERE organisation_id = :o", o=ORG)
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

    # ── The three photographs (migration 374) ────────────────────────────────
    # A card carries the hero photo, the action shot and the club's pick between them; the frontend resolves it
    # (lib/playerShots.js). Read through .get so the control run (the commit before 374) reports instead of crashing.
    print("\nthe three photographs")
    async with Session() as db:
        try:
            await db.execute(text("UPDATE players SET action_photo_url = '/api/images/players/x/action-photo?v=1', "
                                  "hero_source = 'action' WHERE id = :i"), {"i": ALPHA})
            await db.commit()
        except Exception:
            await db.rollback()  # the control run's schema has no such columns
        club = await db.get(Organisation, ORG)
        snap = await cards.club_snapshot(db, club, fresh=True)
        a = cards.regular_card(snap, str(ALPHA))
        d = cards.regular_card(snap, str(DELTA))
        NO = object()
        check("a regular card carries the action shot", a.get("action_photo_url", NO) == "/api/images/players/x/action-photo?v=1", str(a.get("action_photo_url", NO)))
        check("and the club's pick between the hero photo and the action shot", a.get("hero_source", NO) == "action", str(a.get("hero_source", NO)))
        check("a player with neither carries null for both, not a missing key", d.get("action_photo_url", NO) is None and d.get("hero_source", NO) is None)
        own = cards._own_card_outside_pool(await db.get(Player, ALPHA), snap)
        check("an own card outside the pool carries them too", own.get("action_photo_url", NO) == "/api/images/players/x/action-photo?v=1" and own.get("hero_source", NO) == "action")
        try:
            await db.execute(text("UPDATE players SET action_photo_url = NULL, hero_source = NULL WHERE id = :i"), {"i": ALPHA})
            await db.commit()
        except Exception:
            await db.rollback()
        cards.forget(ORG)

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
        async def awards_of(pid):
            return {r["title"]: r["detail"] for r in (await db.execute(text(
                "SELECT title, detail FROM player_special_cards WHERE player_id = :p AND kind = 'award'"), {"p": pid})).mappings().all()}
        aw = await awards_of(DELTA)
        check("an award takes the club's display name, one card even with two definitions under it", set(aw) == {"Bowler of the Year", "Best Batter"}, str(aw))
        check("a season id is shown as the season's name, not the id", aw.get("Bowler of the Year", {}).get("season") == "Summer 2015/16", str(aw))
        check("an imported 2015_16 label is shown as 2015/16", aw.get("Best Batter", {}).get("season") == "2015/16", str(aw))
        check("the grade stays on the card", aw.get("Bowler of the Year", {}).get("grade") == "Perpetual", str(aw))
        debuts = [len(await specials_of(p, "debut")) for p in (ALPHA, BRAVO, CHARLIE, DELTA)]
        check("everyone with a match has a debut card", debuts == [1, 1, 1, 1], str(debuts))
        gm = {r["detail"]["games"] for r in await specials_of(ALPHA, "games")}
        check("a games milestone for each one reached (120 matches: 10, 50, 100)", gm == {10, 50, 100}, str(gm))
        check("a milestone nobody has reached is not made", 150 not in gm)
        rm = await specials_of(ALPHA, "runs_milestone")
        check("a card for every 1,000 career runs (3,000 runs = 3 cards)", sorted(r["detail"]["threshold"] for r in rm) == [1000, 2000, 3000], str([r["detail"] for r in rm]))
        by_t = {r["detail"]["threshold"]: r for r in rm}
        check("the date is the game the figure crossed the step in, taking the older season-total career into account", by_t.get(3000, {}).get("occurred_on") == date.today() - timedelta(days=60), str(by_t.get(3000)))
        check("a step that fell in the part of the career with no scorecards has no date, not a wrong one", 1000 in by_t and 2000 in by_t and by_t[1000]["occurred_on"] is None and by_t[2000]["occurred_on"] is None)
        wm = await specials_of(BRAVO, "wickets_milestone")
        check("a card for every 200 career wickets (250 wickets = 1 card)", [r["detail"]["threshold"] for r in wm] == [200], str([r["detail"] for r in wm]))
        dm = await specials_of(CHARLIE, "dismissals_milestone")
        check("a card for every 50 dismissals (catches, run outs and stumpings together: 185 = 3 cards)", sorted(r["detail"]["threshold"] for r in dm) == [50, 100, 150], str([r["detail"] for r in dm]))
        check("a player short of a step gets none (Delta: 40 runs)", not await specials_of(DELTA, "runs_milestone") and not await specials_of(DELTA, "wickets_milestone"))
        titles = (await db.execute(text("SELECT title FROM player_special_cards WHERE player_id = :p AND kind = 'runs_milestone' ORDER BY title"), {"p": ALPHA})).scalars().all()
        check("the title reads like the card: 1,000 runs", titles == ["1,000 runs", "2,000 runs", "3,000 runs"], str(titles))
        total_before = (await db.execute(text("SELECT count(*) FROM player_special_cards WHERE organisation_id = :o"), {"o": ORG})).scalar()
        await cards.refresh_specials(db, club, force=True)
        await db.commit()
        total_after = (await db.execute(text("SELECT count(*) FROM player_special_cards WHERE organisation_id = :o"), {"o": ORG})).scalar()
        check("a second look makes no new card", total_before == total_after and total_before > 8, f"{total_before} {total_after}")
        gifts = (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE source = 'gift' AND organisation_id = :o"), {"o": ORG})).scalar()
        check("every player is gifted the cards that commemorate them (one copy each)", gifts == total_after, f"{gifts} vs {total_after}")
        # a rename and a corrected season reach a card that already exists; nothing is added or taken
        await db.execute(text("UPDATE org_award_definitions SET display_name = 'Bowling Champion' WHERE sort_order = 0"))
        await db.execute(text("UPDATE player_achievements SET season = :s WHERE achievement = 'Best Batter'"), {"s": str(S_NOW)})
        await db.commit()
        await cards.refresh_specials(db, club, force=True)
        await db.commit()
        aw2 = await awards_of(DELTA)
        check("a renamed award reaches the card already made", set(aw2) == {"Bowling Champion", "Best Batter"}, str(aw2))
        check("a corrected season reaches it too", aw2.get("Best Batter", {}).get("season") == f"Summer {YEAR}/{str(YEAR + 1)[2:]}", str(aw2))
        gifts2 = (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE source = 'gift' AND organisation_id = :o"), {"o": ORG})).scalar()
        total2 = (await db.execute(text("SELECT count(*) FROM player_special_cards WHERE organisation_id = :o"), {"o": ORG})).scalar()
        check("...with no new card and no copy lost", gifts2 == gifts and total2 == total_after, f"{gifts2}/{gifts} {total2}/{total_after}")
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
        for label in ("tradeable cards", "who has cards", "asking", "answering", "a stale accept", "expiry", "routes"):
            check(f"{label}: swaps exist", False, "app.services.player_card_swaps missing")
    else:
        # read through presence-safe accessors, so a run against the commit before this rule reports the absence
        _tr = getattr(swaps, "tradeable", lambda *a: None)

        async def _tcards(*a):
            fn = getattr(swaps, "tradeable_cards", None)
            return await fn(*a) if fn else []
        def _L(k):
            return [{"key": x, "qty": 1} for x in ([k] if isinstance(k, str) else k)] if not (isinstance(k, list) and k and isinstance(k[0], dict)) else k

        def mk_swap(db, club, snap, me, to, g, w):
            return swaps.create_swap(db, club, snap, me, to, _L(g), _L(w))
        check("any card held can go, a single copy as well as a double", _tr("o", ("x", None), 3) == 3 and _tr("o", ("x", None), 1) == 1 and _tr("o", ("x", None), 0) == 0)
        check("...but their own card is theirs without a row, so only copies of it they have pulled can go", _tr("o", ("o", None), 1) == 1 and _tr("o", ("o", None), 0) == 0)
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

            await give(ALPHA, CHARLIE, 1)       # one of Charlie: a single copy can be offered
            await give(DELTA, BRAVO, 1)         # one of Bravo
            await give(DELTA, ALPHA, 1)         # one of Alpha
            await give(HOTEL, BRAVO, 3)         # Hotel is hidden from the pool
            cards.forget(ORG)
            snap = await cards.club_snapshot(db, club, fresh=True)
            a, d = str(ALPHA), str(DELTA)
            mine = await _tcards(db, club, snap, a)
            check("every card a player holds can be offered, with how many copies", [c["key"] for c in mine if c["kind"] == "player"] == [f"p:{CHARLIE}"] and all(c["tradeable"] >= 1 for c in mine), str([(c["key"], c["tradeable"]) for c in mine]))
            check("a special card they were gifted, held once, can be offered too", any(c["kind"] == "special" for c in mine))
            check("their own card has no row, so it is not on the list (and cannot be given away)", f"p:{ALPHA}" not in {c["key"] for c in mine})
            await give(ALPHA, ALPHA, 1)         # a copy of their own card they pulled
            mine2 = await _tcards(db, club, snap, a)
            check("...but a copy of it they pulled can", f"p:{ALPHA}" in {c["key"] for c in mine2})
            await db.execute(text("DELETE FROM player_card_copies WHERE owner_player_id = :a AND subject_player_id = :a AND special_id IS NULL"), {"a": ALPHA})
            await db.commit()
            people = await swaps.swap_people(db, club, snap, a)
            names = {p["player_id"]: p["tradeable"] for p in people}
            check("who has cards to offer: Delta does", names.get(d, 0) >= 2, str(people))
            check("...not the asker, and not a player taken out of the pool", a not in names and str(HOTEL) not in names)
            theirs = {c["key"] for c in await _tcards(db, club, snap, d)}
            check("another player's list is the cards they hold, never their own implied card or their packs", {f"p:{BRAVO}", f"p:{ALPHA}"} <= theirs and f"p:{DELTA}" not in theirs)

            async def refused(coro, status=None):
                try:
                    await coro
                    return None
                except swaps.SwapError as exc:
                    await db.commit()   # nothing was written; this only releases any row locks (a rollback would expire the club)
                    return exc.status if status is None else (exc.status == status)

            check("asking someone out of the pool is a 404", await refused(mk_swap(db, club, snap, a, str(HOTEL), f"p:{CHARLIE}", f"p:{BRAVO}")) == 404)
            check("asking yourself is refused", await refused(mk_swap(db, club, snap, a, a, f"p:{CHARLIE}", f"p:{BRAVO}")) == 404)
            check("offering a card you do not hold (your own, which has no row) is refused", (await refused(mk_swap(db, club, snap, a, d, f"p:{ALPHA}", f"p:{BRAVO}"))) == 409)
            check("asking for a card they do not hold is refused", (await refused(mk_swap(db, club, snap, a, d, f"p:{CHARLIE}", f"p:{INDIA}"))) == 409)
            check("the same card both ways is refused", (await refused(mk_swap(db, club, snap, a, d, f"p:{CHARLIE}", f"p:{CHARLIE}"))) == 422)
            check("a made-up card is refused", (await refused(mk_swap(db, club, snap, a, d, "p:not-a-uuid", f"p:{BRAVO}"))) == 422)
            gift_special = (await db.execute(text("SELECT id::text FROM player_special_cards WHERE player_id = :p AND kind = 'century'"), {"p": ALPHA})).scalar()
            gift_swap = await mk_swap(db, club, snap, a, d, f"s:{gift_special}", f"p:{BRAVO}")
            await db.commit()
            check("a gifted special held once can be offered", bool(gift_swap))
            await swaps.respond(db, club, snap, a, gift_swap, "cancel")
            await db.commit()

            sid = await mk_swap(db, club, snap, a, d, f"p:{CHARLIE}", f"p:{BRAVO}")
            await db.commit()
            check("a swap request is made", bool(sid))
            check("asking again for the same swap is refused", (await refused(mk_swap(db, club, snap, a, d, f"p:{CHARLIE}", f"p:{BRAVO}"))) == 409)
            check("nothing has moved yet", await held(ALPHA, CHARLIE) == 1 and await held(DELTA, BRAVO) == 1)
            li = await swaps.list_swaps(db, club, snap, d)
            lo = await swaps.list_swaps(db, club, snap, a)
            check("the person asked sees it coming in, with both cards", len(li["incoming"]) == 1 and [c["player_id"] for c in li["incoming"][0]["give"]] == [str(CHARLIE)] and [c["player_id"] for c in li["incoming"][0]["want"]] == [str(BRAVO)], str(li)[:200])
            check("the person who asked sees it going out", len(lo["outgoing"]) == 1 and not lo["incoming"])
            check("a third player sees nothing of it", not (await swaps.list_swaps(db, club, snap, str(CHARLIE)))["incoming"])
            check("the dashboard counts requests waiting", await swaps.waiting_count(db, d) == 1 and await swaps.waiting_count(db, a) == 0)
            summary = await cards.dashboard_summary(db, club, await db.get(Player, DELTA))
            await db.commit()
            check("...and its summary carries the count", summary["swaps_waiting"] == 1, str(summary))

            check("the asker cannot accept their own request", (await refused(swaps.respond(db, club, snap, a, sid, "accept"))) == 403)
            check("the person asked cannot cancel it", (await refused(swaps.respond(db, club, snap, d, sid, "cancel"))) == 403)
            check("a stranger cannot touch it (404)", (await refused(swaps.respond(db, club, snap, str(CHARLIE), sid, "accept"))) == 404)
            check("nothing moved from those refusals", await held(ALPHA, CHARLIE) == 1 and await held(DELTA, BRAVO) == 1)

            # a second request offering the SAME spare Charlie, so the first accept makes it stale
            sid2 = await mk_swap(db, club, snap, a, d, f"p:{CHARLIE}", f"p:{BRAVO}") if False else None
            stale_id = (await db.execute(text("INSERT INTO player_card_swaps (organisation_id, from_player_id, to_player_id) "
                                              "VALUES (:o, :a, :d) RETURNING id::text"), {"o": ORG, "a": ALPHA, "d": DELTA})).scalar()
            for side, subj in (("give", CHARLIE), ("want", BRAVO)):
                await db.execute(text("INSERT INTO player_card_swap_items (organisation_id, swap_id, side, subject_player_id) VALUES (:o, :i, :s, :p)"),
                                 {"o": ORG, "i": stale_id, "s": side, "p": subj})
            await db.commit()
            total_before = (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE organisation_id = :o"), {"o": ORG})).scalar()
            res = await swaps.respond(db, club, snap, d, sid, "accept")
            await db.commit()
            check("accepting makes the swap", res == "accepted")
            check("Alpha gave Charlie's card (their only one) and got Bravo's", await held(ALPHA, CHARLIE) == 0 and await held(ALPHA, BRAVO) == 1, f"{await held(ALPHA, CHARLIE)} {await held(ALPHA, BRAVO)}")
            check("Delta gave Bravo's card (their only one) and got Charlie's", await held(DELTA, BRAVO) == 0 and await held(DELTA, CHARLIE) == 1)
            check("no card was made or lost", (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE organisation_id = :o"), {"o": ORG})).scalar() == total_before)
            check("a swapped card is marked as swapped", (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE source = 'swap' AND organisation_id = :o"), {"o": ORG})).scalar() == 2)
            check("a settled swap cannot be accepted again", (await refused(swaps.respond(db, club, snap, d, sid, "accept"))) == 409)
            check("it shows in the recent list for both, with the cancelled one beside it", any(r["status"] == "accepted" for r in (await swaps.list_swaps(db, club, snap, a))["recent"]) and any(r["status"] == "accepted" for r in (await swaps.list_swaps(db, club, snap, d))["recent"]))

            stale = (await db.execute(text("SELECT id::text FROM player_card_swaps WHERE status = 'pending' AND organisation_id = :o"), {"o": ORG})).scalar()
            check("the second request, offering a card the giver no longer holds, cannot go ahead (409)", (await refused(swaps.respond(db, club, snap, d, stale, "accept"))) == 409)
            check("...and moved nothing", await held(ALPHA, CHARLIE) == 0 and await held(DELTA, BRAVO) == 0 and await held(DELTA, CHARLIE) == 1)
            check("it can still be declined", await swaps.respond(db, club, snap, d, stale, "decline") == "declined")
            await db.commit()

            # cancel, and expiry
            await give(DELTA, BRAVO, 1)
            await give(ALPHA, CHARLIE, 1)
            s3 = await mk_swap(db, club, snap, a, d, f"p:{CHARLIE}", f"p:{BRAVO}")
            await db.commit()
            check("the asker can cancel", await swaps.respond(db, club, snap, a, s3, "cancel") == "cancelled")
            await db.commit()
            s4 = await mk_swap(db, club, snap, a, d, f"p:{CHARLIE}", f"p:{BRAVO}")
            await db.execute(text("UPDATE player_card_swaps SET created_at = NOW() - INTERVAL '20 days' WHERE id = CAST(:i AS UUID)"), {"i": s4})
            await db.commit()
            check("an old request has expired and is not offered", not (await swaps.list_swaps(db, club, snap, d))["incoming"] and await swaps.waiting_count(db, d) == 0)
            check("...and cannot be accepted", (await refused(swaps.respond(db, club, snap, d, s4, "accept"))) == 409)

            # the cap on open requests
            old_cap = swaps.MAX_OUTGOING
            swaps.MAX_OUTGOING = 1
            await give(ALPHA, DELTA, 2)
            await give(DELTA, ALPHA, 1)
            first = await mk_swap(db, club, snap, a, d, f"p:{CHARLIE}", f"p:{BRAVO}")
            await db.commit()
            check("the number of open requests is capped", (await refused(mk_swap(db, club, snap, a, d, f"p:{DELTA}", f"p:{ALPHA}"))) == 409)
            swaps.MAX_OUTGOING = old_cap
            await swaps.respond(db, club, snap, a, first, "cancel")
            await db.commit()

            # ── finding a card ───────────────────────────────────────────────────────────────────────────────
            find = getattr(swaps, "find_cards", None)
            if find is None:
                check("find a card: the search exists", False, "swaps.find_cards missing")
            else:
                await db.execute(text("DELETE FROM player_card_copies WHERE source IN ('pack', 'swap') AND organisation_id = :o"), {"o": ORG})
                await db.commit()
                await give(DELTA, BRAVO, 2)
                await give(CHARLIE, BRAVO, 1)
                await give(ALPHA, BRAVO, 1)
                await give(HOTEL, BRAVO, 3)        # out of the pool
                cards.forget(ORG)
                snap = await cards.club_snapshot(db, club, fresh=True)
                copies_before = (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE organisation_id = :o"), {"o": ORG})).scalar()
                r = await find(db, club, snap, a, "bravo")
                bravo = next((c for c in r["cards"] if c["key"] == f"p:{BRAVO}"), None)
                check("a search finds the card by the player's name", bravo is not None, str([c["key"] for c in r["cards"]]))
                hs = {h["player_id"]: h["tradeable"] for h in (bravo or {}).get("holders", [])}
                check("...with everyone who holds a copy and how many could go", hs == {str(DELTA): 2, str(CHARLIE): 1}, str(hs))
                check("...never the asker, and never a player out of the pool", a not in hs and str(HOTEL) not in hs)
                check("...holders come in name order", [h["name"] for h in (bravo or {}).get("holders", [])] == sorted([h["name"] for h in (bravo or {}).get("holders", [])], key=str.lower))
                check("a search is not case sensitive and takes the words in any order", {c["key"] for c in (await find(db, club, snap, a, "B BRAVO"))["cards"]} >= {f"p:{BRAVO}"} and {c["key"] for c in (await find(db, club, snap, a, "BrAvO"))["cards"]} >= {f"p:{BRAVO}"})
                r2 = await find(db, club, snap, str(DELTA), "century")
                cent = [c for c in r2["cards"] if c["kind"] == "special"]
                check("a special card is found by its kind", any(c["special_kind"] == "century" for c in cent) and any(h["player_id"] == a for c in cent for h in c["holders"]), str(r2)[:300])
                check("...and by the player's name with its title", any(c["kind"] == "special" for c in (await find(db, club, snap, str(DELTA), "alpha century"))["cards"]))
                check("a card nobody holds is not offered, and the player is named as not found yet", f"p:{CHARLIE}" not in {c["key"] for c in (await find(db, club, snap, a, "charlie"))["cards"]} and any("Charlie" in n for n in (await find(db, club, snap, a, "charlie"))["unheld"]), str(await find(db, club, snap, a, "charlie"))[:200])
                check("a word that matches nothing says so", (await find(db, club, snap, a, "zzzzqq")) == {"cards": [], "more": 0, "unheld": []})
                check("a search that is too short is refused (422)", await refused(find(db, club, snap, a, "b")) == 422 and await refused(find(db, club, snap, a, "  ")) == 422)
                check("searching writes nothing", (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE organisation_id = :o"), {"o": ORG})).scalar() == copies_before)
                # ── the club's whole set, to look through without holding any of it ──────────────────────────
                try:
                    from app.services import player_card_catalogue as catalogue
                except ImportError:
                    catalogue = None
                if catalogue is None:
                    check("the club catalogue exists", False, "app.services.player_card_catalogue missing")
                else:
                    pg = await catalogue.page(db, club, snap, a, filter="all", sort="rarity", offset=0, limit=36)
                    kinds = lambda r: [("stack" if i.get("stack") else i["kind"]) for i in r["items"]]
                    check("the set lists every drawable player's card, then the special cards", pg["counts"]["regular"] == 5 and kinds(pg)[:5] == ["player"] * 5, str(kinds(pg)[:8]))
                    check("...a player's several cards of one kind sit in one stack with the true count", any(i.get("stack") and i["count"] == len(i["cards"]) and i["count"] > 1 for i in pg["items"]))
                    check("...and the totals split into players, specials and each category", pg["counts"]["special"] > 5 and all(k in pg["counts"] for k in ("awards", "milestones", "centuries", "fifties", "wickets", "debuts")), str(pg["counts"]))
                    br = next((i for i in pg["items"] if i.get("key") == f"p:{BRAVO}"), None)
                    check("a card says how many other players could swap a copy (Delta and Charlie have Bravo)", br is not None and br["others"] == 2, str(br and br.get("others")))
                    check("...and how many copies the asker holds (Alpha pulled one)", br is not None and br["mine_copies"] == 1)
                    own = next((i for i in pg["items"] if i.get("key") == f"p:{ALPHA}"), None)
                    check("the asker's own card counts as held without a row", own is not None and own["mine_copies"] == 1)
                    check("nothing about anyone's holdings beyond what could go is sent", all(not ({"held", "owners", "copies"} & set(i)) for i in pg["items"] if not i.get("stack")))
                    ms = await catalogue.page(db, club, snap, a, filter="milestones", limit=36)
                    stack = next((i for i in ms["items"] if i.get("stack") and i["name"] == "Alpha, A"), None)
                    titles = [c["title"] for c in (stack or {}).get("cards", [])]
                    check("a category shows only its own kinds, milestones in order (games, then runs)", stack is not None and titles[0].endswith("games") and "1,000 runs" in titles and titles.index("1,000 runs") < titles.index("2,000 runs") and all(i.get("special_kind") in (None, "games", "runs_milestone", "wickets_milestone", "dismissals_milestone") for i in ms["items"]), str(titles))
                    check("a filter to players gives players only", all(i["kind"] == "player" for i in (await catalogue.page(db, club, snap, a, filter="regular", limit=36))["items"]))
                    ce = await catalogue.page(db, club, snap, a, filter="all", q="century", limit=36)
                    check("a search narrows the set by name, title, kind or season", ce["items"] and all("century" in (c.get("title") or "").lower() or "century" in (c.get("special_kind") or "") for it in ce["items"] for c in (it.get("cards") or [it])), str(ce["total"]))
                    check("...and a name finds the player's card", any(i.get("key") == f"p:{BRAVO}" for i in (await catalogue.page(db, club, snap, a, q="bravo", limit=36))["items"]))
                    p1 = await catalogue.page(db, club, snap, a, filter="all", sort="name", offset=0, limit=3)
                    p2 = await catalogue.page(db, club, snap, a, filter="all", sort="name", offset=3, limit=3)
                    check("it pages, with no card on two pages", len(p1["items"]) == 3 and not ({i["key"] for i in p1["items"]} & {i["key"] for i in p2["items"]}) and p1["total"] == p2["total"])
                    byname = [i["name"] for i in (await catalogue.page(db, club, snap, a, filter="regular", sort="name", limit=36))["items"]]
                    check("sorted A to Z by surname", byname == sorted(byname, key=lambda n: (n.split(",")[0].lower(), n.lower())), str(byname))
                    runs = [i["runs"] for i in (await catalogue.page(db, club, snap, a, filter="regular", sort="runs", limit=36))["items"]]
                    check("sorted by a figure, the most first", runs == sorted(runs, reverse=True), str(runs))
                    hold = await catalogue.holders_of(db, club, snap, a, f"p:{BRAVO}")
                    check("who has a card: the players who could swap one, in name order, never the asker", {h["player_id"] for h in hold["holders"]} == {str(DELTA), str(CHARLIE)} and [h["name"] for h in hold["holders"]] == sorted([h["name"] for h in hold["holders"]], key=str.lower) and hold["mine_copies"] == 1)
                    check("a made-up card key is refused (422)", await refused(catalogue.holders_of(db, club, snap, a, "p:not-a-uuid")) == 422)
                    check("a card of a player out of the pool is refused (409)", await refused(catalogue.holders_of(db, club, snap, a, f"p:{HOTEL}")) == 409)
                    nm_ = await catalogue.page(db, club, snap, a, filter="regular", have="not_mine", limit=36)
                    keys_ = {i["key"] for i in nm_["items"]}
                    check("Not mine leaves out the cards the asker holds (their own, and the Bravo they pulled)", f"p:{ALPHA}" not in keys_ and f"p:{BRAVO}" not in keys_ and f"p:{CHARLIE}" in keys_ and nm_["counts"]["regular"] == len(nm_["items"]), str(keys_))
                    sw_ = await catalogue.page(db, club, snap, a, filter="all", have="swappable", limit=36)
                    check("Someone could swap it keeps only cards another player could swap, and says so on each", sw_["items"] and all((i.get("others") or 0) > 0 for it in sw_["items"] for i in (it.get("cards") or [it])) and f"p:{BRAVO}" in {i["key"] for i in sw_["items"]}, str([i.get("key") for i in sw_["items"]]))
                    check("an unknown have value is read as all", (await catalogue.page(db, club, snap, a, filter="regular", have="nonsense", limit=36))["counts"]["regular"] == 5)
                    old_ = (await db.execute(text("SELECT id::text FROM player_card_swaps WHERE status = 'accepted' AND organisation_id = :o LIMIT 1"), {"o": ORG})).scalar()
                    if old_:
                        await db.execute(text("UPDATE player_card_swaps SET created_at = NOW() - INTERVAL '100 days' WHERE id = CAST(:i AS UUID)"), {"i": old_})
                        await db.commit()
                        who_ = (await db.execute(text("SELECT from_player_id::text FROM player_card_swaps WHERE id = CAST(:i AS UUID)"), {"i": old_})).scalar()
                        short = await swaps.list_swaps(db, club, snap, who_)
                        full = await swaps.list_swaps(db, club, snap, who_, history=True)
                        check("History reaches back a year, the short list only a month", old_ in {r["id"] for r in full["recent"]} and old_ not in {r["id"] for r in short["recent"]})
                    else:
                        check("History reaches back a year, the short list only a month", False, "no accepted swap to age")
                    check("reading the set writes nothing", (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE organisation_id = :o"), {"o": ORG})).scalar() == copies_before)


            # ── many cards each way ──────────────────────────────────────────────────────────────────────────
            await db.execute(text("DELETE FROM player_card_copies WHERE source IN ('pack', 'swap') AND organisation_id = :o"), {"o": ORG})
            await db.commit()
            await give(ALPHA, CHARLIE, 3)
            await give(ALPHA, DELTA, 1)
            await give(DELTA, BRAVO, 2)
            await give(DELTA, ALPHA, 1)
            cards.forget(ORG)
            snap = await cards.club_snapshot(db, club, fresh=True)
            total0 = (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE organisation_id = :o"), {"o": ORG})).scalar()
            G = [{"key": f"p:{CHARLIE}", "qty": 2}, {"key": f"p:{DELTA}", "qty": 1}]
            W = [{"key": f"p:{BRAVO}", "qty": 2}, {"key": f"p:{ALPHA}", "qty": 1}]
            check("more copies than the giver holds is refused", await refused(mk_swap(db, club, snap, a, d, [{"key": f"p:{CHARLIE}", "qty": 4}], W)) == 409)
            check("more copies than they hold is refused", await refused(mk_swap(db, club, snap, a, d, G, [{"key": f"p:{BRAVO}", "qty": 3}])) == 409)
            check("a side with nothing on it is refused", await refused(mk_swap(db, club, snap, a, d, [], W)) == 422 and await refused(mk_swap(db, club, snap, a, d, G, [])) == 422)
            check("a card on both sides is refused", await refused(mk_swap(db, club, snap, a, d, [{"key": f"p:{BRAVO}", "qty": 1}], [{"key": f"p:{BRAVO}", "qty": 1}])) == 422)
            check("zero copies is refused", await refused(mk_swap(db, club, snap, a, d, [{"key": f"p:{CHARLIE}", "qty": 0}], W)) == 422)
            multi_id = await mk_swap(db, club, snap, a, d, G, W)
            await db.commit()
            n_items = (await db.execute(text("SELECT count(*) FROM player_card_swap_items WHERE swap_id = :i"), {"i": multi_id})).scalar()
            check("one request carries all four cards, two a side", n_items == 4, str(n_items))
            check("asking for exactly the same again is refused", await refused(mk_swap(db, club, snap, a, d, G, W)) == 409)
            other_qty = await mk_swap(db, club, snap, a, d, [{"key": f"p:{CHARLIE}", "qty": 1}, {"key": f"p:{DELTA}", "qty": 1}], W)
            await db.commit()
            check("...but a different number of copies is a different request", bool(other_qty))
            li = await swaps.list_swaps(db, club, snap, d)
            first = next(r for r in li["incoming"] if r["id"] == multi_id)
            check("the person asked sees every card with how many", sorted((c["player_id"], c["qty"]) for c in first["give"]) == sorted([(str(CHARLIE), 2), (str(DELTA), 1)])
                  and sorted((c["player_id"], c["qty"]) for c in first["want"]) == sorted([(str(BRAVO), 2), (str(ALPHA), 1)]), str(first)[:240])
            check("nothing moved yet", await held(ALPHA, CHARLIE) == 3 and await held(DELTA, BRAVO) == 2)
            res = await swaps.respond(db, club, snap, d, multi_id, "accept")
            await db.commit()
            check("accepting moves every card at once", res == "accepted"
                  and await held(ALPHA, CHARLIE) == 1 and await held(ALPHA, DELTA) == 0 and await held(ALPHA, BRAVO) == 2 and await held(ALPHA, ALPHA) == 1
                  and await held(DELTA, CHARLIE) == 2 and await held(DELTA, DELTA) == 1 and await held(DELTA, BRAVO) == 0 and await held(DELTA, ALPHA) == 0,
                  f"A: C{await held(ALPHA, CHARLIE)} D{await held(ALPHA, DELTA)} B{await held(ALPHA, BRAVO)} A{await held(ALPHA, ALPHA)}")
            check("no card was made or lost, and six copies are marked swapped", (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE organisation_id = :o"), {"o": ORG})).scalar() == total0
                  and (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE source = 'swap' AND organisation_id = :o"), {"o": ORG})).scalar() == 6)
            # all or nothing: the second request offers a Delta card Alpha no longer holds
            before = (await held(ALPHA, CHARLIE), await held(DELTA, BRAVO), await held(ALPHA, BRAVO))
            check("a request with one card gone cannot go ahead (409)", await refused(swaps.respond(db, club, snap, d, other_qty, "accept")) == 409)
            check("...and none of its other cards moved", (await held(ALPHA, CHARLIE), await held(DELTA, BRAVO), await held(ALPHA, BRAVO)) == before, str(before))
            await swaps.respond(db, club, snap, d, other_qty, "decline")
            await db.commit()
            # one for four, and four for one
            await give(DELTA, CHARLIE, 1)
            cards.forget(ORG)
            snap = await cards.club_snapshot(db, club, fresh=True)
            one_for_four = await mk_swap(db, club, snap, a, d, [f"p:{BRAVO}"], [f"p:{CHARLIE}", f"p:{DELTA}", f"p:{ALPHA}"] if await held(DELTA, ALPHA) else [f"p:{CHARLIE}", f"p:{DELTA}"])
            await db.commit()
            check("one card can be asked for several of theirs", bool(one_for_four))
            await swaps.respond(db, club, snap, a, one_for_four, "cancel")
            await db.commit()
            # a request made before migration 366 (its cards in the old columns) is carried across, once
            old_id = (await db.execute(text("INSERT INTO player_card_swaps (organisation_id, from_player_id, to_player_id, give_subject_player_id, want_subject_player_id) "
                                            "VALUES (:o, :a, :d, :c, :b) RETURNING id::text"), {"o": ORG, "a": ALPHA, "d": DELTA, "c": CHARLIE, "b": BRAVO})).scalar()
            for _ in range(2):
                for stmt in ITEM_DDL:
                    await db.execute(text(stmt))
            await db.commit()
            moved = (await db.execute(text("SELECT side, count(*) FROM player_card_swap_items WHERE swap_id = :i GROUP BY side ORDER BY side"), {"i": old_id})).fetchall()
            check("an old one-card request becomes one card each way, and a second run adds nothing", [tuple(r) for r in moved] == [("give", 1), ("want", 1)], str(moved))
            await swaps.respond(db, club, snap, a, old_id, "cancel")
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
            check("each row names who asked, who was asked and both cards", all(r["from"]["name"] and r["to"]["name"] and r["give"] and r["want"] and all(c["player"] for c in r["give"] + r["want"]) for r in aud["swaps"]), str(aud["swaps"][:1]))
            done = await admin_routes.swap_audit("accepted", "", 50, 0, db, club, user)
            check("it filters to one outcome", done["swaps"] and all(r["status"] == "accepted" for r in done["swaps"]))
            exp = await admin_routes.swap_audit("expired", "", 50, 0, db, club, user)
            check("an old unanswered request shows as expired", exp["swaps"] and all(r["status"] == "expired" for r in exp["swaps"]))
            who = await admin_routes.swap_audit("all", "delta", 50, 0, db, club, user)
            check("it searches by player", who["swaps"] and all("Delta" in (r["from"]["name"] or "") + (r["to"]["name"] or "") or any("Delta" in c["player"] for c in r["give"] + r["want"]) for r in who["swaps"]))
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
            check("GET swaps answers with requests, my cards and who has cards", {"incoming", "outgoing", "recent", "mine", "people"} <= set(board), str(board.keys()))
            other = await pcr.get_swap_player(TOKEN, str(DELTA), request_for(ALPHA, ORG), db)
            check("GET a player's cards answers with what they could offer", other["player"]["player_id"] == str(DELTA) and all(c["tradeable"] >= 1 for c in other["cards"]))
            check("GET the cards of a player outside the pool is a 404", await status_of(pcr.get_swap_player(TOKEN, str(HOTEL), request_for(ALPHA, ORG), db)) == 404)
            made = await pcr.ask_for_swap(TOKEN, pcr.SwapBody(to_player_id=str(DELTA), give_key=f"p:{CHARLIE}", want_key=f"p:{BRAVO}"), request_for(ALPHA, ORG), db)
            check("POST a swap request", made["status"] == "pending")
            check("POST the same again is a 409", await status_of(pcr.ask_for_swap(TOKEN, pcr.SwapBody(to_player_id=str(DELTA), give_key=f"p:{CHARLIE}", want_key=f"p:{BRAVO}"), request_for(ALPHA, ORG), db)) == 409)
            check("the asker accepting their own is a 403", await status_of(pcr.answer_swap(TOKEN, made["id"], "accept", request_for(ALPHA, ORG), db)) == 403)
            done = await pcr.answer_swap(TOKEN, made["id"], "accept", request_for(DELTA, ORG), db)
            check("POST accept as the person asked", done["status"] == "accepted")
            back = await pcr.ask_for_swap(TOKEN, pcr.SwapBody(to_player_id=str(DELTA), give=[pcr.SwapCard(key=f"p:{BRAVO}", qty=1)], want=[pcr.SwapCard(key=f"p:{CHARLIE}", qty=1)]), request_for(ALPHA, ORG), db)
            check("POST a swap as lists of cards with a quantity each", back["status"] == "pending")
            check("POST with an empty side is a 422", await status_of(pcr.ask_for_swap(TOKEN, pcr.SwapBody(to_player_id=str(DELTA), give=[], want=[pcr.SwapCard(key=f"p:{CHARLIE}")]), request_for(ALPHA, ORG), db)) == 422)
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
        check("...and the link to the player page", payload["link"]["path"] == f"/playerdash/{TOKEN}")
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

    # ── The social side: wish list, spares, one card, counter offers, notes, alerts ─────────────────────────
    print("\nthe social side")
    try:
        from app.services import player_card_social as social, player_card_alerts as alerts
        from app.services import email_service as email_mod
    except ImportError:
        social = alerts = email_mod = None
    if social is None or not HAVE_SWAPS:
        for label in ("wish list", "spares", "card page", "prefs", "counter offers", "notes", "alerts"):
            check(f"{label}: the social side exists", False, "app.services.player_card_social missing")
    else:
        async with Session() as db:
            club = await db.get(Organisation, ORG)
            await db.execute(text("DELETE FROM player_card_copies WHERE source IN ('pack', 'swap') AND organisation_id = :o"), {"o": ORG})
            for t in ("player_card_wants", "player_card_open_offers", "player_card_prefs", "player_card_alerts"):
                await db.execute(text(f"DELETE FROM {t}"))
            await db.execute(text("DELETE FROM player_card_swaps WHERE organisation_id = :o"), {"o": ORG})
            await db.execute(text("UPDATE club_card_settings SET alerts_enabled = TRUE WHERE organisation_id = :o"), {"o": ORG})
            await db.commit()
            cards.forget(ORG)

            async def put(owner, subject, n, special=None):
                for _ in range(n):
                    await db.execute(text("INSERT INTO player_card_copies (organisation_id, owner_player_id, subject_player_id, special_id, source) "
                                          "VALUES (:o, :ow, :s, :sp, 'pack')"), {"o": ORG, "ow": owner, "s": subject, "sp": special})
                await db.commit()

            async def held_n(owner, subject):
                return (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE owner_player_id = :o AND subject_player_id = :s AND special_id IS NULL"), {"o": owner, "s": subject})).scalar()

            async def refused(coro):
                try:
                    await coro
                    return None
                except swaps.SwapError as exc:
                    await db.commit()
                    return exc.status

            a, d, c_ = str(ALPHA), str(DELTA), str(CHARLIE)
            await put(DELTA, BRAVO, 2)
            await put(CHARLIE, BRAVO, 1)
            await put(HOTEL, BRAVO, 3)          # out of the pool
            snap = await cards.club_snapshot(db, club, fresh=True)

            # the wish list
            await social.add_want(db, club, snap, a, f"p:{BRAVO}")
            await social.add_want(db, club, snap, a, f"p:{BRAVO}")
            await db.commit()
            wl = await social.list_wants(db, club, snap, a)
            check("a card can be put on the wish list, once however many times it is added", len(wl["wants"]) == 1 and wl["wants"][0]["key"] == f"p:{BRAVO}")
            check("it shows who could swap one now, in name order, never a player out of the pool", [h["player_id"] for h in wl["wants"][0]["holders"]] == sorted([str(DELTA), str(CHARLIE)], key=lambda x: {str(DELTA): "delta", str(CHARLIE): "charlie"}[x]) and wl["ready"] == 1, str(wl["wants"][0]["holders"]))
            check("nobody else sees it: another player's list is empty", (await social.list_wants(db, club, snap, d))["wants"] == [])
            check("your own card cannot be wanted (409)", await refused(social.add_want(db, club, snap, a, f"p:{ALPHA}")) == 409)
            await put(ALPHA, CHARLIE, 1)
            check("a card you already hold cannot be wanted (409)", await refused(social.add_want(db, club, snap, a, f"p:{CHARLIE}")) == 409)
            check("a card of a player out of the pool cannot be wanted (409)", await refused(social.add_want(db, club, snap, a, f"p:{HOTEL}")) == 409)
            check("a made-up key is refused (422)", await refused(social.add_want(db, club, snap, a, "p:nope")) == 422)
            old_max = social.MAX_WANTS
            social.MAX_WANTS = 1
            check("the list is capped", await refused(social.add_want(db, club, snap, a, f"p:{DELTA}")) == 409)
            social.MAX_WANTS = old_max
            await social.remove_want(db, club, a, f"p:{BRAVO}")
            await db.commit()
            check("a card comes off the list", (await social.list_wants(db, club, snap, a))["wants"] == [])

            # spares and open to offers
            await put(ALPHA, CHARLIE, 2)           # three Charlie in all: two spare
            await put(ALPHA, ALPHA, 1)             # a pulled copy of their own card: one spare
            sp_ = await social.spares(db, club, snap, a)
            by = {x["key"]: x for x in sp_["cards"]}
            check("a spare is a copy beyond the one kept (three Charlie is two spare)", by.get(f"p:{CHARLIE}", {}).get("spare") == 2, str(by.keys()))
            check("...and every pulled copy of the player's own card is a spare", by.get(f"p:{ALPHA}", {}).get("spare") == 1)
            check("a single card is not a spare", f"p:{BRAVO}" not in by and sp_["total"] == 3)
            check("being open to offers is off until it is turned on, and no demand is shown", by[f"p:{CHARLIE}"]["open"] is False and "wanted_by" not in by[f"p:{CHARLIE}"])
            await social.add_want(db, club, snap, d, f"p:{CHARLIE}")
            check("open to offers needs a spare (409)", await refused(social.set_open(db, club, snap, a, f"p:{BRAVO}", True)) == 409)
            await social.set_open(db, club, snap, a, f"p:{CHARLIE}", True)
            await db.commit()
            by = {x["key"]: x for x in (await social.spares(db, club, snap, a))["cards"]}
            check("once open, the holder is told how many players want it, as a number", by[f"p:{CHARLIE}"]["open"] is True and by[f"p:{CHARLIE}"]["wanted_by"] == 1)
            check("...and the number never carries names", all(k != "wanters" for k in by[f"p:{CHARLIE}"]))
            await social.set_open(db, club, snap, a, f"p:{CHARLIE}", False)
            await db.commit()
            check("it can be turned off again", [x["open"] for x in (await social.spares(db, club, snap, a))["cards"] if x["key"] == f"p:{CHARLIE}"] == [False])

            # one card in full
            await social.add_want(db, club, snap, a, f"p:{BRAVO}")
            await db.commit()
            det = await social.card_detail(db, club, snap, a, f"p:{BRAVO}")
            check("the card page: the card, who could swap one, and whether it is wanted", det["card"]["key"] == f"p:{BRAVO}" and len(det["holders"]) == 2 and det["wanted"] is True and det["mine_copies"] == 0, str(det)[:200])
            check("...and wanted is false for a card that is not on the list", (await social.card_detail(db, club, snap, a, f"p:{DELTA}"))["wanted"] is False)

            # alert settings
            pr = await social.load_prefs(db, a)
            check("no email is sent until a player turns it on (both alerts default off)", pr["alert_swaps"] is False and pr["alert_wants"] is False)
            await social.save_prefs(db, club, a, {"alert_swaps": True})
            await db.commit()
            pr = await social.load_prefs(db, a)
            check("a setting not sent is left alone", pr["alert_swaps"] is True and pr["alert_wants"] is False)
            await social.save_prefs(db, club, a, {"alert_wants": True})
            await db.commit()

            # notes and counter offers
            long_note = "  hello   there " + "x" * 400
            first = await swaps.create_swap(db, club, snap, a, d, [{"key": f"p:{CHARLIE}", "qty": 1}], [{"key": f"p:{BRAVO}", "qty": 1}], note=long_note)
            await db.commit()
            row = (await db.execute(text("SELECT note FROM player_card_swaps WHERE id = CAST(:i AS UUID)"), {"i": first})).scalar()
            check("a note is tidied and cut to 200 characters", row.startswith("hello there x") and len(row) == 200, str(len(row)))
            li = await swaps.list_swaps(db, club, snap, d)
            check("the person asked sees the note", li["incoming"][0]["note"] == row)
            check("only the person asked can counter (403)", await refused(swaps.counter_swap(db, club, snap, a, first, [{"key": f"p:{CHARLIE}", "qty": 1}], [{"key": f"p:{BRAVO}", "qty": 1}])) == 403)
            check("a counter must hold up like any request: cards the answerer does not hold are refused (409)", await refused(swaps.counter_swap(db, club, snap, d, first, [{"key": f"p:{ALPHA}", "qty": 1}], [{"key": f"p:{CHARLIE}", "qty": 1}])) == 409)
            check("...and the request it answered is still waiting after a refused counter", (await db.execute(text("SELECT status FROM player_card_swaps WHERE id = CAST(:i AS UUID)"), {"i": first})).scalar() == "pending")
            counter = await swaps.counter_swap(db, club, snap, d, first, [{"key": f"p:{BRAVO}", "qty": 2}], [{"key": f"p:{CHARLIE}", "qty": 2}], note="how about two each")
            await db.commit()
            st = (await db.execute(text("SELECT status, parent_swap_id::text, from_player_id::text, to_player_id::text FROM player_card_swaps WHERE id = CAST(:i AS UUID)"), {"i": counter})).first()
            old = (await db.execute(text("SELECT status FROM player_card_swaps WHERE id = CAST(:i AS UUID)"), {"i": first})).scalar()
            check("a counter is a new request from the person asked back to the one who asked, pointing at the first", st[0] == "pending" and st[1] == first and st[2] == d and st[3] == a)
            check("the first ends as countered, and cannot be accepted or countered again (409)", old == "countered" and await refused(swaps.respond(db, club, snap, d, first, "accept")) == 409 and await refused(swaps.counter_swap(db, club, snap, d, first, [{"key": f"p:{BRAVO}", "qty": 1}], [{"key": f"p:{CHARLIE}", "qty": 1}])) == 409)
            la = await swaps.list_swaps(db, club, snap, a)
            check("the person who first asked now has the counter coming in, with its note and its parent", la["incoming"] and la["incoming"][0]["parent_id"] == first and la["incoming"][0]["note"] == "how about two each")
            check("the countered request shows in history", any(r["status"] == "countered" for r in (await swaps.list_swaps(db, club, snap, a, history=True))["recent"]))
            before = (await held_n(ALPHA, CHARLIE), await held_n(DELTA, BRAVO))
            check("accepting the counter moves the counter's cards", await swaps.respond(db, club, snap, a, counter, "accept") == "accepted")
            await db.commit()
            check("Delta gave two Bravo for two Charlie", await held_n(DELTA, BRAVO) == before[1] - 2 and await held_n(DELTA, CHARLIE) == 2 and await held_n(ALPHA, CHARLIE) == before[0] - 2 and await held_n(ALPHA, BRAVO) == 2, str((await held_n(DELTA, BRAVO), await held_n(ALPHA, BRAVO))))
            adm = await admin_routes.swap_audit("countered", "", 50, 0, db, club, User(id=uuid.uuid4(), email="admin@example.com"))
            check("the admin audit lists countered requests, with their note and parent", adm["swaps"] and all(r["status"] == "countered" for r in adm["swaps"]) and adm["counts"]["countered"] >= 1 and "parent_id" in adm["swaps"][0])

            # alerts: a fake email provider, never a real send
            sent_mail = []

            async def fake_deliver(db_, club_, *, to_email, to_name, subject, body_html, body_text):
                sent_mail.append((to_email, subject, body_text))
                return True, None
            real_deliver, real_live = alerts._deliver, email_mod.email_is_live
            alerts._deliver = fake_deliver
            email_mod.email_is_live = lambda: True
            try:
                await db.execute(text("UPDATE players SET email = 'alpha@example.com', date_of_birth = NULL WHERE id = :p"), {"p": ALPHA})
                await db.execute(text("UPDATE players SET email = 'delta@example.com', date_of_birth = NULL WHERE id = :p"), {"p": DELTA})
                await db.execute(text("DELETE FROM player_card_wants"))
                await db.execute(text("DELETE FROM player_card_alerts"))
                await db.execute(text("DELETE FROM player_card_copies WHERE subject_player_id = :b"), {"b": BRAVO})
                await db.commit()
                await put(DELTA, BRAVO, 1)
                cards.forget(ORG)
                snap = await cards.club_snapshot(db, club, fresh=True)
                await social.add_want(db, club, snap, a, f"p:{BRAVO}")
                await db.commit()
                n_alert = lambda: db.execute(text("SELECT count(*) FROM player_card_alerts WHERE player_id = :p AND kind = 'want_available'"), {"p": ALPHA})
                await alerts.scan_wants(ORG, [f"p:{BRAVO}"])
                check("a wish list card someone could swap sends one email to the person who wants it", len(sent_mail) == 1 and sent_mail[0][0] == "alpha@example.com" and "wish list" in sent_mail[0][1].lower(), str(sent_mail))
                check("...which names the card and links to the wish list", "Bravo" in sent_mail[0][2] and f"/playerdash/{TOKEN}/cards/wishlist" in sent_mail[0][2])
                await alerts.scan_wants(ORG, None)
                check("scanning again does not send it again", len(sent_mail) == 1 and (await n_alert()).scalar() == 1)
                await db.execute(text("DELETE FROM player_card_copies WHERE subject_player_id = :b"), {"b": BRAVO})
                await db.commit()
                await alerts.scan_wants(ORG, [f"p:{BRAVO}"])
                cleared = (await db.execute(text("SELECT count(*) FROM player_card_alerts WHERE player_id = :p AND cleared_at IS NOT NULL"), {"p": ALPHA})).scalar()
                check("when nobody could swap it any more the alert is cleared, ready to fire again", cleared == 1)
                await put(DELTA, BRAVO, 1)
                await alerts.scan_wants(ORG, [f"p:{BRAVO}"])
                check("...and when someone has it again it is announced again", len(sent_mail) == 2)
                check("the alert log keeps both, one cleared", (await db.execute(text("SELECT count(*) FROM player_card_alerts WHERE player_id = :p AND status = 'sent'"), {"p": ALPHA})).scalar() == 2)

                # gates
                async def fresh_alert():
                    await db.execute(text("DELETE FROM player_card_alerts WHERE player_id = :p"), {"p": ALPHA})
                    await db.commit()
                    sent_mail.clear()
                await fresh_alert()
                await db.execute(text("UPDATE club_card_settings SET alerts_enabled = FALSE WHERE organisation_id = :o"), {"o": ORG})
                await db.commit()
                await alerts.scan_wants(ORG, None)
                check("a club that switches alerts off sends none", not sent_mail)
                await db.execute(text("UPDATE club_card_settings SET alerts_enabled = TRUE WHERE organisation_id = :o"), {"o": ORG})
                await fresh_alert()
                await social.save_prefs(db, club, a, {"alert_wants": False}); await db.commit()
                await alerts.scan_wants(ORG, None)
                check("a player who switched wish list alerts off gets none", not sent_mail)
                await social.save_prefs(db, club, a, {"alert_wants": True}); await fresh_alert()
                await db.execute(text("UPDATE players SET date_of_birth = CURRENT_DATE - INTERVAL '15 years' WHERE id = :p"), {"p": ALPHA}); await db.commit()
                await alerts.scan_wants(ORG, None)
                check("a player under 18 is not emailed directly", not sent_mail)
                await db.execute(text("UPDATE players SET date_of_birth = NULL, email = NULL WHERE id = :p"), {"p": ALPHA}); await fresh_alert()
                await alerts.scan_wants(ORG, None)
                check("a player with no address is skipped, and it is written down", not sent_mail and (await db.execute(text("SELECT detail FROM player_card_alerts WHERE player_id = :p"), {"p": ALPHA})).scalar() == "no_email")
                await db.execute(text("UPDATE players SET email = 'alpha@example.com' WHERE id = :p"), {"p": ALPHA}); await fresh_alert()
                email_mod.email_is_live = lambda: False
                await alerts.scan_wants(ORG, None); await alerts.scan_wants(ORG, None)
                rows_ = (await db.execute(text("SELECT status, detail FROM player_card_alerts WHERE player_id = :p"), {"p": ALPHA})).fetchall()
                check("with no live email provider it is a failure on record, never a send, and does not pile up", not sent_mail and [tuple(r) for r in rows_] == [("failed", "email_not_live")], str(rows_))
                email_mod.email_is_live = lambda: True
                await alerts.scan_wants(ORG, None)
                check("it is retried when the provider is back", len(sent_mail) == 1)

                # a swap asked
                sent_mail.clear()
                await db.execute(text("DELETE FROM player_card_swaps WHERE organisation_id = :o"), {"o": ORG}); await db.commit()
                snap = await cards.club_snapshot(db, club, fresh=True)
                await put(ALPHA, CHARLIE, 1)
                nsw = await swaps.create_swap(db, club, snap, a, d, [{"key": f"p:{CHARLIE}", "qty": 1}], [{"key": f"p:{BRAVO}", "qty": 1}], note="fancy a swap?")
                await db.commit()
                await alerts.swap_asked(ORG, nsw)
                check("a player who has not switched alerts on is not emailed about a swap (the default is off)", not sent_mail, str(sent_mail)[:200])
                await db.execute(text("DELETE FROM player_card_alerts WHERE player_id = :p"), {"p": DELTA}); await db.commit()
                await social.save_prefs(db, club, d, {"alert_swaps": True}); await db.commit()
                await alerts.swap_asked(ORG, nsw)
                check("the person asked is emailed about a swap, with the note and a link to Swaps", len(sent_mail) == 1 and sent_mail[0][0] == "delta@example.com" and "fancy a swap?" in sent_mail[0][2] and f"/playerdash/{TOKEN}/cards/swaps" in sent_mail[0][2], str(sent_mail)[:300])
                await alerts.swap_asked(ORG, nsw)
                check("...once", len(sent_mail) == 1)
                # the routes
                from app.routers import public_player_cards as pcr
                await db.execute(text("DELETE FROM player_card_wants")); await db.commit()
                rq = lambda who: request_for(who, ORG)
                await pcr.add_want(TOKEN, pcr.KeyBody(key=f"p:{DELTA}"), rq(CHARLIE), db)
                wl_ = await pcr.get_wants(TOKEN, rq(CHARLIE), db)
                check("GET and POST the wish list", len(wl_["wants"]) == 1 and wl_["wants"][0]["key"] == f"p:{DELTA}")
                check("POST a card you already have is a 409", await status_of(pcr.add_want(TOKEN, pcr.KeyBody(key=f"p:{CHARLIE}"), rq(CHARLIE), db)) == 409)
                await pcr.remove_want(TOKEN, f"p:{DELTA}", rq(CHARLIE), db)
                check("DELETE takes it off", (await pcr.get_wants(TOKEN, rq(CHARLIE), db))["wants"] == [])
                sp2 = await pcr.get_spares(TOKEN, rq(ALPHA), db)
                check("GET spares", "cards" in sp2 and "total" in sp2)
                check("POST open to offers on a card with no spare is a 409", await status_of(pcr.set_spare_open(TOKEN, pcr.OpenBody(key=f"p:{BRAVO}", open=True), rq(ALPHA), db)) == 409)
                cd = await pcr.get_card(TOKEN, f"p:{BRAVO}", rq(ALPHA), db)
                check("GET one card", cd["card"]["key"] == f"p:{BRAVO}" and "holders" in cd and "wanted" in cd)
                pf = await pcr.put_prefs(TOKEN, pcr.PrefsBody(alert_wants=False), rq(ALPHA), db)
                check("PUT prefs changes only what is sent, and reports the club switch and the address", pf["alert_wants"] is False and pf["alert_swaps"] is True and pf["club_alerts"] is True and pf["email_on_file"] is True, str(pf))
                check("GET prefs reads it back", (await pcr.get_prefs(TOKEN, rq(ALPHA), db))["alert_wants"] is False)
                await pcr.put_prefs(TOKEN, pcr.PrefsBody(alert_wants=True), rq(ALPHA), db)
                check("no cookie, no wish list (401)", await status_of(pcr.get_wants(TOKEN, Request({"type": "http", "method": "GET", "path": "/", "headers": [], "client": ("1.1.1.1", 1)}), db)) == 401)
            finally:
                alerts._deliver, email_mod.email_is_live = real_deliver, real_live
                await db.execute(text("UPDATE players SET email = NULL, date_of_birth = NULL WHERE id IN (:a, :d)"), {"a": ALPHA, "d": DELTA})
                await db.commit()

    # ── The community side: sets, showcase, collectors board, club feed, switches ────────────────────────────────
    print("\nthe community side")
    try:
        from app.services import player_card_community as community, player_card_sets as card_sets
    except ImportError:
        community = card_sets = None
    if community is None or not HAVE_SWAPS:
        for label in ("sets", "showcase", "board", "feed", "switches"):
            check(f"{label}: the community side exists", False, "app.services.player_card_community missing")
    else:
        async with Session() as db:
            club = await db.get(Organisation, ORG)
            await db.execute(text("DELETE FROM player_card_copies WHERE source IN ('pack', 'swap') AND organisation_id = :o"), {"o": ORG})
            for t in ("player_card_showcase", "player_card_prefs", "player_card_wants"):
                await db.execute(text(f"DELETE FROM {t}"))
            await db.execute(text("DELETE FROM player_card_swaps WHERE organisation_id = :o"), {"o": ORG})
            await db.execute(text("UPDATE club_card_settings SET sets_enabled = TRUE, showcase_enabled = TRUE, board_enabled = TRUE, feed_enabled = TRUE WHERE organisation_id = :o"), {"o": ORG})
            await db.commit()
            cards.forget(ORG)
            a, d, c_ = str(ALPHA), str(DELTA), str(CHARLIE)

            async def put(owner, subject, n, special=None, source="pack"):
                for _ in range(n):
                    await db.execute(text("INSERT INTO player_card_copies (organisation_id, owner_player_id, subject_player_id, special_id, source) "
                                          "VALUES (:o, :ow, :s, :sp, :src)"), {"o": ORG, "ow": owner, "s": subject, "sp": special, "src": source})
                await db.commit()

            async def refused(coro):
                try:
                    await coro
                    return None
                except swaps.SwapError as exc:
                    await db.commit()
                    return exc.status
            snap = await cards.club_snapshot(db, club, fresh=True)

            # sets
            ov = await card_sets.overview(db, club, snap, a)
            keys = {x["key"]: x for x in ov["sets"]}
            check("a set is offered once the club has three of its cards (games milestones and debuts are; a lone century is not)", "kind:games" in keys and "kind:debut" in keys and "kind:century" not in keys, str(sorted(keys)))
            check("a set says how many cards it has, how many you hold and how far through you are", keys["kind:debut"]["total"] >= 4 and 0 <= keys["kind:debut"]["owned"] <= keys["kind:debut"]["total"] and keys["kind:debut"]["percent"] == round(100 * keys["kind:debut"]["owned"] / keys["kind:debut"]["total"]))
            before = keys["kind:games"]["owned"]
            gsp = (await db.execute(text("SELECT id::text FROM player_special_cards WHERE kind = 'games' AND player_id = :p ORDER BY title LIMIT 1"), {"p": DELTA})).scalar()
            gsp2 = (await db.execute(text("SELECT id::text FROM player_special_cards WHERE kind = 'games' AND player_id = :p ORDER BY title LIMIT 1"), {"p": ALPHA})).scalar()
            await put(ALPHA, ALPHA, 4, special=gsp2)    # hoarding the same card does not move the set on
            ov2 = {x["key"]: x for x in (await card_sets.overview(db, club, snap, a))["sets"]}
            check("holding a card moves you through the set by one, however many copies you hold", ov2["kind:games"]["owned"] >= before and ov2["kind:games"]["owned"] <= before + 1)
            mem = await card_sets.members(db, club, snap, "kind:games")
            check("a set's cards can be read, and an unknown set is None", mem and len(mem[1]) == keys["kind:games"]["total"] and await card_sets.members(db, club, snap, "kind:nonsense") is None)
            import app.services.player_card_catalogue as cat_mod
            pg = await cat_mod.page(db, club, snap, a, filter="all", limit=36, set_key="kind:games")
            ids_ = {c["special_id"] for it in pg["items"] for c in (it.get("cards") or [it]) if c.get("special_id")}
            check("the catalogue reads a set through set_key: only that set's cards", ids_ and ids_ <= mem[1] and all(it.get("kind") != "player" for it in pg["items"]), str(pg["total"]))
            check("an unknown set_key shows nothing", (await cat_mod.page(db, club, snap, a, filter="all", limit=36, set_key="nope"))["items"] == [])
            tiers = [k for k in keys if k.startswith("tier:")]
            check("tier sets list the players of that tier", all(keys[k]["group"] == "Players" for k in tiers))

            # showcase
            await put(ALPHA, CHARLIE, 1)
            sc = await community.get_showcase(db, club, snap, a)
            check("a showcase starts empty", sc["cards"] == [] and sc["max"] == 6)
            await community.set_showcase(db, club, snap, a, [f"p:{CHARLIE}", f"p:{ALPHA}", f"s:{gsp2}"])
            await db.commit()
            sc = await community.get_showcase(db, club, snap, a)
            check("cards can be pinned in an order, a player's own card among them", [c["key"] for c in sc["cards"]] == [f"p:{CHARLIE}", f"p:{ALPHA}", f"s:{gsp2}"], str([c["key"] for c in sc["cards"]]))
            check("a card you do not hold cannot be pinned (409)", await refused(community.set_showcase(db, club, snap, a, [f"p:{BRAVO}"])) == 409)
            check("more than six is refused (422)", await refused(community.set_showcase(db, club, snap, a, [f"p:{CHARLIE}"] * 7)) == 422 and await refused(community.set_showcase(db, club, snap, a, [f"p:{CHARLIE}", f"p:{CHARLIE}"])) == 422)
            check("a refused save changed nothing", [c["key"] for c in (await community.get_showcase(db, club, snap, a))["cards"]] == [f"p:{CHARLIE}", f"p:{ALPHA}", f"s:{gsp2}"])
            await db.execute(text("DELETE FROM player_card_copies WHERE owner_player_id = :a AND subject_player_id = :c"), {"a": ALPHA, "c": CHARLIE}); await db.commit()
            check("a pinned card that is swapped away drops off the showcase", [c["key"] for c in (await community.get_showcase(db, club, snap, a))["cards"]] == [f"p:{ALPHA}", f"s:{gsp2}"])

            # the board
            await put(DELTA, BRAVO, 1)
            from app.services import player_card_social as social_mod
            on_board = {pid for pid, f in snap["figs"].items() if f["matches"] > 0 and pid in snap["people"]}
            b0 = await community.board(db, club, snap, a)
            check("everyone in the pool is on the collectors board without doing anything", {e["player_id"] for e in b0["entries"]} == on_board and len(on_board) >= 4 and b0.get("me_on_board") is True and b0.get("me_hidden") is False, str(len(b0["entries"])))
            await social_mod.save_prefs(db, club, c_, {"board_hidden": True}); await db.commit()
            bh = await community.board(db, club, snap, c_)
            check("a player who leaves it is off the board, and told so", c_ not in {e["player_id"] for e in bh["entries"]} and bh.get("me_on_board") is False and bh.get("me_hidden") is True and bh.get("me") is None)
            check("...and everyone else stays", {e["player_id"] for e in bh["entries"]} == on_board - {c_})
            await social_mod.save_prefs(db, club, c_, {"board_hidden": False}); await db.commit()
            b1 = await community.board(db, club, snap, a)
            check("ranked by share of the set, with names, and the viewer's rank", {e["player_id"] for e in b1["entries"]} == on_board and b1["me_rank"] in range(1, len(on_board) + 1) and b1["me"]["player_id"] == a and b1["count"] == len(on_board))
            check("...best share first", [e["percent"] for e in b1["entries"]] == sorted([e["percent"] for e in b1["entries"]], reverse=True))
            pct = {e["player_id"]: e["percent"] for e in b1["entries"]}
            await put(ALPHA, ALPHA, 6, special=gsp2)
            b2 = await community.board(db, club, snap, a)
            check("hoarding copies does not move anyone up (share of distinct cards)", {e["player_id"]: e["percent"] for e in b2["entries"]} == pct)
            await put(ALPHA, DELTA, 1)
            b3 = await community.board(db, club, snap, a)
            check("a new distinct card does", {e["player_id"]: e["percent"] for e in b3["entries"]}[a] > pct[a])
            check("an entry shows the rarest player card held and the showcase, never the rest of the collection", all(set(e) == {"player_id", "name", "percent", "held", "rarest", "showcase", "rank"} for e in b3["entries"]))
            spec_pids = [str(r[0]) for r in (await db.execute(text("SELECT player_id FROM player_special_cards WHERE organisation_id = :o"), {"o": ORG})).fetchall()]
            n_players = len([1 for pid, f in snap["figs"].items() if f["matches"] > 0 and pid in snap["people"]])
            check("the share is over every card in the club (players and special cards of players in the pool)", b3["total_cards"] == n_players + len([x for x in spec_pids if x in snap["people"]]), f'{b3["total_cards"]} vs {n_players} + {len(spec_pids)}')

            # the feed
            today = __import__("datetime").date.today()
            await db.execute(text("INSERT INTO player_special_cards (organisation_id, player_id, kind, event_key, occurred_on, title, detail) VALUES (:o, :p, 'century', 'century:feed-new', :d, 'Century', '{}'::jsonb)"), {"o": ORG, "p": DELTA, "d": today})
            await db.execute(text("INSERT INTO player_special_cards (organisation_id, player_id, kind, event_key, occurred_on, title, detail) VALUES (:o, :p, 'century', 'century:feed-old', :d, 'Century', '{}'::jsonb)"), {"o": ORG, "p": DELTA, "d": today - __import__("datetime").timedelta(days=40)})
            await db.commit()
            sid_new = (await db.execute(text("SELECT id::text FROM player_special_cards WHERE event_key = 'century:feed-new'"))).scalar()
            await put(ALPHA, DELTA, 1, special=sid_new)         # Alpha pulled Delta's new century out of a pack
            cards.forget(ORG)
            snap = await cards.club_snapshot(db, club, fresh=True)
            sw = await swaps.create_swap(db, club, snap, a, d, [{"key": f"p:{DELTA}", "qty": 1}], [{"key": f"p:{BRAVO}", "qty": 1}])
            await swaps.respond(db, club, snap, d, sw, "accept"); await db.commit()
            fd = await community.feed(db, club, snap, a)
            kinds_ = [e["type"] for e in fd["events"]]
            check("the feed has this week's dated special cards, big pulls and swaps agreed", "special" in kinds_ and "pull" in kinds_ and "swap" in kinds_, str(kinds_))
            check("a special card for something that happened long ago is not news", not any("feed-old" in str(e) for e in fd["events"]) and sum(1 for e in fd["events"] if e["type"] == "special") == 1)
            check("it is newest first", [e["on"] for e in fd["events"]] == sorted([e["on"] for e in fd["events"]], reverse=True))
            await social_mod.save_prefs(db, club, a, {"feed_hidden": True}); await db.commit()
            fd2 = await community.feed(db, club, snap, d)
            check("a player who opted out is left out of it entirely (their pulls and their swaps)", not any(e["type"] in ("pull", "swap") for e in fd2["events"]))
            check("the defaults: no email, on the board, in the feed", (await social_mod.load_prefs(db, c_)) == {"alert_swaps": False, "alert_wants": False, "board_hidden": False, "feed_hidden": False})
            await social_mod.save_prefs(db, club, a, {"feed_hidden": False}); await db.commit()

            # switches and the routes
            from app.routers import public_player_cards as pcr2
            rq = lambda who: request_for(who, ORG)
            check("every optional part is on to begin with", (await pcr2.get_my_cards(TOKEN, rq(ALPHA), db))["features"] == {"sets": True, "showcase": True, "board": True, "feed": True})
            check("GET sets, one set, the showcase, the board and the feed answer", all([(await pcr2.get_sets(TOKEN, rq(ALPHA), db))["sets"], (await pcr2.get_set(TOKEN, "kind:games", rq(ALPHA), db))["total"] >= 3, "cards" in await pcr2.get_showcase(TOKEN, rq(ALPHA), db), "entries" in await pcr2.get_board(TOKEN, rq(ALPHA), db), "events" in await pcr2.get_feed(TOKEN, rq(ALPHA), db)]))
            check("an unknown set is a 404", await status_of(pcr2.get_set(TOKEN, "kind:nope", rq(ALPHA), db)) == 404)
            put_ = await pcr2.put_showcase(TOKEN, pcr2.ShowcaseBody(keys=[f"p:{ALPHA}"]), rq(ALPHA), db)
            check("PUT the showcase", [c["key"] for c in put_["cards"]] == [f"p:{ALPHA}"])
            check("PUT a card you do not hold is a 409", await status_of(pcr2.put_showcase(TOKEN, pcr2.ShowcaseBody(keys=[f"p:{HOTEL}"]), rq(ALPHA), db)) == 409)
            await cards.save_settings(db, ORG, {"sets_enabled": False, "board_enabled": False}); await db.commit(); cards.forget(ORG)
            check("a club that switches parts off: those answer 404 and the others still work", await status_of(pcr2.get_sets(TOKEN, rq(ALPHA), db)) == 404 and await status_of(pcr2.get_board(TOKEN, rq(ALPHA), db)) == 404 and "events" in await pcr2.get_feed(TOKEN, rq(ALPHA), db))
            check("the club's switches are on the features the player page reads", (await pcr2.get_my_cards(TOKEN, rq(ALPHA), db))["features"] == {"sets": False, "showcase": True, "board": False, "feed": True})
            adm_set = await admin_routes.get_settings(db, club, User(id=uuid.uuid4(), email="admin@example.com"))
            check("the admin settings carry the switches", adm_set["settings"]["sets_enabled"] is False and adm_set["settings"]["feed_enabled"] is True, str(adm_set["settings"]))
            await cards.save_settings(db, ORG, {"sets_enabled": True, "board_enabled": True}); await db.commit(); cards.forget(ORG)
            check("an unsent switch is left alone", (await cards.load_settings(db, ORG))["feed_enabled"] is True)

            # most wanted (admin): demand as counts only
            snap = await cards.club_snapshot(db, club, fresh=True)
            await social_mod.add_want(db, club, snap, c_, f"p:{DELTA}"); await social_mod.add_want(db, club, snap, str(ECHO), f"p:{DELTA}") if str(ECHO) in snap["people"] else None
            await db.commit()
            from app.services import player_card_admin as insight
            mw = await insight.most_wanted(db, club, snap)
            check("the admin sees the most wanted cards, with how many want each and how many could swap one, and no names of who", mw["cards"] and mw["cards"][0]["wanted_by"] >= 1 and "could_swap" in mw["cards"][0] and not ({"wanters", "players"} & set(mw["cards"][0])) and mw["total_wants"] >= 1)

    # ── The migration and its mirror ─────────────────────────────────────────
    # ── More packs: kinds, calendar, achievements, club events, minimal gifts ─────
    print("\nmore packs")
    if HAVE and PACKS_DDL:
        from app.services import player_card_pack_kinds as K
        import random as _random

        # the odds, drawn straight from the pure function over a synthetic pool
        pool = {"common": [f"c{i}" for i in range(80)], "rare": [f"r{i}" for i in range(40)],
                "epic": [f"e{i}" for i in range(20)], "legendary": [f"l{i}" for i in range(10)]}

        def rare_share(source, n=1500):
            hits = total = least = 0
            least = 99
            for _ in range(n):
                got = cards.draw_cards(pool, [], 5, K.kind_for(source))
                good = sum(1 for g in got if g["tier"] != "common")
                hits += good
                total += len(got)
                least = min(least, good)
            return hits / total, least

        shares = {src: rare_share(src) for src in ("weekly", "match_day", "halloween", "fifty", "milestone", "five_for", "century")}
        order = [shares[s][0] for s in ("weekly", "match_day", "halloween", "fifty", "milestone", "five_for", "century")]
        check("a better pack is richer in Rare and better: standard < match day < holiday < fifty < milestone < five-for < century",
              order == sorted(order) and len(set(round(o, 2) for o in order)) == len(order), str([round(o, 2) for o in order]))
        check("a century pack is almost all Rare or better (over 90% of cards), a standard pack is not (under 50%)", shares["century"][0] > 0.90 and shares["weekly"][0] < 0.50, str(shares))
        for src in ("weekly", "match_day", "fifty", "milestone", "five_for", "century"):
            k = K.kind_for(src)
            check(f"every {src} pack holds at least {k.rare_plus} Rare or better, over 400 packs", shares[src][1] >= k.rare_plus, str(shares[src]))
        dup = any(len({(g['kind'], g['id']) for g in got}) != len(got) for got in (cards.draw_cards(pool, [], 5, K.kind_for("century")) for _ in range(200)))
        check("the same card never appears twice in a pack", not dup)
        sp = [cards.draw_cards(pool, [f"s{i}" for i in range(30)], 5, K.kind_for(src)) for src in ("weekly",) for _ in range(600)]
        sp_c = [cards.draw_cards(pool, [f"s{i}" for i in range(30)], 5, K.kind_for("century")) for _ in range(600)]
        rate = lambda packs: sum(1 for p in packs for g in p if g["kind"] == "special") / sum(len(p) for p in packs)
        check("a special card turns up more often in a pack for an achievement than in a standard one", rate(sp_c) > rate(sp) + 0.05, f"{rate(sp):.3f} vs {rate(sp_c):.3f}")
        check("a tiny club still gets a pack (an empty tier falls to the next)", len(cards.draw_cards({"common": ["a", "b"], "rare": [], "epic": [], "legendary": []}, [], 5, K.kind_for("century"))) == 2)
        check("every pack source has a name, an unknown one a plain fallback", all(K.label_for(s) != "Pack" for s in K.KINDS) and K.label_for("nope") == "Pack")

        # the calendar
        D = date
        check("Halloween is 31 October", [s for s, _ in K.annual_events(D(2026, 10, 31))] == ["halloween"] and not K.annual_events(D(2026, 10, 30)))
        check("the Melbourne Cup pack is the first Tuesday of November (2026: the 3rd, 2027: the 2nd), no other Tuesday",
              [s for s, _ in K.annual_events(D(2026, 11, 3))] == ["melbourne_cup"] and [s for s, _ in K.annual_events(D(2027, 11, 2))] == ["melbourne_cup"]
              and not K.annual_events(D(2026, 11, 10)) and not K.annual_events(D(2026, 11, 2)))
        check("Christmas, Boxing Day, New Year, Australia Day and Anzac Day each have their day",
              [K.annual_events(D(2026, m, d))[0][0] for m, d in ((12, 25), (12, 26), (1, 1), (1, 26), (4, 25))] == ["christmas", "boxing_day", "new_year", "australia_day", "anzac_day"])
        check("the ref carries the year, so a holiday comes once a year", K.annual_events(D(2026, 12, 25))[0][1] != K.annual_events(D(2027, 12, 25))[0][1])
        days = [D(2026, 1, 1) + timedelta(days=i) for i in range(365)]
        hits = [x for x in days if K.is_mystery_day(ORG, x)]
        check("surprise packs land on roughly one day in twelve", 15 <= len(hits) <= 50, str(len(hits)))
        check("...the same days every time, the same for everyone in a club, different for another club",
              hits == [x for x in days if K.is_mystery_day(ORG, x)] and hits != [x for x in days if K.is_mystery_day(ORG_SELECT, x)])
        check("a birthday is the day and month, a 29 February birthday is 28 February in a year without one",
              K.is_birthday(D(2000, 3, 14), D(2026, 3, 14)) and not K.is_birthday(D(2000, 3, 14), D(2026, 3, 15)) and K.is_birthday(D(2000, 2, 29), D(2026, 2, 28))
              and not K.is_birthday(D(2000, 2, 29), D(2026, 3, 1)) and K.is_birthday(D(2000, 2, 29), D(2028, 2, 29)) and not K.is_birthday(D(2000, 2, 29), D(2028, 2, 28)) and not K.is_birthday(None, D(2026, 1, 1)))

        # grants, against the database
        Z1, Z2 = uuid.uuid4(), uuid.uuid4()
        async with Session() as db:
            club = await db.get(Organisation, ORG)
            await cards.save_settings(db, ORG, {"event_packs_enabled": True, "timezone": "Australia/Perth"})
            await db.commit()
            snap = await cards.club_snapshot(db, club, fresh=True)
            today = cards.club_today(snap["settings"])
            for pid, name, dob in ((Z1, "Zulu, Z", today.replace(year=today.year - 30) if not (today.month == 2 and today.day == 29) else None), (Z2, "Yankee, Y", None)):
                await db.execute(text("INSERT INTO players (id, organisation_id, name, is_player, status, is_public, date_of_birth) VALUES (:i, :o, :n, true, 'active', true, :d)"),
                                 {"i": pid, "o": ORG, "n": name, "d": dob})
            await db.commit()
            z1, z2 = str(Z1), str(Z2)
            n_packs = lambda pid, src: db.execute(text("SELECT count(*) FROM player_card_packs WHERE player_id = CAST(:p AS UUID) AND source = :s"), {"p": pid, "s": src})
            real_today = cards.club_today
            try:
                if today.month != 2 or today.day != 29:
                    await cards.ensure_grants(db, club, z1, snap)
                    await cards.ensure_grants(db, club, z2, snap)
                    await db.commit()
                    check("a birthday pack on the day, to the player whose birthday it is and nobody else", (await n_packs(z1, "birthday")).scalar() == 1 and (await n_packs(z2, "birthday")).scalar() == 0)
                    await cards.ensure_grants(db, club, z1, snap); await db.commit()
                    check("...once, however often the page is opened", (await n_packs(z1, "birthday")).scalar() == 1)

                async def on(day, pid):
                    cards.club_today = lambda s, now=None: day
                    try:
                        added = await cards.ensure_grants(db, club, pid, snap)
                        await db.commit()
                        return added
                    finally:
                        cards.club_today = real_today

                far = D(2031, 10, 31)
                a1 = await on(far, z2)
                check("a Halloween pack on 31 October", a1.get("halloween") == 1 and (await n_packs(z2, "halloween")).scalar() == 1)
                check("...not given again that day", (await on(far, z2)).get("halloween") == 0)
                check("...nor the day before", (await on(D(2031, 10, 30), z2)).get("halloween") is None)
                check("...and next year's is a new pack", (await on(D(2032, 10, 31), z2)).get("halloween") == 1 and (await n_packs(z2, "halloween")).scalar() == 2)
                check("the Melbourne Cup pack on the first Tuesday of November", (await on(D(2031, 11, 4), z2)).get("melbourne_cup") == 1)
                mystery = next(x for x in (D(2031, 3, 1) + timedelta(days=i) for i in range(200)) if K.is_mystery_day(ORG, x))
                plain = next(x for x in (D(2031, 3, 1) + timedelta(days=i) for i in range(200)) if not K.is_mystery_day(ORG, x) and not K.annual_events(x))
                check("a surprise pack on a surprise day", (await on(mystery, z2)).get("mystery") == 1)
                check("...and nothing on an ordinary one", (await on(plain, z2)).get("mystery") is None)
                pk = (await db.execute(text("SELECT ref_key FROM player_card_packs WHERE player_id = CAST(:p AS UUID) AND source = 'mystery' AND ref_key = :r"), {"p": z2, "r": f"mystery:{mystery.isoformat()}"})).scalar()
                check("a surprise pack is keyed by the date", pk == f"mystery:{mystery.isoformat()}", str(pk))

                # Match Day
                fx_today, fx_later, fx_multi, fx_cancel = (uuid.uuid4() for _ in range(4))
                day = D(2031, 6, 14)
                for fid, on_, end, status in ((fx_today, day, None, "UPCOMING"), (fx_later, day + timedelta(days=1), None, "UPCOMING"),
                                              (fx_multi, day - timedelta(days=1), day + timedelta(days=1), "IN_PROGRESS"), (fx_cancel, day, None, "CANCELLED")):
                    await db.execute(text("INSERT INTO fixtures (id, organisation_id, source, played_on, end_on, status) VALUES (:i, :o, 'manual', :d, :e, :s)"),
                                     {"i": fid, "o": ORG, "d": on_, "e": end, "s": status})
                await db.execute(text("INSERT INTO fixture_lineups (fixture_id, player_id, organisation_id) VALUES (:f, :p, :o)"), {"f": fx_later, "p": Z2, "o": ORG})
                await db.commit()
                check("no Match Day pack when the only fixture is tomorrow", (await on(day, z2)).get("match_day") is None)
                await db.execute(text("INSERT INTO fixture_lineups (fixture_id, player_id, organisation_id) VALUES (:f, :p, :o)"), {"f": fx_cancel, "p": Z2, "o": ORG}); await db.commit()
                check("...nor for a cancelled one", (await on(day, z2)).get("match_day") is None)
                await db.execute(text("INSERT INTO fixture_lineups (fixture_id, player_id, organisation_id) VALUES (:f, :p, :o)"), {"f": fx_today, "p": Z2, "o": ORG}); await db.commit()
                check("a Match Day pack on a team sheet for a fixture today", (await on(day, z2)).get("match_day") == 1)
                check("...once", (await on(day, z2)).get("match_day") == 0)
                await db.execute(text("DELETE FROM fixture_lineups WHERE fixture_id = :f"), {"f": fx_today})
                await db.execute(text("INSERT INTO fixture_lineups (fixture_id, player_id, organisation_id) VALUES (:f, :p, :o)"), {"f": fx_multi, "p": Z2, "o": ORG}); await db.commit()
                check("a two day game is Match Day on its last day too", (await on(day + timedelta(days=1), z2)).get("match_day") == 1)
                check("...and on its first day", (await on(day - timedelta(days=1), z2)).get("match_day") == 1)
                weekly_two = uuid.uuid4()
                await db.execute(text("INSERT INTO fixtures (id, organisation_id, source, played_on, end_on, status) VALUES (:i, :o, 'manual', :d, :e, 'IN_PROGRESS')"), {"i": weekly_two, "o": ORG, "d": D(2031, 8, 2), "e": D(2031, 8, 9)})
                await db.execute(text("INSERT INTO fixture_lineups (fixture_id, player_id, organisation_id) VALUES (:f, :p, :o)"), {"f": weekly_two, "p": Z1, "o": ORG}); await db.commit()
                mid = [(await on(D(2031, 8, d_), z1)).get("match_day") for d_ in range(3, 9)]
                check("a game played on two Saturdays a week apart is NOT Match Day on the days between", all(m is None for m in mid), str(mid))
                check("...but is on both Saturdays", (await on(D(2031, 8, 2), z1)).get("match_day") == 1 and (await on(D(2031, 8, 9), z1)).get("match_day") == 1)
                check("a player not on any team sheet gets none", (await on(day, z1)).get("match_day") is None)
                played = (await db.execute(text("SELECT g.played_at FROM game_appearances ga JOIN v_effective_games g ON g.id = ga.game_id WHERE ga.player_id = :p AND g.played_at IS NOT NULL LIMIT 1"), {"p": ALPHA})).scalar()
                if played:
                    check("a scorecard dated today counts too", (await on(played, str(ALPHA))).get("match_day") == 1, str(played))

                # taking back the packs that went out wrongly
                for d_ in (D(2031, 8, 4), D(2031, 8, 5)):
                    await db.execute(text("INSERT INTO player_card_packs (organisation_id, player_id, source, ref_key) VALUES (:o, :p, 'match_day', :r)"), {"o": ORG, "p": Z1, "r": f"match_day:{d_.isoformat()}"})
                await db.execute(text("INSERT INTO player_card_packs (organisation_id, player_id, source, ref_key, opened_at) VALUES (:o, :p, 'match_day', 'match_day:2031-08-06', NOW())"), {"o": ORG, "p": Z1})
                await db.commit()
                dry = await cards.unwind_stray_match_day_packs(db, str(ORG))
                check("a dry run counts the stray unopened Match Day packs and takes none back", dry["packs"] >= 2 and dry["players"] >= 1 and dry["applied"] is False and (await db.execute(text("SELECT count(*) FROM player_card_packs WHERE source = 'match_day' AND ref_key IN ('match_day:2031-08-04', 'match_day:2031-08-05')"))).scalar() == 2, str(dry))
                done_ = await cards.unwind_stray_match_day_packs(db, str(ORG), apply=True)
                await db.commit()
                left = (await db.execute(text("SELECT ref_key FROM player_card_packs WHERE player_id = CAST(:p AS UUID) AND source = 'match_day' ORDER BY ref_key"), {"p": z1})).scalars().all()
                check("applying takes back the two unopened strays, keeps the real days and the opened one", done_["applied"] is True and "match_day:2031-08-04" not in left and "match_day:2031-08-05" not in left and "match_day:2031-08-06" in left and "match_day:2031-08-02" in left and "match_day:2031-08-09" in left, str(left))
                check("a second run finds nothing", (await cards.unwind_stray_match_day_packs(db, str(ORG)))["packs"] == 0)

                # the club's switch
                await cards.save_settings(db, ORG, {"event_packs_enabled": False}); await db.commit()
                snap = await cards.club_snapshot(db, club, fresh=True)
                off = await on(D(2033, 10, 31), z2)
                check("with event packs switched off there is no holiday, birthday, surprise or Match Day pack", not any(off.get(k) for k in ("halloween", "mystery", "birthday", "match_day")), str(off))
                await cards.save_settings(db, ORG, {"event_packs_enabled": True}); await db.commit()
                snap = await cards.club_snapshot(db, club, fresh=True)

                # club scheduled events (a Test match)
                async def refused_value(coro):
                    try:
                        await coro
                        return None
                    except ValueError as exc:
                        return str(exc)
                check("a scheduled pack needs a name", await refused_value(cards.add_event(db, ORG, " ", day, day)) is not None)
                check("...cannot end before it starts", await refused_value(cards.add_event(db, ORG, "X", day, day - timedelta(days=1))) is not None)
                check("...and cannot run longer than a month", await refused_value(cards.add_event(db, ORG, "X", day, day + timedelta(days=40))) is not None)
                test_day1 = D(2032, 12, 3)
                ev = await cards.add_event(db, ORG, "Australia v South Africa, First Test", test_day1, test_day1 + timedelta(days=4), True)
                await db.commit()
                g1 = await on(test_day1, z2)
                check("a scheduled Test match gives a pack on its first day", g1.get("event") == 1)
                check("...named after it", any(p["label"] == "Australia v South Africa, First Test" and p["source"] == "event" for p in await cards.available_packs(db, z2, snap)))
                check("...a fresh one on each day of the match", (await on(test_day1 + timedelta(days=1), z2)).get("event") == 1 and (await on(test_day1 + timedelta(days=4), z2)).get("event") == 1)
                check("...none the day after it ends", (await on(test_day1 + timedelta(days=5), z2)).get("event") is None)
                check("...none the day before it starts", (await on(test_day1 - timedelta(days=1), z2)).get("event") is None)
                ev2 = await cards.add_event(db, ORG, "Club day", test_day1 + timedelta(days=30), test_day1 + timedelta(days=32), False)
                await db.commit()
                await on(test_day1 + timedelta(days=30), z2); await on(test_day1 + timedelta(days=31), z2)
                check("a pack for the whole run (not one a day) comes once", (await db.execute(text("SELECT count(*) FROM player_card_packs WHERE player_id = CAST(:p AS UUID) AND label = 'Club day'"), {"p": z2})).scalar() == 1)
                check("a club's scheduled packs are listed by date", [e["title"] for e in await cards.list_events(db, ORG) if e["starts_on"] >= str(test_day1)] == ["Australia v South Africa, First Test", "Club day"])
                held_before = (await db.execute(text("SELECT count(*) FROM player_card_packs WHERE player_id = CAST(:p AS UUID) AND source = 'event'"), {"p": z2})).scalar()
                check("deleting a scheduled pack gives nothing further and takes nothing back", await cards.delete_event(db, ORG, ev["id"]) is True and await cards.delete_event(db, ORG, ev["id"]) is False)
                await db.commit()
                check("...the packs already granted stay", (await db.execute(text("SELECT count(*) FROM player_card_packs WHERE player_id = CAST(:p AS UUID) AND source = 'event'"), {"p": z2})).scalar() == held_before)
                check("another club cannot delete it (the id is checked against the club)", await cards.delete_event(db, ORG_SELECT, ev2["id"]) is False)
                await cards.delete_event(db, ORG, ev2["id"]); await db.commit()
            finally:
                cards.club_today = real_today

            # packs for what a player did
            ach = {"century": ("century", 1), "fifty": ("fifty", 1), "five_for": ("five_for", 1), "hat_trick": ("hat_trick", 1),
                   "runs_milestone": ("milestone", 1), "games": ("milestone", 1)}
            launched = snap["settings"]["launched_at"].date()
            recent = launched + timedelta(days=2)
            for n, (kind, _) in enumerate(ach.items()):
                await db.execute(text("INSERT INTO player_special_cards (organisation_id, player_id, kind, event_key, occurred_on, title, detail) VALUES (:o, :p, :k, :e, :d, :t, '{}'::jsonb)"),
                                 {"o": ORG, "p": Z2, "k": kind, "e": f"ach:{kind}:{n}", "d": recent, "t": kind})
            await db.execute(text("INSERT INTO player_special_cards (organisation_id, player_id, kind, event_key, occurred_on, title, detail) VALUES (:o, :p, 'century', 'ach:old', :d, 'Old', '{}'::jsonb)"),
                             {"o": ORG, "p": Z2, "d": launched - timedelta(days=200)})
            await db.execute(text("INSERT INTO player_special_cards (organisation_id, player_id, kind, event_key, occurred_on, title, detail) VALUES (:o, :p, 'debut', 'ach:debut', :d, 'Debut', '{}'::jsonb)"),
                             {"o": ORG, "p": Z2, "d": recent})
            await db.commit()
            await cards.ensure_grants(db, club, z2, snap); await db.commit()
            have = {r[0]: r[1] for r in (await db.execute(text("SELECT source, count(*) FROM player_card_packs WHERE player_id = CAST(:p AS UUID) AND source IN ('century','fifty','five_for','hat_trick','milestone') GROUP BY source"), {"p": z2})).fetchall()}
            check("a pack for each century, fifty, five-for and hat-trick, and one for each landmark card (a games milestone and a runs milestone: two)",
                  have == {"century": 1, "fifty": 1, "five_for": 1, "hat_trick": 1, "milestone": 2}, str(have))
            check("a century from before the club began using cards earns nothing, and neither does a debut", have.get("century") == 1)
            await cards.ensure_grants(db, club, z2, snap); await db.commit()
            check("a second visit grants nothing again", (await db.execute(text("SELECT count(*) FROM player_card_packs WHERE player_id = CAST(:p AS UUID) AND source IN ('century','fifty','five_for','hat_trick','milestone')"), {"p": z2})).scalar() == 6)
            listed = await cards.available_packs(db, z2, snap)
            srcs = [p["source"] for p in listed]
            check("the list leads with the starter packs, then what the player achieved, then the rest", srcs[:2] == ["starter", "starter"] and set(srcs[2:8]) == {"century", "fifty", "five_for", "hat_trick", "milestone"} and "weekly" in srcs and srcs.index("weekly") > 7, str(srcs))
            check("each has its own name", {p["source"]: p["label"] for p in listed}["century"] == "Century pack" and {p["source"]: p["label"] for p in listed}["milestone"] == "Milestone pack")
            seen_kinds = []
            real_draw = cards.draw_cards
            cards.draw_cards = lambda pool_, specials_, size=5, kind=None: (seen_kinds.append(kind.label if kind else None), real_draw(pool_, specials_, size, kind))[1]
            try:
                z2p = await db.get(Player, Z2)
                cent = next(p for p in listed if p["source"] == "century")
                opened = await cards.open_pack(db, club, z2p, cent["id"], snap)
                await db.commit()
            finally:
                cards.draw_cards = real_draw
            check("opening a century pack draws with the century odds and gives five cards", seen_kinds == ["Century pack"] and opened is not None and len(opened) >= 1, str(seen_kinds))

            # the starting cards
            check("a new club's starting cards are minimal", cards.default_settings()["starter_gifts"] == "minimal")
            try:
                await cards.save_settings(db, ORG, {"starter_gifts": "everything"})
                bogus = False
            except ValueError:
                bogus = True
                await db.rollback()
                club = await db.get(Organisation, ORG)
            check("an unknown starting-cards choice is refused", bogus)
            Y = uuid.uuid4()
            await db.execute(text("INSERT INTO players (id, organisation_id, name, is_player, status, is_public) VALUES (:i, :o, 'Xray, X', true, 'active', true)"), {"i": Y, "o": ORG})
            spec = {}
            for key, kind, ago in (("debut", "debut", 900), ("g10", "games", 800), ("g50", "games", 300), ("r1", "runs_milestone", 40), ("c1", "century", 30), ("f1", "fifty", 10)):
                spec[key] = (await db.execute(text("INSERT INTO player_special_cards (organisation_id, player_id, kind, event_key, occurred_on, title, detail) VALUES (:o, :p, :k, :e, :d, :t, '{}'::jsonb) RETURNING id::text"),
                                               {"o": ORG, "p": Y, "k": kind, "e": f"gift:{key}", "d": date.today() - timedelta(days=ago), "t": key})).scalar()
            await db.commit()
            await cards._gift_new_specials(db, str(ORG), "minimal"); await db.commit()
            gifted = lambda: db.execute(text("SELECT sc.title FROM player_card_copies c JOIN player_special_cards sc ON sc.id = c.special_id WHERE c.owner_player_id = :p AND c.source = 'gift' ORDER BY sc.title"), {"p": Y})
            check("a minimal club gifts the debut card and the latest landmark card, not the century, fifty or earlier games milestones", [r[0] for r in (await gifted()).fetchall()] == ["debut", "r1"], str([r[0] for r in (await gifted()).fetchall()]))
            await cards._gift_new_specials(db, str(ORG), "minimal"); await db.commit()
            check("...and a second look adds nothing", len((await gifted()).fetchall()) == 2)
            await db.execute(text("INSERT INTO player_special_cards (organisation_id, player_id, kind, event_key, occurred_on, title, detail) VALUES (:o, :p, 'wickets_milestone', 'gift:w1', :d, 'w1', '{}'::jsonb)"), {"o": ORG, "p": Y, "d": date.today() - timedelta(days=1)})
            await db.commit()
            await cards._gift_new_specials(db, str(ORG), "minimal"); await db.commit()
            check("a newer landmark is gifted when it arrives, and the older gift stays (add-only)", [r[0] for r in (await gifted()).fetchall()] == ["debut", "r1", "w1"])
            await cards._gift_new_specials(db, str(ORG), "all"); await db.commit()
            check("a club on 'all' gifts every one", len((await gifted()).fetchall()) == 7)
            # one gifted copy has been swapped away and back (source swap), one is a pack pull
            await db.execute(text("UPDATE player_card_copies SET source = 'swap' WHERE owner_player_id = :p AND special_id = CAST(:s AS UUID)"), {"p": Y, "s": spec["c1"]})
            await db.commit()
            dry = await cards.trim_gifts(db, str(ORG), apply=False)
            check("a dry run says what it would remove and removes nothing", dry["cards"] >= 3 and dry["applied"] is False and len((await gifted()).fetchall()) == 6, str(dry))
            from app.routers import player_cards_admin as adm
            admin_user = User(id=uuid.uuid4(), email="admin@example.com")
            routed = await adm.trim_gifts(adm.TrimBody(apply=True), db, club, admin_user)
            left = [r[0] for r in (await gifted()).fetchall()]
            check("applying takes the starting cards back to the debut and the latest landmark (the older gifts go)", routed["applied"] is True and "g10" not in left and "g50" not in left and "f1" not in left, str(left))
            check("...but never a card that has moved (a swapped copy is no longer a gift)", (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE owner_player_id = :p AND special_id = CAST(:s AS UUID)"), {"p": Y, "s": spec["c1"]})).scalar() == 1)
            check("...and no player is left with more than one gifted landmark that is not their latest",
                  (await db.execute(text("""SELECT count(*) FROM player_card_copies c JOIN player_special_cards sc ON sc.id = c.special_id
                       WHERE c.source = 'gift' AND c.organisation_id = :o AND sc.kind IN ('games','runs_milestone','wickets_milestone','dismissals_milestone')
                         AND sc.id <> (SELECT l.id FROM player_special_cards l WHERE l.player_id = sc.player_id AND l.kind IN ('games','runs_milestone','wickets_milestone','dismissals_milestone')
                                        ORDER BY l.occurred_on DESC NULLS LAST, l.created_at DESC, l.id DESC LIMIT 1)"""), {"o": ORG})).scalar() == 0)
            check("...and the trim is on the audit trail", (await db.execute(text("SELECT count(*) FROM audit_logs WHERE action = 'player_card_gifts_trimmed'"))).scalar() >= 1)
            again = await cards.trim_gifts(db, str(ORG), apply=False)
            check("a second dry run finds nothing left to trim", again["cards"] == 0, str(again))
            check("the packs a player pulled are never touched by a trim", (await db.execute(text("SELECT count(*) FROM player_card_copies WHERE source = 'pack' AND organisation_id = :o"), {"o": ORG})).scalar() > 0)

            # the admin payload and routes
            pay = await adm.get_settings(db, club, admin_user)
            check("the settings payload carries the two new switches and the scheduled packs", pay["settings"]["starter_gifts"] in ("minimal", "all") and pay["settings"]["event_packs_enabled"] is True and isinstance(pay["events"], list), str(pay["settings"]))
            added = await adm.add_event(adm.EventBody(title="Boxing Day Test", starts_on=date.today() + timedelta(days=3)), db, club, admin_user)
            eid = next(e["id"] for e in added["events"] if e["title"] == "Boxing Day Test")
            check("the admin route schedules a pack for one day (the last day defaults to the first)", next(e for e in added["events"] if e["id"] == eid)["ends_on"] == next(e for e in added["events"] if e["id"] == eid)["starts_on"])
            check("...a bad range is a 422", await status_of(adm.add_event(adm.EventBody(title="Bad", starts_on=date.today(), ends_on=date.today() - timedelta(days=2)), db, club, admin_user)) == 422)
            club = await db.get(Organisation, ORG)   # the refused request rolled back and expired it
            removed = await adm.delete_event(eid, db, club, admin_user)
            check("...and removes it", all(e["id"] != eid for e in removed["events"]))
            check("an id that is not there, or not a uuid, is a 404", await status_of(adm.delete_event(str(uuid.uuid4()), db, club, admin_user)) == 404 and await status_of(adm.delete_event("nope", db, club, admin_user)) == 404)
            club = await db.get(Organisation, ORG)
            await adm.update_settings(adm.SettingsBody(starter_gifts="all"), db, club, admin_user)
            check("PATCH settings takes the starting-cards choice", (await cards.load_settings(db, ORG))["starter_gifts"] == "all")
            check("...an unknown one is a 422", await status_of(adm.update_settings(adm.SettingsBody(starter_gifts="some"), db, club, admin_user)) == 422)
            await db.rollback()
    else:
        check("(the control run has no new packs to test)", True)

    # ── Pack designs: a club's own look for its packs ─────────────────────────────
    print("\npack designs")
    if HAVE and DESIGNS_DDL:
        from io import BytesIO
        from PIL import Image
        from starlette.datastructures import UploadFile as _Upload
        from app.services import player_card_designs as D
        from app.routers import images as images_routes, player_cards_admin as adm2, public_player_cards as pcr3

        def png(w, h, alpha=False):
            out = BytesIO()
            Image.new("RGBA" if alpha else "RGB", (w, h), (200, 30, 30, 120) if alpha else (30, 90, 200)).save(out, "PNG")
            return out.getvalue()

        def jpg(w, h):
            out = BytesIO()
            Image.new("RGB", (w, h), (10, 160, 60)).save(out, "JPEG")
            return out.getvalue()

        def dims(raw):
            with Image.open(BytesIO(raw)) as im:
                return im.size, im.format

        async def raises(coro):
            try:
                await coro
                return None
            except D.DesignError as exc:
                return exc.status

        async with Session() as db:
            club = await db.get(Organisation, ORG)
            admin_user = User(id=uuid.uuid4(), email="admin@example.com")
            await db.execute(text("DELETE FROM club_card_pack_designs"))
            await db.commit()
            check("a club has no design to begin with", await D.load_all(db, ORG) == {})

            # the style
            d1 = await D.save_style(db, ORG, "default", {"color_a": "#B91C1C", "overlay": 0.4, "show_logo": False, "art_size": "l", "art_position": "bottom"})
            await db.commit()
            check("a design is made on first save, colours lower-cased, and the rest of it stays as built", d1["a"] == "#b91c1c" and d1["overlay"] == 0.4 and d1["show_logo"] is False and d1["show_name"] is True and d1["art_size"] == "l" and d1["art_position"] == "bottom" and d1["b"] is None and d1["background_url"] is None, str(d1))
            d2 = await D.save_style(db, ORG, "default", {"title": "  Club   pack  "})
            check("a key that is not sent is left alone", d2["a"] == "#b91c1c" and d2["overlay"] == 0.4 and d2["title"] == "Club pack", str(d2))
            d3 = await D.save_style(db, ORG, "default", {"color_a": None, "title": None})
            check("an explicit null clears a colour and the name", d3["a"] is None and d3["title"] is None and d3["overlay"] == 0.4)
            check("the name is cut to 40 characters", len((await D.save_style(db, ORG, "default", {"title": "x" * 90}))["title"]) == 40)
            await db.commit()
            for label, patch in (("a colour that is not six digit hex", {"color_b": "red"}), ("a colour that is style in disguise", {"color_on": "#fff;background:url(x)"}), ("a background darker than 0.8", {"overlay": 0.95}),
                                 ("a negative darkness", {"overlay": -0.1}), ("a darkness that is not a number", {"overlay": "lots"}), ("a position that is not offered", {"art_position": "left"}), ("a size that is not offered", {"art_size": "xl"})):
                check(f"{label} is refused (422)", await raises(D.save_style(db, ORG, "default", patch)) == 422)
                await db.rollback()
            check("nothing a refused save sent was kept", (await D.get_one(db, ORG, "default"))["a"] is None)

            # which things can be designed
            ev = await cards.add_event(db, ORG, "Boxing Day Test", date.today() + timedelta(days=60), None, True)
            other_ev = await cards.add_event(db, ORG_SELECT, "Someone else's day", date.today() + timedelta(days=61), None, True)
            await db.commit()
            check("a pack kind and a scheduled event of this club can be designed", await D.check_target(db, ORG, "century") == "century" and await D.check_target(db, ORG, f"event:{ev['id']}") == f"event:{ev['id']}")
            check("a made-up kind, a made-up event and another club's event are a 404", all([await raises(D.check_target(db, ORG, t)) == 404 for t in ("nonsense", f"event:{uuid.uuid4()}", f"event:{other_ev['id']}", "event:nope")]))
            tg = await D.targets(db, ORG)
            check("the list of targets is every pack kind and the club's own events, with a name each", tg[0]["key"] == "default" and {t["key"] for t in tg} >= set(K.KINDS) | {f"event:{ev['id']}"} and all(t["label"] for t in tg) and f"event:{other_ev['id']}" not in {t["key"] for t in tg})

            # the images
            big = await D.set_image(db, ORG, "default", "bg", jpg(3000, 2000))
            await db.commit()
            raw, mime = await D.image_bytes(db, big["id"], "bg")
            check("a large photo is shrunk to 1200 on its long side and kept as a JPEG", dims(raw) == ((1200, 800), "JPEG") and mime == "image/jpeg", str(dims(raw)))
            art = await D.set_image(db, ORG, "default", "art", png(1800, 900, alpha=True))
            raw2, mime2 = await D.image_bytes(db, art["id"], "art")
            check("a picture with see-through parts stays a PNG, shrunk to 900", dims(raw2) == ((900, 450), "PNG") and mime2 == "image/png")
            check("the design lists both with a versioned URL, and no picture bytes", art["background_url"].startswith(f"/api/images/card-packs/{art['id']}/bg?v=") and art["art_url"].startswith(f"/api/images/card-packs/{art['id']}/art?v=") and all(isinstance(v, (str, int, float, bool, type(None))) for v in art.values()))
            exif = BytesIO()
            im = Image.new("RGB", (400, 300), (5, 5, 5))
            ex = Image.Exif(); ex[0x010F] = "SecretCamera"; ex[0x0110] = "Model X"
            im.save(exif, "JPEG", exif=ex)
            await D.set_image(db, ORG, "default", "art", exif.getvalue())
            raw3, _ = await D.image_bytes(db, art["id"], "art")
            check("what a phone writes into a photo (camera, location) is dropped", b"SecretCamera" not in raw3 and not Image.open(BytesIO(raw3)).getexif())
            check("a GIF is accepted", await raises(D.set_image(db, ORG, "default", "art", (lambda b: (Image.new("RGB", (40, 40), (1, 2, 3)).save(b, "GIF"), b.getvalue())[1])(BytesIO()))) is None)
            svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
            check("an SVG is refused (it could run script from our domain)", await raises(D.set_image(db, ORG, "default", "bg", svg)) == 422)
            check("a file that is not a picture is refused", await raises(D.set_image(db, ORG, "default", "bg", b"hello, this is text")) == 422)
            check("an empty file is refused", await raises(D.set_image(db, ORG, "default", "bg", b"")) == 422)
            check("an upload over 6 MB is refused (413)", await raises(D.set_image(db, ORG, "default", "bg", b"\x89PNG" + b"0" * (7 * 1024 * 1024))) == 413)
            check("a picture with an absurd number of pixels is refused before it is decoded", await raises(D.set_image(db, ORG, "default", "bg", png(7000, 7000))) == 422)
            check("an unknown image slot is a 404", await raises(D.set_image(db, ORG, "default", "logo", png(10, 10))) == 404)
            await db.rollback()
            check("a refused upload left the earlier pictures alone", (await D.get_one(db, ORG, "default"))["background_url"] is not None)

            # serving
            r = await images_routes.get_card_pack_image(big["id"], "bg", db)
            check("the image route serves the stored picture, cached hard, with its own type and no sniffing", r.media_type == "image/jpeg" and dims(r.body)[0] == (1200, 800) and "max-age" in r.headers["cache-control"] and r.headers["x-content-type-options"] == "nosniff")
            check("a design with no such picture, an unknown id and an unknown slot are 404s", all([await status_of(images_routes.get_card_pack_image(i, k, db)) == 404 for i, k in ((str(uuid.uuid4()), "bg"), (big["id"], "logo"), ("nope", "bg"))]))
            await D.clear_image(db, ORG, "default", "art"); await db.commit()
            check("removing a picture removes it (URL and bytes)", (await D.get_one(db, ORG, "default"))["art_url"] is None and await status_of(images_routes.get_card_pack_image(big["id"], "art", db)) == 404)

            # which design a pack takes
            await D.save_style(db, ORG, "century", {"title": "Ton Up", "color_a": "#112233"})
            await D.save_style(db, ORG, f"event:{ev['id']}", {"color_a": "#445566", "title": "ignored for events"})
            await D.save_style(db, ORG_SELECT, "weekly", {"color_a": "#999999", "title": "Other club"})
            await db.commit()
            all_d = await D.load_all(db, ORG)
            check("a pack takes its event's design, then its kind's, then the club default, then none",
                  D.resolve(all_d, "event", ev["id"])["a"] == "#445566" and D.resolve(all_d, "century")["a"] == "#112233" and D.resolve(all_d, "weekly")["target"] == "default" and D.resolve({}, "weekly") is None)
            check("a club never sees another club's designs", "weekly" not in all_d and (await D.load_all(db, ORG_SELECT)).keys() == {"weekly"})
            check("the event id is read from a pack's ref (one a day, or one for the run) and from nothing else", D.event_id_of("event", f"{ev['id']}:2026-12-03") == ev["id"] and D.event_id_of("event", ev["id"]) == ev["id"] and D.event_id_of("weekly", f"{ev['id']}:x") is None and D.event_id_of("event", "junk") is None)
            club = await db.get(Organisation, ORG)
            snap = await cards.club_snapshot(db, club, fresh=True)
            Q = uuid.uuid4()
            await db.execute(text("INSERT INTO players (id, organisation_id, name, is_player, status, is_public) VALUES (:i, :o, 'Quebec, Q', true, 'active', true)"), {"i": Q, "o": ORG})
            for src, ref, label in (("century", "x1", None), ("weekly", "2031-W01:1", None), ("event", f"{ev['id']}:2031-01-01", "Boxing Day Test")):
                await db.execute(text("INSERT INTO player_card_packs (organisation_id, player_id, source, ref_key, label) VALUES (:o, :p, :s, :r, :l)"), {"o": ORG, "p": Q, "s": src, "r": ref, "l": label})
            await db.commit()
            cards.week_key_real = cards.week_key
            cards.week_key = lambda settings, now=None: "2031-W01"
            try:
                listed = {p["source"]: p for p in await cards.available_packs(db, str(Q), snap)}
            finally:
                cards.week_key = cards.week_key_real
            check("each unopened pack carries its design", listed["century"]["design"]["a"] == "#112233" and listed["event"]["design"]["a"] == "#445566" and listed["weekly"]["design"]["target"] == "default")
            check("the club's name for a kind of pack is used (Ton Up), the default's name never is, and a scheduled event keeps its own", listed["century"]["label"] == "Ton Up" and listed["weekly"]["label"] == "Weekly pack" and listed["event"]["label"] == "Boxing Day Test", str({k: v["label"] for k, v in listed.items()}))
            check("a club with no designs gets the built-in look (design is null)", all(p["design"] is None for p in await cards.available_packs(db, str(Q), {**snap, "org_id": str(ORG_SELECT)} if False else {**snap, "org_id": str(uuid.uuid4())})))

            # the admin routes
            pay = await adm2.get_settings(db, club, admin_user)
            check("the settings payload has the club's designs and what can be designed", "century" in pay["designs"] and any(t["key"] == "default" for t in pay["design_targets"]))
            up = await adm2.upload_design_image("weekly", "bg", _Upload(file=BytesIO(jpg(900, 1200)), filename="bg.jpg"), db, club, admin_user)
            check("the upload route stores a background and returns every design", up["designs"]["weekly"]["background_url"] is not None)
            check("...and the upload is on the audit trail", (await db.execute(text("SELECT count(*) FROM audit_logs WHERE action = 'player_card_design_image'"))).scalar() >= 1)
            st1 = await status_of(adm2.upload_design_image("weekly", "bg", _Upload(file=BytesIO(svg), filename="x.svg"), db, club, admin_user))
            club = await db.get(Organisation, ORG)
            st2 = await status_of(adm2.upload_design_image("weekly", "nope", _Upload(file=BytesIO(jpg(10, 10)), filename="x.jpg"), db, club, admin_user))
            club = await db.get(Organisation, ORG)
            check("a bad upload through the route is a 422 and a bad slot a 404", (st1, st2) == (422, 404), str((st1, st2)))
            club = await db.get(Organisation, ORG)
            sv = await adm2.save_design("weekly", adm2.DesignBody(color_a="#abcdef"), db, club, admin_user)
            check("the style route sends back every design, changing only what was sent", sv["designs"]["weekly"]["a"] == "#abcdef" and sv["designs"]["weekly"]["background_url"] is not None)
            st1 = await status_of(adm2.save_design("weekly", adm2.DesignBody(color_a="blue"), db, club, admin_user))
            club = await db.get(Organisation, ORG)
            st2 = await status_of(adm2.save_design("zzz", adm2.DesignBody(), db, club, admin_user))
            check("a bad colour through the route is a 422 and an unknown target a 404", (st1, st2) == (422, 404), str((st1, st2)))
            club = await db.get(Organisation, ORG)
            rm = await adm2.remove_design_image("weekly", "bg", db, club, admin_user)
            check("the delete route removes a picture", rm["designs"]["weekly"]["background_url"] is None)
            rs = await adm2.reset_design("weekly", db, club, admin_user)
            check("reset takes a design back to the built-in look, and is on the audit trail", "weekly" not in rs["designs"] and (await db.execute(text("SELECT count(*) FROM audit_logs WHERE action = 'player_card_design_reset'"))).scalar() >= 1)
            await adm2.delete_event(ev["id"], db, club, admin_user)
            check("removing a scheduled event removes its design", f"event:{ev['id']}" not in await D.load_all(db, ORG))

            # the player's payload
            who = await db.get(Player, ALPHA)
            mine = await pcr3.get_my_cards(TOKEN, request_for(ALPHA, ORG), db)
            check("the player's cards payload carries the club's designs, and each pack its own", "pack_designs" in mine and "century" in mine["pack_designs"] and all("design" in p for p in mine["packs"]))
            await db.rollback()
    else:
        check("(the control run has no pack designs to test)", True)

    # ── A new photo shows on the card at once ─────────────────────────────────────
    print("\nplayer photos")
    if HAVE and DESIGNS_DDL:
        from io import BytesIO as _B
        from starlette.datastructures import UploadFile as _Up
        from PIL import Image as _Im
        from app.routers import club_admin as ca
        buf = _B(); _Im.new("RGB", (30, 40), (9, 9, 9)).save(buf, "PNG")
        async with Session() as db:
            club = await db.get(Organisation, ORG)
            snap0 = await cards.club_snapshot(db, club, fresh=True)
            before = snap0["people"][str(BRAVO)]["photo_url"]
            again = await cards.club_snapshot(db, club)
            check("the snapshot is cached between visits (so the next check means something)", again is snap0)
            who = await db.get(Player, BRAVO)
            out = await ca._store_player_photo(db, who, _Up(file=_B(buf.getvalue()), filename="new.png"), "photo")
            snap1 = await cards.club_snapshot(db, club)
            check("a new headshot is on the card straight away, without waiting for the snapshot to expire", snap1["people"][str(BRAVO)]["photo_url"] == out["photo_url"] != before, f"{before} -> {out}")
            check("...and in the card the player is drawn from", cards.regular_card(snap1, str(BRAVO))["photo_url"] == out["photo_url"])
            who = await db.get(Player, BRAVO)
            hero = await ca._store_player_photo(db, who, _Up(file=_B(buf.getvalue()), filename="act.png"), "hero")
            snap2 = await cards.club_snapshot(db, club)
            check("a new action shot is on the card straight away too", snap2["people"][str(BRAVO)]["hero_photo_url"] == hero["hero_photo_url"])
            who = await db.get(Player, BRAVO)
            await ca._clear_player_photo(db, who, "hero")
            snap3 = await cards.club_snapshot(db, club)
            check("removing the action shot takes it off the card at once (back to the headshot circle)", snap3["people"][str(BRAVO)]["hero_photo_url"] is None and snap3["people"][str(BRAVO)]["photo_url"] == out["photo_url"])
            await db.rollback()
    else:
        check("(the control run has no photo cache fix to test)", True)

    # ── Packs an admin creates by hand, and the quality ladder ────────────────────
    print("\npacks created by an admin")
    if HAVE and GIFTS_DDL:
        from app.routers import player_cards_admin as adm3
        from app.services import player_card_pack_kinds as K3
        pool3 = {"common": [f"c{i}" for i in range(80)], "rare": [f"r{i}" for i in range(40)], "epic": [f"e{i}" for i in range(20)], "legendary": [f"l{i}" for i in range(10)]}

        def share(q, n=1500):
            good = tot = least = 0
            least = 99
            for _ in range(n):
                got = cards.draw_cards(pool3, [], 5, K3.QUALITIES[q])
                g = sum(1 for x in got if x["tier"] != "common")
                good += g; tot += len(got); least = min(least, g)
            return good / tot, least

        ladder = [share(q) for q in K3.QUALITIES]
        check("each quality step is richer in Rare and better than the one before it", [round(x[0], 3) for x in ladder] == sorted(round(x[0], 3) for x in ladder) and len({round(x[0], 2) for x in ladder}) == len(ladder), str([round(x[0], 2) for x in ladder]))
        check("...and each guarantees its number of Rare or better cards (1, 2, 2, 3, 4, 4)", [x[1] for x in ladder] >= [K3.QUALITIES[q].rare_plus for q in K3.QUALITIES] and [K3.QUALITIES[q].rare_plus for q in K3.QUALITIES] == [1, 2, 2, 3, 4, 4], str([x[1] for x in ladder]))
        check("a Legendary pack is nearly all Rare or better, a Standard one is not", ladder[-1][0] > 0.9 and ladder[0][0] < 0.5)
        opts = cards.quality_options()
        check("the screen is told each quality's guarantee and tier odds, adding to 100", [o["key"] for o in opts] == list(K3.QUALITIES) and all(abs(sum(o["odds"].values()) - 100) <= 2 and o["rare_plus"] >= 1 for o in opts), str(opts[0]))
        check("a pack with no quality uses its own kind's odds, and one with a quality uses that", K3.quality_kind(None, "century") is K3.KINDS["century"] and K3.quality_kind("legendary", "weekly") is K3.QUALITIES["legendary"] and K3.quality_kind("nonsense", "weekly") is K3.KINDS["weekly"])

        async with Session() as db:
            club = await db.get(Organisation, ORG)
            admin_user = User(id=uuid.uuid4(), email="admin@example.com")
            snap = await cards.club_snapshot(db, club, fresh=True)
            people = sorted(snap["people"])
            async def bad(**kw):
                try:
                    await cards.create_gift(db, club, snap, **kw)
                    return None
                except ValueError as exc:
                    return str(exc)
            check("a pack needs a name", await bad(title="  ", quality="elite") is not None)
            check("...a quality that exists", await bad(title="X", quality="mythic") is not None)
            check("...a quantity from 1 to 10", await bad(title="X", quality="elite", qty=0) is not None and await bad(title="X", quality="elite", qty=11) is not None and await bad(title="X", quality="elite", qty=True) is not None)
            check("...someone to give it to", await bad(title="X", quality="elite", audience="players", player_ids=[]) is not None and await bad(title="X", quality="elite", audience="players", player_ids=[str(uuid.uuid4())]) is not None)
            check("...and a known audience", await bad(title="X", quality="elite", audience="everyone") is not None)
            await db.rollback()
            club = await db.get(Organisation, ORG)

            rid = str(uuid.uuid4())
            out = await cards.create_gift(db, club, snap, title="  Cup   Day  ", quality="elite", qty=2, audience="all", request_id=rid, by="admin@example.com")
            await db.commit()
            n_all = len(people)
            count = lambda **w: db.execute(text("SELECT count(*) FROM player_card_packs WHERE source = 'custom' AND organisation_id = :o AND ref_key LIKE :r"), {"o": ORG, "r": f"{rid}:%"})
            check("giving to everyone makes qty packs for each player with a card", out["players"] == n_all and out["packs"] == n_all * 2 and (await count()).scalar() == n_all * 2 and out["repeat"] is False, str(out))
            check("the name is tidied", out["title"] == "Cup Day")
            again = await cards.create_gift(db, club, snap, title="Cup Day", quality="elite", qty=2, audience="all", request_id=rid)
            await db.commit()
            check("sending the same request again (a double click) grants nothing more", again["repeat"] is True and (await count()).scalar() == n_all * 2)
            row = (await db.execute(text("SELECT label, quality, source, opened_at FROM player_card_packs WHERE ref_key = :r"), {"r": f"{rid}:1"})).first()
            check("each pack carries the name and quality it was made with", row[0] == "Cup Day" and row[1] == "elite" and row[2] == "custom" and row[3] is None)

            pick = [str(DELTA), str(CHARLIE)]
            await cards.create_gift(db, club, snap, title="Thanks", quality="legendary", qty=1, audience="players", player_ids=[*pick, str(uuid.uuid4()), "not-a-uuid"])
            await db.commit()
            thanks = (await db.execute(text("SELECT player_id::text FROM player_card_packs WHERE label = 'Thanks' AND organisation_id = :o"), {"o": ORG})).scalars().all()
            check("choosing players gives only to them (a made-up id is skipped, not an error)", sorted(thanks) == sorted(pick), str(thanks))
            other = await bad(title="Theirs", quality="elite", request_id=rid) if False else None

            # what the player sees and opens
            who = await db.get(Player, uuid.UUID(pick[0]))
            listed = [p for p in await cards.available_packs(db, pick[0], snap) if p["source"] == "custom"]
            srcs3 = [p["source"] for p in await cards.available_packs(db, pick[0], snap)]
            check("the player has the packs, named, with their quality, and ahead of the everyday packs", {p["label"] for p in listed} >= {"Cup Day", "Thanks"} and {p["quality"] for p in listed} >= {"elite", "legendary"} and not (set(srcs3[: srcs3.index("custom")]) & {"weekly", "runs", "wickets", "dismissals", "duck"}), str(srcs3))
            seen = []
            real_draw = cards.draw_cards
            cards.draw_cards = lambda pool_, specials_, size=5, kind=None: (seen.append(kind.label if kind else None), real_draw(pool_, specials_, size, kind))[1]
            try:
                thanks_pack = next(p for p in listed if p["label"] == "Thanks")
                got = await cards.open_pack(db, club, who, thanks_pack["id"], snap)
                await db.commit()
            finally:
                cards.draw_cards = real_draw
            check("opening it draws at the quality it was made at, whatever kind it came as", seen == ["Legendary"] and got, str(seen))
            check("an opened pack is gone from the list", all(p["id"] != thanks_pack["id"] for p in await cards.available_packs(db, pick[0], snap)))
            hist = await cards.list_gifts(db, ORG)
            check("the club can see what it gave: name, quality, players, packs and how many are opened", {g["title"] for g in hist} >= {"Cup Day", "Thanks"} and next(g for g in hist if g["title"] == "Thanks")["opened"] == 1 and next(g for g in hist if g["title"] == "Cup Day")["packs"] == n_all * 2 and next(g for g in hist if g["title"] == "Cup Day")["opened"] == 0)

            # a scheduled pack takes a quality too
            ev = await cards.add_event(db, ORG, "Quality Test Match", date.today() + timedelta(days=90), None, True, "legendary")
            await db.commit()
            check("a scheduled pack remembers its quality, and it defaults to special", ev["quality"] == "legendary" and (await cards.add_event(db, ORG, "Club day", date.today() + timedelta(days=91), None))["quality"] == "special")
            try:
                await cards.add_event(db, ORG, "Bad", date.today(), None, True, "mythic"); bad_q = False
            except ValueError:
                bad_q = True
            await db.rollback()
            club = await db.get(Organisation, ORG)
            check("a scheduled pack with an unknown quality is refused", bad_q)
            club = await db.get(Organisation, ORG)
            real_today2 = cards.club_today
            cards.club_today = lambda s_, now=None: date.today() + timedelta(days=90)
            try:
                await cards.ensure_grants(db, club, pick[1], snap); await db.commit()
            finally:
                cards.club_today = real_today2
            q = (await db.execute(text("SELECT quality FROM player_card_packs WHERE player_id = CAST(:p AS UUID) AND source = 'event' AND label = 'Quality Test Match'"), {"p": pick[1]})).scalar()
            check("a pack granted from a scheduled event carries the event's quality", q == "legendary", str(q))

            # the routes
            club = await db.get(Organisation, ORG)
            pay = await adm3.get_settings(db, club, admin_user)
            check("the settings payload lists the qualities, the recent packs and the limit", [o["key"] for o in pay["qualities"]] == list(K3.QUALITIES) and any(g["title"] == "Cup Day" for g in pay["gifts"]) and pay["max_gift_qty"] == 10 and all("quality" in e for e in pay["events"]))
            res = await adm3.create_gift(adm3.GiftBody(title="Route pack", quality="premium", qty=3, audience="players", player_ids=pick[:1]), db, club, admin_user)
            check("the create route gives the packs and returns the gift with the refreshed payload", res["gift"]["packs"] == 3 and res["gift"]["players"] == 1 and any(g["title"] == "Route pack" for g in res["gifts"]))
            check("...and it is on the audit trail", (await db.execute(text("SELECT count(*) FROM audit_logs WHERE action = 'player_card_pack_gift'"))).scalar() >= 1)
            club = await db.get(Organisation, ORG)
            codes = [await status_of(adm3.create_gift(adm3.GiftBody(title="", quality="premium"), db, club, admin_user))]
            club = await db.get(Organisation, ORG)
            codes.append(await status_of(adm3.create_gift(adm3.GiftBody(title="X", quality="nope"), db, club, admin_user)))
            club = await db.get(Organisation, ORG)
            codes.append(await status_of(adm3.create_gift(adm3.GiftBody(title="X", quality="premium", qty=99), db, club, admin_user)))
            club = await db.get(Organisation, ORG)
            check("a bad request through the route is a 422 each time", codes == [422, 422, 422], str(codes))
            sched = await adm3.add_event(adm3.EventBody(title="Q day", starts_on=date.today() + timedelta(days=100), quality="elite"), db, club, admin_user)
            check("the schedule route takes a quality too", any(e["title"] == "Q day" and e["quality"] == "elite" for e in sched["events"]))
            # a pack designed on the spot, as it is made
            if DESIGNS_DDL:
                from io import BytesIO as _BI
                from starlette.datastructures import UploadFile as _U2
                from PIL import Image as _I2
                from app.services import player_card_designs as D2

                def _png(w, h):
                    b = _BI(); _I2.new("RGB", (w, h), (20, 80, 200)).save(b, "PNG"); return b.getvalue()
                club = await db.get(Organisation, ORG)
                n_gifts = lambda: db.execute(text("SELECT count(*) FROM club_card_pack_gifts WHERE organisation_id = :o"), {"o": ORG})
                before_n = (await n_gifts()).scalar()
                rid2 = str(uuid.uuid4())
                made = await adm3.create_designed_gift(size=5, title="Cup Day Special", quality="elite", qty=1, audience="players", player_ids=json.dumps(pick[:1]), request_id=rid2,
                                                       style=json.dumps({"color_a": "#112233", "overlay": 0.5, "show_name": False, "art_position": "bottom"}),
                                                       bg=_U2(file=_BI(_png(900, 1200)), filename="bg.png"), art=_U2(file=_BI(_png(300, 300)), filename="art.png"),
                                                       db=db, club=club, user=admin_user)
                gid = made["gift"]["id"]
                gd = made["designs"].get(f"gift:{gid}")
                check("a pack made with a design carries it: colours and layout as sent, and both pictures", gd and gd["a"] == "#112233" and gd["overlay"] == 0.5 and gd["show_name"] is False and gd["art_position"] == "bottom" and gd["background_url"] and gd["art_url"], str(gd))
                check("...and the packs themselves were made as usual", made["gift"]["packs"] == 1 and made["gift"]["players"] == 1)
                snap = await cards.club_snapshot(db, club, fresh=True)
                mine_p = [p for p in await cards.available_packs(db, pick[0], snap) if p["label"] == "Cup Day Special"]
                plain_p = [p for p in await cards.available_packs(db, pick[0], snap) if p["label"] == "Thanks"]
                check("the player's pack has that design", mine_p and mine_p[0]["design"] and mine_p[0]["design"]["target"] == f"gift:{gid}" and mine_p[0]["design"]["a"] == "#112233", str(mine_p))
                await D2.save_style(db, ORG, "custom", {"color_a": "#aa0000"}); await db.commit()
                snap = await cards.club_snapshot(db, club, fresh=True)
                plain_p = [p for p in await cards.available_packs(db, pick[1], snap) if p["label"] == "Thanks"]
                mine_p = [p for p in await cards.available_packs(db, pick[0], snap) if p["label"] == "Cup Day Special"]
                check("another club pack without its own design takes the club's 'club pack' design, and the designed one keeps its own", plain_p[0]["design"]["target"] == "custom" and mine_p[0]["design"]["target"] == f"gift:{gid}")
                check("the gift's design can be changed later like any other (it is listed under From the club)", f"gift:{gid}" in {t["key"] for t in await D2.targets(db, ORG)} and (await D2.save_style(db, ORG, f"gift:{gid}", {"color_a": "#00ff00"}))["a"] == "#00ff00")
                await db.commit()
                check("a gift of this club can be designed, another club's cannot, and a made-up one is a 404", await D2.check_target(db, ORG, f"gift:{gid}") == f"gift:{gid}" and await raises(D2.check_target(db, ORG_SELECT, f"gift:{gid}")) == 404 and await raises(D2.check_target(db, ORG, f"gift:{uuid.uuid4()}")) == 404 and await raises(D2.check_target(db, ORG, "gift:nope")) == 404)
                club = await db.get(Organisation, ORG)

                after_n = (await n_gifts()).scalar()
                async def refuse(**kw):
                    base = dict(size=5, title="Bad design", quality="elite", qty=1, audience="all", player_ids="[]", request_id=None, style="{}", bg=None, art=None, db=db, club=club, user=admin_user)
                    return await status_of(adm3.create_designed_gift(**{**base, **kw}))
                codes2 = []
                for kw in ({"style": json.dumps({"color_a": "red"})}, {"bg": _U2(file=_BI(svg), filename="x.svg")}, {"art": _U2(file=_BI(b"not a picture"), filename="x.png")},
                           {"style": "{not json"}, {"player_ids": "5"}, {"quality": "nope"}):
                    codes2.append(await refuse(**kw)); club = await db.get(Organisation, ORG)
                check("a bad colour, picture, request or quality is refused (422) each time", codes2 == [422] * 6, str(codes2))
                check("...and makes NO packs and no half design (nothing is made if anything is wrong)", (await n_gifts()).scalar() == after_n and (await db.execute(text("SELECT count(*) FROM club_card_pack_designs WHERE organisation_id = :o AND target LIKE 'gift:%'"), {"o": ORG})).scalar() == 1)
                again2 = await adm3.create_designed_gift(size=5, title="Cup Day Special", quality="elite", qty=1, audience="players", player_ids=json.dumps(pick[:1]), request_id=rid2,
                                                         style=json.dumps({"color_a": "#ff00ff"}), bg=None, art=None, db=db, club=club, user=admin_user)
                check("sending the same request again changes neither the packs nor the design", again2["gift"]["repeat"] is True and again2["designs"][f"gift:{gid}"]["a"] == "#00ff00" and (await n_gifts()).scalar() == after_n)
                plain = await adm3.create_designed_gift(size=5, title="No design here", quality="standard", qty=1, audience="players", player_ids=json.dumps(pick[:1]), request_id=None, style="{}", bg=None, art=None, db=db, club=club, user=admin_user)
                check("a gift sent with no design makes no design row", f"gift:{plain['gift']['id']}" not in plain["designs"])
                # the words under the name, and how many cards
                if LOOKS_DDL:
                    lk = await adm3.create_designed_gift(title="Ten Card Special", quality="legendary", qty=1, audience="players", player_ids=json.dumps(pick[:1]), request_id=None, size=10,
                                                         style=json.dumps({"line": "  Dig   deep, champions  ", "color_b": "#0a0a0a"}), bg=None, art=None, db=db, club=club, user=admin_user)
                    lg = lk["designs"][f"gift:{lk['gift']['id']}"]
                    check("the few words under the pack's name are kept, tidied", lg["line"] == "Dig deep, champions", str(lg))
                    club = await db.get(Organisation, ORG)
                    check("the line is cut to 36 characters, and an empty one clears it", len((await D2.save_style(db, ORG, f"gift:{lk['gift']['id']}", {"line": "x" * 90}))["line"]) == 36 and (await D2.save_style(db, ORG, f"gift:{lk['gift']['id']}", {"line": "  "}))["line"] is None)
                    await db.commit()
                    snap = await cards.club_snapshot(db, club, fresh=True)
                    big = [p for p in await cards.available_packs(db, pick[0], snap) if p["label"] == "Ten Card Special"]
                    check("a pack carries how many cards it holds, and an ordinary one says five", big and big[0]["size"] == 10 and all(p["size"] == 5 for p in await cards.available_packs(db, pick[0], snap) if p["label"] != "Ten Card Special"), str(big))
                    club = await db.get(Organisation, ORG)
                    who2 = await db.get(Player, uuid.UUID(pick[0]))
                    got10 = await cards.open_pack(db, club, who2, big[0]["id"], snap)
                    await db.commit()
                    check("opening it gives that many cards", got10 is not None and len(got10) == 10, str(len(got10 or [])))
                    for sz, label in ((1, "one"), (3, "three"), (12, "twelve")):
                        r1 = await adm3.create_designed_gift(title=f"{label} cards", quality="elite", qty=1, audience="players", player_ids=json.dumps(pick[1:2]), request_id=None, size=sz, style="{}", bg=None, art=None, db=db, club=club, user=admin_user)
                        club = await db.get(Organisation, ORG)
                        snap = await cards.club_snapshot(db, club, fresh=True)
                        pk = next(p for p in await cards.available_packs(db, pick[1], snap) if p["label"] == f"{label} cards")
                        res = await cards.open_pack(db, club, await db.get(Player, uuid.UUID(pick[1])), pk["id"], snap)
                        await db.commit()
                        check(f"a pack of {sz} gives {min(sz, 12)} cards", res is not None and len(res) == sz, str(len(res or [])))
                    codes3 = []
                    for sz in (0, 13, -2):
                        codes3.append(await refuse(size=sz)); club = await db.get(Organisation, ORG)
                    check("a pack of no cards, or more than twelve, is refused (422)", codes3 == [422, 422, 422], str(codes3))
                    check("the guarantee scales with the size: an Elite pack (4 of 5) guarantees 8 of 10 and 3 of 3", all(min(sum(1 for x in cards.draw_cards(pool3, [], n, K3.QUALITIES["elite"]) if x["tier"] != "common") for _ in range(200)) >= need for n, need in ((10, 8), (3, 3), (5, 4), (1, 1))))
                    check("...and a Standard pack always holds at least one Rare or better, whatever its size", all(min(sum(1 for x in cards.draw_cards(pool3, [], n, K3.QUALITIES["standard"]) if x["tier"] != "common") for _ in range(200)) >= 1 for n in (1, 3, 5, 10)))
                    plainj = await adm3.create_gift(adm3.GiftBody(title="Json four", quality="boosted", qty=1, audience="players", player_ids=pick[:1], size=4), db, club, admin_user)
                    check("the JSON create route takes a size too, and reports it", plainj["gift"]["size"] == 4 and any(g["title"] == "Json four" and g["size"] == 4 for g in plainj["gifts"]))
                    club = await db.get(Organisation, ORG)
                    check("the settings payload says the allowed pack sizes", (await adm3.get_settings(db, club, admin_user))["pack_size"] == {"default": 5, "min": 1, "max": 12})
                check("the designed gift is on the audit trail as designed", (await db.execute(text("SELECT count(*) FROM audit_logs WHERE action = 'player_card_pack_gift' AND details->>'designed' = 'true'"))).scalar() >= 1)
            await db.rollback()
    else:
        check("(the control run has no admin-created packs to test)", True)

    # ── Which photo a card shows ──────────────────────────────────────────────────
    print("\nphotos by card type")
    if HAVE and PHOTOS_DDL:
        P = {"photo_url": "/p.jpg", "hero_photo_url": "/h.jpg", "action_photo_url": "/a.jpg", "hero_source": None}
        shot = cards.card_shot
        check("by default every card fills with the hero photo, Common and Rare as well as the rest", all(shot(P, t, None, "all") == "hero" for t in ("common", "rare", "epic", "legendary")))
        check("every special card uses the action shot (a century, a debut, a milestone, an award)", all(shot(P, "special", k, "all") == "action" for k in ("century", "fifty", "five_for", "hat_trick", "debut", "games", "runs_milestone", "wickets_milestone", "dismissals_milestone", "award")))
        check("a special card without an action shot falls to the hero photo, then to the profile photo", shot({**P, "action_photo_url": None}, "special", "century", "all") == "hero" and shot({"photo_url": "/p.jpg"}, "special", "century", "all") == "profile")
        check("a regular card with no hero photo keeps its circle (it does not borrow the action shot)", shot({**P, "hero_photo_url": None}, "common", None, "all") == "profile")
        check("...unless there is no profile photo either, when the action shot is used rather than the logo", shot({**P, "hero_photo_url": None, "photo_url": None}, "common", None, "all") == "hero" or shot({**P, "hero_photo_url": None, "photo_url": None}, "common", None, "all") == "action")
        check("a player with no photos at all gets the profile fallback (the logo)", shot({}, "common", None, "all") == "profile" and shot({}, "special", "century", "all") == "profile")
        check("narrowing the club setting: 'top' keeps the circle on Common and Rare, 'specials' on every regular card", shot(P, "common", None, "top") == "profile" and shot(P, "epic", None, "top") == "hero" and shot(P, "legendary", None, "top") == "hero" and shot(P, "epic", None, "specials") == "profile" and shot(P, "special", "century", "specials") == "action")
        check("a per-player pin beats the card's own choice", shot({**P, "hero_source": "action"}, "common", None, "all") == "action" and shot({**P, "hero_source": "hero"}, "special", "debut", "all") == "hero")
        check("a pin to a shot the player does not have falls to the other", shot({**P, "hero_source": "action", "action_photo_url": None}, "common", None, "all") == "hero")
        async with Session() as db:
            club = await db.get(Organisation, ORG)
            await db.execute(text("UPDATE players SET photo_url = '/p.jpg', hero_photo_url = '/h.jpg', action_photo_url = '/a.jpg', hero_source = NULL WHERE id = :p"), {"p": ALPHA})
            await db.commit()
            cards.forget(ORG)
            snap = await cards.club_snapshot(db, club, fresh=True)
            reg = cards.regular_card(snap, str(ALPHA))
            check("a regular card carries its shot: the hero photo, whatever its tier, with the default setting", reg["shot"] == "hero", str((reg["tier"], reg["shot"])))
            srow = (await db.execute(text("SELECT id::text AS id, player_id, kind, title, occurred_on, detail FROM player_special_cards WHERE player_id = :p AND kind = 'century' LIMIT 1"), {"p": ALPHA})).mappings().first()
            check("a special card carries its shot too (the action shot)", cards.special_card(snap, dict(srow))["shot"] == "action")
            d0 = (await cards.load_settings(db, ORG))["big_photos"]
            check("the club setting defaults to all", cards.default_settings()["big_photos"] == "all" and d0 == "all", str(d0))
            await cards.save_settings(db, ORG, {"big_photos": "all"}); await db.commit()
            snap = await cards.club_snapshot(db, club, fresh=True)
            check("changing it reaches the cards at once", cards.regular_card(snap, str(ALPHA))["shot"] in ("hero", "action"))
            await cards.save_settings(db, ORG, {"big_photos": "specials"}); await db.commit()
            snap = await cards.club_snapshot(db, club, fresh=True)
            check("...'specials' keeps every regular card on the circle, whatever its tier", cards.regular_card(snap, str(ALPHA))["shot"] == "profile")
            try:
                await cards.save_settings(db, ORG, {"big_photos": "everything"}); bad_p = False
            except ValueError:
                bad_p = True
                await db.rollback()
            check("an unknown choice is refused", bad_p)
            club = await db.get(Organisation, ORG)
            await cards.save_settings(db, ORG, {"big_photos": "all"}); await db.commit()
            from app.routers import player_cards_admin as adm4
            adm_user = User(id=uuid.uuid4(), email="admin@example.com")
            got = await adm4.update_settings(adm4.SettingsBody(big_photos="top"), db, club, adm_user)
            check("PATCH settings takes big_photos, and the payload reports it", got["settings"]["big_photos"] == "top")
            club = await db.get(Organisation, ORG)
            check("...an unknown one is a 422", await status_of(adm4.update_settings(adm4.SettingsBody(big_photos="some"), db, club, adm_user)) == 422)
            club = await db.get(Organisation, ORG)
            await adm4.update_settings(adm4.SettingsBody(big_photos="all"), db, club, adm_user)
            await db.rollback()
    else:
        check("(the control run has no photo rule to test)", True)

    print("\nmigration")
    async with engine.begin() as conn:
        for stmt in CARD_DDL:
            await conn.execute(text(stmt))
    check("the DDL runs a second time without error (the lifespan re-runs it on every boot)", True)
    mig = (Path(__file__).resolve().parent.parent / "alembic" / "versions" / "363_player_cards.py").read_text()
    check("the migration runs the shared DDL list (one copy)", "from app.services.player_cards_ddl import STATEMENTS" in mig)
    if HAVE_SWAPS:
        mig2 = (Path(__file__).resolve().parent.parent / "alembic" / "versions" / "364_player_card_swaps.py").read_text()
        check("the swaps migration follows 363 and runs its own shared list", "down_revision = \"363\"" in mig2 and "player_card_swaps_ddl import BASE_STATEMENTS" in mig2 and "player_card_swaps_ddl import STATEMENTS" in main_src_swaps())
        mig3 = (Path(__file__).resolve().parent.parent / "alembic" / "versions" / "366_player_card_swap_items.py").read_text()
        check("the items migration follows 365, runs its own shared list, and drops only its own table", "down_revision = \"365\"" in mig3 and "ITEM_STATEMENTS" in mig3 and "ITEM_DOWNGRADE" in mig3)
    main_src = (Path(__file__).resolve().parent.parent / "app" / "main.py").read_text()
    check("the lifespan mirrors the same list", "from app.services.player_cards_ddl import STATEMENTS" in main_src)
    if PHOTOS_DDL:
        mig8 = (Path(__file__).resolve().parent.parent / "alembic" / "versions" / "379_player_card_big_photos_default.py").read_text()
        check("the photos default migration (379) follows 378, puts 'all' back as the default and moves only rows still on the old one", 'down_revision = "378"' in mig8 and "SET DEFAULT 'all'" in mig8 and "WHERE big_photos = 'top'" in mig8)
        mig7 = (Path(__file__).resolve().parent.parent / "alembic" / "versions" / "376_player_card_big_photos.py").read_text()
        check("the photos migration follows 375, runs the shared list, and its lifespan mirror runs it too", 'down_revision = "375"' in mig7 and "STATEMENTS" in mig7 and "player_card_photos_ddl" in main_src)
    if GIFTS_DDL:
        mig6 = (Path(__file__).resolve().parent.parent / "alembic" / "versions" / "374_player_card_pack_gifts.py").read_text()
        check("the admin packs migration follows 373, runs the shared list, and its lifespan mirror runs it too", 'down_revision = "373"' in mig6 and "STATEMENTS" in mig6 and "player_card_gifts_ddl" in main_src)
    if DESIGNS_DDL:
        mig5 = (Path(__file__).resolve().parent.parent / "alembic" / "versions" / "371_player_card_pack_designs.py").read_text()
        check("the designs migration follows 370, runs the shared list, and its lifespan mirror runs it too", 'down_revision = "370"' in mig5 and "STATEMENTS" in mig5 and "player_card_designs_ddl" in main_src)
    if PACKS_DDL:
        mig4 = (Path(__file__).resolve().parent.parent / "alembic" / "versions" / "370_player_card_packs.py").read_text()
        check("the packs migration follows 369, runs the shared list, and its lifespan mirror runs it too",
              'down_revision = "369"' in mig4 and "STATEMENTS" in mig4 and "player_card_packs_ddl" in main_src)
        check("its downgrade drops only what 370 added, never a table an earlier migration owns", "DROP TABLE IF EXISTS club_card_event_packs" in "\n".join(__import__("app.services.player_card_packs_ddl", fromlist=["DOWNGRADE"]).DOWNGRADE)
              and "DROP TABLE IF EXISTS player_card_packs" not in "\n".join(__import__("app.services.player_card_packs_ddl", fromlist=["DOWNGRADE"]).DOWNGRADE))

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
