"""The admin Matches list shows imported matches, not only synced ones.

Reported off Hamilton Veterans: the 2010/11 scorecard opens fine and shows on
the public Games page, but BetterStats -> Club Data -> Matches (season 2010/11)
reads "No matches found for this season". Their history came in from
CricketStatz, so those matches live in `manual_games`, and the admin
`GET /club-admin/games` list read only the CA-synced `games` table.

This runs the SHIPPED route body (`club_admin.list_games`, imported, nothing
retyped) against a real Postgres, over `v_effective_games` (games union
manual_games). A control re-runs the OLD query shape in the same run and shows
it hiding the imported season, so the fix is proven within one pass.

    python -m verification.verify_admin_games_imported
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements

from app.models.db import Base, Organisation, User
from app.routers.club_admin import list_games

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres@127.0.0.1:5432/verify_admin_games",
)

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


ORG = uuid.uuid4()          # Hamilton Veterans-like: a CricketStatz-imported club
OTHER = uuid.uuid4()

S_SYNCED = uuid.uuid4()     # a normal CA-synced season
S_IMPORTED = uuid.uuid4()   # the reported 2010/11 season, brought in by import
S_OTHER = uuid.uuid4()

G_SYNC = uuid.uuid4()
G_IMP = uuid.uuid4()
G_OTHER = uuid.uuid4()

GAME_SYNC = uuid.uuid4()          # an ordinary synced, completed game
GAME_ABANDONED = uuid.uuid4()     # a synced fixture called off, 2 players named
MG_GRADED = uuid.uuid4()          # an imported match with a grade
MG_NOGRADE = uuid.uuid4()         # an imported match with NO grade (LEFT JOIN)
MG_OTHER = uuid.uuid4()           # another club's imported match


async def build_schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        # `games.raw_payload` is JSON on the ORM and JSONB in the database the
        # migrations build; the view's UNION can't mix a JSON column with a
        # NULL::jsonb, so reconcile it the way the neighbouring suites do.
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb '
                f'USING "{col}"::text::jsonb'))
        # Only the one view this endpoint reads. Applying the others would drag
        # in tables (import_effective_deltas, ...) this test has no need for.
        for name, sql in view_statements():
            if name != "v_effective_games":
                continue
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))


async def seed(db) -> None:
    async def ex(sql, **kw):
        await db.execute(text(sql), kw)

    for oid, nm, slug in ((ORG, "Hamilton Veterans", "hamilton-veterans"),
                          (OTHER, "Somebody Else CC", "somebody-else")):
        await ex("INSERT INTO organisations (id, name, slug, is_active) "
                 "VALUES (:i, :n, :s, true)", i=oid, n=nm, s=slug)

    # A synced season with real grassroots ids, and an imported season the
    # club created itself (grassroots_id NULL — the "not from a sync" marker).
    await ex("INSERT INTO seasons (id, organisation_id, grassroots_id, name, year) "
             "VALUES (:i, :o, 'ca-2025', 'Summer 2025/26', 2025)", i=S_SYNCED, o=ORG)
    await ex("INSERT INTO seasons (id, organisation_id, grassroots_id, name, year) "
             "VALUES (:i, :o, NULL, 'Summer 2010/11', 2010)", i=S_IMPORTED, o=ORG)
    await ex("INSERT INTO seasons (id, organisation_id, grassroots_id, name, year) "
             "VALUES (:i, :o, 'ca-x', 'Summer 2010/11', 2010)", i=S_OTHER, o=OTHER)

    for gid, sid, nm in ((G_SYNC, S_SYNCED, "1st Grade"),
                         (G_IMP, S_IMPORTED, "A Grade"),
                         (G_OTHER, S_OTHER, "A Grade")):
        await ex("INSERT INTO grades (id, season_id, name) VALUES (:i, :s, :n)",
                 i=gid, s=sid, n=nm)

    # Two synced games: one ordinary completed, one called off with 2 named.
    await ex("INSERT INTO games (id, grade_id, played_at, home_team, away_team, "
             "result, winning_team, is_final, status) "
             "VALUES (:i, :g, :d, 'Hamilton Vets', 'Rovers', "
             "'Hamilton Vets won by 5 wickets', 'Hamilton Vets', false, 'COMPLETED')",
             i=GAME_SYNC, g=G_SYNC, d=dt.date(2025, 11, 1))
    await ex("INSERT INTO games (id, grade_id, played_at, home_team, away_team, "
             "is_final, status) "
             "VALUES (:i, :g, :d, 'Hamilton Vets', 'United', false, 'ABANDONED')",
             i=GAME_ABANDONED, g=G_SYNC, d=dt.date(2025, 11, 8))

    players = [uuid.uuid4(), uuid.uuid4()]
    for pid in players:
        await ex("INSERT INTO players (id, organisation_id, name) "
                 "VALUES (:i, :o, 'A Player')", i=pid, o=ORG)
    for pid in players:
        await ex("INSERT INTO game_appearances (game_id, player_id) "
                 "VALUES (:g, :p)", g=GAME_ABANDONED, p=pid)

    # The imported season's matches (manual_games) — the reported case. One with
    # a grade, one with none at all.
    await ex("INSERT INTO manual_games (id, organisation_id, season_id, grade_id, "
             "played_at, home_team, away_team, opposition, result, winning_team, "
             "is_final, cricketstatz_match_id) "
             "VALUES (:i, :o, :s, :g, :d, 'Hamilton Vets', 'Old Boys', 'Old Boys', "
             "'Hamilton Vets won by 40 runs', 'Hamilton Vets', false, 'cs-1')",
             i=MG_GRADED, o=ORG, s=S_IMPORTED, g=G_IMP, d=dt.date(2010, 11, 20))
    await ex("INSERT INTO manual_games (id, organisation_id, season_id, grade_id, "
             "played_at, home_team, away_team, opposition, result, is_final) "
             "VALUES (:i, :o, :s, NULL, :d, 'Hamilton Vets', 'Wanderers', 'Wanderers', "
             "'Draw', false)",
             i=MG_NOGRADE, o=ORG, s=S_IMPORTED, d=dt.date(2010, 12, 4))

    # Another club's imported match in an identically-named season/grade — must
    # never appear on this club's list.
    await ex("INSERT INTO manual_games (id, organisation_id, season_id, grade_id, "
             "played_at, home_team, away_team, opposition, is_final) "
             "VALUES (:i, :o, :s, :g, :d, 'Somebody Else', 'Third Club', 'Third Club', false)",
             i=MG_OTHER, o=OTHER, s=S_OTHER, g=G_OTHER, d=dt.date(2010, 11, 20))

    await db.commit()


async def old_query_rows(db, org_id, season_id):
    """The pre-fix query shape: synced `games` only, INNER JOIN grades/seasons."""
    q = text("""
        SELECT g.id FROM games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE s.organisation_id = :org_id AND s.id = :season_id
    """)
    return (await db.execute(q, {"org_id": str(org_id), "season_id": str(season_id)})).all()


async def main() -> int:
    engine = create_async_engine(DB_URL)
    await build_schema(engine)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        await seed(db)

    org = Organisation(id=ORG, name="Hamilton Veterans", slug="hamilton-veterans")
    other = Organisation(id=OTHER, name="Somebody Else CC", slug="somebody-else")
    user = User(id=uuid.uuid4(), username="admin-ag", email="a@b.c", password_hash="x")

    async with Session() as db:
        # The reported case: the imported 2010/11 season.
        imported = await list_games(season_id=str(S_IMPORTED), current_user=user, club=org, db=db)
        ids = {r["id"] for r in imported}

        print("\nThe imported season now lists its matches")
        check("the graded imported match appears", str(MG_GRADED) in ids,
              f"got {len(imported)} rows")
        check("a grade-less imported match still appears (LEFT JOIN)",
              str(MG_NOGRADE) in ids)
        check("the imported season is not empty", len(imported) == 2,
              f"got {len(imported)}")

        by_id = {r["id"]: r for r in imported}
        graded = by_id.get(str(MG_GRADED), {})
        nograde = by_id.get(str(MG_NOGRADE), {})
        check("an imported row is marked source 'manual'", graded.get("source") == "manual",
              str(graded.get("source")))
        check("an imported row carries no PlayHQ status", graded.get("status") is None)
        check("an imported row has no players_named (synced-only)",
              graded.get("players_named") is None)
        check("a graded import resolves its grade name", graded.get("grade") == "A Grade",
              str(graded.get("grade")))
        check("a grade-less import shows no grade but keeps its season",
              nograde.get("grade") is None and nograde.get("season") == "Summer 2010/11",
              f"grade={nograde.get('grade')} season={nograde.get('season')}")

        print("\nControl: the old query shape hid exactly these matches")
        old = await old_query_rows(db, ORG, S_IMPORTED)
        check("the pre-fix query returned nothing for the imported season", len(old) == 0,
              f"old query got {len(old)} rows")

        print("\nSynced season is unchanged")
        synced = await list_games(season_id=str(S_SYNCED), current_user=user, club=org, db=db)
        s_ids = {r["id"] for r in synced}
        s_by = {r["id"]: r for r in synced}
        check("the synced completed game still lists", str(GAME_SYNC) in s_ids,
              f"got {len(synced)} rows")
        check("a synced game is marked source 'api'",
              s_by.get(str(GAME_SYNC), {}).get("source") == "api")
        check("the synced result text is carried through",
              s_by.get(str(GAME_SYNC), {}).get("result") == "Hamilton Vets won by 5 wickets")
        aband = s_by.get(str(GAME_ABANDONED), {})
        check("a called-off synced fixture reports its status", aband.get("status") == "ABANDONED")
        check("a called-off synced fixture counts its named players",
              aband.get("players_named") == 2, str(aband.get("players_named")))

        print("\nCross-club scoping holds (no manual-branch leak)")
        check("another club's imported match never appears here",
              str(MG_OTHER) not in ids and str(MG_OTHER) not in s_ids)
        # With no season filter at all, the whole club's list, still scoped.
        allrows = await list_games(season_id=None, current_user=user, club=org, db=db)
        all_ids = {r["id"] for r in allrows}
        check("unfiltered, the club sees both its synced and imported matches",
              {str(GAME_SYNC), str(GAME_ABANDONED), str(MG_GRADED), str(MG_NOGRADE)} <= all_ids,
              f"got {len(allrows)} rows")
        check("unfiltered, another club's match is still not there",
              str(MG_OTHER) not in all_ids)
        # And the other club sees only its own.
        other_rows = await list_games(season_id=None, current_user=user, club=other, db=db)
        other_ids = {r["id"] for r in other_rows}
        check("the other club sees its own imported match",
              str(MG_OTHER) in other_ids)
        check("the other club sees none of Hamilton's matches",
              not ({str(GAME_SYNC), str(MG_GRADED), str(MG_NOGRADE)} & other_ids))

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILURES:")
        for f in FAIL:
            print("  -", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
