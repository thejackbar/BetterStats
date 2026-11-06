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
    BattingInnings, Fixture, FixtureLineup, FeeMember, FeeMemberSeason, FeePayment, FeeSchedule, FantasyLeague, FantasyManager, FantasyPoolPlayer, FantasyRound, FantasySeason, FantasySquad,
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
                    "availability_maybe_ddl", "availability_site_link_ddl", "player_contact_ddl", "fines_ddl", "fines_cap_ddl", "fantasy_queue_ddl", "player_cards_ddl", "player_card_swaps_ddl", "player_card_social_ddl", "player_card_community_ddl", "player_card_packs_ddl", "player_card_designs_ddl", "player_card_gifts_ddl", "player_card_photos_ddl", "player_card_looks_ddl", "player_card_challenges_ddl", "player_card_winner_ddl"):
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
        db.add(Organisation(id=org, name="Dash CC", is_active=True, slug=f"dash-{org.hex[:8]}", module_overrides=["select", "fantasy", "fees"],
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
                                                                "fantasy_link_token": "x", "player_dashboard_enabled": None,
                                                                "availability_self_service_enabled": True, "availability_show_on_site": True})())}
    check("the admin list no longer offers Availability", "availability" in cat, False)
    check("it offers Fantasy", "fantasy" in cat, True)
    mods = (await profile("sam"))["modules"]
    check("a club that never chose is offered Fantasy (it runs fantasy)", "fantasy" in mods, True)
    check("and 'availability' is not in the served list", "availability" in mods, False)
    await set_modules(None)
    await set_org(org, player_dashboard_modules={"on": ["season"], "known": ["availability", "votes", "squad", "selected", "training", "ladder", "season", "fees", "fines"]})
    mods = (await profile("sam"))["modules"]
    check("a club that saved its list before Fantasy existed gets Fantasy switched on (and, since v9.130.0, Player Cards, which arrive switched on the same way)", mods, ["cards", "fantasy", "season"])
    await set_modules(["season", "fantasy"])
    # A stale stored 'availability' is dropped quietly.
    await set_org(org, player_dashboard_modules=["availability", "season", "fantasy"])
    check("a stored list that still names availability just loses it", (await profile("sam"))["modules"], ["cards", "season", "fantasy"])
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


    print("\n# H. A record of fees paid")
    await set_modules(["fees", "season"])
    async with Session() as db:
        old_season = uuid.uuid4()
        db.add(Season(id=old_season, organisation_id=org, name="Summer 25/26", year=2025))
        await db.flush()
        sched = FeeSchedule(id=uuid.uuid4(), organisation_id=org, season_id=season, name="Senior", membership_amount=100, match_day_rate=0)
        sched_old = FeeSchedule(id=uuid.uuid4(), organisation_id=org, season_id=old_season, name="Senior", membership_amount=90, match_day_rate=0)
        db.add_all([sched, sched_old])
        fm = FeeMember(id=uuid.uuid4(), organisation_id=org, player_id=P["sam"], full_name="Sam Sledge")
        fm_ann = FeeMember(id=uuid.uuid4(), organisation_id=org, player_id=P["ann"], full_name="Ann Anchor")
        db.add_all([fm, fm_ann])
        await db.flush()
        ms_new = FeeMemberSeason(id=uuid.uuid4(), member_id=fm.id, season_id=season, organisation_id=org, fee_schedule_id=sched.id)
        ms_old = FeeMemberSeason(id=uuid.uuid4(), member_id=fm.id, season_id=old_season, organisation_id=org, fee_schedule_id=sched_old.id)
        ms_ann = FeeMemberSeason(id=uuid.uuid4(), member_id=fm_ann.id, season_id=season, organisation_id=org, fee_schedule_id=sched.id)
        db.add_all([ms_new, ms_old, ms_ann])
        await db.flush()
        def pay(ms, amt, days, kind="membership", method=None, notes=None, ref=None):
            db.add(FeePayment(id=uuid.uuid4(), member_season_id=ms.id, organisation_id=org, amount=amt,
                              paid_at=TODAY - timedelta(days=days), kind=kind, method=method, notes=notes, bank_ref=ref))
        pay(ms_new, 40, 20, method="Bank transfer", notes="TREASURER ONLY NOTE", ref="REF-SECRET-1")
        pay(ms_new, 15, 5, kind="match_day", method="Cash")
        pay(ms_new, 0, 3)
        pay(ms_old, 90, 300, method="Square")
        pay(ms_ann, 77, 2, method="Cash")
        await db.commit()
    fe = (await profile("sam")).get("fees") or {}
    pays = fe.get("payments") or []
    check("every payment with money in it, newest first, across seasons",
          [(p["amount"], p["kind"], p["method"], p["season"]) for p in pays],
          [(15.0, "Match fees", "Cash", "Summer 26/27"), (40.0, "Membership", "Bank transfer", "Summer 26/27"), (90.0, "Membership", "Square", "Summer 25/26")])
    check("a zero row is not a payment", any(p["amount"] == 0 for p in pays), False)
    blob = json.dumps(await profile("sam"))
    check("the treasurer's notes and bank reference never reach the page", any(w in blob for w in ("TREASURER ONLY NOTE", "REF-SECRET-1")), False)
    check("nobody else's payment is in it", any(p["amount"] == 77 for p in pays), False)
    check("this season's owing and paid are unchanged (60 owing, 55 paid)", (fe.get("total_outstanding"), fe.get("total_paid")), (60.0, 55.0))
    ann_pays = ((await profile("ann")).get("fees") or {}).get("payments")
    check("Ann sees only her own", [p["amount"] for p in ann_pays or []], [77.0])
    none = (await profile("dup")).get("fees") or {}
    check("a person with no fee record gets on_record false and an empty list", (none.get("on_record"), none.get("payments")), (False, []))
    await set_org(org, availability_require_pin=False)
    check("with the PIN off the fees module is not served at all", "fees" in (await profile("sam"))["modules"], False)
    await set_org(org, availability_require_pin=True)

    print("\n# I. The Player Page button on the club's public site")
    import app.routers.clubs as clubs_router
    import app.routers.availability as av
    from app.models.db import User

    async def club_payload(club_id):
        async with Session() as db:
            club = await db.get(Organisation, club_id)
            return await clubs_router.get_club_by_slug(club.slug, Request({"type": "http", "headers": []}), db)

    async def cols():
        async with Session() as db:
            return (await db.execute(text("SELECT column_default FROM information_schema.columns "
                                          "WHERE table_name='organisations' AND column_name='availability_show_on_site'"))).scalar()

    check("the column exists and defaults to on", await cols(), "true")
    pl = await club_payload(org)
    check("a club with BetterSelect and the link on gets the path", pl.get("player_page_path"), f"/playerdash/{tok}")
    await set_org(org, availability_show_on_site=False)
    check("a club that hides it gets null", (await club_payload(org)).get("player_page_path"), None)
    await set_org(org, availability_show_on_site=True, availability_self_service_enabled=False)
    check("link switched off: null", (await club_payload(org)).get("player_page_path"), None)
    await set_org(org, availability_self_service_enabled=True, availability_link_token=None)
    check("no token yet: null", (await club_payload(org)).get("player_page_path"), None)
    await set_org(org, availability_link_token=tok, module_overrides=["fantasy", "fees"])
    # Player Cards (v9.130.0): the player page is no longer BetterSelect-only. A club without it has
    # the page (cards and season, no availability) whenever it has a link and has not hidden it.
    check("a club without BetterSelect has the page too (its Player Cards live there)", (await club_payload(org)).get("player_page_path"), f"/playerdash/{tok}")
    await set_org(org, availability_show_on_site=False)
    check("...unless it hides the link", (await club_payload(org)).get("player_page_path"), None)
    await set_org(org, availability_show_on_site=True)
    await set_org(org, module_overrides=["select", "fantasy", "fees"])
    check("restored, it is back", (await club_payload(org)).get("player_page_path"), f"/playerdash/{tok}")
    blob = json.dumps(await club_payload(org))
    check("the public club payload carries nothing else from the link (no PIN setting, no modules)", any(k in blob for k in ("require_pin", "dashboard_modules")), False)

    async def self_service(body):
        async with Session() as db:
            club = await db.get(Organisation, org)
            user = User(id=uuid.uuid4(), username=f"u{uuid.uuid4().hex[:8]}", email=f"{uuid.uuid4().hex[:6]}@x.com", password_hash="x", display_name="Admin")
            return await av.update_self_service(body, db=db, club=club, user=user)
    res = await self_service(av.SelfServiceUpdate(show_on_site=False))
    check("the admin switch turns it off", (res.get("show_on_site"), (await club_payload(org)).get("player_page_path")), (False, None))
    res = await self_service(av.SelfServiceUpdate(allow_maybe=True))
    check("a POST that does not send it leaves it alone", res.get("show_on_site"), False)
    res = await self_service(av.SelfServiceUpdate(show_on_site=True))
    check("and it turns back on", (res.get("show_on_site"), (await club_payload(org)).get("player_page_path")), (True, f"/playerdash/{tok}"))

    print("\n# J. Update my details")
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.services import merge_profile, rate_limit
    import app.routers.players as players_router

    async def call(fn, *a, **k):
        try:
            return await fn(*a, **k), None
        except HTTPException as e:
            return None, e

    ABSENT = (None, SimpleNamespace(status_code="route missing"))

    async def get_details(key):
        if not hasattr(pa, "get_my_details"):
            return ABSENT
        async with Session() as db:
            return await call(pa.get_my_details, tok, req_for(org, P[key]), db)

    def reset_limits():
        rate_limit._limiter._buckets.clear()
        rate_limit._failures._failures.clear()

    async def patch_details(key, _keep_limits=False, **fields):
        if not _keep_limits:
            reset_limits()
        if not hasattr(pa, "update_my_details"):
            return ABSENT
        async with Session() as db:
            return await call(pa.update_my_details, tok, pa.DetailsBody(**fields), req_for(org, P[key]), db)

    async def player_row(key):
        async with Session() as db:
            return await db.get(Player, P[key])

    async def audit_rows(key):
        async with Session() as db:
            return (await db.execute(text("SELECT area, action, via, user_name, summary, detail FROM audit_events "
                                          "WHERE player_id = :p AND action = 'details_updated' ORDER BY created_at"), {"p": P[key]})).fetchall()

    pr = await profile("sam")
    check("the page says the Update details button may be offered (PIN on)", pr.get("can_update_details"), True)
    res, err = await get_details("sam")
    check("the form is filled from their own record", (res or {}).get("details", {}).get("email"), "sam@dash.org")
    check("...with every field present, empty ones as blank text", sorted((res or {}).get("details", {})) == sorted(getattr(pa, "DETAIL_FIELDS", ["missing"])), True)

    print("  - the PIN")
    res, err = await patch_details("sam", email="new.sam@dash.org")
    check("no PIN sent is refused", err.status_code if err else None, 401)
    res, err = await patch_details("sam", pin="9999", email="new.sam@dash.org")
    check("a wrong PIN is refused", err.status_code if err else None, 401)
    check("and nothing was written", (await player_row("sam")).email, "sam@dash.org")
    reset_limits()
    for _ in range(5):
        await patch_details("sam", _keep_limits=True, pin="9999", email="x@y.com")
    res, err = await patch_details("sam", _keep_limits=True, pin="0001", email="new.sam@dash.org")
    check("repeated misses lock it out, even for the right PIN (the same lockout as signing in)", err.status_code if err else None, 429)
    reset_limits()
    for i in range(10):
        await patch_details("dup", _keep_limits=True, pin="0003", suburb=f"S{i}")
    res, err = await patch_details("dup", _keep_limits=True, pin="0003", suburb="one too many")
    check("an 11th change inside ten minutes is throttled", err.status_code if err else None, 429)
    reset_limits()

    print("  - saving")
    res, err = await patch_details("sam", pin="0001", email="  New.Sam@Dash.org ", address_line1="12 Wicket Way", suburb="Applecross",
                                   state="WA", postcode="6153", emergency_contact_name="Pat Sledge", emergency_contact_phone="0412 345 678")
    check("the right PIN saves", (res or {}).get("status"), "ok")
    row = await player_row("sam")
    check("every field is stored (email trimmed, address and emergency contact)",
          tuple(getattr(row, n, "absent") for n in ("email", "address_line1", "suburb", "state", "postcode", "emergency_contact_name", "emergency_contact_phone")),
          ("New.Sam@Dash.org", "12 Wicket Way", "Applecross", "WA", "6153", "Pat Sledge", "0412 345 678"))
    check("the response says which fields changed", sorted((res or {}).get("changed", [])),
          sorted(["email", "address_line1", "suburb", "state", "postcode", "emergency_contact_name", "emergency_contact_phone"]))
    res, _ = await patch_details("sam", pin="0001", suburb="Mount Pleasant")
    row = await player_row("sam")
    check("a field that is not sent is left alone", tuple(getattr(row, n, "absent") for n in ("suburb", "address_line1", "email")), ("Mount Pleasant", "12 Wicket Way", "New.Sam@Dash.org"))
    res, _ = await patch_details("sam", pin="0001", address_line1="")
    check("an explicit blank clears it", getattr(await player_row("sam"), "address_line1", "absent"), None)
    res, _ = await patch_details("sam", pin="0001", suburb="Mount Pleasant")
    check("saving what is already there changes nothing and says so", (res or {}).get("changed"), [])

    print("  - what is refused")
    for label, fields in (("an email with no @", {"email": "nope"}), ("an email with spaces inside", {"email": "a b@c.com"}),
                          ("a phone with letters", {"phone": "04ab5678"}), ("a phone that is too short", {"phone": "12345"}),
                          ("an emergency phone with letters", {"emergency_contact_phone": "call mum"}),
                          ("an over-long address", {"address_line1": "x" * 500}), ("a postcode with symbols", {"postcode": "61;53"})):
        res, err = await patch_details("sam", pin="0001", **fields)
        check(f"{label} is a 422", err.status_code if err else None, 422)
    res, err = await patch_details("sam", pin="0001", phone="")
    check("the mobile cannot be cleared (it is the PIN)", err.status_code if err else None, 422)
    check("and nothing from any refused save was kept", (await player_row("sam")).email, "New.Sam@Dash.org")

    print("  - changing the mobile changes the PIN")
    res, _ = await patch_details("sam", pin="0001", phone="0411 222 777")
    check("a new mobile saves", (await player_row("sam")).phone, "0411 222 777")
    res, err = await patch_details("sam", pin="0001", suburb="Elsewhere")
    check("the old PIN no longer works", err.status_code if err else None, 401)
    res, err = await patch_details("sam", pin="2777", suburb="Elsewhere")
    check("the new one does", (res or {}).get("status"), "ok")

    print("  - the fee record moves with the player only where it mirrored them")
    async with Session() as db:
        fm_sam = (await db.execute(text("SELECT id FROM fee_members WHERE player_id = :p"), {"p": P["sam"]})).scalar()
        await db.execute(text("UPDATE fee_members SET email = 'new.sam@dash.org', mobile = NULL WHERE id = :i"), {"i": fm_sam})
        await db.execute(text("UPDATE fee_members SET email = 'parent@dash.org', mobile = '0499 111 222' WHERE player_id = :p"), {"p": P["ann"]})
        await db.commit()
    async def fee(key):
        async with Session() as db:
            return tuple((await db.execute(text("SELECT email, mobile FROM fee_members WHERE player_id = :p"), {"p": P[key]})).first())
    res, _ = await patch_details("sam", pin="2777", email="sam.again@dash.org", phone="0411 222 888")
    check("a fee email that was the player's old one follows, and an empty mobile is filled", await fee("sam"), ("sam.again@dash.org", "0411 222 888"))
    res, _ = await patch_details("ann", pin="0002", email="ann.new@dash.org", phone="0400 000 902")
    check("a different email (a parent's) and mobile on the fee record are the club's own and are left alone", await fee("ann"), ("parent@dash.org", "0499 111 222"))
    check("the player's own record did change", ((await player_row("ann")).email, (await player_row("ann")).phone), ("ann.new@dash.org", "0400 000 902"))

    print("  - the trail")
    rows = await audit_rows("sam")
    check("every real change wrote one entry, under the Player details area, by the player, via their link",
          (len(rows) >= 3, {r[0] for r in rows}, {r[1] for r in rows}, {r[2] for r in rows}, {r[3] for r in rows}),
          (True, {"details"}, {"details_updated"}, {"player link"}, {"Sam Sledge"}))
    first = rows[0] if rows else ("", "", "", "", "", {})
    check("the first entry names what changed in words, not values", ("email" in first[4], "address" in first[4], "@" in first[4]), (True, True, False))
    check("and keeps the old and new values so the club can put it back", json.dumps(first[5]).count("sam@dash.org") >= 1 and "New.Sam@Dash.org" in json.dumps(first[5]), True)
    check("an entry says when the fee record moved too", any("email" in (r[5].get("fee_record_also_updated") or []) for r in rows if isinstance(r[5], dict)), True)
    check("a save that changed nothing wrote nothing extra", len([r for r in rows if "Mount Pleasant" in json.dumps(r[5]) and "Mount Pleasant" == r[5]["fields"].get("suburb", {}).get("to")]), 1)

    print("  - who can see it")
    blob = json.dumps(await profile("sam")) + json.dumps(await me("sam"))
    check("the profile and availability payloads carry none of the new details", any(w in blob for w in ("Wicket Way", "Pat Sledge", "0412 345 678", "sam.again@dash.org")), False)
    check("a player cannot read or write anyone else's: the route takes no player id and uses the cookie's",
          ((await get_details("ann"))[0] or {}).get("details", {}).get("email"), "ann.new@dash.org")
    pl_fields = players_router._profile_fields(await player_row("sam"))  # the row has the attributes only once the model maps them
    check("the club's admin profile carries them", (pl_fields.get("suburb"), pl_fields.get("emergency_contact_name")), ("Elsewhere", "Pat Sledge"))
    check("the admin PATCH model accepts them", {"address_line1", "suburb", "state", "postcode", "emergency_contact_name", "emergency_contact_phone"} <= set(players_router.PlayerProfileUpdate.model_fields), True)
    keep = SimpleNamespace(**{c: None for c in merge_profile.FIELDS}, id=uuid.uuid4(), photo_url=None, photo_data=None, photo_mime=None, hero_photo_url=None, hero_photo_data=None, hero_photo_mime=None)
    gone = SimpleNamespace(**{c: ("x" if c not in ("is_overseas", "date_of_birth") else None) for c in merge_profile.FIELDS}, id=uuid.uuid4(), photo_url=None, photo_data=None, photo_mime=None, hero_photo_url=None, hero_photo_data=None, hero_photo_mime=None)
    filled = merge_profile.carry_profile(keep, gone)
    check("a merge carries the new fields onto the keeper where it had none", {"address_line1", "postcode", "emergency_contact_phone"} <= set(filled), True)

    print("  - PIN off")
    await set_org(org, availability_require_pin=False)
    pr = await profile("ann")
    check("the button is not offered", pr.get("can_update_details"), False)
    res, err = await get_details("ann")
    check("reading the form is refused", err.status_code if err else None, 403)
    res, err = await patch_details("ann", pin="0002", suburb="Nowhere")
    check("saving is refused", err.status_code if err else None, 403)
    check("and nothing was written", getattr(await player_row("ann"), "suburb", "absent"), None)
    await set_org(org, availability_require_pin=True)
    async with Session() as db:
        nophone = uuid.uuid4()
        db.add(Player(id=nophone, organisation_id=org, name="Phil Phoneless", gender="male", is_player=True, status="active"))
        await db.commit()
    async with Session() as db:
        c = jose_jwt.encode({"club": str(org), "pid": str(nophone), "typ": "avail", "exp": datetime.now(timezone.utc) + timedelta(days=1)},
                            settings.secret_key, algorithm=settings.algorithm)
        r = Request({"type": "http", "headers": [(b"cookie", f"{pa.COOKIE_NAME}={c}".encode())]})
        res, err = await call(pa.update_my_details, tok, pa.DetailsBody(pin="1234", suburb="x"), r, db) if hasattr(pa, "update_my_details") else ABSENT
    check("a player with no mobile on file cannot be verified, so cannot save", (err.status_code if err else None, str(getattr(err, "detail", ""))[:18]), (409, "There is no mobile"))

    print("\n# K. A selected side names its fixture, so the date it is on can say so")
    fx_locked, fx_open = uuid.uuid4(), uuid.uuid4()
    async with Session() as db:
        db.add(Fixture(id=fx_locked, organisation_id=org, source="manual", played_on=TODAY + timedelta(days=4), status="UPCOMING",
                       opponent_name="Rovers", label="Rovers", round="5", locked_at=NOW))
        db.add(Fixture(id=fx_open, organisation_id=org, source="manual", played_on=TODAY + timedelta(days=5), status="UPCOMING",
                       opponent_name="Saints", label="Saints", round="5"))
        await db.flush()
        db.add(FixtureLineup(fixture_id=fx_locked, player_id=P["sam"], organisation_id=org, batting_order=1, is_captain=True))
        db.add(FixtureLineup(fixture_id=fx_open, player_id=P["sam"], organisation_id=org, batting_order=1))
        await db.commit()
    await set_modules(["selected"])
    sel = (await profile("sam")).get("selected") or []
    check("only the locked side is shown, and it carries its fixture id", [(x.get("fixture_id"), x.get("opponent_name"), x.get("is_captain")) for x in sel],
          [(str(fx_locked), "Rovers", True)])
    check("the draft side (not locked) is not", any(x.get("opponent_name") == "Saints" for x in sel), False)

    print("\n# L. Season rankings for runs, wickets and catches")
    async with Session() as db:
        for key, runs, wk, ct in (("ann", 500, 3, 10), ("rival", 412, 0, 0), ("dup", 100, 12, 6)):
            db.add(PlayerSeasonStats(player_id=P[key], season_id=season, matches=8, batting_innings=8, runs=runs, not_outs=0,
                                     balls_faced=runs, high_score=50, wickets=wk, runs_conceded=wk * 25, overs=wk * 3 if wk else 0,
                                     bowling_balls=wk * 18, catches=ct))
        # Another club's player on the same season row must not count.
        db.add(PlayerSeasonStats(player_id=P["stranger"], season_id=season, matches=9, batting_innings=9, runs=9999, not_outs=0,
                                 balls_faced=9999, high_score=200, wickets=99, runs_conceded=1, overs=50, bowling_balls=300, catches=99))
        await db.commit()
    await set_modules(["season"])
    import app.services.player_dashboard as pdash

    async def ranks(key):
        getattr(pdash, "_RANK_CACHE", {}).clear()
        if not hasattr(pa, "get_my_ranks"):
            return None
        async with Session() as db:
            res, err = await call(pa.get_my_ranks, tok, req_for(org, P[key]), db)
        return (res or {}).get("ranks")

    rk = await ranks("sam")
    r = (rk or {}).get("ranks") or {}
    check("the season named is the one the dashboard shows", (rk or {}).get("season"), "Summer 26/27")
    check("runs: 412 puts Sam equal second, behind Ann's 500", (r.get("runs") or {}).get("rank"), 2)
    check("...of the four club players with runs, another club's 9999 not among them", (r.get("runs") or {}).get("of"), 4)
    check("...and the value is his own", (r.get("runs") or {}).get("value"), 412)
    check("wickets: 9 is second behind Dee's 12", ((r.get("wickets") or {}).get("rank"), (r.get("wickets") or {}).get("of")), (2, 3))
    check("catches: 6 level with Dee behind Ann's 10 shares second place", ((r.get("catches") or {}).get("rank"), (r.get("catches") or {}).get("of")), (2, 3))
    rk_ann = await ranks("ann")
    check("Ann is first for runs and catches", (((rk_ann or {}).get("ranks") or {}).get("runs", {}).get("rank"), ((rk_ann or {}).get("ranks") or {}).get("catches", {}).get("rank")), (1, 1))
    rk_rival = await ranks("rival")
    check("a player with nothing on a board is left off it, not shown last", sorted(((rk_rival or {}).get("ranks") or {})), ["runs"])
    check("a tie takes the better place for both (Rex shares second on runs)", (((rk_rival or {}).get("ranks") or {}).get("runs") or {}).get("rank"), 2)
    rk_none = await ranks("noemail")
    check("a player with no season games has no ranks block at all", rk_none, None)
    check("the player's own dashboard figure and the board agree on the value", ((await profile("sam")).get("season") or {}).get("runs"), (r.get("runs") or {}).get("value"))
    check("rank_in handles an empty board", ((getattr(pdash, "rank_in", None) or (lambda *a: "missing"))({}, "x"), (getattr(pdash, "rank_in", None) or (lambda *a: "missing"))({"x": 0.0}, "x")), (None, None))
    check("ranks are not on the profile payload (they are read on their own)", "ranks" in await profile("sam"), False)
    await set_modules(["fees"])
    if hasattr(pa, "get_my_ranks"):
        async with Session() as db:
            res, err = await call(pa.get_my_ranks, tok, req_for(org, P["sam"]), db)
    else:
        res, err = None, SimpleNamespace(status_code="missing")
    check("with the season module off the route is a 404", err.status_code if err else None, 404)

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


asyncio.run(main())
