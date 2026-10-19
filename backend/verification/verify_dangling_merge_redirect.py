"""Sync must not lose a whole game because one player's id redirects to a record that is gone.

Reported (Oak Park St Francis de Sales, October 2026): only the 2nd XI game from the weekend
showed; the 1st XI and 3rd XI games of the last two weekends never arrived. Cricket Australia held
all four, complete. Every run since the first one after those games read as a success, with
`gr_games_new` 0 and 4 of the 36 matches it saw counted nowhere.

Cause: Cricket Australia reissued participant ids for 2026/27, and a few of those new ids sit in
`merge_logs` as a redirect to the club's old record. In production two of them (Kobi Maynard and
Brayden Moore, found by following every chain, 18 Oct) form a LOOP: the redirect chain circles back,
and sync's cycle break resolves the id to ITSELF, a player the merge had already deleted. A redirect
to a record that is simply gone gives the same result. Sync attached the game's rows to that missing id, the foreign key refused them,
the per-game `except` swallowed the error, and the game rolled back. Every game naming that one
person was lost, on every run, with no counter and no flag.

Drives `sync_grassroots_game_level_data` itself with the Cricket Australia client stubbed to
return the match list and scorecards. Scenarios:

  bad     roster names a player whose new id redirects to a missing record  -> stored, the
          person attached to the old record by full name
  self    a player whose id is recorded as merged into ITSELF                -> the same
  loop    two ids recorded as merged into each other (A->B, B->A)            -> the same
  live    roster names a player whose new id redirects to a record that exists -> still redirected
  plain   an ordinary game                                                     -> stored
  broken  a scorecard the database refuses for another reason                   -> counted as failed,
          not stored, and does not stop the games after it (its error is kept, without the SQL)

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_dangling_merge_redirect.py

The control run is the same script against the previous sync.py (`git stash push
backend/app/services/sync.py`): the `bad` game is missing and the counters are absent.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import Base
from app.services import grassroots_scores_client as gr
from app.services import merge_redirects
from app.services.sync import sync_grassroots_game_level_data

try:
    from app.services.competition_ddl import STATEMENTS as COMP_STATEMENTS
except ImportError:  # pragma: no cover
    COMP_STATEMENTS = []

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


TODAY = date.today()
ORG, OPP_ORG = uuid.uuid4(), uuid.uuid4()
SEASON, GRADE_GUID = uuid.uuid4(), str(uuid.uuid4())
GRADE = uuid.UUID(GRADE_GUID)

MATE = uuid.uuid4()                                   # an ordinary player, in every game
OLD_KOBI, NEW_KOBI = uuid.uuid4(), uuid.uuid4()       # old record, and the id CA issued this season
OLD_RICK, NEW_RICK = uuid.uuid4(), uuid.uuid4()
GONE = uuid.uuid4()                                   # a kept player who is no longer in `players`

OLD_SAM, NEW_SAM = uuid.uuid4(), uuid.uuid4()         # a redirect from an id to itself
OLD_LOU, NEW_LOU, NEW_LOU2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()   # two ids merged into each other

G_BAD, G_LIVE, G_PLAIN, G_BROKEN, G_SELF, G_LOOP = (uuid.uuid4() for _ in range(6))
NAMES = {MATE: "Mick Mate", NEW_KOBI: "Kobi Maynard", NEW_RICK: "Rick Rotundo",
         NEW_SAM: "Sam Selfish", NEW_LOU: "Lou Looper"}


def card_for(match_id, roster, runs_by_pid, days_ago):
    """A scorecard whose club innings is batted by `roster` (participant id -> runs)."""
    iso = (TODAY - timedelta(days=days_ago)).isoformat() + "T10:00:00Z"
    ours, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    return {
        "id": str(match_id),
        "matchSchedule": [{"startDateTime": iso}],
        "venue": {"name": "Oval"},
        "grade": {"id": GRADE_GUID, "name": "1st XI"},
        "teams": [
            {"id": ours, "displayName": "OP 1st XI", "owningOrganisation": {"id": str(ORG)},
             "players": [{"participantId": str(p), "name": NAMES.get(p, "Someone"), "roles": []} for p in roster]},
            {"id": theirs, "displayName": "Them 1st XI", "owningOrganisation": {"id": str(OPP_ORG)}, "players": []},
        ],
        "matchSummary": {
            "resultText": "OP won",
            "teams": [{"id": ours, "displayName": "OP 1st XI", "isHome": True},
                      {"id": theirs, "displayName": "Them 1st XI", "isHome": False}],
        },
        "innings": [{
            "inningsOrder": 1, "battingTeamId": ours, "fielding": [], "bowling": [], "fallOfWickets": [],
            "batting": [
                {"participantId": str(p), "dismissalTypeId": 2, "dismissalType": "Bowled",
                 "runsScored": runs_by_pid[p], "ballsFaced": 10, "batOrder": i + 1}
                for i, p in enumerate(roster)
            ],
        }],
    }


def match_entry(match_id, days_ago):
    iso = (TODAY - timedelta(days=days_ago)).isoformat() + "T10:00:00Z"
    return {
        "id": str(match_id), "matchSchedule": [{"startDateTime": iso}], "status": "COMPLETED",
        "matchType": "One Day", "round": {"name": "Round 2"},
        "teams": [{"id": str(uuid.uuid4()), "owningOrganisation": {"id": str(ORG)}},
                  {"id": str(uuid.uuid4()), "owningOrganisation": {"id": str(OPP_ORG), "name": "Them"}}],
    }


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS amalgamate_seasons BOOLEAN NOT NULL DEFAULT false"))
        for stmt in COMP_STATEMENTS:
            await conn.execute(text(stmt))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)"""))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID,
                keep_player_id UUID, keep_player_name TEXT, removed_player_id UUID,
                removed_player_name TEXT, undone_at TIMESTAMPTZ)"""))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)
        for oid, nm, slug in ((ORG, "Oak Park", "op"), (OPP_ORG, "Them CC", "them")):
            await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)",
                     i=oid, n=nm, s=slug)
        await ex("INSERT INTO seasons (id, organisation_id, name, year, grassroots_id) "
                 "VALUES (:i, :o, 'Summer 2026/27', 2026, :g)", i=SEASON, o=ORG, g=str(SEASON))
        await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                 "VALUES (:i, :s, '1st XI', :g, 'senior', ARRAY['senior'])", i=GRADE, s=SEASON, g=GRADE_GUID)
        # The club's players, each under the id CA issued them in an earlier season.
        for pid, nm in ((MATE, "Mate, Mick"), (OLD_KOBI, "Maynard, Kobi"), (OLD_RICK, "Rotundo, Rick"),
                        (OLD_SAM, "Selfish, Sam"), (OLD_LOU, "Looper, Lou")):
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                     "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=ORG, n=nm, g=str(pid))
        # This season's new ids are redirects. Kobi's leads to a record that is gone; Rick's to one
        # that exists. Neither new id is a player.
        # Sam's id is recorded as merged into itself; Lou's is merged into a second new id that is merged
        # straight back (a loop). Production had this shape for two players: the cycle break in sync
        # resolves each to itself, and neither is a player.
        for removed, keep, nm in ((NEW_KOBI, GONE, "Kobi Maynard"), (NEW_RICK, OLD_RICK, "Rick Rotundo"),
                                  (NEW_SAM, NEW_SAM, "Sam Selfish"),
                                  (NEW_LOU, NEW_LOU2, "Lou Looper"), (NEW_LOU2, NEW_LOU, "Lou Looper")):
            await ex("INSERT INTO merge_logs (org_id, keep_player_id, keep_player_name, removed_player_id, "
                     " removed_player_name) VALUES (:o, :k, 'kept', :r, :n)", o=ORG, k=keep, r=removed, n=nm)
        await s.commit()


async def stored(game_id) -> bool:
    async with Session() as s:
        return bool((await s.execute(text("SELECT COUNT(*) FROM games WHERE id = :g"), {"g": game_id})).scalar())


async def runs_of(game_id, player) -> list:
    async with Session() as s:
        rows = (await s.execute(text(
            "SELECT runs FROM batting_innings WHERE game_id = :g AND player_id = :p ORDER BY runs"),
            {"g": game_id, "p": player})).all()
    return [r[0] for r in rows]


async def total_batting() -> int:
    async with Session() as s:
        return (await s.execute(text("SELECT COUNT(*) FROM batting_innings"))).scalar()


async def main() -> None:
    await build_schema()
    await seed()

    cards = {
        str(G_BAD): card_for(G_BAD, [NEW_KOBI, MATE], {NEW_KOBI: 41, MATE: 12}, 4),
        str(G_LIVE): card_for(G_LIVE, [NEW_RICK, MATE], {NEW_RICK: 27, MATE: 9}, 3),
        str(G_PLAIN): card_for(G_PLAIN, [MATE], {MATE: 5}, 2),
        str(G_SELF): card_for(G_SELF, [NEW_SAM, MATE], {NEW_SAM: 18, MATE: 7}, 5),
        str(G_LOOP): card_for(G_LOOP, [NEW_LOU, MATE], {NEW_LOU: 33, MATE: 4}, 6),
        # More runs than the column can hold: the database refuses the game at commit.
        str(G_BROKEN): card_for(G_BROKEN, [MATE], {MATE: 10 ** 12}, 1),
    }
    listing = [match_entry(G_BAD, 4), match_entry(G_LIVE, 3), match_entry(G_PLAIN, 2), match_entry(G_BROKEN, 1),
               match_entry(G_SELF, 5), match_entry(G_LOOP, 6)]

    async def fake_matches(grade_guid, *a, **k):
        return listing

    async def fake_card(match_id, *a, **k):
        return cards.get(str(match_id))

    gr.get_grade_matches = fake_matches
    gr.get_match_scorecard = fake_card

    print("\n-- the redirect helper, on both shapes sync builds --")
    async with Session() as s:
        live, dangling = await merge_redirects.drop_dangling(
            s, {str(NEW_KOBI): GONE, str(NEW_RICK): OLD_RICK})          # aggregate pass: str -> UUID
        check("a redirect to a missing player is dangling", list(dangling) == [str(NEW_KOBI)], str(dangling))
        check("a redirect to a player who exists is kept", list(live) == [str(NEW_RICK)], str(live))
        live, dangling = await merge_redirects.drop_dangling(
            s, {NEW_KOBI: GONE, NEW_RICK: OLD_RICK})                    # scorecard pass: UUID -> UUID
        check("the same, with UUID keys", list(dangling) == [NEW_KOBI] and list(live) == [NEW_RICK])
        live, dangling = await merge_redirects.drop_dangling(s, {NEW_SAM: NEW_SAM})
        check("an id redirected to itself, when it is not a player, is dangling", list(dangling) == [NEW_SAM], str(live))
        live, dangling = await merge_redirects.drop_dangling(s, {OLD_SAM: OLD_SAM})
        check("...but a player who is recorded as merged into themselves is not (they are there)",
              list(live) == [OLD_SAM] and not dangling, str(dangling))
        check("an empty map is two empty halves", await merge_redirects.drop_dangling(s, {}) == ({}, {}))

    print("\n-- A FULL RUN --")
    stats = await sync_grassroots_game_level_data(str(ORG))
    print(f"  stats: new={stats.get('gr_games_new')} failed={stats.get('gr_games_failed')} "
          f"dangling={stats.get('gr_dangling_redirects')} errors={stats.get('gr_game_errors')}")

    check("the ordinary game is stored", await stored(G_PLAIN))
    check("the game naming a player with a dangling redirect is stored", await stored(G_BAD))
    check("that player's innings is on his old record, matched by full name",
          await runs_of(G_BAD, OLD_KOBI) == [41], str(await runs_of(G_BAD, OLD_KOBI)))
    check("and the rest of the side is there too", await runs_of(G_BAD, MATE) == [12])
    check("a player recorded as merged into himself: the game is stored, his innings on the old record",
          await stored(G_SELF) and await runs_of(G_SELF, OLD_SAM) == [18], str(await runs_of(G_SELF, OLD_SAM)))
    check("two ids merged into each other (a loop): the game is stored, the innings on the old record",
          await stored(G_LOOP) and await runs_of(G_LOOP, OLD_LOU) == [33], str(await runs_of(G_LOOP, OLD_LOU)))
    check("a redirect to a player who exists still redirects",
          await stored(G_LIVE) and await runs_of(G_LIVE, OLD_RICK) == [27], str(await runs_of(G_LIVE, OLD_RICK)))
    check("a game the database refuses is not stored", not await stored(G_BROKEN))
    check("and nothing of it is left behind", await runs_of(G_BROKEN, MATE) == [])

    print("\n-- THE RUN SAYS SO --")
    check("the run counts the redirects it ignored (the missing one, the self one, both ends of the loop)",
          stats.get("gr_dangling_redirects") == 4,
          str(stats.get("gr_dangling_redirects")))
    check("it counts exactly the one game that failed", stats.get("gr_games_failed") == 1,
          str(stats.get("gr_games_failed")))
    errors = stats.get("gr_game_errors") or []
    check("and names it, with the database's own words", len(errors) == 1 and errors[0].get("match") == str(G_BROKEN)
          and "out of int32 range" in (errors[0].get("error") or ""), str(errors))
    check("the stored error carries no SQL", not any(w in (e.get("error") or "") for e in errors for w in ("[SQL", "INSERT")), str(errors))
    check("five games were stored", stats.get("gr_games_new") == 5, str(stats.get("gr_games_new")))

    print("\n-- A SECOND RUN CHANGES NOTHING --")
    before = await total_batting()
    again = await sync_grassroots_game_level_data(str(ORG))
    check("no batting is written twice", await total_batting() == before, f"{before} -> {await total_batting()}")
    check("the five stored games are done, the broken one fails again",
          again.get("gr_games_skipped_done") == 5 and again.get("gr_games_failed") == 1,
          f"done={again.get('gr_games_skipped_done')} failed={again.get('gr_games_failed')}")

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
