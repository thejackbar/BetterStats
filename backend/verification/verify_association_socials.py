"""Association socials workspaces, against a real Postgres.

An association workspace (`organisations.workspace_kind = 'association'`) has no
club behind it. Its BetterPosts pulls read a WHOLE grade from a pasted link
(services/social_competition.py). This runs the SHIPPED route bodies in
routers/admin.py and routers/club_admin.py with only the Cricket Australia client
stubbed, on a hand-built grade:

  Round 1 (done)      APPLECROSS v SUBIACO MARIST
  Round 2 (done)      M1 APPLECROSS v WESTERN SUBURBS        a full card
                      M2 SUBIACO MARIST v BENTLEY RED         bare on the first read, full on the re-read
                      M3 BENTLEY BLACK v SWAN VALLEY          bare on every read: skipped, and named
                      M4 KALAMUNDA v ABANDONED                status 4 (abandoned), never "ahead"
  Round 3 (upcoming)  two fixtures

Bentley has two teams in the grade, so each keeps its own team name. Applecross
is also a club registered here, so its crest is our hosted one.

The workspace is named "Applecross Socials" on purpose: club name matching would
claim Applecross's games for it, and nothing here may use it.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/assoc_verify?host=/tmp/pgv/sock&port=5544 \\
      python verification/verify_association_socials.py
A control run on the commit before this feature reports the workspace checks as
FAIL (no workspace pulls, no workspace routes) without crashing, and the club
checks marked [club] pass on both.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.models.db import Base, Organisation  # noqa: E402
from app.routers import admin as admin_router  # noqa: E402
from app.routers import club_admin as club_admin_router  # noqa: E402
from app.routers import organisations as org_router  # noqa: E402
from app.services import grassroots_scores_client as gr  # noqa: E402
from app.services import social_rounds  # noqa: E402

try:
    from app.services import social_competition as sc  # noqa: E402
except Exception:  # the control commit has no such module
    sc = None
try:
    from app.services import association_crests as crests  # noqa: E402
except Exception:  # the control commit has no crest library
    crests = None

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


CURRENT_DB = {}


async def attempt(label, coro):
    """Run a route body; a crash is reported as a FAIL, never raised, and the
    session is rolled back so one failure does not poison the checks after it."""
    global FAIL
    try:
        # A zero-argument callable builds the call inside the guard, so a route
        # that lacks a parameter on the control commit is a FAIL, not a crash.
        return await (coro() if callable(coro) else coro)
    except Exception as exc:  # noqa: BLE001
        FAIL += 1
        print(f"  FAIL {label}: raised {type(exc).__name__}: {str(exc)[:160]}")
        db = CURRENT_DB.get("db")
        if db is not None:
            await db.rollback()
            # A rollback expires every loaded object: read the workspace and club
            # again so one failed step does not take the checks after it down.
            for inst in CURRENT_DB.get("keep", []):
                try:
                    await db.refresh(inst)
                except Exception:  # noqa: BLE001
                    pass
        return None


def g(d, *path, default=None):
    """Presence-safe read: g(row, 'dates', 0, 'fixtures')."""
    for k in path:
        try:
            d = d[k]
        except (KeyError, IndexError, TypeError):
            return default
    return d


# ── The stubbed grade ─────────────────────────────────────────────────────────
GRADE = "f584d7c6-e416-4075-979a-f2a25f059932"
R1, R2, R3 = (str(uuid.uuid4()) for _ in range(3))
APPLECROSS_ORG = uuid.uuid4()   # registered here, with our own crest
CLUBS = {
    "app": (str(APPLECROSS_ORG), "Applecross Cricket Club"),
    "wsc": (str(uuid.uuid4()), "Western Suburbs Cricket Club"),
    "sub": (str(uuid.uuid4()), "Subiaco Marist Cricket Club"),
    "ben": (str(uuid.uuid4()), "Bentley Cricket Club"),
    "swv": (str(uuid.uuid4()), "Swan Valley Cricket Club"),
    "kal": (str(uuid.uuid4()), "Kalamunda Cricket Club"),
}
TEAMS = {  # team key -> (team id, display name, club key)
    "app": ("a0000000-0000-0000-0000-000000000001", "Applecross 2nd XI", "app"),
    "wsc": ("a0000000-0000-0000-0000-000000000002", "Hola Health WSCC 2nd XI", "wsc"),
    "sub": ("a0000000-0000-0000-0000-000000000003", "Subiaco Marist 2nd XI", "sub"),
    "benr": ("a0000000-0000-0000-0000-000000000004", "Bentley Red", "ben"),
    "benb": ("a0000000-0000-0000-0000-000000000005", "Bentley Black", "ben"),
    "swv": ("a0000000-0000-0000-0000-000000000006", "Swan Valley 2nd XI", "swv"),
    "kal": ("a0000000-0000-0000-0000-000000000007", "Kalamunda 2nd XI", "kal"),
}
M0, M1, M2, M3, M4, F1, F2 = (str(uuid.uuid4()) for _ in range(7))


def cdn(club):
    return f"https://res.cloudinary.com/playhq/{club}.png"


def team_obj(key, home, players=None):
    tid, name, club = TEAMS[key]
    oid, cname = CLUBS[club]
    t = {"id": tid, "displayName": name, "isHome": home,
         "owningOrganisation": {"id": oid, "name": cname, "logoUrl": cdn(club)}}
    if players is not None:
        t["players"] = players
    return t


def list_item(mid, rnd, rname, day, home, away, status, sid, result=""):
    return {"id": mid, "status": status, "statusId": sid, "resultText": result,
            "round": {"id": rnd, "name": rname},
            "matchSchedule": [{"matchDay": 1, "startDateTime": f"{day}T12:00:00.0000000+08:00"}],
            "venue": {"name": f"{TEAMS[home][1]} Oval"},
            "teams": [team_obj(home, True), team_obj(away, False)]}


GRADE_LIST = [
    list_item(M0, R1, "Round 1", "2026-10-10", "app", "sub", "COMPLETED", 3, "Applecross 2nd XI won by 5 runs"),
    list_item(M1, R2, "Round 2", "2026-10-17", "app", "wsc", "COMPLETED", 3, "Applecross 2nd XI won by 9 wickets"),
    list_item(M2, R2, "Round 2", "2026-10-17", "sub", "benr", "COMPLETED", 3, "Subiaco Marist 2nd XI won by 30 runs"),
    list_item(M3, R2, "Round 2", "2026-10-17", "benb", "swv", "COMPLETED", 3, "Swan Valley won by 2 runs"),
    list_item(M4, R2, "Round 2", "2026-10-17", "kal", "app", "ABANDONED", 4, "Abandoned"),
    list_item(F1, R3, "Round 3", "2026-10-24", "wsc", "sub", "UPCOMING", 0),
    list_item(F2, R3, "Round 3", "2026-10-24", "swv", "app", "UPCOMING", 0),
]
# M4 is listed with Applecross away to a second Kalamunda game; it is abandoned,
# so the "next round" pick must skip it and land on Round 3.

PIDS: dict[str, str] = {}


def pid(name):
    return PIDS.setdefault(name, str(uuid.uuid4()))


def bat(name, r, b, out=True):
    return {"participantId": pid(name), "playerShortName": name, "runsScored": r, "ballsFaced": b,
            "foursScored": 0, "sixesScored": 0, "dismissalType": "caught" if out else "not out",
            "dismissalTypeId": 2 if out else 1}


def bowl(name, overs, m, r, w):
    return {"participantId": pid(name), "playerShortName": name, "oversBowled": overs,
            "maidensBowled": m, "runsConceded": r, "wicketsTaken": w}


def roster(names, keeper=None):
    return [{"participantId": pid(n), "name": n, "displayName": n, "playerShortName": n,
             "roles": (["Wicket Keeper"] if n == keeper else [])} for n in names]


def card(mid, home, away, home_bat, away_bat, home_bowl, away_bowl, result, home_won, home_runs, away_runs):
    """home_bowl is the home side's bowling while the AWAY side bats."""
    ht, at = TEAMS[home][0], TEAMS[away][0]
    hnames = [b["playerShortName"] for b in home_bat] + [b["playerShortName"] for b in home_bowl]
    anames = [b["playerShortName"] for b in away_bat] + [b["playerShortName"] for b in away_bowl]
    return {
        "id": mid, "grade": {"id": GRADE, "name": "2nd Grade"}, "round": {"id": R2, "name": "Round 2"},
        "matchSchedule": [{"startDateTime": "2026-10-17T12:00:00+08:00"}],
        "matchSummary": {"resultText": result, "teams": [
            {"id": ht, "displayName": TEAMS[home][1], "isHome": True, "isWinner": home_won,
             "resultType": "WON" if home_won else "LOST"},
            {"id": at, "displayName": TEAMS[away][1], "isHome": False, "isWinner": not home_won,
             "resultType": "LOST" if home_won else "WON"}]},
        "teams": [team_obj(home, True, roster(sorted(set(hnames)))), team_obj(away, False, roster(sorted(set(anames))))],
        "innings": [
            {"battingTeamId": ht, "runsScored": home_runs, "numberOfWicketsFallen": 4, "oversBowled": 30,
             "batting": home_bat, "bowling": away_bowl, "fielding": []},
            {"battingTeamId": at, "runsScored": away_runs, "numberOfWicketsFallen": 10, "oversBowled": 35,
             "batting": away_bat, "bowling": home_bowl, "fielding": []},
        ],
    }


CARDS = {
    M1: card(M1, "app", "wsc",
             [bat("A Ace", 90, 70), bat("A Two", 10, 20)], [bat("W Wally", 40, 50), bat("W Two", 5, 9)],
             [bowl("A Spin", 10, 2, 30, 4)], [bowl("W Quick", 8, 0, 40, 1)],
             "Applecross 2nd XI won by 9 wickets", True, 160, 150),
    M2: card(M2, "sub", "benr",
             [bat("S One", 120, 90), bat("S Two", 80, 70, out=False), bat("S Three", 75, 60)],
             [bat("B Red", 30, 40)],
             [bowl("S Four", 10, 1, 20, 3)], [bowl("B Bowl", 10, 0, 60, 2)],
             "Subiaco Marist 2nd XI won by 30 runs", True, 280, 250),
}
BARE = {"id": M3, "grade": {"id": GRADE, "name": "2nd Grade"}, "matchSummary": {"teams": []}, "teams": []}
CALLS = {"m2_reads": 0}


async def fake_scorecard(match_id, *, force=False):
    if match_id == M3:
        return dict(BARE)
    if match_id == M2:
        CALLS["m2_reads"] += 1
        # First read is bare (Cricket Australia sometimes serves one); a forced
        # re-read is the real card.
        return CARDS[M2] if force else {**BARE, "id": M2}
    return CARDS.get(match_id)


async def fake_detail(match_id, *, force=False):
    item = next((m for m in GRADE_LIST if m["id"] == match_id), None)
    if not item:
        return None
    home = next(t for t in item["teams"] if t["isHome"])
    away = next(t for t in item["teams"] if not t["isHome"])
    hk = next(k for k, v in TEAMS.items() if v[0] == home["id"])
    ak = next(k for k, v in TEAMS.items() if v[0] == away["id"])
    return {**item, "grade": {"id": GRADE, "name": "2nd Grade"},
            "matchSummary": {"teams": [{"id": home["id"], "displayName": home["displayName"], "isHome": True},
                                       {"id": away["id"], "displayName": away["displayName"], "isHome": False}]},
            "teams": [team_obj(hk, True, roster([f"{hk} p{i}" for i in range(11)], keeper=f"{hk} p0")),
                      team_obj(ak, False, [])]}


async def fake_details(ids):
    out = {}
    for i in ids:
        d = await fake_detail(i)
        if d:
            out[i] = d
    return out


async def fake_grade_matches(grade_id, *, force=False):
    return list(GRADE_LIST) if grade_id.lower() == GRADE else []


# Crest pictures Cricket Australia would serve: each club's colour on a WHITE
# square, so the library has a plain background to take off. Kalamunda's host
# is down (the fetch fails), so its crest must fall back to the raw address.
CREST_COLOUR = {"app": (20, 60, 160), "wsc": (200, 30, 30), "sub": (20, 110, 50), "ben": (25, 30, 80),
                "swv": (10, 120, 60), "kal": None}
FETCHES: list[str] = []


def crest_png(rgb):
    import io
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (200, 200), (255, 255, 255, 255))
    ImageDraw.Draw(im).ellipse((30, 20, 170, 180), fill=(*rgb, 255))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


async def fake_fetch_logo(url, *, client=None):
    FETCHES.append(url)
    key = url.rsplit("/", 1)[-1].split(".")[0].split("?")[0]
    rgb = CREST_COLOUR.get(key)
    return crest_png(rgb) if rgb else None


if crests is not None:
    crests.fetch_logo = fake_fetch_logo

gr.get_match_scorecard = fake_scorecard
admin_router.get_match_scorecard = fake_scorecard  # the scorecard route imported it by name
gr.get_match_detail = fake_detail
gr.get_matches_detail = fake_details
gr.get_grade_matches = fake_grade_matches

MATCH_LINK = f"https://play.cricket.com.au/match/{M1}/applecross-2nd-xi-v-wscc?tab=scorecard"
GRADE_R2 = f"https://play.cricket.com.au/grade/{GRADE}?tab=matches&roundId={R2}"
GRADE_BARE = f"https://play.cricket.com.au/grade/{GRADE}?tab=matches"
PLAYHQ = "https://www.playhq.com/cricket-australia/org/x/y/game-centre/abcd1234"


class SuperUser:
    id = uuid.uuid4()
    role = "super_admin"


async def setup():
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        # Independent of the DDL module so the control commit gets the same table.
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS workspace_kind TEXT"))
        # The crest library, copied column for column from association_crest_ddl.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS association_crests (
                workspace_id UUID NOT NULL, ca_org_id TEXT NOT NULL, name TEXT, src_url TEXT,
                original_png BYTEA, cleaned_png BYTEA, uploaded_png BYTEA,
                use_cleaned BOOLEAN NOT NULL DEFAULT TRUE, colour TEXT, colour2 TEXT,
                colour_by_hand BOOLEAN NOT NULL DEFAULT FALSE, version TEXT, uploaded_by UUID,
                uploaded_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (workspace_id, ca_org_id))
        """))
        await conn.execute(text("ALTER TABLE association_crests ADD COLUMN IF NOT EXISTS cut_style TEXT NOT NULL DEFAULT 'auto'"))
        await conn.execute(text("ALTER TABLE association_crests ADD COLUMN IF NOT EXISTS clean_version INTEGER NOT NULL DEFAULT 1"))
        # usage_events is a raw lifespan table (main.py), copied column for column;
        # All Clubs reads it for "last active".
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS usage_events (
                id BIGSERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                event_type TEXT NOT NULL DEFAULT 'api',
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                route TEXT,
                status INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER,
                user_id UUID,
                org_id UUID,
                ip_hash TEXT,
                user_agent TEXT,
                referer TEXT,
                metadata JSONB DEFAULT '{}'
            )
        """))
        # The lifespan and migration 118 give the id a default; create_all does not.
        await conn.execute(text("ALTER TABLE org_module_subscriptions ALTER COLUMN id SET DEFAULT gen_random_uuid()"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS org_module_subscriptions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL, module_key TEXT NOT NULL, status TEXT NOT NULL,
                renewal_date DATE, started_at TIMESTAMPTZ, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ,
                UNIQUE (organisation_id, module_key))
        """))
    async with Session() as db:
        db.add(Organisation(id=APPLECROSS_ORG, name="Applecross Cricket Club", short_name="Applecross",
                            slug="applecross", is_active=True, logo_url="/api/images/organisations/app/logo"))
        db.add(Organisation(id=uuid.uuid4(), name="Kalamunda Cricket Club", slug="kalamunda", is_active=True))
        await db.commit()


async def main():
    await setup()
    async with Session() as db:
        CURRENT_DB["db"] = db
        print("\n[workspace] create, list and keep off the club lists")
        made = await attempt("create workspace", club_admin_router.create_association_workspace(
            club_admin_router.AssociationWorkspaceCreate(name="Applecross Socials", short_name="Applecross"),
            SuperUser(), db)) if hasattr(club_admin_router, "create_association_workspace") else None
        check("create route exists", hasattr(club_admin_router, "create_association_workspace"))
        ws_id = g(made, "id")
        ws = await db.get(Organisation, uuid.UUID(ws_id)) if ws_id else None
        check("workspace kind stored", getattr(ws, "workspace_kind", None), "association")
        check("workspace never is_active (scheduler and public site pass it by)", getattr(ws, "is_active", None), False)
        check("workspace has no slug (no public page)", getattr(ws, "slug", "x"), None)
        check("workspace holds BetterSocials only", getattr(ws, "module_overrides", None), ["socials"])
        subs = (await db.execute(text(
            "SELECT module_key, status FROM org_module_subscriptions WHERE organisation_id = CAST(:o AS uuid) ORDER BY 1"
        ), {"o": ws_id or str(uuid.uuid4())})).all()
        check("core and socials subscription rows written active", [tuple(r) for r in subs],
              [("core", "active"), ("socials", "active")])
        dup = None
        if hasattr(club_admin_router, "create_association_workspace"):
            try:
                await club_admin_router.create_association_workspace(
                    club_admin_router.AssociationWorkspaceCreate(name="applecross socials"), SuperUser(), db)
            except HTTPException as e:
                dup = e.status_code
        check("a second workspace with the same name is refused", dup, 409)
        bad = None
        if hasattr(club_admin_router, "create_association_workspace"):
            try:
                await club_admin_router.create_association_workspace(
                    club_admin_router.AssociationWorkspaceCreate(name="X", primary_color="red"), SuperUser(), db)
            except HTTPException as e:
                bad = e.status_code
        check("a colour that is not hex is refused", bad, 422)

        if ws is None:
            # Control commit: the route is missing, so put the same row in by hand.
            # The club lists below must then be shown to leave out a row that IS there.
            await db.execute(text(
                "INSERT INTO organisations (id, name, short_name, is_active, workspace_kind, module_overrides, "
                "tier, subscription_status) VALUES (gen_random_uuid(), 'Applecross Socials', 'Applecross', false, "
                "'association', '[\"socials\"]', 'good', 'active')"))
            await db.commit()
        present = await db.scalar(text("SELECT count(*) FROM organisations WHERE workspace_kind = 'association'"))
        check("a workspace row is present for the exclusion checks to find", present, 1)
        listed = await attempt("list workspaces", club_admin_router.list_association_workspaces(SuperUser(), db)) \
            if hasattr(club_admin_router, "list_association_workspaces") else None
        check("workspace list shows it", [w["name"] for w in g(listed, "workspaces", default=[])], ["Applecross Socials"])
        clubs = await attempt("All Clubs", club_admin_router.list_all_clubs(False, SuperUser(), db))
        names = {(c.get("name") if isinstance(c, dict) else getattr(c, "name", None)) for c in (clubs or [])}
        check("[club] All Clubs still lists the real clubs", {"Applecross Cricket Club", "Kalamunda Cricket Club"} <= names)
        check("All Clubs leaves the workspace out", "Applecross Socials" in names, False)
        public = await attempt("GET /organisations", org_router.list_organisations(db))
        pnames = {o.name for o in (public or [])}
        check("[club] public organisation list still has clubs", "Applecross Cricket Club" in pnames)
        check("public organisation list leaves the workspace out", "Applecross Socials" in pnames, False)

        # A failed step above rolled the session back, which expires every loaded
        # object; read them fresh so later attribute reads are not lazy IO.
        if ws is not None:
            await db.refresh(ws)
        if ws is None:  # control: the hand-built row, so the pulls can still be asked
            wid = await db.scalar(text("SELECT id FROM organisations WHERE workspace_kind = 'association'"))
            ws = await db.get(Organisation, wid)
            ws.workspace_kind = "association"
        club = await db.get(Organisation, APPLECROSS_ORG)
        await db.refresh(club)
        CURRENT_DB["keep"] = [ws, club]

        print("\n[fixtures] a grade link with no round is the next round to be played")
        fx = await attempt("fixtures", admin_router.get_social_fixtures(GRADE_BARE, db, ws))
        rows = g(fx, "dates", 0, "fixtures", default=[])
        check("kind round", g(fx, "kind"), "round")
        check("next round skips the abandoned game and lands on Round 3", g(fx, "dates", 0, "round"),
              social_rounds._round_label("Round 3"))
        check("both Round 3 fixtures, home team first", [(r.get("home"), r.get("opp")) for r in rows],
              [("WESTERN SUBURBS", "SUBIACO MARIST"), ("SWAN VALLEY", "APPLECROSS")])
        check("grade name is the competition line", g(fx, "dates", 0, "comp"), "2ND GRADE")
        check("rows are neutral and read from home", all(r.get("neutral") and r.get("ha") == "H" for r in rows) and bool(rows))
        check("`grade` carries the home side so every layout names it first", [r.get("grade") for r in rows],
              ["WESTERN SUBURBS", "SWAN VALLEY"])
        lib = f"/api/images/association-crests/{ws.id}/"
        check("an unregistered club prints its crest from the workspace library",
              str(g(rows, 0, "homeLogo", default="")).startswith(lib + CLUBS["wsc"][0]))
        check("a registered club's crest also comes from the library (one look for the grade)",
              str(g(rows, 1, "oppLogo", default="")).startswith(lib + str(APPLECROSS_ORG)))
        check("each side carries the colour read from its crest", (g(rows, 0, "homeColor"), g(rows, 1, "oppColor")),
              ("#c81e1e", "#143ca0"))
        check("no transient keys leak", bool(rows) and not any(k.startswith("_") for r in rows for k in r))

        print("\n[crests] the workspace's crest library")
        fetched_once = len(FETCHES)
        fx_again = await attempt("fixtures again", admin_router.get_social_fixtures(GRADE_BARE, db, ws))
        check("a second pull fetches no crest again (kept for the workspace)", len(FETCHES), fetched_once)
        check("a second pull prints the same crests", [r.get("homeLogo") for r in g(fx_again, "dates", 0, "fixtures", default=[])],
              [r.get("homeLogo") for r in rows])
        lib_list = await attempt("crest list", lambda: admin_router.get_social_crests(db, ws))
        held = {c["caOrgId"]: c for c in g(lib_list, "crests", default=[])}
        wsc_id = CLUBS["wsc"][0]
        check("the library lists every club a pull named", {CLUBS[k][0] for k in ("wsc", "sub", "swv", "app")} <= set(held))
        png = await crests.crest_image(db, str(ws.id), wsc_id) if crests else None

        def corner(data):
            import io
            from PIL import Image
            return Image.open(io.BytesIO(data)).convert("RGBA").getpixel((0, 0)) if data else None

        def centre(data):
            import io
            from PIL import Image
            im = Image.open(io.BytesIO(data)).convert("RGBA") if data else None
            return im.getpixel((im.width // 2, im.height // 2)) if im else None
        check("the white square is taken off (corner is see-through)", (corner(png) or (0, 0, 0, 255))[3], 0)
        check("the crest itself is kept (centre is the club's red)", (centre(png) or (0, 0, 0, 0))[:3], (200, 30, 30))
        orig = await crests.crest_image(db, str(ws.id), wsc_id, "original") if crests else None
        check("the original is kept beside it (corner still white)", corner(orig), (255, 255, 255, 255))
        from PIL import Image as _Img
        import io as _io
        check("trimmed so the crest fills its box", _Img.open(_io.BytesIO(png)).size[0] < 200 if png else False)
        kal_logo = None
        fxk = await attempt("fixtures by match link (Kalamunda)", admin_router.get_social_fixtures(MATCH_LINK, db, ws))
        for r in g(fxk, "dates", 0, "fixtures", default=[]):
            if r.get("home") == "KALAMUNDA":
                kal_logo = r.get("homeLogo")
        check("a crest that cannot be fetched falls back to Cricket Australia's address", kal_logo, cdn("kal"))

        # A person's choices are never replaced by code.
        upd = await attempt("use the original", lambda: admin_router.patch_social_crest(
            wsc_id, admin_router.CrestUpdate(use_cleaned=False), db, ws, SuperUser()))
        served = await crests.crest_image(db, str(ws.id), wsc_id) if crests else None
        check("'use the original' serves the original picture", corner(served), (255, 255, 255, 255))
        await attempt("hand colour", lambda: admin_router.patch_social_crest(
            wsc_id, admin_router.CrestUpdate(colour="#123456"), db, ws, SuperUser()))
        bad_colour = None
        try:
            await admin_router.patch_social_crest(wsc_id, admin_router.CrestUpdate(colour="red"), db, ws, SuperUser())
        except HTTPException as e:
            bad_colour = e.status_code
        except Exception:
            bad_colour = "crash"
            await db.rollback()
            await db.refresh(ws)
            await db.refresh(club)
        check("a colour that is not hex is refused", bad_colour, 422)
        from starlette.datastructures import UploadFile as _UF
        up = await attempt("upload", lambda: admin_router.upload_social_crest(
            wsc_id, _UF(file=_io.BytesIO(crest_png((90, 0, 120))), filename="mine.png"), db, ws, SuperUser()))
        served = await crests.crest_image(db, str(ws.id), wsc_id) if crests else None
        check("an upload is what a post draws", (centre(served) or (0, 0, 0, 0))[:3], (90, 0, 120))
        # Cricket Australia changes its address: the automatic copy refreshes, the upload and colour stay.
        await db.execute(text("UPDATE association_crests SET src_url = 'https://old.example/wsc.png' "
                              "WHERE ca_org_id = :c"), {"c": wsc_id})
        await db.commit()
        fx3 = await attempt("fixtures after address change", admin_router.get_social_fixtures(GRADE_BARE, db, ws))
        served = await crests.crest_image(db, str(ws.id), wsc_id) if crests else None
        check("a refresh by code leaves the upload in place", (centre(served) or (0, 0, 0, 0))[:3], (90, 0, 120))
        check("a refresh by code leaves the hand-set colour", g(fx3, "dates", 0, "fixtures", 0, "homeColor"), "#123456")
        await attempt("drop upload", lambda: admin_router.patch_social_crest(
            wsc_id, admin_router.CrestUpdate(drop_upload=True, use_cleaned=True), db, ws, SuperUser()))
        served = await crests.crest_image(db, str(ws.id), wsc_id) if crests else None
        check("going back from an upload serves the cleaned crest again", (corner(served) or (0, 0, 0, 255))[3], 0)
        print("\n[crests] how a crest is cut out")
        ben_id = CLUBS["ben"][0]
        ben_row = (await db.execute(text("SELECT cut_style, clean_version, cleaned_png, original_png FROM association_crests "
                                          "WHERE ca_org_id = :c"), {"c": ben_id})).mappings().first() if crests else None
        styles = crests.cut_styles(ben_row["original_png"]) if (crests and ben_row and hasattr(crests, "cut_styles")) else None
        check("a dark crest (navy on white) is put on a white edge by itself, so it reads on a dark post",
              bool(styles) and ben_row["cleaned_png"] == styles["edge"])
        wsc_styles = crests.cut_styles((await db.execute(text("SELECT original_png FROM association_crests WHERE ca_org_id = :c"),
                                                         {"c": wsc_id})).scalar()) if (crests and hasattr(crests, "cut_styles")) else None
        check("a bright crest stays a plain cut-out", bool(wsc_styles) and wsc_styles["auto"] == wsc_styles["plain"])
        await attempt("plain style", lambda: admin_router.patch_social_crest(
            ben_id, admin_router.CrestUpdate(cut_style="plain"), db, ws, SuperUser()))
        served = await crests.crest_image(db, str(ws.id), ben_id) if crests else None
        check("choosing Cut out serves the plain cut-out", bool(styles) and served == styles["plain"])
        bad_style = None
        try:
            await admin_router.patch_social_crest(ben_id, admin_router.CrestUpdate(cut_style="glow"), db, ws, SuperUser())
        except HTTPException as e:
            bad_style = e.status_code
        except Exception:
            bad_style = "crash"
            await db.rollback()
            await db.refresh(ws)
            await db.refresh(club)
        check("an unknown cut style is refused", bad_style, 422)
        # A crest kept by the first clean-up is cleaned again from its original, with no fetch.
        sub_id = CLUBS["sub"][0]
        try:
            await db.execute(text("UPDATE association_crests SET clean_version = 1, cleaned_png = original_png "
                                  "WHERE ca_org_id = :c"), {"c": sub_id})
            await db.commit()
        except Exception:  # the control commit has no clean_version column
            await db.rollback()
            await db.refresh(ws)
            await db.refresh(club)
        before = len(FETCHES)
        await attempt("fixtures re-clean", admin_router.get_social_fixtures(MATCH_LINK, db, ws))
        sub_row = (await db.execute(text("SELECT * FROM association_crests WHERE ca_org_id = :c"), {"c": sub_id})).mappings().first()
        check("a crest from an older clean-up is cleaned again", (sub_row or {}).get("clean_version"),
              getattr(crests, "CLEAN_VERSION", "missing"))
        check("its background is off again (corner see-through)", (corner((sub_row or {}).get("cleaned_png")) or (0, 0, 0, 255))[3], 0)
        check("re-cleaning fetched nothing for that club (made from the kept original)",
              [u for u in FETCHES[before:] if u == cdn("sub")], [])

        def lettering(hole_px, disc=False):
            import io as _i
            from PIL import Image as _I, ImageDraw as _D
            im = _I.new("RGBA", (300, 300), (255, 255, 255, 255))
            d = _D.Draw(im)
            d.ellipse((40, 40, 260, 260), fill=(120, 20, 40, 255))
            if disc:
                d.ellipse((60, 60, 240, 240), fill=(255, 255, 255, 255))   # a big white disc inside a ring
            else:
                d.ellipse((150 - hole_px, 150 - hole_px, 150 + hole_px, 150 + hole_px), fill=(255, 255, 255, 255))  # an O's hole
            b = _i.BytesIO()
            im.save(b, "PNG")
            return b.getvalue()
        if crests and hasattr(crests, "cut_styles"):
            o_hole = crests.cut_styles(crests.original_png(lettering(8)))["plain"]
            ring = crests.cut_styles(crests.original_png(lettering(0, disc=True)))["plain"]
            check("the background showing through a letter's hole is cleared", centre(o_hole)[3], 0)
            check("a big white disc inside a ring is the crest's own and stays", centre(ring)[:3], (255, 255, 255))
            from PIL import Image as _I2
            im = _I2.open(_io.BytesIO(o_hole)).convert("RGBA")
            pale = [p for p in im.getdata() if p[3] > 40 and sum(p[:3]) > 3 * 200]
            check("no pale fringe left on the crest's edge", len(pale), 0)
        else:
            check("cut styles exist", False)

        refused_lib = None
        try:
            await admin_router.get_social_crests(db, club)
        except HTTPException as e:
            refused_lib = e.status_code
        except Exception:
            refused_lib = "crash"
            await db.rollback()
            await db.refresh(ws)
            await db.refresh(club)
        check("a club has no crest library", refused_lib, 404)

        fx2 = await attempt("fixtures by match link", admin_router.get_social_fixtures(MATCH_LINK, db, ws))
        r2 = [r.get("home") for r in g(fx2, "dates", 0, "fixtures", default=[])]
        check("a match link pulls its whole round, every club", r2,
              ["APPLECROSS", "SUBIACO MARIST", "BENTLEY BLACK", "KALAMUNDA"])
        check("a club with two teams in the grade keeps each team's own name",
              (g(fx2, "dates", 0, "fixtures", 1, "opp"), g(fx2, "dates", 0, "fixtures", 2, "home")), ("BENTLEY RED", "BENTLEY BLACK"))
        check("the workspace's own name never claims a side (Applecross Socials)",
              g(fx2, "dates", 0, "fixtures", 0, "opp"), "WESTERN SUBURBS")

        nl = await attempt("fixtures no link", admin_router.get_social_fixtures("", db, ws))
        check("no link asks for one (a workspace has no club games)", g(nl, "kind"), "needs_link")
        ph = await attempt("fixtures playhq", admin_router.get_social_fixtures(PLAYHQ, db, ws))
        check("[both] a PlayHQ game-centre link is explained", g(ph, "kind"), "playhq")

        print("\n[results] the round's results across the grade")
        CALLS["m2_reads"] = 0
        rr = await attempt("results", admin_router.get_social_results(GRADE_R2, False, db, ws))
        res = g(rr, "dates", 0, "results", default=[])
        check("two results: M1, and M2 after its re-read", [r.get("grade") for r in res], ["APPLECROSS", "SUBIACO MARIST"])
        check("a bare card is read once more past the cache", CALLS["m2_reads"], 2)
        check("a card still bare is named, not silently dropped", g(rr, "skipped"), ["BENTLEY BLACK V SWAN VALLEY"])
        check("home side's score is `us`", (g(res, 0, "us"), g(res, 0, "them")), ("4/160", "150"))
        check("outcome read from the home side", g(res, 0, "outcome"), "W")
        check("margin comes from Cricket Australia's resultText", g(res, 0, "margin"), "BY 9 WICKETS")
        check("both sides' top performers come through", (g(res, 0, "topBat", 0, "name"), g(res, 0, "oppTopBat", 0, "name")),
              ("A. ACE", "W. WALLY"))
        check("abandoned match is not a result", bool(res) and not any(r.get("matchId") == M4 for r in res))
        check("leaders come from BOTH sides, best first", [(p.get("name"), p.get("team")) for p in g(res, 0, "leadBat", default=[])],
              [("A. ACE", "home"), ("W. WALLY", "away")])
        check("wicket takers from both sides, most wickets first",
              [(p.get("name"), p.get("team")) for p in g(res, 0, "leadBowl", default=[])],
              [("A. SPIN", "home"), ("W. QUICK", "away")])
        check("a side can hold both leading places", [p.get("team") for p in g(res, 1, "leadBat", default=[])], ["home", "home"])
        check("the winner is named by side, not W or L", (g(res, 0, "winnerSide"), g(res, 1, "winnerSide")), ("home", "home"))

        print("\n[team of the week] every club in the round, optional cap per club")
        tw = await attempt("totw", lambda: admin_router.get_social_totw(GRADE_R2, db, ws, "", "", "all", "week", 0))
        pool = g(tw, "players", default=[])
        clubs_in = {p.get("club") for p in pool}
        check("both sides of every scored match are pooled",
              {"APPLECROSS", "WESTERN SUBURBS", "SUBIACO MARIST", "BENTLEY RED"} <= clubs_in)
        check("top of the pool is the best performance (S One, 120)", (g(pool, 0, "last"), g(pool, 0, "points")), ("One", 120))
        check("no player is ever a club player id", all(p.get("pid") is None for p in pool) and bool(pool))
        app_p = next((p for p in pool if p.get("club") == "APPLECROSS"), {})
        check("a player carries their own club's crest (from the library)",
              str(app_p.get("clubLogo") or "").startswith(f"/api/images/association-crests/{ws.id}/{APPLECROSS_ORG}"))
        check("and their club's colour", app_p.get("clubColor"), "#143ca0")
        check("matches counted", g(tw, "matches"), 2)
        check("skipped match reported", g(tw, "skipped"), ["BENTLEY BLACK V SWAN VALLEY"])
        top11 = [p.get("club") for p in pool[:11]]
        check("uncapped: Subiaco Marist has 3 in the top 11", top11.count("SUBIACO MARIST") >= 3)
        tw2 = await attempt("totw cap 2", lambda: admin_router.get_social_totw(GRADE_R2, db, ws, "", "", "all", "week", 2))
        pool2 = g(tw2, "players", default=[])
        top2 = [p.get("club") for p in pool2[:6]]
        check("cap 2: no club has more than 2 at the top", max((top2.count(c) for c in set(top2)), default=99) <= 2)
        over = [p for p in pool2 if p.get("overCap")]
        check("a capped player is kept, moved down and flagged", bool(over) and pool2.index(over[0]) >= 6
              and over[0].get("club") == "SUBIACO MARIST")
        check("cap echoed", g(tw2, "cap"), 2)
        check("the pool says how many clubs it holds", g(tw2, "clubs"), 4)
        if sc is not None:
            check("apply_club_cap(0) leaves the pool alone", sc.apply_club_cap([{"club": "A"}] * 3, 0), [{"club": "A"}] * 3)
            spread = sc.apply_club_cap([{"club": c} for c in "AAABBC"], 1)
            check("past the cap the clubs take turns (A B C, then A B, then A)", "".join(p["club"] for p in spread), "ABCABA")
            check("only the first of each club is within the cap", [bool(p.get("overCap")) for p in spread],
                  [False, False, False, True, True, True])
        else:
            check("apply_club_cap exists", False)

        print("\n[player of the match] both sides, each with their own club")
        pm = await attempt("potm", admin_router.get_social_potm(M1, db, ws))
        pp = g(pm, "players", default=[])
        check("players from both sides", {p.get("club") for p in pp}, {"APPLECROSS", "WESTERN SUBURBS"})
        wally = next((p for p in pp if p.get("last") == "Wally"), {})
        check("an away player names the home side as opponent", (wally.get("opp"),
              str(wally.get("oppLogo") or "").startswith(f"/api/images/association-crests/{ws.id}/{APPLECROSS_ORG}")),
              ("APPLECROSS", True))

        print("\n[scorecard] each side's crest and colour")
        # The harness has no merge_logs table (a raw lifespan table), so the
        # scorecard's best-effort merge lookup fails and rolls back: the
        # workspace must come through that rollback readable.
        scd = await attempt("workspace scorecard", admin_router.get_social_scorecard(M1, db, SuperUser(), ws))
        check("home side's crest from the library", str(g(scd, "home", "logo", default="")).startswith(lib + str(APPLECROSS_ORG)))
        check("away side's crest from the library", str(g(scd, "away", "logo", default="")).startswith(lib + CLUBS["wsc"][0]))
        # Western Suburbs' colour was set by hand above, so it is that one.
        check("each side's colour from its crest (or set by hand), not the stock blue and red",
              (g(scd, "home", "color"), g(scd, "away", "color")), ("#143ca0", "#123456"))
        csc = await attempt("club scorecard", admin_router.get_social_scorecard(M1, db, SuperUser(), club))
        check("[club] an opponent with no hosted crest prints its club's Cricket Australia crest (was a monogram)",
              g(csc, "away", "logo"), cdn("wsc"))

        await db.rollback()
        await db.refresh(ws)
        await db.refresh(club)
        print("\n[lineups and match list]")
        lu = await attempt("lineups", admin_router.get_social_competition_lineups(GRADE_BARE, db, ws)) \
            if hasattr(admin_router, "get_social_competition_lineups") else None
        check("lineups route exists", hasattr(admin_router, "get_social_competition_lineups"))
        lm = g(lu, "matches", default=[])
        check("one entry per Round 3 match", len(lm), 2)
        check("home side first, no side is ours", [(t.get("label"), t.get("is_home"), t.get("is_ours")) for t in g(lm, 0, "teams", default=[])],
              [("WESTERN SUBURBS", True, False), ("SUBIACO MARIST", False, False)])
        check("each side carries its crest from the library", str(g(lm, 0, "teams", 0, "logo_url", default="")).startswith(lib))
        check("published side carries its players and keeper", (len(g(lm, 0, "teams", 0, "players", default=[])),
              g(lm, 0, "teams", 0, "players", 0, "is_wicket_keeper")), (11, True))
        ml = await attempt("matches", admin_router.get_social_competition_matches(GRADE_R2, ws)) \
            if hasattr(admin_router, "get_social_competition_matches") else None
        check("match pick list for the round", [(m.get("home"), m.get("completed")) for m in g(ml, "matches", default=[])],
              [("APPLECROSS", True), ("SUBIACO MARIST", True), ("BENTLEY BLACK", True), ("KALAMUNDA", False)])
        lk = await attempt("match lookup", admin_router.social_match_lookup(MATCH_LINK, db, ws))
        check("match lookup resolves a match link", (g(lk, "kind"), g(lk, "match_id")), ("match", M1))
        lk2 = await attempt("match lookup grade", admin_router.social_match_lookup(GRADE_R2, db, ws))
        check("a grade link is not one match", g(lk2, "kind"), "invalid")

        print("\n[club] a club is unchanged")
        await db.rollback()
        await db.refresh(club)  # any failed step above expired it
        refused = None
        if hasattr(admin_router, "get_social_competition_lineups"):
            try:
                await admin_router.get_social_competition_lineups(GRADE_BARE, db, club)
            except HTTPException as e:
                refused = e.status_code
        check("a club cannot read a whole grade's lineups", refused, 404)
        seen = {}

        async def sentinel(db_, org_, q_):
            seen["q"] = q_
            return {"kind": "club-path"}
        orig = social_rounds.social_fixtures_for_reference
        social_rounds.social_fixtures_for_reference = sentinel
        try:
            cf = await attempt("club fixtures", admin_router.get_social_fixtures(MATCH_LINK, db, club))
        finally:
            social_rounds.social_fixtures_for_reference = orig
        check("[club] a club's link pull still takes the club path", g(cf, "kind"), "club-path")
        row = social_rounds._result_row(CARDS[M1], club, [], "2nd Grade")
        check("[club] a club's result row still reads its own side", (g(row, "us"), g(row, "opp")), ("4/160", "HOLA HEALTH WSCC"))
        check("club Results margin reads resultText (was blank)", g(row, "margin"), "BY 9 WICKETS")

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
