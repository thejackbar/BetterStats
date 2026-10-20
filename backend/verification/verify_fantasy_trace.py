"""Verification: the Fantasy player trace names the filter that drops a game. Real Postgres.

Reported (Scarborough): players who had played were on 0 and nobody could say why from
outside. `fantasy_pool_check.trace_player` follows one player through the same filters
the scoring engine applies and reports, per game, the first one it fails.

Runs the SHIPPED `trace_player` and `zero_stat_pool_players`.

Run:  DATABASE_URL=postgresql+asyncpg://root@/fantasy_test?host=/var/run/postgresql \
      python verification/verify_fantasy_trace.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import text

import verify_fantasy_unsettle as base
from app.models.db import Player, Game, Grade, BattingInnings, GameAppearance, ManualGame, ManualBattingInnings
from app.services import fantasy_pool_check as chk
from app.services.club_grades import club_grade_rows

Session, check = base.Session, base.check
ORG, FS_ID, TODAY = base.ORG, base.FS_ID, base.TODAY
D1, D2, D1B, T_OK, T_NOROUND, T_OFF, Q, IMP, HID = (uuid.uuid4() for _ in range(9))


async def verdict_for(term: str, name: str) -> list[dict]:
    async with Session() as s:
        t = await chk.trace_player(s, ORG, term)
        await s.rollback()
    p = next(p for p in t["players"] if p["name"] == name)
    return p["games"]


async def main() -> int:
    await base.build_schema()
    async with base.engine.begin() as conn:
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS grade_merge_logs (
            id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL,
            canonical_name TEXT NOT NULL, alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)"""))
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS merge_logs (
            id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID, keep_player_id UUID, keep_player_name TEXT,
            removed_player_id UUID, removed_player_name TEXT, undone_at TIMESTAMPTZ)"""))
    # The pairing rule lives in superseded_ddl (re-applied on every boot), not in a migration,
    # so the base harness views do not carry it: apply what the app runs.
    from app.services.superseded_ddl import STATEMENTS as SUPERSEDED
    async with base.engine.begin() as conn:
        for stmt in SUPERSEDED:
            await conn.execute(text(stmt))
    await base.seed()
    async with Session() as s:
        own_grade = (await s.execute(text("SELECT id, season_id FROM grades LIMIT 1"))).first()
        seconds = uuid.uuid4()
        s.add(Grade(id=seconds, season_id=own_grade[1], name="Seconds", grassroots_id="g2"))
        s.add_all([Player(id=T_OK, name="Counting Carl", organisation_id=ORG, grassroots_id="c1"),
                   Player(id=T_NOROUND, name="Gap Gary", organisation_id=ORG, grassroots_id="c2"),
                   Player(id=T_OFF, name="Off Oscar", organisation_id=ORG, grassroots_id="c3"),
                   Player(id=D1, name="Gardner, David", organisation_id=ORG, grassroots_id="d1"),
                   Player(id=D2, name="David Gardner", organisation_id=ORG),
                   Player(id=Q, name="Quiet Quinn", organisation_id=ORG, grassroots_id="q1"),
                   Player(id=IMP, name="Imported Ivan", organisation_id=ORG, grassroots_id="i1"),
                   Player(id=HID, name="Hidden Hank", organisation_id=ORG, grassroots_id="h1")])
        await s.flush()

        async def game(gid, days, grade, players):
            s.add(Game(id=gid, grade_id=grade, played_at=TODAY - timedelta(days=days), home_team="A", away_team="B", home_org_id=ORG, status="COMPLETED"))
            await s.flush()
            for pid in players:
                s.add(GameAppearance(game_id=gid, player_id=pid, team_name="A"))
                s.add(BattingInnings(game_id=gid, player_id=pid, innings_number=1, runs=20, balls=20, fours=0, sixes=0, dismissal_type="bowled", not_out=False))
        await game(uuid.uuid4(), 3, own_grade[0], [T_OK, D1])            # inside round 2's window, a grade that counts
        await game(uuid.uuid4(), 100, own_grade[0], [T_NOROUND])         # no round covers it
        await game(uuid.uuid4(), 3, seconds, [T_OFF])                    # a grade that will be switched off
        # An imported (manual) match: its rows live in manual_batting_innings, not in
        # batting_innings, so a trace that only read the synced tables found no game.
        manual_gid = uuid.uuid4()
        s.add(ManualGame(id=manual_gid, organisation_id=ORG, season_id=own_grade[1], grade_id=own_grade[0],
                         played_at=TODAY - timedelta(days=3), home_team="A", away_team="B"))
        await s.flush()
        s.add(ManualBattingInnings(manual_game_id=manual_gid, innings_number=1, player_id=IMP, runs=40, balls=30,
                                   fours=0, sixes=0, dismissal_type="bowled", not_out=False))
        # A synced game paired to an imported twin that is preferred: the synced rows
        # stop counting, and that is the one place a played game can score nothing.
        paired_gid, twin_gid = uuid.uuid4(), uuid.uuid4()
        await game(paired_gid, 3, own_grade[0], [HID])
        s.add(ManualGame(id=twin_gid, organisation_id=ORG, season_id=own_grade[1], grade_id=own_grade[0],
                         played_at=TODAY - timedelta(days=3), home_team="A", away_team="B"))
        await s.flush()
        await s.execute(text("UPDATE manual_games SET superseded_by_game_id = :g, pair_prefers_import = TRUE WHERE id = :m"),
                        {"g": paired_gid, "m": twin_gid})
        for pid in (T_OK, T_NOROUND, T_OFF, D1, D2, Q, IMP, HID):
            s.add(base.FantasyPoolPlayer(fantasy_season_id=FS_ID, organisation_id=ORG, player_id=pid, role="batter", role_source="admin", base_price=5, current_price=5))
        await s.commit()
        rows = await club_grade_rows(s, ORG)
        seconds_key = next(c.key for c in rows if str(c.id) == str(seconds))
        await s.execute(text("UPDATE fantasy_seasons SET rules = jsonb_set(COALESCE(rules,'{}'::jsonb), '{excluded_grade_keys}', CAST(:k AS jsonb)) WHERE id=:f"),
                        {"k": f'["{seconds_key}"]', "f": FS_ID})
        await s.commit()

    print("1. Each reason is named")
    g = await verdict_for("Counting Carl", "Counting Carl")
    check("a game that is the club's, in the year, in a counted grade and inside a round counts", len(g) == 1 and g[0]["verdict"] == "counts" and g[0]["round"] == 2, repr(g))
    g = await verdict_for("Gap Gary", "Gap Gary")
    check("a game no round covers says so", len(g) == 1 and "no round covers" in g[0]["verdict"], repr(g))
    g = await verdict_for("Off Oscar", "Off Oscar")
    check("a game in a switched-off grade says so, naming the grade", len(g) == 1 and "switched off" in g[0]["verdict"] and "Seconds" in g[0]["verdict"], repr(g))

    print("2. Two records with the same name are both found, however the name is written")
    async with Session() as s:
        t = await chk.trace_player(s, ORG, "david gardner")
        await s.rollback()
    names = sorted(p["name"] for p in t["players"])
    check("'David Gardner' finds both 'Gardner, David' and 'David Gardner'", names == ["David Gardner", "Gardner, David"], repr(names))
    by = {p["name"]: p for p in t["players"]}
    check("it shows which one has games and which has none", len(by["Gardner, David"]["games"]) == 1 and by["David Gardner"]["games"] == [], repr({k: len(v["games"]) for k, v in by.items()}))
    check("and their ids, so a duplicate can be told apart", by["Gardner, David"]["grassroots_id"] == "d1" and by["David Gardner"]["grassroots_id"] is None)
    async with Session() as s:
        by_id = await chk.trace_player(s, ORG, str(D1))
        await s.rollback()
    check("a player id finds exactly that record", [p["name"] for p in by_id["players"]] == ["Gardner, David"], repr(by_id["players"]))

    print("3. 'Added by hand' means no Cricket Australia id, not 'an admin changed the role'")
    async with Session() as s:
        rows = {r["name"]: r for r in await chk.zero_stat_pool_players(s, ORG)}
        await s.rollback()
    check("the record with no ids is called added by hand", rows["David Gardner"]["added_by_hand"] is True, repr(rows.get("David Gardner")))
    check("a synced record (has a CA id) whose pool role an admin set is not, even with no games yet", rows.get("Quiet Quinn", {}).get("added_by_hand") is False, repr(rows.get("Quiet Quinn")))

    print("4. Imported and paired matches are found, and named for what they are")
    g = await verdict_for("Imported Ivan", "Imported Ivan")
    check("a player whose only rows are in an imported (manual) match still shows that game",
          len(g) == 1 and g[0]["source"] == "manual" and g[0]["rows"].startswith("bat 1"), repr(g))
    check("and it counts when it is the club's, in the year, in a counted grade, inside a round",
          bool(g) and g[0]["verdict"] == "counts" and g[0]["round"] == 2, repr(g))
    g = await verdict_for("Hidden Hank", "Hidden Hank")
    check("a synced game hidden by a preferred paired import says so instead of vanishing",
          any("imported match" in x["verdict"] and x["source"] == "api" for x in g), repr(g))
    return base.FAIL


if __name__ == "__main__":
    failed = asyncio.run(main())
    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    sys.exit(1 if failed else 0)
