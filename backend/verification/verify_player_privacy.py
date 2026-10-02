"""Verification for hiding a player at their own request (migration 316),
against a real Postgres.

Runs the SHIPPED `services/player_privacy.py`, `scripts/hide_player_at_request.py`
and the shipped routers (`players` through FastAPI itself, `seo`, `og_preview`,
`club_admin`) over a club with three players:

  * TRENT    asked to be removed. Has a photo, an action photo and a BetterIQ
             scouting copy of the photo, plus a row against him in another table.
  * PLAIN    the control: never asked, same photos, must stay fully visible.
  * CLUBHID  a player the CLUB hid with the older `is_public` switch alone
             (no request marker): the gap the new work closes.

Every "X is gone" check is paired with a check that X is there before, for the
control player, and for a club admin (rule 21).

CONTROL MODE. The same suite runs against the commit BEFORE this change, where
`services/player_privacy.py` does not exist. "Asking to be removed" is then
reproduced the only way the old code allowed, `players.is_public = false`, so
the control reports the reported behaviour (stats still served, still in the
sitemap and share card, photo still stored) as failed checks rather than
crashing on an import.

Run:  DATABASE_URL=postgresql+asyncpg://root@/privacy_test?host=/var/run/postgresql \
      python verification/verify_player_privacy.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import Base, Organisation, Player, User
import app.models.scout  # noqa: F401  (registers scouted_players on Base)

HAVE = importlib.util.find_spec("app.services.player_privacy") is not None
if HAVE:
    from app.services import player_privacy
    from app.services.player_privacy_ddl import STATEMENTS as PRIVACY_DDL
    from app.scripts import hide_player_at_request as script
else:
    player_privacy = script = None
    PRIVACY_DDL = []

from app.routers import club_admin as club_admin_router
from app.routers import og_preview as og_router
from app.routers import players as players_router
from app.routers import seo as seo_router

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


# The merge's own raw-SQL tables, in the shape verify_merge_carry.py builds them.
EXTRA_DDL = (
    """
    CREATE TABLE IF NOT EXISTS merge_logs (
        id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID,
        keep_player_id UUID, keep_player_name TEXT,
        removed_player_id UUID, removed_player_name TEXT,
        removed_player_playhq_id TEXT, keep_original_playhq_id TEXT,
        moved_season_stat_ids JSONB DEFAULT '[]', batting_innings_ids JSONB DEFAULT '[]',
        bowling_spell_ids JSONB DEFAULT '[]', fielding_stat_ids JSONB DEFAULT '[]',
        fall_of_wicket_ids JSONB DEFAULT '[]', batter1_partnership_ids JSONB DEFAULT '[]',
        batter2_partnership_ids JSONB DEFAULT '[]', milestone_ids JSONB DEFAULT '[]',
        bowler_wicket_ids JSONB DEFAULT '[]', fielder_wicket_ids JSONB DEFAULT '[]',
        grade_stat_ids JSONB DEFAULT '[]', appearance_game_ids JSONB DEFAULT '[]',
        imported_stat_ids JSONB DEFAULT '[]',
        carried_row_ids JSONB DEFAULT '{}', removed_cricketstatz_player_id TEXT,
        undone_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS player_achievements (
        id SERIAL PRIMARY KEY, org_id UUID NOT NULL, player_id UUID,
        player_name TEXT NOT NULL, season TEXT, season_end TEXT,
        category TEXT NOT NULL, subcategory TEXT, achievement TEXT NOT NULL,
        detail TEXT, import_batch_id UUID, created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id SERIAL PRIMARY KEY, org_id UUID, user_id UUID, action TEXT,
        target_type TEXT, target_id TEXT, details JSONB,
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS player_name_aliases (
        id SERIAL PRIMARY KEY, organisation_id UUID NOT NULL,
        player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        alias_key TEXT NOT NULL, alias_name TEXT NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE (organisation_id, alias_key)
    )
    """,
)


def uid() -> uuid.UUID:
    return uuid.uuid4()


OURS, SEASON, ADMIN = uid(), uid(), uid()
TRENT, PLAIN, CLUBHID = uid(), uid(), uid()
OTHER, NEWORG, SIB = uid(), uid(), uid()   # Trent's row at ANOTHER club, and a club that joins later
PHOTO = b"\x89PNG-fake-headshot"
HERO = b"\x89PNG-fake-action"


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
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
        from app.services.junior_hiding_ddl import STATEMENTS as JUNIOR_DDL
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
        # The sitemap lists the video library, a raw-SQL lifespan table.
        try:
            from app.services.instructional_video_ddl import STATEMENTS as VIDEO_DDL
            for stmt in VIDEO_DDL:
                await conn.execute(text(stmt))
        except Exception as exc:  # pragma: no cover - harness detail
            print("  (video DDL not applied:", exc, ")")
        for stmt in EXTRA_DDL:
            await conn.execute(text(stmt))
        # The SHIPPED DDL for migration 316 (the suppression table is raw SQL, so
        # create_all never makes it), not a retyped copy.
        for stmt in PRIVACY_DDL:
            await conn.execute(text(stmt))
        # The ORM maps instructional_videos without the later raw-SQL columns the
        # sitemap's video listing reads; the shipped DDL above adds them only
        # when the table is absent, so add the one it selects.
        await conn.execute(text("ALTER TABLE instructional_videos ADD COLUMN IF NOT EXISTS duration_seconds INT"))
        # A fixture is one row; the sitemap reads hide_juniors from organisations.
        # create_all already has it (ORM-mapped). Nothing else to add.


async def seed(session) -> None:
    session.add(Organisation(id=OURS, name="Applecross", is_active=True))
    await session.flush()
    for pid, name in ((TRENT, "Trent Steenholdt"), (PLAIN, "Pat Plain"), (CLUBHID, "Cass Clubhid")):
        session.add(Player(
            id=pid, name=name, organisation_id=OURS, grassroots_id=str(pid),
            photo_data=PHOTO, photo_mime="image/png",
            photo_url=f"/api/images/players/{pid}/photo?v=1",
            hero_photo_data=HERO, hero_photo_mime="image/png",
            hero_photo_url=f"/api/images/players/{pid}/hero-photo?v=1",
        ))
    # The same person at another club: a per-club row (uuid5 id) carrying the
    # SAME Cricket Australia participant id, with its own photo.
    session.add(Organisation(id=OTHER, name="Rival Club", is_active=True))
    session.add(Organisation(id=NEWORG, name="Joins Later", is_active=True))
    await session.flush()
    session.add(Player(
        id=SIB, name="Trent Steenholdt", organisation_id=OTHER, grassroots_id=str(TRENT),
        photo_data=PHOTO, photo_mime="image/png", photo_url=f"/api/images/players/{SIB}/photo?v=1",
    ))
    await session.flush()
    await session.execute(text(
        "INSERT INTO users (id, username, email, failed_login_count) VALUES (:i,'admin1','a@x.test',0)"), {"i": ADMIN})
    await session.execute(text(
        "INSERT INTO club_memberships (id, club_id, user_id, role) "
        "VALUES (gen_random_uuid(), :c, :u, 'club_admin')"), {"c": OURS, "u": ADMIN})
    # BetterIQ scouting copies: one keyed on his Cricket Australia participant
    # id, one on the control player. Both hold a photograph.
    for guid, name in ((str(TRENT), "Trent Steenholdt"), (str(PLAIN), "Pat Plain")):
        await session.execute(text(
            "INSERT INTO scouted_players (id, source, grassroots_participant_id, name, photo_data, photo_mime, photo_url) "
            "VALUES (gen_random_uuid(), 'au_grassroots', :g, :n, :b, 'image/png', '/api/images/scouted-players/x/photo')"),
            {"g": guid, "n": name, "b": PHOTO})
    await session.commit()


def make_app(who: dict):
    import httpx  # noqa: F401
    from fastapi import FastAPI
    from app.models.db import get_db
    from app.routers.auth import get_optional_user

    app = FastAPI()
    app.include_router(players_router.router)
    app.include_router(seo_router.router)

    async def _db():
        async with Session() as s:
            yield s

    async def _viewer():
        return who["user"]

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_optional_user] = _viewer
    return app


async def public_view(c, pid, label_prefix, expect_visible: bool, note: str = "") -> None:
    """The profile and the tabs behind it, as the public, against one expectation."""
    p = await c.get(f"/players/{pid}")
    s = await c.get(f"/players/{pid}/stats")
    a = await c.get(f"/players/{pid}/activity")
    if expect_visible:
        check(f"{label_prefix}: profile 200{note}", p.status_code == 200, str(p.status_code))
        check(f"{label_prefix}: stats tab 200{note}", s.status_code == 200, str(s.status_code))
        check(f"{label_prefix}: activity tab 200{note}", a.status_code == 200, str(a.status_code))
    else:
        check(f"{label_prefix}: profile 404{note}", p.status_code == 404, str(p.status_code))
        check(f"{label_prefix}: stats tab 404 (not one direct request away){note}", s.status_code == 404, str(s.status_code))
        check(f"{label_prefix}: activity tab 404{note}", a.status_code == 404, str(a.status_code))


async def sitemap_ids(c) -> set[str]:
    r = await c.get("/sitemap.xml")
    check("sitemap serves", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    return {pid for pid in map(str, (TRENT, PLAIN, CLUBHID)) if f"/players/{pid}<" in r.text}


async def og_present(pid) -> bool:
    async with Session() as db:
        html = await og_router._player_html(str(pid), f"https://betterat.cricket/players/{pid}", "https://betterat.cricket", db)
    return html is not None and "Steenholdt" in html if str(pid) == str(TRENT) else html is not None


async def col(sql: str, **kw):
    async with Session() as db:
        return (await db.execute(text(sql), kw)).scalar()


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await build_schema()
    async with Session() as s:
        await seed(s)

    import httpx
    who: dict = {"user": None}
    app = make_app(who)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        # ------------------------------------------------------------ BEFORE
        print("before: everybody is visible")
        await public_view(c, TRENT, "Trent", True)
        await public_view(c, PLAIN, "control", True)
        await public_view(c, SIB, "Trent at another club", True)
        listed = await sitemap_ids(c)
        check("sitemap lists all three before", listed == {str(TRENT), str(PLAIN), str(CLUBHID)}, str(listed))
        check("share card exists for Trent before", await og_present(TRENT))

        # ---------------------------------------------------------- HIDE HIM
        print("asking to be removed")
        if HAVE:
            # Dry run first: writes nothing.
            args = SimpleNamespace(player_id=str(TRENT), reason="asked by email", by="Jack", report=False,
                                   restore=False, keep_photos=False, apply=False)
            import contextlib, io
            buf = io.StringIO()
            # The script opens its own session on the app's engine; point it at ours.
            script.async_session_maker = Session
            with contextlib.redirect_stdout(buf):
                rc = await script.run(args)
            check("dry run exits cleanly", rc == 0, str(rc))
            check("dry run wrote nothing (still public, photo kept)",
                  await col("SELECT is_public AND photo_data IS NOT NULL FROM players WHERE id=:i", i=TRENT) is True)
            check("dry run report names what is held (scouting copy)", "scouting_copies" in buf.getvalue() and "has_photo" in buf.getvalue())

            args.apply = True
            with contextlib.redirect_stdout(io.StringIO()):
                rc = await script.run(args)
            check("--apply exits cleanly", rc == 0, str(rc))
        else:
            print("  CONTROL RUN: services/player_privacy.py does not exist at this commit; "
                  "hiding is is_public=false alone")
            async with Session() as db:
                await db.execute(text("UPDATE players SET is_public = false WHERE id = :i"), {"i": TRENT})
                await db.commit()

        async with Session() as db:
            await db.execute(text("UPDATE players SET is_public = false WHERE id = :i"), {"i": CLUBHID})
            await db.commit()

        # ------------------------------------------------------------- AFTER
        print("after: public viewer")
        await public_view(c, TRENT, "Trent", False)
        await public_view(c, CLUBHID, "club-hidden player", False, " (older switch, no marker)")
        await public_view(c, PLAIN, "control", True, " (stays visible)")
        await public_view(c, SIB, "Trent's row at ANOTHER club", False, " (same person, same participant id)")
        check("his photo at the other club is gone too",
              await col("SELECT photo_data IS NULL AND photo_url IS NULL FROM players WHERE id=:i", i=SIB) is True)
        listed = await sitemap_ids(c)
        check("sitemap no longer lists Trent", str(TRENT) not in listed, str(listed))
        check("sitemap no longer lists the club-hidden player", str(CLUBHID) not in listed, str(listed))
        check("sitemap still lists the control player", str(PLAIN) in listed, str(listed))
        check("no share card for Trent (crawlers get no name or photo)", not await og_present(TRENT))
        check("share card still built for the control player", await og_present(PLAIN))

        print("after: what is stored")
        check("Trent's headshot is gone",
              await col("SELECT photo_data IS NULL AND photo_url IS NULL FROM players WHERE id=:i", i=TRENT) is True)
        check("Trent's action photo is gone",
              await col("SELECT hero_photo_data IS NULL AND hero_photo_url IS NULL FROM players WHERE id=:i", i=TRENT) is True)
        check("the BetterIQ scouting copy of his photo is gone",
              await col("SELECT photo_data IS NULL AND photo_url IS NULL FROM scouted_players "
                        "WHERE grassroots_participant_id=:g", g=str(TRENT)) is True)
        check("the control player's headshot is untouched",
              await col("SELECT photo_data IS NOT NULL FROM players WHERE id=:i", i=PLAIN) is True)
        check("the control player's scouting copy is untouched",
              await col("SELECT photo_data IS NOT NULL FROM scouted_players WHERE grassroots_participant_id=:g",
                        g=str(PLAIN)) is True)
        check("the player ROW is kept (his match records hang off it)",
              await col("SELECT COUNT(*) FROM players WHERE id=:i", i=TRENT) == 1)

        if HAVE:
            check("marker is set on the row",
                  await col("SELECT privacy_hidden_at IS NOT NULL AND privacy_hidden_by='Jack' "
                            "AND privacy_hidden_reason='asked by email' FROM players WHERE id=:i", i=TRENT) is True)
            check("an audit entry was written for the club",
                  await col("SELECT COUNT(*) FROM manual_edit_logs WHERE action='privacy_hide' "
                            "AND target_id=:t AND organisation_id=:o", t=str(TRENT), o=OURS) == 1)
            check("the audit entry holds no photo bytes",
                  await col("SELECT NOT (before_json::text ILIKE '%PNG%' OR after_json::text ILIKE '%PNG%') "
                            "FROM manual_edit_logs WHERE action='privacy_hide' AND target_id=:t", t=str(TRENT)) is True)
            check("the control player carries no marker",
                  await col("SELECT privacy_hidden_at IS NULL FROM players WHERE id=:i", i=PLAIN) is True)

            # ---- idempotent
            first = await col("SELECT privacy_hidden_at FROM players WHERE id=:i", i=TRENT)
            async with Session() as db:
                pl = await db.get(Player, TRENT)
                out = await player_privacy.hide_at_request(db, pl, by="Jack", reason="asked by email")
                await db.commit()
            check("hiding twice reports it was already hidden", out["already_hidden"] is True)
            check("hiding twice keeps the original timestamp",
                  await col("SELECT privacy_hidden_at FROM players WHERE id=:i", i=TRENT) == first)

            # ---- the club cannot put him back
            print("the club cannot undo it")
            async with Session() as db:
                pl = await db.get(Player, TRENT)
                admin = await db.get(User, ADMIN)
                body = players_router.PlayerProfileUpdate(is_public=True)
                try:
                    await players_router.update_player_profile(str(TRENT), body, db, admin)
                    refused = None
                except HTTPException as e:
                    refused = e.status_code
            check("profile edit switching him public is refused (409)", refused == 409, str(refused))
            check("...and he is still hidden",
                  await col("SELECT is_public FROM players WHERE id=:i", i=TRENT) is False)
            async with Session() as db:
                admin = await db.get(User, ADMIN)
                try:
                    await players_router.update_player_profile(
                        str(TRENT), players_router.PlayerProfileUpdate(shirt_number="7"), db, admin)
                    ok = True
                except HTTPException as e:
                    ok = False
            check("an unrelated profile edit still works for him (not a lock on the record)", ok)
            async with Session() as db:
                pl = await db.get(Player, TRENT)
                up = UploadFile(filename="x.png", file=__import__("io").BytesIO(PHOTO))
                try:
                    await club_admin_router._store_player_photo(db, pl, up, "photo")
                    st = None
                except HTTPException as e:
                    st = e.status_code
            check("a photo upload for him is refused (409)", st == 409, str(st))
            async with Session() as db:
                pl = await db.get(Player, PLAIN)
                up = UploadFile(filename="x.png", file=__import__("io").BytesIO(PHOTO))
                try:
                    await club_admin_router._store_player_photo(db, pl, up, "photo")
                    st = None
                except HTTPException as e:
                    st = e.status_code
            check("...while the control player's upload still works", st is None, str(st))

            # ---- the sync does not resurrect or alter him
            print("the sync")
            from app.services import sync as sync_mod
            async with Session() as db:
                rows = (await db.execute(text(
                    "SELECT COALESCE(grassroots_id, id::text), id FROM players WHERE organisation_id=:o"), {"o": OURS})).all()
                pmap = {g: i for g, i in rows}
                got = await sync_mod._resolve_org_player(db, OURS, pmap, str(TRENT), "Trent Steenholdt", {})
                await db.flush()
                await db.rollback()
            check("sync resolves him to the SAME row, creating no duplicate", got == TRENT, str(got))
            # A club that joins later, or a fixture another club syncs, mints a NEW row
            # for the same person. It must be born hidden.
            async with Session() as db:
                got2 = await sync_mod._resolve_org_player(db, NEWORG, {}, str(TRENT), "Trent Steenholdt", {})
                await db.flush()
                other_guid = str(uid())
                got3 = await sync_mod._resolve_org_player(db, NEWORG, {}, other_guid, "Someone Else", {})
                await db.commit()
            check("a NEW row minted for him at a club that joins later is born hidden",
                  await col("SELECT is_public IS FALSE AND privacy_hidden_at IS NOT NULL FROM players WHERE id=:i",
                            i=got2) is True)
            await public_view(c, got2, "the new row", False)
            check("...while a new player nobody asked about is created public (the guard is not blanket)",
                  await col("SELECT is_public IS TRUE AND privacy_hidden_at IS NULL FROM players WHERE id=:i",
                            i=got3) is True)
            check("his row still carries the marker after a sync-style resolve",
                  await col("SELECT privacy_hidden_at IS NOT NULL AND is_public IS FALSE FROM players WHERE id=:i", i=TRENT) is True)

            # ---- a merge must not put him back
            print("merging a duplicate")
            from app.routers.admin import _merge_players_core
            DUP_HIDDEN, DUP_KEEP = uid(), uid()
            async with Session() as db:
                db.add(Player(id=DUP_HIDDEN, name="Trent S (dup)", organisation_id=OURS, grassroots_id=str(DUP_HIDDEN),
                              photo_data=PHOTO, photo_mime="image/png"))
                db.add(Player(id=DUP_KEEP, name="Trent Steenholdt (keeper)", organisation_id=OURS,
                              grassroots_id=str(DUP_KEEP), photo_data=PHOTO, photo_mime="image/png"))
                await db.commit()
            async with Session() as db:
                dup = await db.get(Player, DUP_HIDDEN)
                await player_privacy.hide_at_request(db, dup, by="Jack", reason="asked by email")
                await db.commit()
            try:
                async with Session() as db:
                    admin = await db.get(User, ADMIN)
                    await _merge_players_core(db, DUP_KEEP, DUP_HIDDEN, OURS, admin)
                merged = True
            except Exception as exc:  # pragma: no cover - harness detail
                merged = False
                print("  merge raised:", repr(exc)[:200])
            check("the merge ran", merged)
            check("the removed duplicate row is gone",
                  await col("SELECT COUNT(*) FROM players WHERE id=:i", i=DUP_HIDDEN) == 0)
            check("the keeper inherited the request: hidden, marker set",
                  await col("SELECT is_public IS FALSE AND privacy_hidden_at IS NOT NULL FROM players WHERE id=:i",
                            i=DUP_KEEP) is True)
            check("the keeper's photo was removed too",
                  await col("SELECT photo_data IS NULL FROM players WHERE id=:i", i=DUP_KEEP) is True)
            await public_view(c, DUP_KEEP, "merged keeper", False)

            # ---- the report
            async with Session() as db:
                pl = await db.get(Player, TRENT)
                rep = await player_privacy.holdings(db, pl)
            check("the access report lists his rows at the other clubs (the first club and the one that joined later)", len(rep["other_club_rows"]) == 2, str(rep["other_club_rows"]))
            check("the access report says a suppression is in place", rep["suppressed"] is True)
            check("the access report lists the scouting copy", len(rep["scouting_copies"]) == 1, str(rep["scouting_copies"]))
            check("the access report says the photo is gone", rep["player"]["has_photo"] is False)

        # -------------------------------------------------------- CLUB ADMIN
        print("a signed-in club admin")
        async with Session() as db:
            who["user"] = await db.get(User, ADMIN)
        await public_view(c, TRENT, "club admin sees Trent", True, " (club sees its own record whole)")
        who["user"] = None

        # ----------------------------------------------------------- RESTORE
        if HAVE:
            print("restore")
            args = SimpleNamespace(player_id=str(TRENT), reason=None, by="Jack", report=False,
                                   restore=True, keep_photos=False, apply=True)
            with contextlib.redirect_stdout(io.StringIO()):
                rc = await script.run(args)
            check("restore exits cleanly", rc == 0)
            await public_view(c, TRENT, "after restore", True)
            check("restore does NOT bring the photo back",
                  await col("SELECT photo_data IS NULL FROM players WHERE id=:i", i=TRENT) is True)
            check("restore lifts the other club's row and the suppression too",
                  await col("SELECT is_public IS TRUE AND privacy_hidden_at IS NULL FROM players WHERE id=:i", i=SIB) is True
                  and await col("SELECT COUNT(*) FROM player_privacy_suppressions WHERE grassroots_id=:g", g=str(TRENT)) == 0)
            check("marker cleared",
                  await col("SELECT privacy_hidden_at IS NULL FROM players WHERE id=:i", i=TRENT) is True)

            # ---- DDL: idempotent, and really adds the columns
            print("migration 316 DDL")
            async with engine.begin() as conn:
                for stmt in ("ALTER TABLE players DROP COLUMN privacy_hidden_at",
                             "ALTER TABLE players DROP COLUMN privacy_hidden_by",
                             "ALTER TABLE players DROP COLUMN privacy_hidden_reason"):
                    await conn.execute(text(stmt))
                for _ in range(2):  # the lifespan re-runs it on every boot
                    for stmt in PRIVACY_DDL:
                        await conn.execute(text(stmt))
            cols = (await col("SELECT string_agg(column_name, ',' ORDER BY column_name) FROM information_schema.columns "
                              "WHERE table_name='players' AND column_name LIKE 'privacy_hidden_%'")) or ""
            check("STATEMENTS add the three columns, and re-running them is harmless",
                  cols == "privacy_hidden_at,privacy_hidden_by,privacy_hidden_reason", cols)
            from app.services.player_privacy_ddl import DOWNGRADE
            async with engine.begin() as conn:
                for stmt in DOWNGRADE:
                    await conn.execute(text(stmt))
                for stmt in PRIVACY_DDL:
                    await conn.execute(text(stmt))
            check("the suppression table exists after the re-run",
                  await col("SELECT COUNT(*) FROM information_schema.tables WHERE table_name='player_privacy_suppressions'") == 1)
            check("DOWNGRADE drops only what it added",
                  await col("SELECT COUNT(*) FROM information_schema.tables WHERE table_name='players'") == 1)

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("FAILED:", *FAILURES, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
