"""A person who asked to be removed stays removed through everything a club can run.

Runs the SHIPPED sync player resolver (`services.sync._resolve_org_player`), the
hard-refresh wipe SQL, the merge and `undo_merge` bodies, against a real Postgres.

The rule: the hide survives a sync, a Full Rebuild or hard refresh, the club's
rows being deleted and re-pulled, and the undoing of a merge. Every "stays hidden"
check is paired with a control person who never asked and must stay visible.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/privacy_sync?host=/var/run/postgresql \
      python verification/verify_privacy_survives_sync.py
The same suite against the previous commit shows the undo-merge check failing.
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

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base, Player
import app.models.scout  # noqa: F401
from app.routers.admin import _merge_players_core, undo_merge, UndoMergeRequest
from app.services import player_privacy, sync
from app.services.player_privacy_ddl import STATEMENTS as PRIVACY_DDL
from verify_merge_carry import EXTRA_DDL, FakeUser

DB_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres@/privacy_sync?host=/var/run/postgresql")
PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail and not ok else ""))


ORG1 = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000001")
ORG2 = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000002")
TRENT = uuid.UUID("bbbbbbbb-1111-4000-8000-000000000001")   # raw CA participant id
OTHER = uuid.UUID("bbbbbbbb-1111-4000-8000-000000000002")   # control: never asked


async def state(maker, pid):
    async with maker() as db:
        r = (await db.execute(text(
            "SELECT is_public, privacy_hidden_at IS NOT NULL AS marked FROM players WHERE id = :p"),
            {"p": str(pid)})).first()
    return None if r is None else (r[0] is not False, bool(r[1]))


async def resolve(maker, org, guid, name="Steenholdt, Trent", cache=None):
    async with maker() as db:
        pid = await sync._resolve_org_player(db, org, cache if cache is not None else {}, str(guid), name, {})
        await db.commit()
    return pid


async def main() -> int:
    engine = create_async_engine(DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        for st in EXTRA_DDL:
            await conn.execute(text(st))
        for st in PRIVACY_DDL:
            await conn.execute(text(st))
        await conn.execute(text("TRUNCATE players, organisations CASCADE"))
        await conn.execute(text("TRUNCATE player_privacy_suppressions"))
    async with maker() as db:
        for org, slug in ((ORG1, "club-one"), (ORG2, "club-two")):
            await db.execute(text("INSERT INTO organisations (id, name, slug, is_active) VALUES (:o, :n, :s, true)"),
                             {"o": str(org), "n": slug, "s": slug})
        for pid, name in ((TRENT, "Steenholdt, Trent"), (OTHER, "Steenholdt, Pat")):
            await db.execute(text(
                "INSERT INTO players (id, organisation_id, name, grassroots_id) VALUES (:p, :o, :n, :g)"),
                {"p": str(pid), "o": str(ORG1), "n": name, "g": str(pid)})
        await db.commit()
    async with maker() as db:
        t = await db.get(Player, TRENT)
        await player_privacy.hide_at_request(db, t, by="verifier", reason="privacy request")
        await db.commit()

    print("\nBefore anything runs")
    check("Trent is hidden and marked", await state(maker, TRENT) == (False, True))
    check("the control player is visible and unmarked", await state(maker, OTHER) == (True, False))

    print("\nA sync meeting him again")
    cache = {str(TRENT): TRENT, str(OTHER): OTHER}
    got = await resolve(maker, ORG1, TRENT, cache=cache)
    check("a sync that already knows him leaves the same row", got == TRENT)
    check("and he is still hidden", await state(maker, TRENT) == (False, True))
    check("a sync does not touch the control either", await state(maker, OTHER) == (True, False))

    print("\nAnother club syncing a fixture he played in")
    new_id = await resolve(maker, ORG2, TRENT)
    check("his row at the second club is born hidden and marked", await state(maker, new_id) == (False, True))
    other_new = await resolve(maker, ORG2, OTHER, name="Steenholdt, Pat")
    check("the control's row at that club is born visible", await state(maker, other_new) == (True, False))

    print("\nHard refresh and Full Rebuild (the exact wipe the app runs)")
    async with maker() as db:
        await db.execute(text("""
            DELETE FROM games
            WHERE id IN (SELECT DISTINCT game_id FROM batting_innings)
              AND grade_id IN (SELECT gr.id FROM grades gr JOIN seasons se ON se.id = gr.season_id
                                WHERE se.organisation_id = :oid)
        """), {"oid": str(ORG1)})
        await db.commit()
    check("the wipe leaves him hidden and marked", await state(maker, TRENT) == (False, True))
    check("and the wipe leaves the control visible", await state(maker, OTHER) == (True, False))

    print("\nA club's rows deleted and pulled again from scratch")
    async with maker() as db:
        await db.execute(text("DELETE FROM players WHERE organisation_id = :o"), {"o": str(ORG2)})
        await db.commit()
    again = await resolve(maker, ORG2, TRENT)
    check("the re-pulled row is hidden again from the suppression record", await state(maker, again) == (False, True))
    again_other = await resolve(maker, ORG2, OTHER, name="Steenholdt, Pat")
    check("the control comes back visible", await state(maker, again_other) == (True, False))

    print("\nA merge, then somebody undoes it")
    DUP = uuid.UUID("bbbbbbbb-2222-4000-8000-000000000001")
    KEEP = uuid.UUID("bbbbbbbb-2222-4000-8000-000000000002")
    CTRL_DUP = uuid.UUID("bbbbbbbb-2222-4000-8000-000000000003")
    CTRL_KEEP = uuid.UUID("bbbbbbbb-2222-4000-8000-000000000004")
    async with maker() as db:
        for pid, name in ((DUP, "Dup Person"), (KEEP, "Keep Person"), (CTRL_DUP, "Ctrl Dup"), (CTRL_KEEP, "Ctrl Keep")):
            await db.execute(text(
                "INSERT INTO players (id, organisation_id, name, grassroots_id) VALUES (:p, :o, :n, :g)"),
                {"p": str(pid), "o": str(ORG1), "n": name, "g": str(pid)})
        await db.commit()
    async with maker() as db:
        d = await db.get(Player, DUP)
        await player_privacy.hide_at_request(db, d, by="verifier", reason="privacy request")
        await db.commit()
    async with maker() as db:
        await _merge_players_core(db, KEEP, DUP, ORG1, FakeUser())
    async with maker() as db:
        await _merge_players_core(db, CTRL_KEEP, CTRL_DUP, ORG1, FakeUser())
    check("the merge carries the hide onto the kept record", (await state(maker, KEEP)) == (False, True))
    check("a merge of two ordinary people hides nobody", (await state(maker, CTRL_KEEP)) == (True, False))
    async with maker() as db:
        logs = (await db.execute(text(
            "SELECT id, removed_player_id FROM merge_logs WHERE org_id = :o"), {"o": str(ORG1)})).mappings().all()
    by_removed = {str(r["removed_player_id"]): r["id"] for r in logs}
    for rid in (DUP, CTRL_DUP):
        async with maker() as db:
            await undo_merge(UndoMergeRequest(merge_log_id=by_removed[str(rid)], org_id=str(ORG1)),
                             db=db, current_user=FakeUser())
    check("undoing the merge brings his record back", await state(maker, DUP) is not None)
    check("and it comes back hidden and marked, not visible", await state(maker, DUP) == (False, True),
          str(await state(maker, DUP)))
    check("undoing an ordinary merge brings the person back visible", await state(maker, CTRL_DUP) == (True, False),
          str(await state(maker, CTRL_DUP)))

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for n in FAIL:
        print(f"  FAILED: {n}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
