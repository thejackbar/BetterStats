"""A NEW club's first sync writes its premierships, and an existing club heals on its next sync. Real Postgres.

Asked: will a club that syncs for the first time get the automatic premierships without anybody running a
backfill, and will a club that already synced before round names were stored get them too?

Drives `sync.sync_organisation` itself (the one gate every caller goes through: the nightly full and
incremental runs, Sync Now, the self-serve trial and onboarding sync, Full Rebuild), with Cricket
Australia stubbed to return a match list and scorecards. Only `_sync_organisation_impl`'s season and
grade discovery is replaced, by the game-level phase it ends in, so the wrapper's own post-sync steps run
for real. The club starts with its players, season and grade and NO games, as sync's earlier phases leave
a new club. The grade holds four games the club WON or LOST:

  GF_WIN    Grand Final, won     -> everybody on the sheet gets the Premiership, linked to this game
  GF_LOSS   Grand Final, lost    -> nothing
  SEMI_WIN  Semi Final, won      -> nothing (a final, but not the decider)
  RD_WIN    Round 3, won         -> nothing

  FIRST SYNC   round names stored, honours written, all of it from the sync alone
  SECOND SYNC  nothing added, nothing doubled
  EXISTING     a club synced before round names existed (round_name NULL, no honours): an ordinary
               sync stores the names on the games it rediscovers and writes the honours

CONTROL MODE. Run against the commit BEFORE this change, `games.round_name` does not exist, so the
stored-name and honour checks fail (nothing crashes: absence is read through presence-safe queries).

Run:  DATABASE_URL=postgresql+asyncpg://root@/newclub_prem?host=/var/run/postgresql \
      python verification/verify_new_club_premiership_sync.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

import verify_reread_incomplete_game as h   # its engine, schema and match listing helpers; main() is guarded
from app.services import grassroots_scores_client as gr
from app.services import sync

check = h.check
Session = h.Session

NAMES = ["Payne", "Hall", "Bivens", "Sweet"]
PID = {n: uuid.uuid4() for n in NAMES}
GF_WIN, GF_LOSS, SEMI_WIN, RD_WIN = (uuid.uuid4() for _ in range(4))
ROUND = {GF_WIN: "Grand Final", GF_LOSS: "Grand Final", SEMI_WIN: "Semi Final", RD_WIN: "Round 3"}
WON = {GF_WIN: True, GF_LOSS: False, SEMI_WIN: True, RD_WIN: True}
DAYS = {GF_WIN: 8, GF_LOSS: 9, SEMI_WIN: 15, RD_WIN: 30}


def card(game_id):
    iso = (h.TODAY - timedelta(days=DAYS[game_id])).isoformat() + "T10:00:00Z"
    ours, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    won = WON[game_id]
    return {
        "id": str(game_id), "matchSchedule": [{"startDateTime": iso}], "venue": {"name": "Oval"},
        "status": "COMPLETED", "grade": {"id": h.GRADE_GUID, "name": "1st Grade"},
        "teams": [
            {"id": ours, "displayName": "New Club 1st", "owningOrganisation": {"id": str(h.ORG)},
             "players": [{"participantId": str(p), "roles": []} for p in PID.values()]},
            {"id": theirs, "displayName": "Them 1st", "owningOrganisation": {"id": str(h.OPP_ORG)}, "players": []},
        ],
        "matchSummary": {"resultText": "New Club won" if won else "Them won",
                         "teams": [{"id": ours, "displayName": "New Club 1st", "isHome": True,
                                    "isWinner": won, "resultType": "WON" if won else "LOST"},
                                   {"id": theirs, "displayName": "Them 1st", "isHome": False,
                                    "isWinner": not won, "resultType": "LOST" if won else "WON"}]},
        "innings": [{
            "inningsOrder": 1, "battingTeamId": ours, "fielding": [], "bowling": [],
            "batting": [{"participantId": str(PID[n]), "batOrder": i, "dismissalTypeId": 2, "dismissalType": "Bowled",
                         "runsScored": 10 + i, "ballsFaced": 20, "playerShortName": n}
                        for i, n in enumerate(NAMES, 1)],
        }],
    }


def entry(game_id):
    e = h.match_entry(game_id, DAYS[game_id])
    e["round"] = {"name": ROUND[game_id]}
    return e


async def seed_new_club() -> None:
    """A club that has never synced a game: players, a season and a grade, and nothing else."""
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)
        for oid, nm, slug in ((h.ORG, "New Club", "new-club"), (h.OPP_ORG, "Them CC", "them")):
            await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)", i=oid, n=nm, s=slug)
        await ex("INSERT INTO seasons (id, organisation_id, name, year, grassroots_id) "
                 "VALUES (:i, :o, 'Summer 2026/27', 2026, :g)", i=h.SEASON, o=h.ORG, g=str(h.SEASON))
        await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                 "VALUES (:i, :s, '1st Grade', :g, 'senior', ARRAY['senior'])", i=h.GRADE, s=h.SEASON, g=h.GRADE_GUID)
        for n, pid in PID.items():
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                     "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=h.ORG, n=n, g=str(pid))
        await s.commit()


async def round_names() -> dict:
    """{game id: round_name}, or {} where the column does not exist (the control commit)."""
    async with Session() as s:
        try:
            rows = (await s.execute(text("SELECT id, round_name FROM games"))).all()
        except Exception:
            await s.rollback()
            return {}
    return {r[0]: r[1] for r in rows}


async def honours() -> list[dict]:
    async with Session() as s:
        try:
            rows = (await s.execute(text(
                "SELECT player_id, subcategory, achievement, linked_game_id, auto_created "
                "FROM player_achievements WHERE category = 'Premiership'"))).mappings().all()
        except Exception:
            await s.rollback()
            return []
    return [dict(r) for r in rows]


async def main() -> None:
    await h.build_schema()
    async with h.engine.begin() as conn:
        # The lifespan's own raw-SQL tables this path reads, column for column (rule 24).
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_achievements (
                id SERIAL PRIMARY KEY, org_id UUID NOT NULL, player_id UUID, player_name TEXT NOT NULL,
                season TEXT, category TEXT NOT NULL, subcategory TEXT, achievement TEXT NOT NULL,
                detail TEXT, created_at TIMESTAMPTZ DEFAULT NOW())"""))
        await conn.execute(text("ALTER TABLE player_achievements ADD COLUMN IF NOT EXISTS season_end TEXT"))
        await conn.execute(text("ALTER TABLE player_achievements ADD COLUMN IF NOT EXISTS import_batch_id UUID"))
        await conn.execute(text("ALTER TABLE player_achievements ADD COLUMN IF NOT EXISTS club_role_id UUID"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL,
                canonical_name TEXT NOT NULL, alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)"""))
        try:
            from app.services.premierships_ddl import STATEMENTS
        except ImportError:   # the control commit
            STATEMENTS = []
        for stmt in STATEMENTS:
            await conn.execute(text(stmt))
        from app.services.fow_override_ddl import STATEMENTS as FOW_DDL   # migration 357, as the lifespan makes it
        for stmt in FOW_DDL:
            await conn.execute(text(stmt))
    await seed_new_club()

    cards = {str(g): card(g) for g in ROUND}
    listing = [entry(g) for g in ROUND]

    async def fake_matches(grade_guid, *a, **k):
        return listing

    async def fake_card(match_id, *a, **k):
        return cards.get(str(match_id))

    gr.get_grade_matches = fake_matches
    gr.get_match_scorecard = fake_card

    # The season and grade discovery that precedes the game-level phase is not what is under test: swap the
    # impl for that phase alone, so `sync_organisation`'s own steps after it (the premierships among them) run.
    async def impl(org_id_str, run_id=None, kind="org_full", since=None):
        await sync.sync_grassroots_game_level_data(org_id_str)
        return {}

    sync._sync_organisation_impl = impl

    print("\n-- BEFORE: a new club with no games --")
    async with Session() as s:
        check("nothing is stored for the club yet", (await s.execute(text("SELECT count(*) FROM games"))).scalar() == 0)
    check("and no honours", await honours() == [])

    print("\n-- ITS FIRST SYNC (sync_organisation, as every caller runs it) --")
    await sync.sync_organisation(str(h.ORG), kind="org_full")
    async with Session() as s:
        games = (await s.execute(text("SELECT count(*) FROM games"))).scalar()
    check("all four games are stored", games == 4, str(games))
    names = await round_names()
    check("each game's round name is stored from the match list",
          {g: names.get(g) for g in ROUND} == ROUND, str(names))
    rows = await honours()
    squad = {r["player_id"] for r in rows if r["linked_game_id"] == GF_WIN}
    check("the grand final win gives the Premiership to everybody on the sheet",
          squad == set(PID.values()), f"{len(squad)} of {len(PID)}")
    check("the honours are the automatic kind, for the grade, linked to the grand final",
          bool(rows) and all(r["auto_created"] and r["subcategory"] == "1st Grade" and r["achievement"] == "Premiership"
                             for r in rows), str(rows[:1]))
    check("and nothing else earns one: not the lost final, the semi or a round game",
          {r["linked_game_id"] for r in rows} == {GF_WIN} and len(rows) == len(PID),
          str({str(r["linked_game_id"])[:6] for r in rows}))

    print("\n-- A SECOND SYNC --")
    await sync.sync_organisation(str(h.ORG), kind="org_full")
    check("adds nothing and doubles nothing", len(await honours()) == len(PID))

    print("\n-- AN EXISTING CLUB: synced before round names, no honours --")
    async with Session() as s:
        try:
            await s.execute(text("UPDATE games SET round_name = NULL"))
        except Exception:
            await s.rollback()
        await s.execute(text("DELETE FROM player_achievements"))
        await s.commit()
    check("starting state: names blank, honours gone", set((await round_names()).values()) <= {None} and await honours() == [])
    await sync.sync_organisation(str(h.ORG), kind="org_full")
    names = await round_names()
    check("an ordinary sync stores the names on games it rediscovers (already stored, so no per-game block)",
          {g: names.get(g) for g in ROUND} == ROUND, str(names))
    rows = await honours()
    check("and writes the honours", {r["player_id"] for r in rows if r["linked_game_id"] == GF_WIN} == set(PID.values()))

    print("\n-- AN INCREMENTAL RUN (the nightly one) --")
    await sync.sync_organisation(str(h.ORG), kind="org_recent")
    check("is the same path and changes nothing", len(await honours()) == len(PID))

    print(f"\n{h.PASS} passed, {h.FAIL} failed")
    await h.engine.dispose()
    sys.exit(1 if h.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
