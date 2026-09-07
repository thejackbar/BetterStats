"""A merge must move a player's record, never delete it.

Reported off Brad Quinsee's profile: merging his duplicate dropped roughly
half his career. `_merge_players_core` was written for the SYNCED per-game
tables and never touched the MANUAL ones — where an uploaded scorecard, and
every match a CricketStatz import writes, actually live. All of them are
`ON DELETE CASCADE` on `players.id`, so removing the merged-away player
deleted the record outright, with nothing in the undo log to hand back.

Runs the SHIPPED `_merge_players_core` and `undo_merge` bodies against a real
Postgres. Nothing here is a replay of their logic.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base
from app.routers.admin import _merge_players_core, undo_merge, UndoMergeRequest
from app.services import merge_carry
from app.services import cricketstatz_import as importer

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres@/bettercricket?host=/tmp&port=5599",
)
PASS, FAIL = [], []

# Lifespan-created in raw SQL, so the ORM's create_all never makes them. Kept
# in the same shape main.py builds — a harness table that merely looks right
# is worse than none.
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

ORG = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
KEEP = uuid.UUID("aaaaaaaa-0000-4000-8000-00000000000a")
REMOVE = uuid.UUID("aaaaaaaa-0000-4000-8000-00000000000b")


class FakeUser:
    id = uuid.UUID("aaaaaaaa-0000-4000-8000-0000000000ff")
    username = "verifier"


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not ok else ""))



# ── the rule, enforced rather than written down ──────────────────────────────
#
# NEVER REMOVE A GAME A CLUB ENTERED BY HAND. Typing a scorecard in costs a
# club hours, and there is no upstream to re-pull it from. Every place in the
# codebase that can delete a manual game or its children is listed below with
# the reason it is allowed to; anything not on the list fails this check, so a
# new one cannot be added without somebody saying why.
ALLOWED_DELETES = {
    # The manual-game editor replacing a game's own rows as it saves it — that
    # IS the person's edit, not a loss.
    ("app/routers/manual_entries.py", "the editor replacing a game it is saving"),
    # Restoring a snapshot on undo: the rows going in are the ones coming back.
    ("app/routers/manual_entries.py", "undo putting a snapshot back"),
    # Undoing an import removes what that import wrote, scoped by its own id;
    # and a re-import taking back a duplicate of a match the club already holds
    # from the sync — its own copy, never a hand-typed one (a game somebody has
    # edited is checked first and left standing).
    ("app/services/cricketstatz_import.py", "an import undoing its own work"),
}
ALLOWED_FILES = {f for f, _ in ALLOWED_DELETES}

DELETE_PATTERN = re.compile(
    r"DELETE\s+FROM\s+(manual_\w+)|sa_delete\(\s*(Manual\w+)", re.I)


def verify_no_new_delete_sites() -> None:
    print("\nNothing new may delete a manually entered game")
    root = Path(__file__).resolve().parent.parent / "app"
    offenders = []
    sites = 0
    for path in sorted(root.rglob("*.py")):
        rel = str(path.relative_to(root.parent))
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if not DELETE_PATTERN.search(line):
                continue
            sites += 1
            if rel not in ALLOWED_FILES:
                offenders.append(f"{rel}:{lineno}")
    check("every place that deletes a manual row is one we have justified",
          not offenders,
          "unlisted: " + ", ".join(offenders) if offenders else "")
    check("and the list is not empty, so the search itself still works",
          sites >= 8, str(sites))

    # The merge is the one that got this wrong: it deleted rather than moved.
    # Every manual table has to be on the carry list or the next merge loses it.
    models = (root / "models" / "db.py").read_text()
    manual_tables = set(re.findall(r'__tablename__\s*=\s*["\'](manual_\w+)', models))
    # `manual_games` itself hangs off the ORGANISATION, not a player, so a merge
    # never reaches it; `manual_edit_logs` is the audit trail.
    manual_tables -= {"manual_games", "manual_edit_logs"}
    carried = {t for t, _c, _i, _u in merge_carry.CARRIED}
    player_linked = set()
    for table in manual_tables:
        block = models[models.index(f'"{table}"'):]
        block = block[:block.find("class ", 10)] if "class " in block[10:] else block[:2000]
        if 'ForeignKey("players.id"' in block:
            player_linked.add(table)
    missing = sorted(player_linked - carried)
    # A vacuous pass is the failure mode here: if the scan found no
    # player-linked manual table at all, "none are missing" is trivially true.
    check("the scan finds the manual tables that point at a player",
          len(player_linked) >= 8, f"{len(player_linked)}: {sorted(player_linked)}")
    check("every manual table that points at a player is carried by a merge",
          not missing, ", ".join(missing))


async def seed(db) -> dict:
    """The reported shape: one person held twice, each carrying half a career.

    Every match is a MANUAL game, which is what a CricketStatz import writes
    and what an uploaded scorecard writes.
    """
    await db.execute(text("""
        INSERT INTO organisations (id, name, slug, is_active)
        VALUES (:o, 'Keon Park Cricket Club', 'keon-park', true)
    """), {"o": str(ORG)})
    season = uuid.uuid4()
    await db.execute(text("""
        INSERT INTO seasons (id, organisation_id, name, year)
        VALUES (:s, :o, 'Summer 1982/83', 1982)
    """), {"s": str(season), "o": str(ORG)})
    await db.execute(text("""
        INSERT INTO players (id, organisation_id, name, cricketstatz_player_id) VALUES
            (:k, :o, 'Quinsee, Brad', NULL),
            (:r, :o, 'Brad Quinsee', '3337518')
    """), {"k": str(KEEP), "r": str(REMOVE), "o": str(ORG)})

    games = []
    for idx in range(6):
        gid = uuid.uuid4()
        games.append(gid)
        await db.execute(text("""
            INSERT INTO manual_games (id, organisation_id, season_id, played_at,
                                      opposition)
            VALUES (:g, :o, :s, CAST(:d AS date), 'Montmorency')
        """), {"g": str(gid), "o": str(ORG), "s": str(season),
               "d": date(1982 + idx % 5, 11, idx + 1)})

    # Two games the club's own record holds, four the imported one does.
    owners = [KEEP, KEEP, REMOVE, REMOVE, REMOVE, REMOVE]
    for gid, owner in zip(games, owners):
        await db.execute(text("""
            INSERT INTO manual_batting_innings
                (manual_game_id, player_id, innings_number, batting_position, runs, balls)
            VALUES (:g, :p, 1, 3, 50, 60)
        """), {"g": str(gid), "p": str(owner)})
        await db.execute(text("""
            INSERT INTO manual_bowling_spells
                (manual_game_id, player_id, innings_number, overs, maidens, runs, wickets)
            VALUES (:g, :p, 2, 10, 2, 30, 3)
        """), {"g": str(gid), "p": str(owner)})
        await db.execute(text("""
            INSERT INTO manual_fielding_stats (manual_game_id, player_id, catches)
            VALUES (:g, :p, 1)
        """), {"g": str(gid), "p": str(owner)})

    # A game BOTH records hold a row for — the same physical innings, read
    # under two identities. The keeper's row must win; the removed one's is a
    # duplicate, not a second innings.
    clash = games[0]
    await db.execute(text("""
        INSERT INTO manual_batting_innings
            (manual_game_id, player_id, innings_number, batting_position, runs, balls)
        VALUES (:g, :p, 1, 3, 50, 60)
    """), {"g": str(clash), "p": str(REMOVE)})
    await db.execute(text("""
        INSERT INTO manual_fielding_stats (manual_game_id, player_id, catches)
        VALUES (:g, :p, 1)
    """), {"g": str(clash), "p": str(REMOVE)})

    # A hand-typed correction and an honour, both on the removed record.
    await db.execute(text("""
        INSERT INTO manual_season_adjustments
            (player_id, season_id, organisation_id, games_played, batting_runs)
        VALUES (:p, :s, :o, 2, 40)
    """), {"p": str(REMOVE), "s": str(season), "o": str(ORG)})
    await db.execute(text("""
        INSERT INTO manual_career_adjustments
            (player_id, organisation_id, games_played)
        VALUES (:p, :o, 5)
    """), {"p": str(REMOVE), "o": str(ORG)})
    await db.execute(text("""
        INSERT INTO player_achievements
            (org_id, player_id, player_name, season, category, subcategory,
             achievement)
        VALUES (:o, :p, 'Brad Quinsee', '1992/93', 'Life Membership', 'Club',
                'Life Membership')
    """), {"o": str(ORG), "p": str(REMOVE)})
    await db.commit()
    return {"season": season, "games": games}



async def verify_hand_edit_guard(session_maker) -> None:
    """A re-import must not write over a match somebody has worked on by hand."""
    print("\nA hand-edited match is never written over")
    org = uuid.uuid4()
    season = uuid.uuid4()
    imported, edited = uuid.uuid4(), uuid.uuid4()
    async with session_maker() as db:
        await db.execute(text("""
            INSERT INTO organisations (id, name, slug, is_active)
            VALUES (:o, 'Edited CC', 'edited-cc', true)
        """), {"o": str(org)})
        await db.execute(text("""
            INSERT INTO seasons (id, organisation_id, name, year)
            VALUES (:s, :o, 'Summer 2001/02', 2001)
        """), {"s": str(season), "o": str(org)})
        for gid, match in ((imported, "900001"), (edited, "900002")):
            await db.execute(text("""
                INSERT INTO manual_games (id, organisation_id, season_id, played_at,
                                          opposition, cricketstatz_match_id)
                VALUES (:g, :o, :s, CAST('2001-11-03' AS date), 'Lalor', :m)
            """), {"g": str(gid), "o": str(org), "s": str(season), "m": match})
        # Somebody corrected the second one through Manual Entries.
        await db.execute(text("""
            INSERT INTO manual_edit_logs
                (organisation_id, action, target_table, target_id, summary)
            VALUES (:o, 'update', 'manual_games', :t, 'fixed the opposition')
        """), {"o": str(org), "t": str(edited)})
        # And an edit on the first one that was later taken back.
        await db.execute(text("""
            INSERT INTO manual_edit_logs
                (organisation_id, action, target_table, target_id, summary, undone_at)
            VALUES (:o, 'update', 'manual_games', :t, 'reverted', NOW())
        """), {"o": str(org), "t": str(imported)})
        await db.commit()

    async with session_maker() as db:
        touched = await importer.hand_edited_games(db, org)
    check("a match somebody edited is recognised as theirs",
          str(edited) in touched, str(touched))
    check("an edit that was undone does not count — they took it back",
          str(imported) not in touched, str(touched))

    caches = {"seasons": {}, "grades": {}, "players": {}, "roster": None,
              "near_matches": {}, "hand_edited": touched,
              "season_label": "Summer 2001/02", "season_value": "2001S"}
    card = {"source_match_id": "900002", "date": "2001-11-03",
            "home_team": "Edited CC", "away_team": "Somebody Else",
            "venue": "Elsewhere", "result": "Match Drawn", "innings": []}
    row = {"source_match_id": "900002", "division": "A-GRADE",
           "round": "03", "date": "2001-11-03"}
    async with session_maker() as db:
        note = await importer.import_match(
            db, org, uuid.uuid4(), card, row, lambda n: "Edited" in (n or ""), caches)
        await db.commit()
    check("the import leaves it alone and says so",
          bool(note) and "edited by hand" in note, str(note))
    async with session_maker() as db:
        after = (await db.execute(text(
            "SELECT opposition, venue FROM manual_games WHERE id = :g"),
            {"g": str(edited)})).mappings().first()
    check("their own figures are exactly as they left them",
          after["opposition"] == "Lalor" and after["venue"] is None, str(dict(after)))

    # The one nobody has touched is refreshed as normal, which is what makes a
    # re-import the recovery path for a club that has lost rows.
    card["source_match_id"] = "900001"
    row["source_match_id"] = "900001"
    async with session_maker() as db:
        note = await importer.import_match(
            db, org, uuid.uuid4(), card, row, lambda n: "Edited" in (n or ""), caches)
        await db.commit()
    check("a match nobody has touched is still refreshed", note is None, str(note))
    async with session_maker() as db:
        after = (await db.execute(text(
            "SELECT venue FROM manual_games WHERE id = :g"),
            {"g": str(imported)})).mappings().first()
    check("so a re-import can put back what was lost",
          after["venue"] == "Elsewhere", str(dict(after)))


async def counts(db, player_id) -> dict:
    out = {}
    for table, column in (("manual_batting_innings", "player_id"),
                          ("manual_bowling_spells", "player_id"),
                          ("manual_fielding_stats", "player_id"),
                          ("manual_season_adjustments", "player_id"),
                          ("manual_career_adjustments", "player_id"),
                          ("player_achievements", "player_id")):
        out[table] = (await db.execute(text(
            f"SELECT COUNT(*) FROM {table} WHERE {column} = :p"),
            {"p": str(player_id)})).scalar()
    return out


async def main() -> int:
    engine = create_async_engine(DB_URL, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for statement in EXTRA_DDL:
            await conn.execute(text(statement))

    verify_no_new_delete_sites()

    print("\nThe reported case: merging a duplicate must not lose a career")
    async with session_maker() as db:
        await seed(db)
        before_keep = await counts(db, KEEP)
        before_remove = await counts(db, REMOVE)
    check("the club holds the person twice, each with part of the career",
          before_keep["manual_batting_innings"] == 2
          and before_remove["manual_batting_innings"] == 5,
          f"{before_keep} / {before_remove}")

    async with session_maker() as db:
        total_before = (await db.execute(text(
            "SELECT COUNT(*) FROM manual_batting_innings"))).scalar()
        result = await _merge_players_core(db, KEEP, REMOVE, ORG, FakeUser())

    async with session_maker() as db:
        after = await counts(db, KEEP)
        gone = (await db.execute(text(
            "SELECT COUNT(*) FROM players WHERE id = :p"), {"p": str(REMOVE)})).scalar()
    check("the duplicate record is gone", gone == 0)
    async with session_maker() as db:
        total_after = (await db.execute(text(
            "SELECT COUNT(*) FROM manual_batting_innings"))).scalar()
    # 7 rows, less the one both records held. A merge drops a duplicate; it
    # must never delete an innings only one of them had.
    check("no innings was destroyed by the merge",
          total_after == total_before - 1, f"{total_before} -> {total_after}")
    # 2 the keeper held + 5 the removed one held, less the 1 they both held.
    check("every innings the removed record held is now the keeper's",
          after["manual_batting_innings"] == 6, str(after))
    check("its bowling came across too", after["manual_bowling_spells"] == 6, str(after))
    check("and its fielding", after["manual_fielding_stats"] == 6, str(after))
    check("an innings both records held is kept once, not twice",
          after["manual_batting_innings"] == 6 and after["manual_fielding_stats"] == 6,
          str(after))
    check("a hand-typed season correction is not destroyed",
          after["manual_season_adjustments"] == 1, str(after))
    check("nor a career one", after["manual_career_adjustments"] == 1, str(after))
    check("the honour board follows the person",
          after["player_achievements"] == 1, str(after))
    check("the merge reports what it carried",
          (result.get("carried") or {}).get("manual_batting_innings") == 4,
          str(result.get("carried")))
    check("the import's own identity moves onto the record that is kept",
          (await _cs_id(session_maker, KEEP)) == "3337518")

    async with session_maker() as db:
        log = (await db.execute(text(
            "SELECT id, carried_row_ids FROM merge_logs WHERE org_id = :o"),
            {"o": str(ORG)})).mappings().first()
    check("the merge log records exactly which rows moved",
          log is not None and len(log["carried_row_ids"] or {}) >= 6,
          str(log and list((log["carried_row_ids"] or {}).keys())))

    print("\nThe list of tables a merge has to carry")
    async with session_maker() as db:
        missed = []
        for table, column, _t, _u in merge_carry.CARRIED:
            present = (await db.execute(text("SELECT to_regclass(:t)"),
                                        {"t": table})).scalar()
            if present is None:
                continue
            left = (await db.execute(text(
                f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL "
                f"  AND NOT EXISTS (SELECT 1 FROM players p WHERE p.id = {table}.{column})"
            ))).scalar()
            if left:
                missed.append(f"{table}.{column}={left}")
    check("no carried row is left pointing at a player who no longer exists",
          not missed, ", ".join(missed))

    print("\nUndo hands them back")
    async with session_maker() as db:
        await undo_merge(UndoMergeRequest(merge_log_id=log["id"], org_id=str(ORG)),
                         db=db, current_user=FakeUser())
    async with session_maker() as db:
        back_keep = await counts(db, KEEP)
        back_remove = await counts(db, REMOVE)
    check("the removed record is back", (await _exists_player(session_maker, REMOVE)))
    check("with the innings it held before the merge",
          back_remove["manual_batting_innings"] == 4, str(back_remove))
    check("and the keeper keeps its own",
          back_keep["manual_batting_innings"] == 2, str(back_keep))
    check("the correction goes back with it",
          back_remove["manual_season_adjustments"] == 1, str(back_remove))
    check("so does the honour",
          back_remove["player_achievements"] == 1
          and back_keep["player_achievements"] == 0, str(back_keep))
    check("and the import's identity",
          (await _cs_id(session_maker, REMOVE)) == "3337518"
          and (await _cs_id(session_maker, KEEP)) is None)
    # The one row both records held was a genuine duplicate and was dropped, so
    # the undo cannot invent it back. Say so rather than pretend otherwise.
    check("a duplicate dropped as a duplicate stays dropped",
          back_keep["manual_batting_innings"] + back_remove["manual_batting_innings"] == 6,
          f"{back_keep} / {back_remove}")


    await verify_hand_edit_guard(session_maker)

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for name in FAIL:
        print(f"  FAILED: {name}")
    return 1 if FAIL else 0


async def _cs_id(session_maker, player_id):
    async with session_maker() as db:
        return (await db.execute(text(
            "SELECT cricketstatz_player_id FROM players WHERE id = :p"),
            {"p": str(player_id)})).scalar()


async def _exists_player(session_maker, player_id) -> bool:
    async with session_maker() as db:
        return bool((await db.execute(text(
            "SELECT 1 FROM players WHERE id = :p"), {"p": str(player_id)})).scalar())


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
