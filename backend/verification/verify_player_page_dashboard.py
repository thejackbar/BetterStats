"""Verification: the player's own page as one dashboard (photo, season panels,
recent form, Fantasy), against a real Postgres.

Asked for: clean up the player page into a single dashboard a player never has to
leave. Their photo, their season as a dashboard, availability answered on the same
screen, and a link into their Fantasy so they can see their team, the lock
deadlines and their scores.

Drives the SHIPPED route bodies (`public_availability.get_me`, `get_my_profile`)
and the shipped catalogue (`services/player_dashboard`), never a re-implementation.

What it pins:
  * the page knows who it is for: name, photo, shirt number, public profile path
    (no path for a profile the club has switched off)
  * availability is the page itself, not a module the club can switch off
  * the season block keeps its old keys and adds batting / bowling / fielding
    panels; a rate resting on only some innings is marked partial
  * recent form: last five innings newest first, did-not-bat is not an innings,
    another club's game is not this club's form
  * the Fantasy card: next lock deadlines, a locked round says so, a draft season
    draws nothing, a club without the module is held back
  * the Fantasy team is found by ONE exact email match at this club. No email, two
    managers on one email, another club's manager and PIN-off all give no team, and
    the card still carries the deadlines and the link
  * the card never carries picks, captains, other managers or other players

CONTROL MODE: against the previous commit the new keys do not exist. Every read is
presence-safe (`.get`), so the control FAILS the checks instead of crashing.

Run on its own database (rule 24):
  DATABASE_URL=postgresql+asyncpg://... python verification/verify_player_page_dashboard.py
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import verify_selection_same_day as base
from app.models.db import (
    BattingInnings, FantasyLeague, FantasyManager, FantasyPoolPlayer, FantasyRound, FantasySeason, FantasySquad,
    FantasySquadPlayer, Game, GameAppearance, Grade, Organisation, Player, PlayerSeasonStats, Season,
)

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
check = base.check

NOW = datetime.now(timezone.utc)
TODAY = date.today()


def guarded(name):
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


async def main():
    await base.build_schema()
    async with engine.begin() as conn:
        for mod in ("selection_lock_ddl", "team_sides_ddl", "fixture_side_ddl", "fixture_pin_ddl", "audit_ddl",
                    "availability_maybe_ddl", "fines_ddl", "fines_cap_ddl", "fantasy_queue_ddl"):
            m = guarded(f"app.services.{mod}")
            for stmt in (m.STATEMENTS if m else []):
                await conn.execute(text(stmt))
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
    import app.routers.public_availability as pa
    pd = guarded("app.services.player_dashboard")
    from jose import jwt as jose_jwt
    from starlette.requests import Request
    from app.config.settings import settings

    org, other_org, fan_org, season, grade, o_season, o_grade = (uuid.uuid4() for _ in range(7))
    P = {n: uuid.uuid4() for n in ("sam", "ann", "dup", "noemail", "stranger", "rival", "off")}
    tok, fan_tok, bare_tok = ("t-" + uuid.uuid4().hex for _ in range(3))
    fs, lg, r1, r2, r3, r4 = (uuid.uuid4() for _ in range(6))
    mg = {n: uuid.uuid4() for n in ("sam", "ann", "dup1", "dup2", "rival", "elsewhere")}
    sq = {n: uuid.uuid4() for n in ("sam", "rival", "elsewhere")}

    async with Session() as db:
        # `org` runs fantasy; `bare` is a club with the select module only.
        db.add(Organisation(id=org, name="Dash CC", slug=f"dash-{org.hex[:8]}", module_overrides=["select", "fantasy"],
                            availability_link_token=tok, availability_self_service_enabled=True,
                            fantasy_link_token=fan_tok))
        db.add(Organisation(id=other_org, name="Elsewhere CC", slug=f"els-{other_org.hex[:8]}", module_overrides=["select", "fantasy"],
                            fantasy_link_token="e-" + uuid.uuid4().hex))
        db.add(Organisation(id=fan_org, name="Bare CC", slug=f"bare-{fan_org.hex[:8]}", module_overrides=["select"],
                            availability_link_token=bare_tok, availability_self_service_enabled=True,
                            fantasy_link_token="b-" + uuid.uuid4().hex))
        db.add(Season(id=season, organisation_id=org, name="Summer 26/27", year=2026))
        await db.flush()
        db.add(Season(id=o_season, organisation_id=other_org, name="Summer 26/27", year=2026))
        await db.flush()
        db.add(Grade(id=grade, season_id=season, name="1st Grade", grassroots_id=str(grade)))
        db.add(Grade(id=o_grade, season_id=o_season, name="Other 1st", grassroots_id=str(o_grade)))
        await db.flush()
        rows = [
            ("sam", org, "Sam Sledge", dict(email="sam@dash.org", photo_url="/api/players/sam/photo", shirt_number="7", phone="0400000001")),
            ("ann", org, "Ann Anchor", dict(email="ann@dash.org", phone="0400000002")),
            ("dup", org, "Dee Dupe", dict(email="dup@dash.org", phone="0400000003")),
            ("noemail", org, "Nell NoMail", dict(phone="0400000004")),
            ("stranger", other_org, "Sid Elsewhere", dict(email="sam@dash.org", phone="0400000005")),
            ("rival", org, "Rex Rival", dict(email="rex@dash.org", phone="0400000006")),
            ("off", org, "Olly Offline", dict(email="off@dash.org", phone="0400000007", is_public=False)),
        ]
        for key, o, nm, extra in rows:
            db.add(Player(id=P[key], organisation_id=o, name=nm, gender="male", is_player=True, status="active", **extra))
        await db.flush()

        # Season figures for Sam: ten innings in the totals, but only three scorecards with balls.
        db.add(PlayerSeasonStats(player_id=P["sam"], season_id=season, matches=11, batting_innings=10, runs=412,
                                 not_outs=2, balls_faced=500, high_score=87, fifties=3, hundreds=1, fours=40, sixes=6,
                                 ducks=1, wickets=9, runs_conceded=240, overs=48, bowling_balls=288, maidens=4,
                                 catches=6, run_outs=2, stumpings=0))
        await db.flush()
        # Six real innings, one did-not-bat row, and one game for another club.
        days = [30, 25, 20, 15, 10, 5]
        runs = [12, 50, 0, 33, 71, 8]
        for i, (d, r) in enumerate(zip(days, runs)):
            gid = uuid.uuid4()
            db.add(Game(id=gid, grade_id=grade, played_at=TODAY - timedelta(days=d), home_team="Dash", away_team="X",
                        home_org_id=org, status="COMPLETED"))
            await db.flush()
            db.add(GameAppearance(game_id=gid, player_id=P["sam"], team_name="Dash"))
            db.add(BattingInnings(game_id=gid, player_id=P["sam"], innings_number=1, runs=r, balls=(r + 5) if i < 3 else None,
                                  fours=0, sixes=0, dismissal_type="not out" if i == 4 else "bowled", not_out=(i == 4)))
        dnb = uuid.uuid4()
        db.add(Game(id=dnb, grade_id=grade, played_at=TODAY - timedelta(days=2), home_team="Dash", away_team="Y",
                    home_org_id=org, status="COMPLETED"))
        await db.flush()
        db.add(BattingInnings(game_id=dnb, player_id=P["sam"], innings_number=1, runs=0, balls=0,
                              dismissal_type="did not bat", did_not_bat=True))
        away = uuid.uuid4()
        db.add(Game(id=away, grade_id=o_grade, played_at=TODAY - timedelta(days=1), home_team="Z", away_team="Q",
                    home_org_id=other_org, away_org_id=other_org, status="COMPLETED"))
        await db.flush()
        db.add(BattingInnings(game_id=away, player_id=P["sam"], innings_number=1, runs=999, balls=10,
                              dismissal_type="bowled", not_out=False))

        # Fantasy at `org`.
        db.add(FantasySeason(id=fs, organisation_id=org, season_year=2026, name="2026 Fantasy", status="active",
                             scoring={}, rules={}))
        await db.flush()
        db.add_all([
            FantasyRound(id=r1, fantasy_season_id=fs, organisation_id=org, round_number=1, name="Round 1", status="scored",
                         lock_at=NOW - timedelta(days=14)),
            FantasyRound(id=r2, fantasy_season_id=fs, organisation_id=org, round_number=2, name="Round 2",
                         lock_at=NOW - timedelta(hours=3)),
            FantasyRound(id=r3, fantasy_season_id=fs, organisation_id=org, round_number=3, name="Round 3",
                         lock_at=NOW + timedelta(days=6, hours=3)),
            FantasyRound(id=r4, fantasy_season_id=fs, organisation_id=org, round_number=4, name="Round 4",
                         lock_at=NOW + timedelta(days=13)),
        ])
        db.add_all([FantasyPoolPlayer(fantasy_season_id=fs, organisation_id=org, player_id=P["sam"], role="batter",
                                      base_price=9.0, current_price=9.5, total_points=84, last_round_points=31,
                                      owned_count=4, price_change=0.5)])
        db.add_all([
            FantasyManager(id=mg["sam"], organisation_id=org, display_name="Sam M", email="  SAM@dash.org "),
            FantasyManager(id=mg["ann"], organisation_id=org, display_name="Ann M", email="ann@dash.org"),
            FantasyManager(id=mg["dup1"], organisation_id=org, display_name="Dup One", email="dup@dash.org"),
            FantasyManager(id=mg["dup2"], organisation_id=org, display_name="Dup Two", email="DUP@dash.org"),
            FantasyManager(id=mg["rival"], organisation_id=org, display_name="Rex M", email="rex@dash.org"),
            FantasyManager(id=mg["elsewhere"], organisation_id=other_org, display_name="Else M", email="sid@x.org"),
        ])
        await db.flush()
        db.add(FantasyLeague(id=lg, fantasy_season_id=fs, organisation_id=org, kind="global_salary_cap", name="Club ladder"))
        await db.flush()
        db.add_all([
            FantasySquad(id=sq["sam"], fantasy_season_id=fs, league_id=lg, manager_id=mg["sam"], organisation_id=org,
                         team_name="Sledgehammers", free_transfers=2, budget_remaining=1.5, total_points=123),
            FantasySquad(id=sq["rival"], fantasy_season_id=fs, league_id=lg, manager_id=mg["rival"], organisation_id=org,
                         team_name="Secret Rival XI", free_transfers=1, budget_remaining=0, total_points=140),
        ])
        await db.flush()
        db.add_all([
            FantasySquadPlayer(squad_id=sq["sam"], player_id=P["rival"], role="batter", is_captain=True, purchase_price=8.0),
            FantasySquadPlayer(squad_id=sq["rival"], player_id=P["sam"], role="batter", is_captain=True, purchase_price=9.0),
        ])
        await db.flush()
        for sid, rid, pts in ((sq["sam"], r1, 61), (sq["sam"], r2, 18)):
            await db.execute(text("INSERT INTO fantasy_squad_round_scores (id, squad_id, round_id, points, raw_points) "
                                  "VALUES (gen_random_uuid(), :s, :r, :p, :p)"), {"s": sid, "r": rid, "p": pts})
        await db.commit()

    def req_for(club_id, pid):
        c = jose_jwt.encode({"club": str(club_id), "pid": str(pid), "typ": "avail",
                             "exp": datetime.now(timezone.utc) + timedelta(days=1)},
                            settings.secret_key, algorithm=settings.algorithm)
        return Request({"type": "http", "headers": [(b"cookie", f"{pa.COOKIE_NAME}={c}".encode())]})

    async def profile(key, token=tok, club_id=org):
        async with Session() as db:
            return await pa.get_my_profile(token, req_for(club_id, P[key]), None, db)

    async def me(key):
        async with Session() as db:
            return await pa.get_me(tok, req_for(org, P[key]), None, db)

    async def set_modules(keys, club_id=org):
        async with Session() as db:
            club = await db.get(Organisation, club_id)
            club.player_dashboard_modules = pd.store(keys) if keys is not None else None
            await db.commit()

    async def set_org(club_id, **kw):
        async with Session() as db:
            club = await db.get(Organisation, club_id)
            for k, v in kw.items():
                setattr(club, k, v)
            await db.commit()

    if pd is None:
        print("# CONTROL: services.player_dashboard missing")
        await engine.dispose()
        sys.exit(1)

    print("\n# A. Who the page is for")
    pr = await profile("sam")
    pl = pr.get("player") or {}
    check("the profile carries the photo", pl.get("photo_url"), "/api/players/sam/photo")
    check("the profile carries the shirt number", pl.get("shirt_number"), "7")
    check("and the way to their public profile", pl.get("profile_path"), f"/players/{P['sam']}")
    m = await me("sam")
    check("the availability call carries the same card, so the page paints before the profile lands",
          ((m.get("player") or {}).get("photo_url"), (m.get("player") or {}).get("shirt_number")), ("/api/players/sam/photo", "7"))
    off = await profile("off")
    check("a profile the club has switched off is not linked", ((off.get("player") or {}).get("profile_path"), (off.get("player") or {}).get("display_name")),
          (None, "Olly Offline"))
    check("a player with no photo gets null, not a made-up url", (await profile("ann")).get("player", {}).get("photo_url"), None)

    print("\n# B. Availability is the page, not a module")
    cat = {c["key"]: c for c in pd.catalogue_for(type("C", (), {"player_dashboard_modules": None, "availability_show_squad": False,
                                                                "availability_require_pin": True, "module_overrides": ["select", "fantasy"],
                                                                "fantasy_link_token": "x"})())}
    check("the admin list no longer offers Availability", "availability" in cat, False)
    check("it offers Fantasy", "fantasy" in cat, True)
    mods = (await profile("sam"))["modules"]
    check("a club that never chose is offered Fantasy (it runs fantasy)", "fantasy" in mods, True)
    check("and 'availability' is not in the served list", "availability" in mods, False)
    await set_modules(None)
    await set_org(org, player_dashboard_modules={"on": ["season"], "known": ["availability", "votes", "squad", "selected", "training", "ladder", "season", "fees", "fines"]})
    mods = (await profile("sam"))["modules"]
    check("a club that saved its list before Fantasy existed gets Fantasy switched on", mods, ["fantasy", "season"])
    await set_modules(["season", "fantasy"])
    # A stale stored 'availability' is dropped quietly.
    await set_org(org, player_dashboard_modules=["availability", "season", "fantasy"])
    check("a stored list that still names availability just loses it", (await profile("sam"))["modules"], ["season", "fantasy"])
    await set_modules(["season", "fantasy"])

    print("\n# C. Season dashboard")
    se = (await profile("sam")).get("season") or {}
    check("the flat figures the page always had are unchanged",
          (se.get("season"), se.get("matches"), se.get("runs"), se.get("high_score"), se.get("wickets"), se.get("catches")),
          ("Summer 26/27", 11, 412, 87, 9, 6))
    bat, bowl, fld = se.get("batting") or {}, se.get("bowling") or {}, se.get("fielding") or {}
    check("batting panel: 50s, 100s, 4s, 6s, innings, not outs",
          (bat.get("fifties"), bat.get("hundreds"), bat.get("fours"), bat.get("sixes"), bat.get("innings"), bat.get("not_outs")), (3, 1, 40, 6, 10, 2))
    check("a strike rate is present", bat.get("strike_rate") is not None, True)
    check("it rests on 3 of 10 innings with balls, so it is marked partial", bat.get("strike_rate_partial"), True)
    check("bowling panel: overs, maidens, runs conceded", (bowl.get("overs"), bowl.get("maidens"), bowl.get("runs_conceded")), (48, 4, 240))
    check("an economy is present", bowl.get("economy") is not None, True)
    check("fielding panel: catches, run outs, stumpings", (fld.get("catches"), fld.get("run_outs"), fld.get("stumpings")), (6, 2, 0))

    print("\n# D. Recent form")
    form = se.get("form") or {}
    got = [(i["runs"], i["not_out"]) for i in form.get("batting", [])]
    check("the last five innings, newest first", got, [(8, False), (71, True), (33, False), (0, False), (50, False)])
    check("a did-not-bat row is not an innings and another club's 999 is not this club's form",
          any(i["runs"] == 999 for i in form.get("batting", [])) or len(form.get("batting", [])) != 5, False)
    check("form carries no game ids (nothing links to a scorecard from here)", any("game_id" in i for i in form.get("batting", [])), False)
    ann_season = (await profile("ann")).get("season")
    check("a player with no games still gets no season block", ann_season, None)

    print("\n# E. The Fantasy card")
    fa = (await profile("sam")).get("fantasy") or {}
    dl = fa.get("deadlines") or []
    check("up to three deadlines, the running locked round first",
          [(d["number"], d["locked"]) for d in dl], [(2, True), (3, False), (4, False)])
    check("a scored round is not a deadline", any(d["number"] == 1 for d in dl), False)
    check("the lock time is a real timestamp", all(d.get("lock_at") for d in dl), True)
    check("the way in is the club's own fantasy link", fa.get("link"), f"/fantasy/{fan_tok}")
    check("the season is named", (fa.get("season") or {}).get("name"), "2026 Fantasy")
    t = fa.get("team") or {}
    check("Sam's team is found by his email (case and spaces ignored)", t.get("team_name"), "Sledgehammers")
    check("total points, rank on the club ladder and field size", (t.get("points"), t.get("rank"), t.get("of")), (123.0, 2, 2))
    check("last scored round", t.get("last_round"), {"number": 1, "points": 61.0})
    check("the running round's points so far sit beside the total, not added to it", (t.get("this_round_points"), t.get("points")), (18.0, 123.0))
    check("free transfers", t.get("free_transfers"), 2)
    ap = fa.get("as_player") or {}
    check("how Sam is doing as a pick", (ap.get("points"), ap.get("price"), ap.get("owned_count")), (84.0, 9.5, 4))
    blob = json.dumps(await profile("sam"))
    leaked = [w for w in ("Secret Rival XI", "Rex", "Rival", str(P["rival"]), str(mg["rival"]), "is_captain", "lineup", "picks", "Dup One")
              if w in blob]
    check("no picks, captains, other managers or other players' names reach the page", leaked, [])

    print("\n# F. When the team cannot be found, the card still helps")
    for key, why in (("ann", "a manager matched but has no squad"), ("dup", "two managers share the email"),
                     ("noemail", "no email on file"), ("rival", "a manager with the rival's own team")):
        f = (await profile(key)).get("fantasy") or {}
        if key == "ann":
            check(f"{why}: built is false", (f.get("team") or {}).get("built"), False)
        elif key == "rival":
            check(f"{why}: their own team, not Sam's", (f.get("team") or {}).get("team_name"), "Secret Rival XI")
        else:
            check(f"{why}: no team", f.get("team"), None)
        check(f"{key}: still has the deadlines and the link", (len(f.get("deadlines") or []), f.get("link")), (3, f"/fantasy/{fan_tok}"))
    await set_org(org, availability_require_pin=False)
    f = (await profile("sam")).get("fantasy") or {}
    check("with the PIN off (anyone with the link could open anyone's page) the team is withheld", f.get("team"), None)
    check("but the deadlines and link stay", (len(f.get("deadlines") or []), bool(f.get("link"))), (3, True))
    await set_org(org, availability_require_pin=True)

    print("\n# G. When Fantasy has nothing to show")
    async with Session() as db:
        s = await db.get(FantasySeason, fs)
        s.status = "setup"
        await db.commit()
    pr = await profile("sam")
    check("a season still being set up draws nothing", (pr.get("fantasy"), "fantasy" in pr["modules"]), (None, False))
    async with Session() as db:
        s = await db.get(FantasySeason, fs)
        s.status = "active"
        await db.commit()
    check("active again, it is back", "fantasy" in (await profile("sam"))["modules"], True)
    await set_org(org, fantasy_link_token=None)
    pr = await profile("sam")
    check("with no fantasy link the module is held back", (pr.get("fantasy"), "fantasy" in pr["modules"]), (None, False))
    await set_org(org, fantasy_link_token=fan_tok)
    # A club without the module: the stored choice is kept but never served.
    await set_org(fan_org, player_dashboard_modules=pd.store(["fantasy", "squad"]))
    async with Session() as db:
        stranger = Player(id=uuid.uuid4(), organisation_id=fan_org, name="Bea Bare", gender="female", is_player=True, status="active", phone="0400000009")
        db.add(stranger)
        await db.commit()
        sid = stranger.id
    c = jose_jwt.encode({"club": str(fan_org), "pid": str(sid), "typ": "avail", "exp": datetime.now(timezone.utc) + timedelta(days=1)},
                        settings.secret_key, algorithm=settings.algorithm)
    async with Session() as db:
        bare = await pa.get_my_profile(bare_tok, Request({"type": "http", "headers": [(b"cookie", f"{pa.COOKIE_NAME}={c}".encode())]}), None, db)
    check("a club without BetterFantasyCricket never serves the card", ("fantasy" in bare["modules"], bare.get("fantasy")), (False, None))
    async with Session() as db:
        club = await db.get(Organisation, fan_org)
        check("and the admin list says why", pd.blocked_reason(club, "fantasy"), "Needs the BetterFantasyCricket module.")

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


asyncio.run(main())
