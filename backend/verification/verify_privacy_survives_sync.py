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


async def names_of(maker, guid):
    """The person's names on the global record; None where the column does not exist (the control)."""
    try:
        async with maker() as db:
            return (await db.execute(text(
                "SELECT names FROM player_privacy_suppressions WHERE grassroots_id = :g"), {"g": str(guid)})).scalar()
    except Exception:
        return None


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

    print("\nA creator nobody taught about the suppression (the database enforces it)")
    ORG3 = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000003")
    async with maker() as db:
        await db.execute(text("INSERT INTO organisations (id, name, slug, is_active) VALUES (:o, 'club-three', 'club-three', true)"),
                         {"o": str(ORG3)})
        raw_id, raw_ctrl, orm_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        # A raw INSERT, like an importer or the undo path: no protect_new_player.
        await db.execute(text(
            "INSERT INTO players (id, organisation_id, name, grassroots_id) VALUES (:p, :o, 'Steenholdt, T', :g)"),
            {"p": str(raw_id), "o": str(ORG3), "g": str(TRENT).upper()})
        await db.execute(text(
            "INSERT INTO players (id, organisation_id, name, grassroots_id) VALUES (:p, :o, 'Steenholdt, Pat', :g)"),
            {"p": str(raw_ctrl), "o": str(ORG3), "g": str(OTHER)})
        # An ORM insert with no guard call at all.
        db.add(Player(id=orm_id, name="Trent S", organisation_id=ORG3, grassroots_id=str(TRENT)))
        await db.commit()
    check("a raw INSERT for his participant id is hidden and marked", await state(maker, raw_id) == (False, True))
    check("an ORM insert that never called the guard is hidden and marked", await state(maker, orm_id) == (False, True))
    check("a raw INSERT for the control stays visible", await state(maker, raw_ctrl) == (True, False))

    print("\nSwitching a suppressed person back on")
    async with maker() as db:
        await db.execute(text("UPDATE players SET is_public = TRUE, privacy_hidden_at = NULL WHERE id = ANY(CAST(:ids AS uuid[]))"),
                         {"ids": [str(TRENT), str(raw_id)]})
        await db.execute(text("UPDATE players SET is_public = FALSE WHERE id = :p"), {"p": str(raw_ctrl)})
        await db.commit()
    check("a direct UPDATE cannot make him visible again", await state(maker, TRENT) == (False, True))
    check("nor his row at another club", await state(maker, raw_id) == (False, True))
    check("an UPDATE on the control still works (it was hidden by the club)", (await state(maker, raw_ctrl))[0] is False)
    async with maker() as db:
        await db.execute(text("UPDATE players SET is_public = TRUE WHERE id = :p"), {"p": str(raw_ctrl)})
        await db.commit()
    check("and can be switched back on", await state(maker, raw_ctrl) == (True, False))

    print("\nA row that escaped before the trigger existed")
    async with maker() as db:
        await db.execute(text("DROP TRIGGER IF EXISTS player_privacy_enforce_ins ON players"))
        await db.execute(text("DROP TRIGGER IF EXISTS player_privacy_enforce_upd ON players"))
        esc = uuid.uuid4()
        ORG4 = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000004")
        await db.execute(text("INSERT INTO organisations (id, name, slug, is_active) VALUES (:o, 'club-four', 'club-four', true)"),
                         {"o": str(ORG4)})
        await db.execute(text(
            "INSERT INTO players (id, organisation_id, name, grassroots_id) VALUES (:p, :o, 'Steenholdt, T', :g)"),
            {"p": str(esc), "o": str(ORG4), "g": str(TRENT)})
        await db.commit()
    check("(setup) it really is visible with no trigger", await state(maker, esc) == (True, False))
    async with engine.begin() as conn:
        for st in PRIVACY_DDL:
            await conn.execute(text(st))
    check("re-running the DDL (a boot) hides it", await state(maker, esc) == (False, True))
    async with engine.begin() as conn:
        for st in PRIVACY_DDL:
            await conn.execute(text(st))
    check("and a second boot is harmless", await state(maker, esc) == (False, True))
    check("and leaves the control alone", await state(maker, OTHER) == (True, False))

    print("\nA hand-typed player with his name (no participant id, so matched on name)")
    keys = await names_of(maker, TRENT)
    check("the global record keeps his name as a key", "steenholdt trent" in (keys or []), str(keys))

    async def typed(name, *, org=ORG3, gid=None, override=None):
        pid = uuid.uuid4()
        async with maker() as db:
            await db.execute(text(
                "INSERT INTO players (id, organisation_id, name, grassroots_id, display_name_override) "
                "VALUES (:p, :o, :n, :g, :d)"),
                {"p": str(pid), "o": str(org), "n": name, "g": gid, "d": override})
            await db.commit()
        return pid

    async def held_by(pid):
        async with maker() as db:
            return (await db.execute(text("SELECT privacy_hidden_by FROM players WHERE id = :p"), {"p": str(pid)})).scalar()

    h1 = await typed("Trent Steenholdt")
    h2 = await typed("  steenholdt,   TRENT ")
    h3 = await typed("Trent S", override="Trent Steenholdt")
    check("'Trent Steenholdt' typed by hand is held hidden", await state(maker, h1) == (False, True))
    check("so is the same name in another order and case", await state(maker, h2) == (False, True))
    check("so is a row whose display name matches", await state(maker, h3) == (False, True))
    check("and it says it is a name hold, not his own request", await held_by(h1) == "name-match", str(await held_by(h1)))
    c_first = await typed("Pat Steenholdt")
    c_sur = await typed("Steenholdt")
    c_init = await typed("T. Steenholdt")
    c_long = await typed("Trent Steenholdt-Jones")
    c_other = await typed("Steenholdt, Trent", org=ORG1, gid=str(uuid.uuid4()))
    check("the same surname with another first name stays visible", await state(maker, c_first) == (True, False))
    check("a lone surname stays visible", await state(maker, c_sur) == (True, False))
    check("an initial and surname stays visible", await state(maker, c_init) == (True, False))
    check("a different, longer name stays visible", await state(maker, c_long) == (True, False))
    check("the same name with a DIFFERENT participant id stays visible (a different person)",
          await state(maker, c_other) == (True, False))

    print("\nA hand-typed player who is already there when somebody asks to be removed")
    ZED = uuid.UUID("bbbbbbbb-3333-4000-8000-000000000001")
    async with maker() as db:
        await db.execute(text("INSERT INTO players (id, organisation_id, name, grassroots_id) VALUES (:p, :o, 'Quinn, Zed', :g)"),
                         {"p": str(ZED), "o": str(ORG1), "g": str(ZED)})
        await db.commit()
    e1 = await typed("Zed Quinn")
    e_ctl = await typed("Pat Quinn")
    check("(setup) the namesake is visible before the request", await state(maker, e1) == (True, False))
    async with maker() as db:
        z = await db.get(Player, ZED)
        out = await player_privacy.hide_at_request(db, z, by="verifier", reason="privacy request")
        await db.commit()
    check("hiding him holds the existing namesake", await state(maker, e1) == (False, True)
          and out.get("name_matches_held") == 1, str(out.get("name_matches_held")))
    check("and leaves a different first name alone", await state(maker, e_ctl) == (True, False))

    print("\nHis names outlive his rows")
    YAN = uuid.UUID("bbbbbbbb-3333-4000-8000-000000000002")
    async with maker() as db:
        await db.execute(text("INSERT INTO players (id, organisation_id, name, grassroots_id) VALUES (:p, :o, 'Rowe, Yan', :g)"),
                         {"p": str(YAN), "o": str(ORG1), "g": str(YAN)})
        await db.commit()
    async with maker() as db:
        y = await db.get(Player, YAN)
        await player_privacy.hide_at_request(db, y, by="verifier", reason="privacy request")
        await db.commit()
    async with maker() as db:
        await db.execute(text("DELETE FROM players WHERE id = :p"), {"p": str(YAN)})
        await db.commit()
    y1 = await typed("Yan Rowe")
    check("with every row of his gone, a hand-typed 'Yan Rowe' is still held", await state(maker, y1) == (False, True))

    print("\nReleasing a name hold, and renaming")
    async with maker() as db:
        row = await db.get(Player, h1)
        try:
            await player_privacy.release_name_match(db, row, by="verifier")
        except AttributeError:
            pass  # the control has no release
        await db.commit()
    check("an admin confirming a different person puts the row back", await state(maker, h1) == (True, False))
    async with maker() as db:
        await db.execute(text("UPDATE players SET name = 'Trent  Steenholdt' WHERE id = :p"), {"p": str(h1)})
        await db.execute(text("UPDATE players SET is_public = TRUE WHERE id = :p"), {"p": str(h1)})
        await db.commit()
    check("and a later edit does not hold it again", await state(maker, h1) == (True, False))
    async with maker() as db:
        refused = False
        try:
            await player_privacy.release_name_match(db, await db.get(Player, TRENT), by="verifier")
        except ValueError:
            refused = True
        except AttributeError:
            pass  # the control has no release
    check("his OWN request cannot be released this way", refused and await state(maker, TRENT) == (False, True))
    async with maker() as db:
        await db.execute(text("UPDATE players SET name = 'Someone Else' WHERE id = :p"), {"p": str(h2)})
        await db.commit()
    check("renaming a held row to a different name lets it go", await state(maker, h2) == (True, False))
    async with maker() as db:
        await db.execute(text("UPDATE players SET name = 'Trent Steenholdt' WHERE id = :p"), {"p": str(h2)})
        await db.commit()
    check("renaming it onto his name holds it again", await state(maker, h2) == (False, True))
    club_hidden = await typed("Lee Smith")
    async with maker() as db:
        await db.execute(text("UPDATE players SET is_public = FALSE WHERE id = :p"), {"p": str(club_hidden)})
        await db.execute(text("UPDATE players SET name = 'Lee Smythe' WHERE id = :p"), {"p": str(club_hidden)})
        await db.commit()
    check("a row the CLUB hid is never un-hidden by a rename", (await state(maker, club_hidden))[0] is False)

    print("\nA suppression recorded before names were kept")
    try:
        async with maker() as db:
            await db.execute(text("UPDATE player_privacy_suppressions SET names = NULL WHERE grassroots_id = :g"), {"g": str(TRENT)})
            await db.commit()
    except Exception:
        pass  # the control has no names column
    async with engine.begin() as conn:
        for st in PRIVACY_DDL:
            await conn.execute(text(st))
    keys = await names_of(maker, TRENT)
    check("a boot fills his names back in from his own rows", "steenholdt trent" in (keys or []), str(keys))

    print("\nPutting him back on request still works")
    async with maker() as db:
        t = await db.get(Player, TRENT)
        await player_privacy.restore_public(db, t, by="verifier")
        await db.commit()
    check("restore brings his rows back, at every club", await state(maker, TRENT) == (True, False)
          and await state(maker, new_id) == (True, False) and await state(maker, raw_id) == (True, False))
    check("his name-matched namesakes are let go with him", await state(maker, h2) == (True, False)
          and await state(maker, h3) == (True, False), str(await state(maker, h2)))
    async with maker() as db:
        t = await db.get(Player, TRENT)
        await player_privacy.hide_at_request(db, t, by="verifier", reason="privacy request")
        await db.commit()
    check("and hiding him again works", await state(maker, TRENT) == (False, True)
          and await state(maker, raw_id) == (False, True))
    check("and holds his namesakes again", await state(maker, h2) == (False, True))

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
