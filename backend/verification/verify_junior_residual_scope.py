"""An import residual is classified by its own grade_label, not kept blind.

Reported off The Basin: Nathan Freeling, a senior player whose only record for
2006/07-2008/09 is a BetterImport residual under senior grade labels ("Division
3/4/5"), showed 18 matches / 376 runs under the JUNIORS filter — and the same
under Women's and Masters. An import residual carries no grade_id, so the
category exclusion (keyed on grade_id) could never name it and kept it under
every category pick. The residual DOES carry a classifiable grade_label, so the
fix judges it by that label instead.

Runs the SHIPPED `resolve_scope`, `_career_residuals` and `_season_by_season_scoped`
against a real Postgres over the real `v_effective_player_season_stats` view.

    VERIFY_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/verify_junior_residual \\
      python -m verification.verify_junior_residual_scope
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/verify_junior_residual",
)
os.environ["DATABASE_URL"] = DB_URL

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from _view_ddl import view_statements  # noqa: E402
from app.models.db import Base  # noqa: E402

MISSING: list[str] = []
try:
    from app.services.grade_scope import resolve_scope, GradeScope
    from app.services.aggregations import (
        _career_residuals, _season_by_season_scoped, _residual_totals_cte,
    )
    HAVE = True
except Exception as exc:  # pragma: no cover - control run only
    HAVE = False
    MISSING.append(str(exc))

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


ORG = uuid.uuid4()
OTHER = uuid.uuid4()
S06, S07, S08 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
G_SEN = uuid.uuid4()   # "Division 3", senior — a real grade row for the label
G_JNR = uuid.uuid4()   # "Under 12", junior
G_WOM = uuid.uuid4()   # "Womens A", womens

SEN_IMP = uuid.uuid4()  # THE REPORTED CASE: senior import residual only
JNR_IMP = uuid.uuid4()  # a genuine junior import residual
LUMP = uuid.uuid4()     # a career lump with no grade_label — unclassifiable
GID_SEN = uuid.uuid4()  # a residual carrying a real senior grade_id
OTHER_P = uuid.uuid4()  # another club's player, must not be touched


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
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


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        for oid, nm, slug, cats in (
                (ORG, "The Basin", "the-basin-v", "'[\"senior\"]'::jsonb"),
                (OTHER, "Elsewhere", "elsewhere-v", "NULL")):
            await ex(f"INSERT INTO organisations (id, name, slug, is_active, "
                     f" stats_grade_categories) VALUES (:i, :n, :s, true, {cats})",
                     i=oid, n=nm, s=slug)
        for sid, nm, yr in ((S06, "Summer 2006/07", 2006),
                            (S07, "Summer 2007/08", 2007),
                            (S08, "Summer 2008/09", 2008)):
            await ex("INSERT INTO seasons (id, organisation_id, name, year) "
                     "VALUES (:i, :o, :n, :y)", i=sid, o=ORG, n=nm, y=yr)
        for gid, nm, cat in ((G_SEN, "Division 3", "senior"),
                             (G_JNR, "Under 12", "junior"),
                             (G_WOM, "Womens A", "womens")):
            await ex("INSERT INTO grades (id, season_id, name, grassroots_id, "
                     " category, categories) VALUES (:i, :s, :n, :g, :c, ARRAY[:c]) ",
                     i=gid, s=S06, n=nm, g=str(gid), c=cat)
        for pid, org in ((SEN_IMP, ORG), (JNR_IMP, ORG), (LUMP, ORG),
                         (GID_SEN, ORG), (OTHER_P, OTHER)):
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, "
                     " status) VALUES (:i, :o, :n, :g, 'active')",
                     i=pid, o=org, n="P", g=str(pid))

        # SEN_IMP — the reported shape: senior import residuals, no grade_id,
        # across the three pre-CA seasons. 5+7=12 / 1 / 5 matches = 18 total.
        for sid, gl, m, r in ((S06, "Division 5", 7, 136), (S06, "Division 4", 5, 38),
                              (S07, "Division 4", 1, 23),
                              (S08, "Division 3", 5, 39), (S08, "Division 4", 0, 140)):
            await imp(ex, ORG, SEN_IMP, sid, gl, m, r)
        # JNR_IMP — a genuine junior import residual.
        await imp(ex, ORG, JNR_IMP, S06, "Under 12", 6, 171)
        # LUMP — the career-level "Prior Seasons & Adjustments" lump: no season,
        # no grade_label. Genuinely unclassifiable.
        await ex("INSERT INTO import_effective_deltas (organisation_id, player_id, "
                 " scope, season_id, grade_id, grade_label, matches, batting_innings, runs) "
                 "VALUES (:o, :p, 'career', NULL, NULL, NULL, 9, 9, 250)",
                 o=ORG, p=LUMP)
        # OTHER_P — another club, senior import residual. Must never move.
        await imp(ex, OTHER, OTHER_P, S06, "Division 3", 4, 88)
        # GID_SEN — a residual carrying a REAL senior grade_id (the manual_aggregate
        # shape), to prove the unchanged grade_id branch still excludes correctly.
        await ex("INSERT INTO import_effective_deltas (organisation_id, player_id, "
                 " scope, season_id, grade_id, grade_label, matches, batting_innings, runs) "
                 "VALUES (:o, :p, 'season', :s, :g, 'Division 3', 8, 8, 200)",
                 o=ORG, p=GID_SEN, s=S06, g=G_SEN)
        await s.commit()


async def imp(ex, org, pid, sid, label, m, r):
    await ex("INSERT INTO import_effective_deltas (organisation_id, player_id, scope, "
             " season_id, grade_id, grade_label, matches, batting_innings, runs) "
             "VALUES (:o, :p, 'season', :s, NULL, :l, :m, :m, :r)",
             o=org, p=pid, s=sid, l=label, m=m, r=r)


async def scope_for(s, cats):
    return await resolve_scope(s, str(ORG), categories=cats)


async def resid(s, pid, scope):
    r = await _career_residuals(s, str(pid), None, scope)
    return int(r.get("games") or 0), int(r.get("total_runs") or 0)


async def main() -> int:
    if not HAVE:
        print("FEATURE ABSENT:", "; ".join(MISSING))
        check("the residual-classification code imports", False, "; ".join(MISSING))
        print(f"\n{PASS} passed, {FAIL} failed")
        return 1

    await build_schema()
    await seed()

    async with Session() as s:
        print("\n── resolve_scope builds excluded_labels from the org's import labels")
        jnr = await scope_for(s, "junior")
        men = await scope_for(s, "senior")
        wom = await scope_for(s, "womens")
        check("Juniors excludes the senior labels",
              {"Division 3", "Division 4", "Division 5"} <= set(getattr(jnr,'excluded_labels',())),
              str(getattr(jnr,"excluded_labels",())))
        check("Juniors does NOT exclude the junior label",
              "Under 12" not in getattr(jnr,"excluded_labels",()), str(getattr(jnr,"excluded_labels",())))
        check("Men's excludes the junior label",
              "Under 12" in getattr(men,"excluded_labels",()), str(getattr(men,"excluded_labels",())))
        check("Men's does NOT exclude a senior label",
              "Division 3" not in getattr(men,"excluded_labels",()), str(getattr(men,"excluded_labels",())))
        check("Women's excludes both the senior and the junior labels",
              {"Division 3", "Under 12"} <= set(getattr(wom,'excluded_labels',())),
              str(getattr(wom,"excluded_labels",())))

        print("\n── the reported player: a senior import residual")
        g, r = await resid(s, SEN_IMP, jnr)
        check("under Juniors he reads 0 / 0 (the reported 18/376 is gone)",
              (g, r) == (0, 0), f"{g}/{r}")
        g, r = await resid(s, SEN_IMP, men)
        check("under Men's his 18 / 376 is kept", (g, r) == (18, 376), f"{g}/{r}")
        g, r = await resid(s, SEN_IMP, wom)
        check("under Women's he reads 0 / 0", (g, r) == (0, 0), f"{g}/{r}")
        mas = await scope_for(s, "masters")
        g, r = await resid(s, SEN_IMP, mas)
        check("under Masters he reads 0 / 0", (g, r) == (0, 0), f"{g}/{r}")
        # ORG's default is stats_grade_categories = ['senior'], so the default is
        # a real junior-excluding filter — the everyday page-load state.
        default = await scope_for(s, None)
        check("the club default is an active (junior-excluding) scope",
              default.active and default.category_active)
        g, r = await resid(s, SEN_IMP, default)
        check("under the club default his senior residual is KEPT (18 / 376)",
              (g, r) == (18, 376), f"{g}/{r}")

        print("\n── a genuine junior import residual")
        g, r = await resid(s, JNR_IMP, jnr)
        check("shows under Juniors (6 / 171)", (g, r) == (6, 171), f"{g}/{r}")
        g, r = await resid(s, JNR_IMP, men)
        check("hidden under Men's (0 / 0)", (g, r) == (0, 0), f"{g}/{r}")
        g, r = await resid(s, JNR_IMP, default)
        check("dropped by the junior-excluding club default (0 / 0)",
              (g, r) == (0, 0), f"{g}/{r}")

        print("\n── a label-less career lump stays unclassifiable and is kept")
        for lbl, sc in (("Juniors", jnr), ("Men's", men), ("Women's", wom)):
            g, r = await resid(s, LUMP, sc)
            check(f"the career lump is kept under {lbl} (9 / 250)",
                  (g, r) == (9, 250), f"{g}/{r}")

        print("\n── a residual with a REAL senior grade_id (unchanged branch)")
        g, r = await resid(s, GID_SEN, jnr)
        check("excluded under Juniors by its grade_id (0 / 0)", (g, r) == (0, 0), f"{g}/{r}")
        g, r = await resid(s, GID_SEN, men)
        check("kept under Men's (8 / 200)", (g, r) == (8, 200), f"{g}/{r}")

        print("\n── the season table reconciles with the header")
        rows = await _season_by_season_scoped(s, str(SEN_IMP), jnr)
        tot = sum(int(row.get("matches") or 0) for row in rows)
        check("under Juniors the season table sums to 0, not 18",
              tot == 0, f"table matches sum = {tot}")
        rows = await _season_by_season_scoped(s, str(SEN_IMP), men)
        tot = sum(int(row.get("matches") or 0) for row in rows)
        check("under Men's the season table sums to 18", tot == 18,
              f"table matches sum = {tot}")

        print("\n── the leaderboard residual CTE agrees")
        for lbl, sc, want in (("Juniors", jnr, 0), ("Men's", men, 18)):
            params: dict = {}
            cte = _residual_totals_cte(sc, None, params)
            params["pid"] = str(SEN_IMP)
            got = (await s.execute(text(
                f"WITH {cte} SELECT COALESCE(games, 0) FROM residual_totals "
                "WHERE player_id = CAST(:pid AS UUID)"), params)).scalar()
            check(f"the leaderboard residual reads {want} under {lbl}",
                  int(got or 0) == want, f"got {got}")

        print("\n── another club's identical senior residual is untouched")
        # OTHER has NULL default, so resolve its own explicit senior scope.
        oth_men = await resolve_scope(s, str(OTHER), categories="senior")
        g, r = await resid(s, OTHER_P, oth_men)
        check("the other club's senior residual still reads 4 / 88 under Men's",
              (g, r) == (4, 88), f"{g}/{r}")

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("FAILURES:", FAILURES)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
