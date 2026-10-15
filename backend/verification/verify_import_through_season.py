"""A historical summary that stops at a season is added to the online record, not reconciled against all of it.

Reported by Kalamunda Cricket Club: their history book, "A Century of Cricket
1904/05 - 2004/05", gives each player's career figures up to the end of 2004/05.
BetterImport reconciled a sheet against the player's WHOLE online record, so a
player whose online data starts in 2012 had a 2004/05 book swallowed whole
(online total above the book's, residual 0) and a player with a few online
seasons before 2005 had the book's figures pinned to its own total, losing
everything the online sources held after it.

This suite types the three players from the photographed book pages (the
pencil corrections on the pages are ignored: the book's own printed figures are
the history) into a CSV, runs the SHIPPED route bodies (`preview_upload`,
`resolve`, `commit`, `list_imports`, `undo_import`) and the shipped
reconciler against a real Postgres over the real `v_effective_*` views, and
reads the result back through the same career and season readers the player
profile uses.

    VERIFY_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/verify_import_through \\
      python -m verification.verify_import_through_season

Run against the commit before the change, the cut-off is ignored (an unknown
field on the request) and the checks that depend on it report; nothing crashes.
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/verify_import_through",
)
os.environ["DATABASE_URL"] = DB_URL

from fastapi import HTTPException, UploadFile  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from _view_ddl import view_statements  # noqa: E402
from app.models.db import (  # noqa: E402
    Base, ImportBatch, ImportedStat, ImportEffectiveDelta, Organisation, Player,
    PlayerSeasonStats, Season,
)
from app.routers import imports as imp  # noqa: E402
from app.services import aggregations as agg  # noqa: E402
from app.services import import_ingest as ingest  # noqa: E402
from app.services import import_reconcile as recon  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "kalamunda_century_of_cricket.csv"

engine = create_async_engine(DB_URL, echo=False)
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


ORG, OTHER = uuid.uuid4(), uuid.uuid4()
USER = SimpleNamespace(id=None)

# The book prints surname and initial only. These first names are stand-ins so
# the roster looks like a real one and the matcher has an initial to resolve.
M, S, T, BYSTANDER, OTHER_M = (uuid.uuid4() for _ in range(5))
YEARS = (2002, 2003, 2004, 2005, 2008, 2012, 2013, 2014)
SEASON: dict[int, uuid.UUID] = {y: uuid.uuid4() for y in YEARS}


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        # Lifespan DDL (main.py), not on the ORM model.
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
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb '
                f'USING "{col}"::text::jsonb'))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))
        # The migration's own DDL, so a missing column on the model or the DDL shows up here.
        try:
            from app.services.import_through_ddl import STATEMENTS
            for stmt in STATEMENTS:
                await conn.execute(text(stmt))
        except ImportError:  # control run against the commit before the change
            pass


# What each player's ONLINE (Cricket Australia) record holds, per season start year.
# (matches, innings, runs, not_outs, wickets, runs_conceded, catches)
ONLINE = {
    M: {2003: (10, 16, 210, 1, 2, 40, 3), 2004: (9, 14, 190, 2, 1, 30, 2),
        2012: (14, 20, 380, 2, 0, 0, 0), 2013: (12, 18, 301, 1, 3, 90, 4)},
    T: {2008: (20, 25, 410, 3, 12, 300, 6)},
    BYSTANDER: {2012: (7, 9, 120, 1, 0, 0, 1)},
}


async def seed() -> None:
    async with Session() as db:
        db.add_all([
            Organisation(id=ORG, name="Kalamunda Cricket Club", slug="kalamunda-v"),
            Organisation(id=OTHER, name="Elsewhere Cricket Club", slug="elsewhere-v"),
        ])
        for y in YEARS:
            db.add(Season(id=SEASON[y], organisation_id=ORG, name=f"Summer {y}/{(y + 1) % 100:02d}", year=y))
        other_season = uuid.uuid4()
        db.add(Season(id=other_season, organisation_id=OTHER, name="Summer 2012/13", year=2012))
        for pid, org, name in ((M, ORG, "Mark Travcich"), (S, ORG, "Simon Travcich"),
                               (T, ORG, "Tim Overton"), (BYSTANDER, ORG, "Pat Bystander"),
                               (OTHER_M, OTHER, "Mark Travcich")):
            db.add(Player(id=pid, organisation_id=org, name=name))
        await db.flush()
        for pid, by_year in ONLINE.items():
            for y, (m, i, r, no, w, rc_, c) in by_year.items():
                db.add(PlayerSeasonStats(player_id=pid, season_id=SEASON[y], matches=m, batting_innings=i,
                                         runs=r, not_outs=no, wickets=w, runs_conceded=rc_, catches=c,
                                         source="api"))
        # Another club's player with the same name: must never be touched.
        db.add(PlayerSeasonStats(player_id=OTHER_M, season_id=other_season, matches=5, batting_innings=6,
                                 runs=99, not_outs=0, source="api"))
        await db.commit()


def upload(data: bytes) -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=FIXTURE.name)


def request(parsed: dict, mapping: dict, **extra):
    fields = dict(rows=parsed["rows"], mapping=mapping, granularity="career")
    fields.update(extra)
    return imp.CommitRequest(filename=FIXTURE.name, **fields)


async def career(pid) -> dict:
    """What the player profile reads: career batting, bowling, fielding and the
    season-by-season table, through the shipped readers and the real views."""
    async with Session() as db:
        bat = await agg.get_career_batting(db, str(pid)) or {}
        bowl = await agg.get_career_bowling(db, str(pid)) or {}
        field = await agg.get_career_fielding(db, str(pid)) or {}
        seasons = await agg.get_season_by_season(db, str(pid), include_prior=True)
    return {"bat": bat, "bowl": bowl, "field": field, "seasons": seasons}


def n(d: dict, key: str) -> int:
    return int(d.get(key) or 0)


async def run_import(through, label: str) -> dict:
    """Preview, confirm the single close matches the way the wizard's "Confirm
    single matches" button does, then commit, through the shipped route bodies."""
    parsed = ingest.parse_upload(FIXTURE.name, FIXTURE.read_bytes())
    mapping = {f: v["column"] for f, v in ingest.suggest_column_mapping(parsed["headers"]).items()}
    extra = {"through_season": through} if through is not None else {}
    async with Session() as db:
        club = await db.get(Organisation, ORG)
        first = await imp.resolve(request(parsed, mapping, **extra), USER, club, db)
    # The book prints "TRAVCICH M": a surname and an initial, so each is a close
    # match with ONE candidate for a person to confirm, never a silent match.
    overrides = {p["raw_name"]: p["candidates"][0]["player_id"]
                 for p in first["players"] if p["status"] == "fuzzy" and len(p["candidates"]) == 1}
    async with Session() as db:
        club = await db.get(Organisation, ORG)
        preview = await imp.resolve(request(parsed, mapping, player_overrides=overrides, **extra), USER, club, db)
    async with Session() as db:
        club = await db.get(Organisation, ORG)
        committed = await imp.commit(request(parsed, mapping, player_overrides=overrides, **extra), USER, club, db)
    print(f"    ({label}) preview rows: "
          + ", ".join(f"{p['player_name']}: club {p['club_runs']} + online {p['gr_runs']}"
                      f" + added {p.get('residual_runs')} + after {p.get('online_after_runs')} = {p['final_runs']}"
                      for p in preview["preview"]))
    return {"first": first, "overrides": overrides, "preview": preview, "commit": committed,
            "mapping": mapping, "parsed": parsed}


async def snapshot_online() -> list:
    async with Session() as db:
        rows = (await db.execute(select(
            PlayerSeasonStats.player_id, PlayerSeasonStats.season_id, PlayerSeasonStats.matches,
            PlayerSeasonStats.runs, PlayerSeasonStats.wickets, PlayerSeasonStats.source))).all()
    return sorted(tuple(map(str, r)) for r in rows)


async def deltas(pid) -> list:
    async with Session() as db:
        return (await db.execute(select(ImportEffectiveDelta).where(
            ImportEffectiveDelta.organisation_id == ORG,
            ImportEffectiveDelta.player_id == pid))).scalars().all()


async def main() -> int:
    print("\n-- the book, transcribed (printed figures only, pencil ignored)")
    # The book prints each player's own averages. They must agree with the
    # figures typed from the photo, or a number was misread.
    rows = {r["Name"]: r for r in ingest.parse_upload(FIXTURE.name, FIXTURE.read_bytes())["rows"]}

    def avg(r, runs_col, inns_col, no_col):
        return round(int(r[runs_col]) / (int(r[inns_col]) - int(r[no_col])), 2)

    for name in rows:
        r = rows[name]
        check(f"{name}: batting average {r['Average']} = {r['Total Runs']} / ({r['No Innings']} - {r['NO']})",
              avg(r, "Total Runs", "No Innings", "NO") == float(r["Average"]))
        check(f"{name}: bowling average {r['Bowling Average']} = {r['Bowling Runs']} / {r['Total Wickets']}",
              round(int(r["Bowling Runs"]) / int(r["Total Wickets"]), 2) == float(r["Bowling Average"]))
    parsed0 = ingest.parse_upload(FIXTURE.name, FIXTURE.read_bytes())
    mapping0 = {f: v["column"] for f, v in ingest.suggest_column_mapping(parsed0["headers"]).items()}
    expected_map = {"player_name": "Name", "games_played": "Games Played", "batting_innings": "No Innings",
                    "batting_runs": "Total Runs", "batting_not_outs": "NO", "batting_fifties": "No 50's",
                    "batting_hundreds": "No 100's", "batting_high_score": "Highest Score",
                    "bowling_overs": "Overs Bowled", "bowling_maidens": "Maidens",
                    "bowling_runs": "Bowling Runs", "bowling_wickets": "Total Wickets",
                    "bowling_five_wicket_innings": "No 5wkt Inns", "bowling_best_figures": "Best Bowling Inn",
                    "fielding_catches": "Catches", "batting_average": "Average",
                    "bowling_average": "Bowling Average"}
    missing = {k: (mapping0.get(k), v) for k, v in expected_map.items() if mapping0.get(k) != v}
    check("the book's own headings map to the right fields on their own", not missing, str(missing))

    await build_schema()
    await seed()
    online_before = await snapshot_online()

    print("\n-- a cut-off that is not a season is refused")
    parsed = parsed0
    for bad in ("2004", "2004/06", "banana", "1700/01"):
        try:
            async with Session() as db:
                club = await db.get(Organisation, ORG)
                await imp.resolve(request(parsed, mapping0, through_season=bad), USER, club, db)
            check(f"'{bad}' is refused", False, "accepted")
        except HTTPException as exc:
            check(f"'{bad}' is refused with a plain message", exc.status_code == 422 and "2004/05" in str(exc.detail),
                  str(exc.detail))
        except Exception as exc:  # control run: field unknown, nothing to refuse
            check(f"'{bad}' is refused", False, f"{type(exc).__name__}: {exc}")
    async with Session() as db:
        club = await db.get(Organisation, ORG)
        blank = await imp.resolve(request(parsed, mapping0, through_season="  "), USER, club, db)
    check("a blank cut-off is an ordinary import", blank.get("through") is None)

    print("\n-- book to 2004/05, online data from 2003/04 and from 2012")
    r = await run_import("2004/05", "through 2004/05")
    pv = {p["player_name"]: p for p in r["preview"]["preview"]}
    first = {p["raw_name"]: p for p in r["first"]["players"]}
    check("each book name is a close match with exactly one candidate, to be confirmed",
          all(first.get(k, {}).get("status") == "fuzzy" and len(first[k]["candidates"]) == 1
              for k in ("TRAVCICH M", "TRAVCICH S", "OVERTON T")),
          str({k: (v.get("status"), len(v.get("candidates") or [])) for k, v in first.items()}))
    check("TRAVCICH M offers Mark and S offers Simon: the two Travcichs are not confused",
          first["TRAVCICH M"]["candidates"][0]["name"] == "Mark Travcich"
          and first["TRAVCICH S"]["candidates"][0]["name"] == "Simon Travcich")
    check("the preview names what it understood: 2004/05",
          (r["preview"].get("through") or {}).get("label") == "2004/05", str(r["preview"].get("through")))
    check("after confirming, all three are in the preview (it names them as the sheet does)",
          set(pv) == {"TRAVCICH M", "TRAVCICH S", "OVERTON T"}, str(set(pv)))
    m = pv.get("TRAVCICH M", {})
    check("preview M: book 64 games, online to 2004/05 19, after 26", (m.get("club_games"), m.get("gr_games"),
          m.get("online_after_games")) == (64, 19, 26), str(m))
    check("preview M: runs book 1158, online to 2004/05 400, adds 758, after 681, final 1839",
          (m.get("club_runs"), m.get("gr_runs"), m.get("residual_runs"), m.get("online_after_runs"), m.get("final_runs"))
          == (1158, 400, 758, 681, 1839), str(m))
    check("preview M: nothing flagged 'online higher'", not m.get("gr_exceeds"))
    t = pv.get("OVERTON T", {})
    check("preview T: online is all after the cut-off, so the whole book is added (777 + 410)",
          (t.get("gr_runs"), t.get("residual_runs"), t.get("online_after_runs"), t.get("final_runs"))
          == (0, 777, 410, 1187), str(t))
    check("no 'online already shows more than your sheet' warning",
          not any("already shows more" in w for w in r["preview"]["warnings"]), str(r["preview"]["warnings"]))

    async with Session() as db:
        batch = (await db.execute(select(ImportBatch).where(ImportBatch.organisation_id == ORG))).scalars().one()
    check("the batch records its cut-off", (getattr(batch, "through_year", None),
          getattr(batch, "through_label", None)) == (2004, "2004/05"),
          str((getattr(batch, "through_year", None), getattr(batch, "through_label", None))))
    check("the commit says so", (r["commit"].get("through") or {}).get("label") == "2004/05")

    cm, cs, ct = await career(M), await career(S), await career(T)
    print("    M career:", {k: cm["bat"].get(k) for k in ("games", "innings", "total_runs", "not_outs", "high_score", "average")},
          {k: cm["bowl"].get(k) for k in ("wickets", "total_wickets")}, {k: cm["field"].get(k) for k in ("total_catches", "catches")})
    check("M profile: matches 64 + 26 = 90", n(cm["bat"], "games") == 90, str(cm["bat"].get("games")))
    check("M profile: innings 84 + 38 = 122", n(cm["bat"], "innings") == 122, str(cm["bat"].get("innings")))
    check("M profile: runs 1158 + 681 = 1839", n(cm["bat"], "total_runs") == 1839, str(cm["bat"].get("total_runs")))
    check("M profile: high score is the book's 81", n(cm["bat"], "high_score") == 81, str(cm["bat"].get("high_score")))
    check("M profile: fifties are the book's 5", n(cm["bat"], "fifties") == 5, str(cm["bat"].get("fifties")))
    check("M profile: wickets 8 + 3 = 11", n(cm["bowl"], "wickets") == 11 or n(cm["bowl"], "total_wickets") == 11,
          str({k: v for k, v in cm["bowl"].items() if "wick" in k}))
    check("M profile: catches 17 + 4 = 21", 21 in (n(cm["field"], "total_catches"), n(cm["field"], "catches")),
          str({k: v for k, v in cm["field"].items() if "catch" in k}))
    lump = [s for s in cm["seasons"] if s.get("season_name") == "Prior Seasons & Adjustments"]
    check("M's added history shows on one 'Prior Seasons & Adjustments' line, 758 runs",
          len(lump) == 1 and n(lump[0], "total_runs") == 758, str([(s.get("season_name"), s.get("total_runs")) for s in cm["seasons"]]))
    check("M's online seasons stay as their own rows",
          {s.get("year") for s in cm["seasons"] if s.get("year")} >= {2003, 2004, 2012, 2013},
          str([(s.get("season_name"), s.get("year")) for s in cm["seasons"]]))

    # The Team tab read every season-less figure as the string 'None' and 500ed.
    async with Session() as db:
        try:
            tb = await agg.get_player_team_breakdown(db, str(M), str(ORG), None, scope=None)
            err = ""
        except Exception as exc:  # control run: report the failure, do not crash
            tb, err = {}, f"{type(exc).__name__}: {str(exc)[:90]}"
    check("M's Team tab loads with the book's adjustment in it (it used to 500)", bool(tb), err)
    # No scorecards are held in this fixture, so the 45 online matches sit unplaced too: 45 + 45.
    check("and its total reads 90 like the header, the book's 45 reported as matches without a grade",
          (tb.get("total_aggregate_matches"), tb.get("unattributed")) == (90, 90),
          str((tb.get("total_aggregate_matches"), tb.get("unattributed"))))
    check("S profile (nothing online): exactly the book, 21 games, 28 innings, 74 runs, high score 11",
          (n(cs["bat"], "games"), n(cs["bat"], "innings"), n(cs["bat"], "total_runs"), n(cs["bat"], "high_score"))
          == (21, 28, 74, 11), str({k: cs["bat"].get(k) for k in ("games", "innings", "total_runs", "high_score")}))
    check("S profile: batting average 4.11 as the book prints it", float(cs["bat"].get("average") or 0) == 4.11,
          str(cs["bat"].get("average")))
    check("S profile: wickets 11", 11 in (n(cs["bowl"], "wickets"), n(cs["bowl"], "total_wickets")))
    check("T profile: runs 777 + 410 = 1187 (the control reads 777)", n(ct["bat"], "total_runs") == 1187,
          str(ct["bat"].get("total_runs")))
    check("T profile: matches 42 + 20 = 62", n(ct["bat"], "games") == 62, str(ct["bat"].get("games")))
    check("T profile: wickets 10 + 12 = 22", 22 in (n(ct["bowl"], "wickets"), n(ct["bowl"], "total_wickets")),
          str({k: v for k, v in ct["bowl"].items() if "wick" in k}))
    cb = await career(BYSTANDER)
    check("a player with online data and no row in the book is untouched (7 games, 120 runs)",
          (n(cb["bat"], "games"), n(cb["bat"], "total_runs")) == (7, 120))
    co = await career(OTHER_M)
    check("another club's player with the same name is untouched (5 games, 99 runs)",
          (n(co["bat"], "games"), n(co["bat"], "total_runs")) == (5, 99))

    check("the online record before the book's cut-off is still there, row for row", await snapshot_online() == online_before)

    print("\n-- the online record keeps changing; the book does not")
    async with Session() as db:
        db.add(PlayerSeasonStats(player_id=M, season_id=SEASON[2002], matches=8, batting_innings=12, runs=100,
                                 not_outs=0, source="api"))
        await db.commit()
    await recon.reconcile_imported_totals(str(ORG))
    cm2 = await career(M)
    lump2 = [x for x in cm2["seasons"] if x.get("season_name") == "Prior Seasons & Adjustments"]
    check("online adds 2002/03 (before the cut-off): the book's share shrinks by those 100 runs to 658",
          len(lump2) == 1 and n(lump2[0], "total_runs") == 658,
          str([(x.get("season_name"), x.get("total_runs")) for x in cm2["seasons"]]))
    check("and the career total does not move (1839): nothing counted twice",
          n(cm2["bat"], "total_runs") == 1839, str(cm2["bat"].get("total_runs")))
    async with Session() as db:
        db.add(PlayerSeasonStats(player_id=M, season_id=SEASON[2014], matches=10, batting_innings=12, runs=250,
                                 not_outs=1, source="api"))
        await db.commit()
    await recon.reconcile_imported_totals(str(ORG))
    cm3 = await career(M)
    check("online adds 2014/15 (after the cut-off): total grows by exactly its 250 runs, the book's share is unchanged",
          n(cm3["bat"], "total_runs") == n(cm2["bat"], "total_runs") + 250,
          f"{n(cm2['bat'], 'total_runs')} -> {n(cm3['bat'], 'total_runs')}")
    again = await recon.reconcile_imported_totals(str(ORG))
    cm4 = await career(M)
    check("reconciling again changes nothing", n(cm4["bat"], "total_runs") == n(cm3["bat"], "total_runs"), str(again))

    print("\n-- the imports list says what the book covers")
    async with Session() as db:
        club = await db.get(Organisation, ORG)
        listed = (await imp.list_imports(USER, club, db))["imports"]
    check("the list carries the cut-off", any(i.get("through_label") == "2004/05" for i in listed), str(listed))

    print("\n-- undo takes the book away and leaves the online record alone")
    async with Session() as db:
        club = await db.get(Organisation, ORG)
        await imp.undo_import(r["commit"]["batch_id"], USER, club, db)
    check("no adjustment rows left for M", not await deltas(M))
    cm5 = await career(M)
    check("M is back to the online figures only (400 + 100 + 681 + 250 = 1431)",
          n(cm5["bat"], "total_runs") == 1431, str(cm5["bat"].get("total_runs")))

    print("\n-- a sheet row past the cut-off is said aloud")
    parsed_seasons = {"headers": ["Name", "Season", "Games Played", "Total Runs"],
                      "rows": [{"Name": "TRAVCICH M", "Season": "2004/05", "Games Played": "9", "Total Runs": "190"},
                               {"Name": "TRAVCICH M", "Season": "2006/07", "Games Played": "5", "Total Runs": "60"}]}
    # 2006/07 does not exist as a season here, so the row is held back as unmatched and the warning must still name it.
    async with Session() as db:
        club = await db.get(Organisation, ORG)
        out = await imp.resolve(imp.ResolveRequest(
            rows=parsed_seasons["rows"],
            mapping={"player_name": "Name", "season_label": "Season", "games_played": "Games Played",
                     "batting_runs": "Total Runs"},
            granularity="season", through_season="2004/05"), USER, club, db)
    check("it warns that 2006/07 comes after 2004/05",
          any("come after 2004/05" in w and "2006/07" in w for w in out["warnings"]), str(out["warnings"]))
    check("and does not warn about 2004/05 itself", not any("2004/05" in w and "come after" in w and "2004/05," in w for w in out["warnings"]))

    print("\n-- control: the same book imported as an ordinary whole-career sheet")
    await build_schema()
    await seed()
    r2 = await run_import(None, "no cut-off")
    ct2, cm6 = await career(T), await career(M)
    check("T: the ordinary import swallows the book (online 410 is not enough to keep, residual 367, total 777)",
          n(ct2["bat"], "total_runs") == 777, str(ct2["bat"].get("total_runs")))
    check("M: the ordinary import pins the career to the book's 1158 and loses 681 online runs",
          n(cm6["bat"], "total_runs") == 1158, str(cm6["bat"].get("total_runs")))

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    return 1 if FAIL else 0


async def _run() -> int:
    try:
        return await main()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
