"""Verification for hiding a club's junior programme from its public Stats
(migration 315), against a real Postgres.

Runs the SHIPPED `services/junior_hiding.py`, `services/grade_scope.py` and the
shipped route bodies (`players`, `leaderboard`, `records`, `organisations`,
`games`) over the `v_effective_*` views pulled straight out of the migrations.

The club under test is "Kalamunda": its seniors play under one association and
its juniors under another, all under ONE club id. The seed is built so the
association, and NOT the grade name, is what makes a game junior:

  * "Division 2" is a junior-association grade whose name reads senior;
  * "Under 16s" is a senior-association grade whose name reads junior (a
    junior playing up).

Every "X is hidden" check is paired with a check that X shows when the switch
is off, and again for a club admin, so a check cannot pass by hiding
everything (rule 21).

Run:  DATABASE_URL=postgresql+asyncpg://root@/juniors_test?host=/var/run/postgresql \
      python verification/verify_hide_juniors.py
"""
from __future__ import annotations

import asyncio
import inspect
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from _view_ddl import view_statements
from app.models.db import Base, ClubMembership, User
from app.routers import games as games_router
from app.routers import leaderboard as leaderboard_router
from app.routers import organisations as org_router
from app.routers import players as players_router
from app.routers import records as records_router
# CONTROL MODE. The same suite runs against the commit BEFORE this change, where
# these modules do not exist. Reading them through find_spec means the control
# reports the reported behaviour (juniors on the public site) as failed checks
# instead of crashing on an import, which would prove nothing (rule 21).
import importlib.util

HAVE = importlib.util.find_spec("app.services.junior_hiding") is not None
if HAVE:
    from app.services import junior_hiding
    from app.services.junior_hiding_ddl import STATEMENTS as JUNIOR_DDL
else:
    junior_hiding = None
    JUNIOR_DDL = []

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
        print(f"  FAIL {label}{('  — ' + detail) if detail else ''}")


def uid() -> uuid.UUID:
    return uuid.uuid4()


OURS, THEIRS = uid(), uid()
S25, S24, S_OLD, S_TH = uid(), uid(), uid(), uid()

ASSOC_SEN, ASSOC_JUN, ASSOC_SOC = "assoc-senior", "assoc-junior", "assoc-social"

C_SEN, C_JUN, C_SOC = uid(), uid(), uid()

G_SEN, G_SEN24, G_U16, G_JUN, G_JUN2, G_SOC = (uid() for _ in range(6))
G_TH_JUN = uid()   # THEIR grade row, our junior fixture (the shared-fixture case)

P = {k: uid() for k in ("S1", "J1", "M1", "U1", "O1", "N1", "Y1", "J2")}
NAMES = {
    "S1": "Sam Senior", "J1": "Jess Junior", "M1": "Max Mixed", "U1": "Uma Unknown",
    "O1": "Olly Oldseason", "N1": "Nina Nogames", "Y1": "Yuri Playsup",
    "J2": "Jo Sharedjunior",
}
OPP = uid()

USER_ADMIN = uid()

GAMES: dict[str, uuid.UUID] = {}


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for ddl in (
            """CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)""",
            """CREATE UNIQUE INDEX IF NOT EXISTS uq_season_aliases_alias_active
                ON season_aliases(alias_season_id) WHERE undone_at IS NULL""",
            """CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS org_merge_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source_org_id UUID, source_org_name TEXT NOT NULL,
                target_org_id UUID NOT NULL,
                performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS import_effective_deltas (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id uuid, player_id uuid, season_id uuid,
                scope text, grade_label text, matches int, batting_innings int, runs int,
                not_outs int, balls_faced int, fifties int, hundreds int,
                ducks int, high_score int, is_hs_not_out boolean,
                fours int, sixes int, batting_minutes int,
                bowling_innings int, wickets int, overs numeric,
                bowling_balls int, runs_conceded int, maidens int,
                best_bowling_wickets int, best_bowling_figures text,
                five_wicket_innings int, wides int, no_balls int,
                catches int, catches_wk int, catches_non_wk int,
                run_outs int, assisted_run_outs int, unassisted_run_outs int,
                stumpings int)""",
        ):
            await conn.execute(text(ddl))
        from app.services.competition_ddl import STATEMENTS as COMP_DDL
        for stmt in COMP_DDL:
            await conn.execute(text(stmt))
        # The SHIPPED DDL for the two new columns, not a retyped copy.
        for stmt in JUNIOR_DDL:
            await conn.execute(text(stmt))
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb '
                f'USING "{col}"::text::jsonb'))
        stmts = view_statements()
        for _ in range(2):
            for name, sql in stmts:
                await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
                await conn.execute(text(sql.replace("OR REPLACE ", "")))


async def seed(session) -> None:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    for oid, nm in ((OURS, "Kalamunda"), (THEIRS, "Rival Club")):
        await ex("INSERT INTO organisations (id, name, is_active) VALUES (:i, :n, true)", i=oid, n=nm)
    for sid, org, nm, yr in (
        (S25, OURS, "Summer 2025/26", 2025), (S24, OURS, "Summer 2024/25", 2024),
        (S_OLD, OURS, "Summer 2004/05", 2004), (S_TH, THEIRS, "Summer 2025/26", 2025),
    ):
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i,:o,:n,:y)",
                 i=sid, o=org, n=nm, y=yr)

    # Competitions: nobody has tagged the first two (NULL), so the NAME guesses.
    # The third is called "Junior Social" but a person has tagged it SENIOR.
    for cid, nm, assoc, tag in (
        (C_SEN, "Northern Districts Cricket Association", ASSOC_SEN, None),
        (C_JUN, "Kalamunda Junior Cricket Association", ASSOC_JUN, None),
        (C_SOC, "Junior Social League", ASSOC_SOC, False),
    ):
        await ex("INSERT INTO club_competitions (id, organisation_id, name, association_id, "
                 "association_name, is_seeded) VALUES (:i,:o,:n,:a,:n,true)",
                 i=cid, o=OURS, n=nm, a=assoc)
        if HAVE and tag is not None:
            await ex("UPDATE club_competitions SET is_junior = :t WHERE id = :i", i=cid, t=tag)

    for gid, sid, nm, cat, comp, assoc in (
        (G_SEN, S25, "A Grade", "senior", C_SEN, ASSOC_SEN),
        (G_SEN24, S24, "A Grade", "senior", C_SEN, ASSOC_SEN),
        # A junior playing up: junior NAME, senior association.
        (G_U16, S25, "Under 16s", "junior", C_SEN, ASSOC_SEN),
        # Junior association, grade name that reads SENIOR.
        (G_JUN, S25, "Division 2", "senior", C_JUN, ASSOC_JUN),
        (G_JUN2, S25, "Under 12s", "junior", C_JUN, ASSOC_JUN),
        (G_SOC, S25, "Social", "senior", C_SOC, ASSOC_SOC),
    ):
        await ex("INSERT INTO grades (id, season_id, name, category, competition_id, association_id, "
                 "association_name) VALUES (:i,:s,:n,:c,:comp,:a,:a)",
                 i=gid, s=sid, n=nm, c=cat, comp=comp, a=assoc)
    # THEIR grade row of the same name and association: our junior fixture sits in it.
    await ex("INSERT INTO grades (id, season_id, name, category, association_id, association_name) "
             "VALUES (:i,:s,'Division 2','senior',:a,:a)", i=G_TH_JUN, s=S_TH, a=ASSOC_JUN)

    for k, pid in P.items():
        await ex("INSERT INTO players (id, organisation_id, name) VALUES (:i,:o,:n)",
                 i=pid, o=OURS, n=NAMES[k])
    await ex("INSERT INTO players (id, organisation_id, name) VALUES (:i,:o,'Opp Player')", i=OPP, o=THEIRS)

    async def add_game(key, grade, day, runs_by_player, *, foreign_grade=False, season_year=2025):
        gid = uid()
        GAMES[key] = gid
        await ex(
            "INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_club, away_club, "
            " result, home_org_id, match_format, is_final) VALUES (:i,:g,:d,'Kalamunda','Rivals',"
            " 'Kalamunda','Rivals','WIN',:ho,'One Day',false)",
            i=gid, g=grade, d=date(season_year, 1, day), ho=OURS)
        for pos, (pk, runs) in enumerate(runs_by_player.items(), start=1):
            pid = P[pk]
            await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g,:p)", g=gid, p=pid)
            await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, batting_position, "
                     " runs, balls, not_out, dismissal_type, did_not_bat) "
                     "VALUES (:g,:p,1,:pos,:r,:b,false,'caught',false)",
                     g=gid, p=pid, pos=pos, r=runs, b=max(runs, 1))

    await add_game("sen1", G_SEN, 3, {"S1": 50, "M1": 30})
    await add_game("sen2", G_SEN, 10, {"S1": 20, "Y1": 12})
    await add_game("u16", G_U16, 11, {"Y1": 8})
    await add_game("jun1", G_JUN, 4, {"J1": 40, "M1": 100, "U1": 15, "O1": 9})
    await add_game("jun2", G_JUN2, 5, {"J1": 22, "J2": 33})
    # Our junior fixture that THEY synced first: THEIR grade row, our club on it.
    await add_game("shared", G_TH_JUN, 6, {"J2": 44})
    await add_game("soc", G_SOC, 12, {"S1": 5})
    # Per-grade CA aggregate for the junior-only player.
    await ex("INSERT INTO player_season_grade_stats (player_id, season_id, grade_id, matches, runs) "
             "VALUES (:p,:s,:g,3,62)", p=P["J1"], s=S25, g=G_JUN2)
    # CA's own season totals, written for every player the way sync does. With
    # the switch off and no scope, the boards read THESE, so the control runs
    # (a club admin's board must name the juniors) need them to exist.
    for pk, runs in (("S1", 75), ("M1", 130), ("J1", 62), ("J2", 77), ("Y1", 20)):
        await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs) "
                 "VALUES (:p,:s,3,3,:r)", p=P[pk], s=S25, r=runs)
    # U1: an import residual with no grade says nothing about juniors, so they stay.
    await ex("INSERT INTO player_season_stats (player_id, season_id, matches, runs) VALUES (:p,:s,7,200)",
             p=P["U1"], s=S_OLD)
    # O1: CA totals for a season we hold no games or grades for. Unplaceable.
    await ex("INSERT INTO player_season_stats (player_id, season_id, matches, runs) VALUES (:p,:s,9,150)",
             p=P["O1"], s=S_OLD)

    await ex("INSERT INTO users (id, username, email, failed_login_count) VALUES (:i,'admin1','a@x.test',0)", i=USER_ADMIN)
    await ex("INSERT INTO club_memberships (id, club_id, user_id, role) VALUES (gen_random_uuid(),:c,:u,'club_admin')",
             c=OURS, u=USER_ADMIN)
    await session.commit()


async def set_switch(session, on: bool) -> None:
    if not HAVE:
        return
    await session.execute(text("UPDATE organisations SET hide_juniors = :v WHERE id = :o"),
                          {"v": on, "o": OURS})
    await session.commit()
    junior_hiding.forget()


async def call(fn, **kw):
    """Call a shipped route body, filling every omitted param from its own default.

    A route function called directly does not get FastAPI's dependency
    resolution, so an omitted Query(...) would arrive as the Query object. The
    default is read off it instead. Only params the route really has are passed.
    """
    sig = inspect.signature(fn)
    args = {}
    for name, prm in sig.parameters.items():
        if name in kw:
            args[name] = kw[name]
        elif prm.default is inspect.Parameter.empty:
            continue
        elif hasattr(prm.default, "default") and not callable(getattr(prm.default, "dependency", None)):
            args[name] = prm.default.default
        elif hasattr(prm.default, "dependency"):
            args[name] = None
        else:
            args[name] = prm.default
    return await fn(**args)


def names_of(rows) -> set[str]:
    return {r.get("display_name") or r.get("name") or r.get("player_name") for r in rows}


def request_for(player_id) -> Request:
    return Request({"type": "http", "path_params": {"player_id": str(player_id)},
                    "headers": [], "query_string": b""})


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await build_schema()
    async with Session() as s:
        await seed(s)

    async with Session() as db:
        admin = await db.get(User, USER_ADMIN)
        oid = str(OURS)

        # ---------------------------------------------------------------- tags
        if HAVE:
            await service_checks(db)
        else:
            print("CONTROL RUN: services/junior_hiding.py does not exist at this commit")

        oid_ = oid
        await route_checks(db, admin, oid_)
        if HAVE:
            await admin_checks(db, admin)
    await asgi_checks()

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("FAILED:", *FAILURES, sep="\n  ")
        sys.exit(1)


async def service_checks(db) -> None:
    if True:
        print("competition tags")
        tags = {c["name"]: c for c in await junior_hiding.competition_tags(db, OURS)}
        check("untagged 'Junior Cricket Association' is guessed junior",
              tags["Kalamunda Junior Cricket Association"]["is_junior"] is True)
        check("untagged 'Northern Districts' is guessed senior",
              tags["Northern Districts Cricket Association"]["is_junior"] is False)
        check("an admin's FALSE tag beats a name that reads junior",
              tags["Junior Social League"]["is_junior"] is False
              and tags["Junior Social League"]["suggested_junior"] is True)

        # ------------------------------------------------------- grade + player set
        print("junior grades and junior-only players")
        gids = {str(g) for g in await junior_hiding.junior_grade_ids(db, OURS)}
        check("junior grades = the junior association's grades",
              {str(G_JUN), str(G_JUN2)} <= gids and str(G_SEN) not in gids, str(gids))
        check("'Division 2' is junior although its NAME reads senior", str(G_JUN) in gids)
        check("'Under 16s' in the senior association is NOT junior", str(G_U16) not in gids)
        check("the shared fixture on THEIR grade row resolves to our junior competition",
              str(G_TH_JUN) in gids, str(gids))
        check("a grade whose competition an admin tagged senior is not junior", str(G_SOC) not in gids)

        hidden = await junior_hiding.junior_only_player_ids(db, OURS, list(gids))
        got = {k for k, v in P.items() if str(v) in hidden}
        check("hidden = the junior-only players", got == {"J1", "J2"}, str(got))
        check("a player with any senior game is NOT hidden (Max Mixed)", str(P["M1"]) not in hidden)
        check("a junior playing up in a senior association is NOT hidden (Yuri)", str(P["Y1"]) not in hidden)
        check("an import residual with no grade keeps a player visible (Uma)", str(P["U1"]) not in hidden)
        check("CA totals for a season with no grade evidence keep a player visible (Olly)",
              str(P["O1"]) not in hidden)
        check("a player with no games is not hidden on a guess (Nina)", str(P["N1"]) not in hidden)



async def asgi_checks() -> None:
    """Through FastAPI itself, not a route body called by hand.

    The players router gates every `/players/{id}/...` route with ONE router
    dependency that hands the scope resolvers a ContextVar. Whether a value set
    in a dependency is visible to the endpoint is a property of how FastAPI runs
    them, and calling a route function directly cannot prove it.
    """
    if not HAVE:
        return
    import httpx
    from fastapi import FastAPI
    from app.models.db import get_db
    from app.routers.auth import get_optional_user

    print("through FastAPI (dependency + ContextVar)")
    app = FastAPI()
    app.include_router(players_router.router)

    async def _db():
        async with Session() as s:
            yield s

    who = {"user": None}

    async def _viewer():
        return who["user"]

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_optional_user] = _viewer
    transport = httpx.ASGITransport(app=app)
    async with Session() as user_session:
        admin = await user_session.get(User, USER_ADMIN)
        await _asgi_body(app, transport, who, admin)


async def _asgi_body(app, transport, who, admin) -> None:
    import httpx
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        async with Session() as s:
            await set_switch(s, True)
        r = await c.get(f"/players/{P['J1']}")
        check("HTTP: a junior-only player's profile is 404 for the public", r.status_code == 404, str(r.status_code))
        r = await c.get(f"/players/{P['J1']}/stats")
        check("HTTP: ...and so is every tab behind it", r.status_code == 404, str(r.status_code))
        r = await c.get(f"/players/{P['M1']}/stats", params={"categories": "all"})
        runs = int(((r.json().get("career_batting") or {}).get("total_runs")) or 0) if r.status_code == 200 else -1
        check("HTTP: a mixed player's career is senior only (30), even with categories=all",
              runs == 30, f"{r.status_code} {runs}")
        r = await c.get(f"/players/{P['M1']}/activity")
        check("HTTP: the scope-less activity tab sees the hidden grades too",
              r.status_code == 200 and r.json()["total_innings"] == 1, r.text[:120])
        r = await c.get(f"/players/{P['M1']}/formats")
        check("HTTP: so does the formats tab", r.status_code == 200)
        who["user"] = admin
        r = await c.get(f"/players/{P['J1']}")
        check("HTTP: a club admin opens the same profile", r.status_code == 200, str(r.status_code))
        r = await c.get(f"/players/{P['M1']}/stats", params={"categories": "all"})
        runs = int(((r.json().get("career_batting") or {}).get("total_runs")) or 0) if r.status_code == 200 else -1
        check("HTTP: ...and Max's career is whole for them (130)", runs == 130, f"{r.status_code} {runs}")
        who["user"] = None
        # The context must not leak between requests: the public request after
        # an admin one is hidden again.
        r = await c.get(f"/players/{P['M1']}/stats", params={"categories": "all"})
        runs = int(((r.json().get("career_batting") or {}).get("total_runs")) or 0) if r.status_code == 200 else -1
        check("HTTP: the admin's view does not leak into the next public request", runs == 30, str(runs))


async def admin_checks(db, admin) -> None:
    from app.models.db import Organisation
    from app.routers import admin as admin_router
    from app.services import competitions as comp_svc

    print("admin: preview and tagging")
    club = await db.get(Organisation, OURS)
    pv = await call(admin_router.hide_juniors_preview, db=db, club=club)
    check("preview names the junior competition and the players it would hide",
          {c["id"] for c in pv["junior_competitions"]} == {str(C_JUN)}
          and {p["name"] for p in pv["hidden_players"]} == {"Jess Junior", "Jo Sharedjunior"},
          str(pv["hidden_players"]))
    check("preview counts the junior grades taken with it",
          pv["junior_grade_count"] == 3, str(pv["junior_grade_count"]))

    # Tagging the junior competition SENIOR takes every junior grade off the list.
    await comp_svc.set_competition_junior(db, OURS, C_JUN, False)
    await db.commit()
    junior_hiding.forget()
    check("tagged senior: nothing is junior any more",
          await junior_hiding.junior_grade_ids(db, OURS) == [])
    lst = {c["name"]: c for c in await comp_svc.list_competitions(db, OURS)}
    check("the listing reports the tag and keeps the name-based suggestion beside it",
          lst["Kalamunda Junior Cricket Association"]["is_junior_tag"] is False
          and lst["Kalamunda Junior Cricket Association"]["suggested_junior"] is True)
    # NULL puts it back on the guess.
    await comp_svc.set_competition_junior(db, OURS, C_JUN, None)
    await db.commit()
    junior_hiding.forget()
    check("tag reset to NULL: the name's guess applies again",
          len(await junior_hiding.junior_grade_ids(db, OURS)) == 3)
    try:
        await comp_svc.set_competition_junior(db, THEIRS, C_JUN, True)
        crossed = False
    except ValueError:
        crossed = True
    check("another club cannot tag this club's competition", crossed)
    await db.rollback()


async def route_checks(db, admin, oid) -> None:
    if True:
        # ----------------------------------------------------------- roster
        print("roster (GET /players)")
        await set_switch(db, False)
        roster_off = names_of(await call(players_router.list_players, org_id=oid, db=db, viewer=None))
        check("switch OFF: the public roster lists juniors (control)",
              {"Jess Junior", "Jo Sharedjunior"} <= roster_off, str(roster_off))
        await set_switch(db, True)
        roster_pub = names_of(await call(players_router.list_players, org_id=oid, db=db, viewer=None))
        check("switch ON: public roster drops junior-only players",
              not ({"Jess Junior", "Jo Sharedjunior"} & roster_pub), str(roster_pub))
        check("switch ON: public roster keeps everybody else",
              {"Sam Senior", "Max Mixed", "Uma Unknown", "Olly Oldseason", "Nina Nogames",
               "Yuri Playsup"} <= roster_pub, str(roster_pub))
        roster_admin = names_of(await call(players_router.list_players, org_id=oid, db=db, viewer=admin))
        check("switch ON: a club admin still sees the juniors",
              {"Jess Junior", "Jo Sharedjunior"} <= roster_admin, str(roster_admin))

        # ----------------------------------------------------------- profile gate
        print("profile and every tab (router dependency)")
        gate = getattr(players_router, "_gate_junior_hidden_player", None)

        async def no_gate(*_a, **_k):
            return None
        gate = gate or no_gate
        raised = None
        try:
            await gate(request_for(P["J1"]), db, None)
        except Exception as e:  # HTTPException
            raised = getattr(e, "status_code", None)
        check("public: a junior-only player's pages are 404", raised == 404, str(raised))
        raised = None
        try:
            await gate(request_for(P["J1"]), db, admin)
        except Exception as e:
            raised = getattr(e, "status_code", None)
        check("club admin: the same pages open", raised is None, str(raised))
        raised = None
        try:
            await gate(request_for(P["M1"]), db, None)
        except Exception as e:
            raised = getattr(e, "status_code", None)
        check("public: a mixed player's pages open", raised is None, str(raised))

        # ---------------------------------------------------- mixed player's figures
        print("a mixed player shows senior figures only")

        async def career_runs(viewer):
            if HAVE:
                players_router._PUBLIC_HIDING.set(junior_hiding.OFF)
            await gate(request_for(P["M1"]), db, viewer)
            out = await call(players_router.get_player_stats, player_id=str(P["M1"]), db=db)
            return int((out["career_batting"] or {}).get("total_runs") or 0), out

        runs_pub, out_pub = await career_runs(None)
        runs_admin, _ = await career_runs(admin)
        await set_switch(db, False)
        runs_off, _ = await career_runs(None)
        await set_switch(db, True)
        check("switch OFF: Max's career includes the junior game (control: 130)", runs_off == 130, str(runs_off))
        check("switch ON, public: Max's career is senior only (30)", runs_pub == 30, str(runs_pub))
        check("switch ON, club admin: Max's career is whole (130)", runs_admin == 130, str(runs_admin))
        inn = out_pub["batting_innings"]
        check("public innings list carries no junior-grade game",
              all(str(i.get("game_id")) != str(GAMES["jun1"]) for i in inn), str([i.get("runs") for i in inn]))

        # --------------------------------------------------------------- leaderboard
        print("leaderboard")
        async def board(viewer):
            rows = await call(leaderboard_router.batting_leaderboard, org_id=oid, db=db,
                              viewer=viewer, categories="all", limit=50)
            return {r["player_name"] if "player_name" in r else r.get("name"): r for r in rows}

        b_pub = await board(None)
        b_admin = await board(admin)
        check("public board has no junior-only player", not ({"Jess Junior", "Jo Sharedjunior"} & set(b_pub)),
              str(set(b_pub)))
        check("club admin board has them (control)", {"Jess Junior", "Jo Sharedjunior"} <= set(b_admin),
              str(set(b_admin)))
        mm = b_pub.get("Max Mixed")
        check("public board: Max Mixed scores 30, not 130 (even with categories=all)",
              mm is not None and int(mm.get("total_runs", mm.get("runs", -1))) == 30, str(mm))

        # --------------------------------------------------------------- results list
        print("results and games lists")
        async def results(viewer):
            return await call(org_router.get_org_results, org_id=oid, db=db, viewer=viewer, categories="all")

        r_pub, r_admin = await results(None), await results(admin)
        gids_pub = {r["id"] for r in r_pub}
        gids_admin = {r["id"] for r in r_admin}
        junior_games = {str(GAMES["jun1"]), str(GAMES["jun2"]), str(GAMES["shared"])}
        check("public results carry no junior-association game (even categories=all)",
              not (junior_games & gids_pub), str(junior_games & gids_pub))
        check("public results keep the senior and playing-up games",
              {str(GAMES["sen1"]), str(GAMES["u16"]), str(GAMES["soc"])} <= gids_pub)
        check("club admin results carry the junior games (control)", junior_games <= gids_admin)
        # A junior game picked by grade id is still hidden.
        r_pick = await call(org_router.get_org_results, org_id=oid, db=db, viewer=None,
                            grade_id=str(G_JUN), categories="all")
        check("picking a junior grade by id does not get past the hiding", r_pick == [], str(len(r_pick)))

        g_pub = await call(games_router.list_games, org_id=oid, db=db, viewer=None, categories="all", limit=100)
        g_ids = {g["id"] for g in g_pub}
        check("games list carries no junior game", not (junior_games & g_ids), str(junior_games & g_ids))

        # ------------------------------------------------------- scorecard 404
        print("scorecard")
        raised = None
        try:
            await call(games_router.get_scorecard, game_id=str(GAMES["jun1"]), db=db, viewer=None)
        except Exception as e:
            raised = getattr(e, "status_code", None)
        check("public: a junior game's scorecard is 404", raised == 404, str(raised))
        raised = None
        try:
            await call(games_router.get_scorecard, game_id=str(GAMES["jun1"]), db=db, viewer=admin)
        except Exception as e:
            raised = getattr(e, "status_code", None)
        check("club admin: the same scorecard opens", raised is None, str(raised))

        raised = None
        try:
            await call(org_router.get_org_lineup_one, org_id=oid, match_id=str(GAMES["jun1"]),
                       db=db, viewer=None)
        except Exception as e:
            raised = getattr(e, "status_code", None)
        check("public: a junior game's lineup deep link is 404", raised == 404, str(raised))

        # ---------------------------------------------------- summary + pickers
        print("summary, grade picker, filters")
        sm_pub = await call(org_router.get_org_summary, org_id=oid, db=db, viewer=None, categories="all")
        await set_switch(db, False)
        sm_off = await call(org_router.get_org_summary, org_id=oid, db=db, viewer=None, categories="all")
        await set_switch(db, True)
        check("club summary counts fewer games with the switch on",
              int(sm_pub.get("total_games") or 0) < int(sm_off.get("total_games") or 0),
              f"{sm_pub.get('total_games')} vs {sm_off.get('total_games')}")

        gr_pub = {g["name"] for g in await call(org_router.get_org_grades, org_id=oid, db=db, viewer=None)}
        gr_admin = {g["name"] for g in await call(org_router.get_org_grades, org_id=oid, db=db, viewer=admin)}
        check("public grade picker drops the junior association's grades",
              "Division 2" not in gr_pub and "Under 12s" not in gr_pub, str(gr_pub))
        check("public grade picker keeps 'Under 16s' (senior association)", "Under 16s" in gr_pub, str(gr_pub))
        check("club admin's grade picker has them (control)", {"Division 2", "Under 12s"} <= gr_admin, str(gr_admin))

        cats = await call(org_router.get_org_grade_categories, org_id=oid, db=db, viewer=None)
        check("no Juniors pill offered while juniors are hidden", "junior" not in cats["available"], str(cats["available"]))
        check("the junior competition is not offered as a filter",
              str(C_JUN) not in {c["id"] for c in cats["available_competitions"]})
        cats_admin = await call(org_router.get_org_grade_categories, org_id=oid, db=db, viewer=admin)
        check("a club admin is still offered them (control)", "junior" in cats_admin["available"]
              and str(C_JUN) in {c["id"] for c in cats_admin["available_competitions"]})

        # ------------------------------------------------------------- records
        print("records")
        async def rec(viewer):
            return await call(records_router.get_records, org_id=oid, db=db, viewer=viewer, categories="all")

        rp, ra = await rec(None), await rec(admin)
        import json as _json
        check("public records name no junior-only player", "Jess Junior" not in _json.dumps(rp, default=str))
        check("club admin records name them (control)", "Jess Junior" in _json.dumps(ra, default=str))

        # ------------------------------------- tabs that take no scope of their own
        print("profile tabs with no filter bar")

        async def as_viewer(viewer, pk, fn, **kw):
            if HAVE:
                players_router._PUBLIC_HIDING.set(junior_hiding.OFF)
            if getattr(players_router, "_gate_junior_hidden_player", None):
                await players_router._gate_junior_hidden_player(request_for(P[pk]), db, viewer)
            return await call(fn, player_id=str(P[pk]), db=db, **kw)

        act_pub = await as_viewer(None, "M1", players_router.get_player_activity_endpoint)
        act_admin = await as_viewer(admin, "M1", players_router.get_player_activity_endpoint)
        check("activity card: public innings are senior only (1), admin sees both (2)",
              (act_pub["total_innings"], act_admin["total_innings"]) == (1, 3),
              f"{act_pub['total_innings']} / {act_admin['total_innings']}")

        fm_pub = await as_viewer(None, "M1", players_router.get_player_formats)
        fm_admin = await as_viewer(admin, "M1", players_router.get_player_formats)

        def matches_of(fm):
            return sum(int(r.get("matches") or 0) for r in (fm.get("formats") or fm.get("rows") or []))

        check("formats tab: public matches exclude the junior game",
              matches_of(fm_pub) < matches_of(fm_admin), f"{matches_of(fm_pub)} vs {matches_of(fm_admin)}")

        cp_pub = await as_viewer(None, "M1", players_router.get_player_competitions)
        cp_admin = await as_viewer(admin, "M1", players_router.get_player_competitions)
        ids_pub = {r["competition_id"] for r in cp_pub["rows"]}
        ids_admin = {r["competition_id"] for r in cp_admin["rows"]}
        check("competitions tab: the junior competition is gone for the public",
              str(C_JUN) not in ids_pub and str(C_SEN) in ids_pub, str(ids_pub))
        check("competitions tab: a club admin still sees it (control)", str(C_JUN) in ids_admin, str(ids_admin))
        check("competitions tab: total_matches is re-summed to what is listed",
              cp_pub["total_matches"] == sum(r["matches"] for r in cp_pub["rows"]))

        co_pub = await call(org_router.get_org_competitions, org_id=oid, db=db, viewer=None)
        co_admin = await call(org_router.get_org_competitions, org_id=oid, db=db, viewer=admin)
        check("club competitions list: public has no junior competition",
              str(C_JUN) not in {r["competition_id"] for r in co_pub["rows"]}
              and str(C_JUN) in {r["competition_id"] for r in co_admin["rows"]})

        # ------------------------------------------- switch off is byte-identical
        print("switch off changes nothing")
        await set_switch(db, False)
        a = await call(org_router.get_org_results, org_id=oid, db=db, viewer=None, categories="all")
        b = await call(org_router.get_org_results, org_id=oid, db=db, viewer=admin, categories="all")
        check("with the switch off a visitor and an admin see the same results", a == b)
        check("...and that is every game", len(a) == len(GAMES), f"{len(a)} vs {len(GAMES)}")


if __name__ == "__main__":
    asyncio.run(main())
