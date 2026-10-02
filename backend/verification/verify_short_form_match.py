"""A short form of a club player's first name is proposed, and pre-selected,
on both stats importers' review screens: "Salter, Steve" in a club's archive
is "Salter, Steven" on its synced roster.

Reported off Shoalwater Bay: the scorecard import minted a second record for
every archive player the club already held under a longer first name, each
holding half a career, and "Create all as new players" swept the close matches
up with the rest. The rule is narrow on purpose (import_ingest's note), so the
half of this suite that matters is what it REFUSES:

  * a nickname that is not a prefix ("Bob" / "Robert");
  * a bare initial;
  * two club players the short form could be;
  * a sheet that names BOTH the short and the full form (two people);
  * two careers twenty years apart (a son under his father's name), offered
    to check but never pre-selected;
  * a name the person has already answered for.

Drives the SHIPPED route bodies of the manual games wizard and Import Stats.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/verify_shortform?host=/tmp&port=5439 \
  python verification/verify_short_form_match.py
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import (
    Base, ManualBattingInnings, Organisation, Player, PlayerSeasonStats, Season, User,
)
from app.services import import_ingest as ing
from app.services.superseded_ddl import STATEMENTS as SUPERSEDED_DDL
from app.routers.manual_entries import (
    GAME_CSV_COLUMNS, GameResolveRequest, commit_manual_games, resolve_manual_games,
)
from app.routers import imports as imports_router

HAVE = all(hasattr(ing, n) for n in (
    "is_short_form", "short_form_suggestions", "apply_short_form_suggestions", "career_gap"))

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


ORG, OTHER, USER = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
P = {n: uuid.uuid4() for n in (
    "salter", "fletcher", "hankey", "trigg", "dillon_a", "dillon_b", "boddy",
    "jones", "nolan", "held", "other_salter")}
S2004, S2023 = uuid.uuid4(), uuid.uuid4()


def row(game, date, season, name, runs):
    r = {c: "" for c in GAME_CSV_COLUMNS}
    r.update(game_key=game, played_at=date, opposition="Mandurah", season_name=season,
             grade_name="A grade", player_name=name, innings_number="1",
             batting_position="1", batting_runs=str(runs), did_not_bat="false")
    return r


SHEET = [
    row("g1", "2004-11-06", "2004/05", "Salter, Steve", 40),
    row("g1", "2004-11-06", "2004/05", "Hankey, Chris", 12),
    row("g1", "2004-11-06", "2004/05", "Trigg, Griffen", 9),
    row("g1", "2004-11-06", "2004/05", "Dillon, Alex", 5),
    row("g1", "2004-11-06", "2004/05", "Jones, Bob", 3),
    row("g1", "2004-11-06", "2004/05", "Nolan, S", 2),
    row("g1", "2004-11-06", "2004/05", "Held, Harry", 20),
    row("g2", "1997-11-08", "1997/98", "Fletcher, Greg", 30),
    # the sheet names BOTH forms of Boddy: two people, whatever the roster says
    row("g2", "1997-11-08", "1997/98", "Boddy, Steve", 11),
    row("g2", "1997-11-08", "1997/98", "Boddy, Steven", 14),
]


async def schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Lifespan DDL (main.py), not on the ORM model: the shared "not played" predicate reads it.
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))
        for stmt in SUPERSEDED_DDL:
            await conn.execute(text(stmt))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_achievements (
                id SERIAL PRIMARY KEY, player_id UUID, organisation_id UUID, season TEXT)"""))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)"""))


async def seed() -> None:
    async with Session() as s:
        for tbl in ("manual_batting_innings", "manual_games", "manual_edit_logs",
                    "player_season_stats", "imported_stats", "grades", "seasons",
                    "players", "organisations", "users"):
            await s.execute(text(f"TRUNCATE {tbl} CASCADE"))
        s.add_all([
            User(id=USER, username="admin", password_hash="x"),
            Organisation(id=ORG, name="Shoalwater Bay", slug="shoalwater"),
            Organisation(id=OTHER, name="Somebody Else", slug="other"),
            Season(id=S2004, organisation_id=ORG, name="Summer 2004/05", year=2004),
            Season(id=S2023, organisation_id=ORG, name="Summer 2023/24", year=2023),
            Player(id=P["salter"], organisation_id=ORG, name="Salter, Steven"),
            Player(id=P["fletcher"], organisation_id=ORG, name="Fletcher, Gregory"),
            Player(id=P["hankey"], organisation_id=ORG, name="Hankey, Christopher"),
            Player(id=P["trigg"], organisation_id=ORG, name="Trigg, Griff"),
            Player(id=P["dillon_a"], organisation_id=ORG, name="Dillon, Alexandra"),
            Player(id=P["dillon_b"], organisation_id=ORG, name="Dillon, Alexander"),
            Player(id=P["boddy"], organisation_id=ORG, name="Boddy, Steven"),
            Player(id=P["jones"], organisation_id=ORG, name="Jones, Robert"),
            Player(id=P["nolan"], organisation_id=ORG, name="Nolan, Sarah"),
            Player(id=P["held"], organisation_id=ORG, name="Held, Harry"),
            Player(id=P["other_salter"], organisation_id=OTHER, name="Salter, Steve"),
        ])
        await s.flush()
        s.add_all([
            PlayerSeasonStats(player_id=P["salter"], season_id=S2004, matches=10, runs=300),
            PlayerSeasonStats(player_id=P["fletcher"], season_id=S2023, matches=4, runs=50),
        ])
        await s.commit()


def pure_checks() -> None:
    print("\n-- the rule on its own --")
    check("Steve is a short form of Steven", ing.is_short_form("steve", "steven"))
    check("and the other way round", ing.is_short_form("kenneth", "ken"))
    check("Chris / Christopher", ing.is_short_form("chris", "christopher"))
    check("a nickname that is not a prefix is not (Bob / Robert)",
          not ing.is_short_form("bob", "robert"))
    check("a bare initial is not", not ing.is_short_form("s", "sarah"))
    check("two letters is not enough (Jo / John)", not ing.is_short_form("jo", "john"))
    check("the same name is not a short form of itself", not ing.is_short_form("steve", "steve"))
    check("overlapping careers have no gap", ing.career_gap((2001, 2006), (2004, 2010)) == 0)
    check("a gap is counted in whole years", ing.career_gap((1996, 2000), (2023, 2023)) == 23)
    check("an unknown career gives no gap", ing.career_gap((1996, 2000), None) is None)

    roster = [("a", "Salter, Steven"), ("b", "Hart, Christopher"), ("c", "Hart, Christian")]
    m = ing.match_players(["Salter, Steve", "Hart, Chris"], roster)
    sug = ing.short_form_suggestions(["Salter, Steve", "Hart, Chris"], roster, m)
    check("one club player who fits is suggested", sug.get("Salter, Steve", {}).get("player_id") == "a",
          str(sug))
    check("two who fit are not (Chris: Christopher or Christian)", "Hart, Chris" not in sug, str(sug))
    names = ["Salter, Steve", "Salter, Steven"]
    m = ing.match_players(names, roster)
    sug = ing.short_form_suggestions(names, roster, m)
    check("a sheet naming both forms keeps them apart", "Salter, Steve" not in sug, str(sug))
    roster = [("a", "Mant, Bradley K")]
    m = ing.match_players(["Mant, Brad J"], roster)
    check("different middle initials are not suggested",
          not ing.short_form_suggestions(["Mant, Brad J"], roster, m))


async def manual_games_checks() -> None:
    print("\n-- the scorecard import's review --")
    async with Session() as s:
        c = await s.get(Organisation, ORG)
        u = await s.get(User, USER)
        res = await resolve_manual_games(
            req=GameResolveRequest(filename="s.csv", rows=SHEET), current_user=u, club=c, db=s)
        pl = {p["raw_name"]: p for p in res["players"]}

        sal = pl.get("Salter, Steve", {})
        check("Salter, Steve is pre-selected as the club's Salter, Steven",
              sal.get("player_id") == str(P["salter"]) and sal.get("status") == "suggested", str(sal))
        check("and says why, with both careers",
              "2004" in (sal.get("note") or "") and "Salter, Steven" in (sal.get("note") or ""),
              sal.get("note", ""))
        check("the suggestion is the first option offered",
              (sal.get("candidates") or [{}])[0].get("player_id") == str(P["salter"]))
        hk = pl.get("Hankey, Chris", {})
        check("Chris / Christopher, which full-string similarity scored as no match, is suggested",
              hk.get("player_id") == str(P["hankey"]) and hk.get("status") == "suggested", str(hk))
        tg = pl.get("Trigg, Griffen", {})
        check("the sheet's longer form finds the club's shorter one (Griffen / Griff)",
              tg.get("player_id") == str(P["trigg"]), str(tg))
        fl = pl.get("Fletcher, Greg", {})
        check("a Greg from the 1990s is NOT pre-selected as a Gregory from 2023",
              not fl.get("player_id") and fl.get("status") == "fuzzy", str(fl))
        check("but is offered, first, with the gap named",
              (fl.get("candidates") or [{}])[0].get("player_id") == str(P["fletcher"])
              and "26 years apart" in (fl.get("note") or ""), fl.get("note", ""))
        check("two club players the short form could be: neither is chosen",
              not pl.get("Dillon, Alex", {}).get("player_id"), str(pl.get("Dillon, Alex")))
        check("a sheet naming both Boddy, Steve and Boddy, Steven keeps Steve apart",
              not pl.get("Boddy, Steve", {}).get("player_id")
              and pl.get("Boddy, Steven", {}).get("player_id") == str(P["boddy"]),
              str(pl.get("Boddy, Steve")))
        check("a nickname is left alone (Bob / Robert)",
              pl.get("Jones, Bob", {}).get("status") != "suggested", str(pl.get("Jones, Bob")))
        check("a bare initial is left alone",
              pl.get("Nolan, S", {}).get("status") != "suggested", str(pl.get("Nolan, S")))
        check("an exact name is still an exact match",
              pl.get("Held, Harry", {}).get("status") == "exact")
        check("another club's player is never offered",
              all(c2.get("player_id") != str(P["other_salter"])
                  for p in res["players"] for c2 in (p.get("candidates") or [])))
        unresolved = res["totals"]["players_unresolved"]
        expect = sum(1 for p in res["players"]
                     if not p.get("player_id") and p.get("status") not in ("new", "skip"))
        check("a suggested match is not counted as still to answer", unresolved == expect
              and "Salter, Steve" not in [p["raw_name"] for p in res["players"]
                                          if not p.get("player_id")], str(unresolved))

        res = await resolve_manual_games(
            req=GameResolveRequest(rows=SHEET, player_overrides={"Salter, Steve": "__new__"}),
            current_user=u, club=c, db=s)
        sal = next(p for p in res["players"] if p["raw_name"] == "Salter, Steve")
        check("the person's own answer wins over the suggestion",
              sal.get("status") == "new" and not sal.get("player_id"), str(sal))

    print("\n-- 'Create all as new players', then import --")
    async with Session() as s:
        c = await s.get(Organisation, ORG)
        u = await s.get(User, USER)
        res = await resolve_manual_games(req=GameResolveRequest(rows=SHEET), current_user=u, club=c, db=s)
        # exactly what the wizard's bulk button sends: every name with nothing chosen
        overrides = {p["raw_name"]: "__new__" for p in res["players"]
                     if not p.get("player_id") and p.get("status") not in ("skip", "ambiguous")}
        check("the bulk button does not reach a suggested match",
              "Salter, Steve" not in overrides and "Hankey, Chris" not in overrides, str(overrides))
        out = await commit_manual_games(
            req=GameResolveRequest(rows=SHEET, player_overrides=overrides),
            current_user=u, club=c, db=s)
        check("the import lands", out.get("games_created") == 2, str(out))
    async with Session() as s:
        dup = (await s.execute(select(Player).where(
            Player.organisation_id == ORG, Player.name == "Salter, Steve"))).scalars().all()
        check("no second Salter record is minted", dup == [], str([d.id for d in dup]))
        runs = (await s.execute(select(ManualBattingInnings.runs).where(
            ManualBattingInnings.player_id == P["salter"]))).scalars().all()
        check("the archive innings is on the club's own Salter, Steven", runs == [40], str(runs))
        greg = (await s.execute(select(Player).where(
            Player.organisation_id == ORG, Player.name == "Fletcher, Greg"))).scalars().all()
        check("the 1990s Greg, left to the person, came in as his own record", len(greg) == 1)


async def import_stats_checks() -> None:
    print("\n-- Import Stats' review --")
    rows = [
        {"Player": "Salter, Steve", "Season": "2004/05", "Games": "10", "Runs": "300"},
        {"Player": "Fletcher, Greg", "Season": "1997/98", "Games": "12", "Runs": "250"},
        {"Player": "Hankey, Chris", "Season": "2001/02", "Games": "8", "Runs": "90"},
    ]
    mapping = {"player_name": "Player", "season_label": "Season",
               "games_played": "Games", "batting_runs": "Runs"}
    async with Session() as s:
        out = await imports_router._resolve(s, ORG, imports_router.ResolveRequest(
            rows=rows, mapping=mapping, granularity="season"))
        pl = {p["raw_name"]: p for p in out["players"]}
        check("Salter, Steve is pre-selected there too",
              pl["Salter, Steve"].get("player_id") == str(P["salter"])
              and pl["Salter, Steve"].get("status") == "suggested", str(pl["Salter, Steve"]))
        check("and its sheet summary is shown beside it", bool(pl["Salter, Steve"].get("sheet")))
        check("Chris / Christopher too", pl["Hankey, Chris"].get("player_id") == str(P["hankey"]))
        check("the 1990s Greg is offered, not chosen",
              not pl["Fletcher, Greg"].get("player_id")
              and pl["Fletcher, Greg"].get("status") == "fuzzy", str(pl["Fletcher, Greg"]))
        check("the suggested player's sheet rows go to them in the preview",
              any(p.get("player_id") == str(P["salter"]) for p in out["preview"]))


async def main() -> None:
    if not HAVE:
        check("the short-form rule exists", False, "import_ingest has no short-form functions")
        print(f"\n{PASS} passed, {FAIL} failed")
        sys.exit(1)
    await schema()
    await seed()
    pure_checks()
    await manual_games_checks()
    await seed()
    await import_stats_checks()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
