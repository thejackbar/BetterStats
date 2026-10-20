"""BetterIQ's opposition scout honours the fixture's grade and the Grade Type /
Match Type filters.

Reported by a club: scouting a Swanbourne 3rd XI fixture with Grade Type Men's
and Match Type Two day returned "WHOLE CLUB · 3 SIDES" and a danger batter whose
79 came at a strike rate of 219, a T20 Div 1 innings for their 1st XI. Two causes:

  * the live dossier built its season form from every game the opponent's club
    played this season. The router resolved the Grade Type / Match Type scope,
    but nothing in `iq_opponent` read it, and the scope was not in the dossier's
    cache key either;
  * a scout started from a fixture used the fixture's grade only to pick the
    season, so with "All grades" in the filter bar it scouted the whole club.

Runs the SHIPPED `apply_grade_scope` dependency and `opposition_dossier` route
body, the real `resolve_scope`, and the real `v_effective_*` views on a real
Postgres. Only the Cricket Australia client is stubbed (no network).

    VERIFY_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/verify_iq_dossier_scope \\
      python -m verification.verify_iq_dossier_scope

Control run: the same file against the previous commit must FAIL on exactly the
"Lane (1st XI, T20) is absent" checks, and pass the "could be present" ones.
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
    "postgresql+asyncpg://postgres:postgres@localhost:5432/verify_iq_dossier_scope",
)
os.environ["DATABASE_URL"] = DB_URL

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from _view_ddl import view_statements  # noqa: E402
from app.models.db import Base, Organisation  # noqa: E402
from app.routers import iq as iq_router  # noqa: E402
from app.services import grade_scope, iq_filters, iq_opponent  # noqa: E402
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


# Home club (us), and the opponent, a synced club.
US, THEM = uuid.uuid4(), uuid.uuid4()
S_US, S_THEM = uuid.uuid4(), uuid.uuid4()
# Our grades: the 3rds the fixture is in, a 4th grade nobody has played yet, our T20 grade.
GA3, GA4, GA_T20 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
# Their grades: 1st XI T20 Div 1, the 3rds (two day, plus one T20 friendly), an Under 14.
GB_T20, GB3, GB_U14 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
# Their players.
LANE, SMITH, HITTER, KID, BOWL_3, BOWL_T20 = (uuid.uuid4() for _ in range(6))
NAMES = {LANE: "Lane, David", SMITH: "Smith, Sam", HITTER: "Hitter, Hugh", KID: "Kid, Kyle",
         BOWL_3: "Bowler, Ben", BOWL_T20: "Quick, Quinn"}
FX3, FX4 = uuid.uuid4(), uuid.uuid4()
OPP_NAME = "Swanbourne CC 3rd XI"


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
        # Migration 063 (not on the ORM): `_load_aliases` swallows a missing table
        # with a rollback, which would expire the session under the route body.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS opponent_aliases (
                id SERIAL PRIMARY KEY,
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                alias_name TEXT NOT NULL, opp_key TEXT NOT NULL, display_name TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_opponent_alias_org_name UNIQUE (organisation_id, alias_name))"""))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb '
                f'USING "{col}"::text::jsonb'))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        for oid, nm, slug in ((US, "Home CC", "home-cc-v"), (THEM, "Swanbourne CC", "swanbourne-v")):
            await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)",
                     i=oid, n=nm, s=slug)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2026/27', 2026)",
                 i=S_US, o=US)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2026/27', 2026)",
                 i=S_THEM, o=THEM)
        for gid, sid, nm, cat in (
                (GA3, S_US, "3rd Grade", "senior"), (GA4, S_US, "4th Grade", "senior"),
                (GA_T20, S_US, "T20 Div 1", "senior"),
                (GB_T20, S_THEM, "T20 Div 1", "senior"), (GB3, S_THEM, "3rd Grade", "senior"),
                (GB_U14, S_THEM, "Under 14", "junior")):
            await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                     "VALUES (:i, :s, :n, :g, :c, ARRAY[:c])", i=gid, s=sid, n=nm, g=str(gid), c=cat)
        for pid in NAMES:
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                     "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=THEM, n=NAMES[pid], g=str(pid))

        async def game(grade, fmt, on, home=THEM, away=None, opp_org="third-club", opp_name="Third CC"):
            gid = uuid.uuid4()
            await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, "
                     " opp_org_id, opp_club_name, match_format, status) "
                     "VALUES (:i, :g, :d, 'WIN', :h, :a, :oo, :on, :f, 'COMPLETED')",
                     i=gid, g=grade, d=on, h=home, a=away, oo=opp_org, on=opp_name, f=fmt)
            return gid

        async def bat(game_id, pid, runs, balls, not_out=False):
            await ex("INSERT INTO batting_innings (game_id, player_id, runs, balls, fours, sixes, not_out, "
                     " dismissal_type, did_not_bat, batting_position) "
                     "VALUES (:g, :p, :r, :b, 4, 2, :n, 'caught', false, 3)",
                     g=game_id, p=pid, r=runs, b=balls, n=not_out)

        async def bowl(game_id, pid, overs, runs, wkts):
            await ex("INSERT INTO bowling_spells (game_id, player_id, overs, maidens, runs, wickets) "
                     "VALUES (:g, :p, :o, 1, :r, :w)", g=game_id, p=pid, o=overs, r=runs, w=wkts)

        # THEIR 1st XI, T20 Div 1: Lane's 79 off 36 balls (SR 219), Quick's 4 wickets.
        g1 = await game(GB_T20, "T20", date(2026, 10, 3))
        await bat(g1, LANE, 79, 36)
        await bowl(g1, BOWL_T20, 4, 22, 4)
        # THEIR 3rds, two day: Smith, Bowler. Plus one T20 friendly inside the SAME grade (Hitter).
        g3a = await game(GB3, "Two Day", date(2026, 10, 3))
        await bat(g3a, SMITH, 45, 120)
        await bowl(g3a, BOWL_3, 18, 52, 3)
        g3b = await game(GB3, "T20", date(2026, 10, 4))
        await bat(g3b, HITTER, 60, 25)
        # THEIR Under 14s, one day.
        gj = await game(GB_U14, "One Day", date(2026, 10, 3))
        await bat(gj, KID, 50, 70)
        # OUR meetings with them: a two-day 3rd Grade game and a T20 one.
        await game(GA3, "Two Day", date(2026, 10, 10), home=US, away=THEM, opp_org=str(THEM), opp_name=OPP_NAME)
        await game(GA_T20, "T20", date(2026, 10, 11), home=US, away=THEM, opp_org=str(THEM), opp_name=OPP_NAME)
        # Fixtures: our 3rds, and our 4th grade (they have no side in it this season).
        for fid, gid in ((FX3, GA3), (FX4, GA4)):
            await ex("INSERT INTO fixtures (id, organisation_id, grade_id, source, played_on, opponent_name, status) "
                     "VALUES (:i, :o, :g, 'manual', :d, :n, 'UPCOMING')",
                     i=fid, o=US, g=gid, d=date(2026, 10, 17), n=OPP_NAME)
        await s.commit()


async def _fake_grade_matches(*_a, **_k):
    return []


async def _fake_scorecard(*_a, **_k):
    return None


async def scout(*, categories=None, formats=None, fixture=None, opponent=None, grade=None, team=None) -> dict:
    """The shipped route body, under the shipped scope dependency, polled to ready."""
    async with Session() as s:
        club = (await s.execute(select(Organisation).where(Organisation.id == US))).scalar_one()
        gen = iq_router.apply_grade_scope(categories=categories, formats=formats,
                                          competitions=None, db=s, club=club)
        await gen.__anext__()
        try:
            res: dict = {}
            for _ in range(150):
                res = await iq_router.opposition_dossier(
                    opponent=opponent, fixture_id=str(fixture) if fixture else None,
                    team=team, grade=grade, name=None, db=s, club=club)
                if res.get("status") != "building":
                    break
                await asyncio.sleep(0.2)
            return res
        finally:
            await gen.aclose()


def names(d: dict, key: str = "batting") -> set[str]:
    return {p.get("name") for p in (d.get(key) or [])}


def who(d: dict, key: str = "batting") -> str:
    return ", ".join(sorted(n or "?" for n in names(d, key))) or "(none)"


async def main() -> int:
    gr_client.get_grade_matches = _fake_grade_matches
    gr_client.get_match_scorecard = _fake_scorecard
    from app.services import iq_scout

    async def _no_external_teams(*_a, **_k):
        return []
    iq_scout.external_club_teams = _no_external_teams
    await build_schema()
    await seed()

    LANE_N, SMITH_N, HITTER_N, KID_N = (NAMES[p] for p in (LANE, SMITH, HITTER, KID))

    print("\n-- the reported scout: the 3rds fixture, Men's, Two day, 'All grades' --")
    d = await scout(categories="senior", formats="two_day", fixture=FX3)
    check("the dossier is built (status ready)", d.get("status") == "ready", str(d.get("status")))
    check("their 3rds' two-day batter is in the squad", SMITH_N in names(d), who(d))
    check("Lane (1st XI, T20 Div 1) is absent from the squad", LANE_N not in names(d), who(d))
    check("Hitter (3rds, but a T20 game) is absent: format is read per fixture", HITTER_N not in names(d), who(d))
    check("Kid (Under 14s) is absent", KID_N not in names(d), who(d))
    check("Lane is not a danger batter", LANE_N not in names(d, "danger_batters"), who(d, "danger_batters"))
    check("the T20 bowler is not a danger bowler", NAMES[BOWL_T20] not in names(d, "danger_bowlers"),
          who(d, "danger_bowlers"))
    check("the 3rds' bowler is", NAMES[BOWL_3] in names(d, "bowling"), who(d, "bowling"))
    check("the grade filter reads 3rd Grade, taken from the fixture",
          d.get("grade_filter") == ["3rd Grade"] and d.get("grade_from_fixture") is True,
          f"{d.get('grade_filter')} fixture={d.get('grade_from_fixture')}")
    check("it is not labelled whole club", not d.get("mixed_grades"), str(d.get("mixed_grades")))
    check("the lens is named", d.get("scope_labels") == ["Men's", "Two day"], str(d.get("scope_labels")))

    print("\n-- the same lens, but ASKING for the whole club: the filter alone is enough --")
    d = await scout(categories="senior", formats="two_day", opponent=str(THEM))
    check("two-day men's: Smith is in", SMITH_N in names(d), who(d))
    check("two-day men's: the T20 batters are out (Lane, Hitter)",
          LANE_N not in names(d) and HITTER_N not in names(d), who(d))
    check("two-day men's: the junior is out", KID_N not in names(d), who(d))

    print("\n-- control for the checks above: each excluded player CAN be present --")
    d = await scout(opponent=str(THEM))
    check("no scope, no fixture: the whole club shows (Lane, Smith, Hitter, Kid)",
          {LANE_N, SMITH_N, HITTER_N, KID_N} <= names(d), who(d))
    check("and it is labelled whole club", d.get("mixed_grades") is True, str(d.get("mixed_grades")))
    d = await scout(categories="senior", formats="t20", opponent=str(THEM))
    check("T20 scope: Lane and Hitter are in", {LANE_N, HITTER_N} <= names(d), who(d))
    check("T20 scope: Smith (two day) is out, and it is not the Two day payload served from cache",
          SMITH_N not in names(d), who(d))
    d = await scout(categories="junior", opponent=str(THEM))
    check("juniors scope: Kid is in, Lane is out", KID_N in names(d) and LANE_N not in names(d), who(d))
    d = await scout(formats="two_day", fixture=FX3, grade="T20 Div 1")
    check("a picked grade beats the fixture's, but the format half still holds: "
          "T20 Div 1 under Two day leaves Lane (a T20 game) out",
          LANE_N not in names(d), who(d))
    d = await scout(fixture=FX3, grade="T20 Div 1")
    check("an explicit grade beats the fixture's: T20 Div 1 picked, no format, Lane is in",
          LANE_N in names(d) and SMITH_N not in names(d) and d.get("grade_from_fixture") is False,
          f"{who(d)} fixture={d.get('grade_from_fixture')}")

    print("\n-- nothing in the fixture's grade: say so, never the whole club --")
    d = await scout(categories="senior", formats="two_day", fixture=FX4)
    check("4th grade fixture: they hold no games in it, so the squad is empty",
          not names(d), who(d))
    check("and it says nothing in this scope yet", d.get("scoped_empty") is True, str(d.get("scoped_empty")))
    check("and the note names the lens",
          any("Nothing for" in n for n in (d.get("coverage") or {}).get("notes", [])),
          str((d.get("coverage") or {}).get("notes")))

    print("\n-- head-to-head: our meetings are scoped too --")
    async with Session() as s:
        both = await iq_opponent._our_games_vs(s, str(US), str(THEM))
        token = iq_filters.set_scope(await grade_scope.resolve_scope(s, str(US), "senior", formats="two_day"))
        try:
            two_day = await iq_opponent._our_games_vs(s, str(US), str(THEM))
        finally:
            iq_filters.reset_scope(token)
    check("no scope: both meetings (two day and T20)", len(both) == 2, str(len(both)))
    check("two-day scope: only the two-day meeting", len(two_day) == 1, str(len(two_day)))

    print("\n-- cache key --")
    k_none = iq_opponent._cache_key(str(THEM), None, None)
    async with Session() as s:
        t = iq_filters.set_scope(await grade_scope.resolve_scope(s, str(US), "senior", formats="two_day"))
        k_two = iq_opponent._cache_key(str(THEM), None, None)
        iq_filters.reset_scope(t)
        t = iq_filters.set_scope(await grade_scope.resolve_scope(s, str(US), "senior", formats="t20"))
        k_t20 = iq_opponent._cache_key(str(THEM), None, None)
        iq_filters.reset_scope(t)
    check("no scope keeps the bare key", k_none == str(THEM), k_none)
    check("two day and T20 scopes do not share a cache row", len({k_none, k_two, k_t20}) == 3,
          f"{k_none} | {k_two} | {k_t20}")

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
