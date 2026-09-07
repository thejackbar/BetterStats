"""A CricketStatz import must not add a second copy of a match the club already
holds. Verified against a real Postgres.

REPORTED off a live import, mid-run: the record boards were "massively
overcounting" and the Highest Individual Scores board listed the same innings
twice — Heath Shephard's 270 at ranks 1 AND 2, Princely Emmanuel's 206* at 3
and 4, and so on. Every duplicated row was from a season Cricket Australia also
covers (2002/03, 2011/12, 2013/14); every un-duplicated one was from before the
sync could reach (1969/70, 1991/92, 1994/95).

The cause is in ``import_match``: it looks for an existing row by
``cricketstatz_match_id`` and NOTHING ELSE, so it has no idea the club already
holds that fixture as a SYNCED game. Both then sit in ``v_effective_games`` and
``v_effective_batting_innings``, which union the synced and manual tables — so
every innings of every overlapping match is counted twice.

**A doubling is invisible in an average**, which is why this reads as plausible
figures rather than obvious nonsense: runs and dismissals both double and the
average is unchanged. Only the counts move.

Runs the SHIPPED ``import_match`` and the SHIPPED records route body over the
``v_effective_*`` views pulled straight out of the migrations that define them.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5432 \
  python verification/verify_cricketstatz_duplicate_games.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import Base
from app.services.cricketstatz_ddl import STATEMENTS as CS_STATEMENTS
from app.services import cricketstatz_import as csi

MISSING: list[str] = []
try:
    from app.services.cricketstatz_import import synced_fixture_index
    HAVE_GUARD = True
except ImportError as exc:  # pragma: no cover - control run only
    HAVE_GUARD = False
    MISSING.append(str(exc))
    synced_fixture_index = None

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
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


ORG = uuid.uuid4()
CLUB_NAME = "Cockburn Cricket Club"

# The modern season Cricket Australia also covers, and an old one only
# CricketStatz has — the two halves of the reported screenshot.
S_MODERN = uuid.uuid4()
S_OLD = uuid.uuid4()
G_FIRSTS = uuid.uuid4()      # the club's own CA grade, "1st Grade"
G_SECONDS = uuid.uuid4()     # a second side playing the same club the same day

SHEPHARD = uuid.uuid4()
LYNCH = uuid.uuid4()

SYNCED_1ST = uuid.uuid4()
SYNCED_2ND = uuid.uuid4()

MATCH_DAY = date(2003, 1, 18)
OLD_DAY = date(1969, 12, 6)


def card(source_id: str, *, played: date, opponent: str, division: str,
         our_team: str, batter: str, runs: int, not_out: bool = False) -> dict:
    """One CricketStatz scorecard, in the shape the parser hands the importer."""
    return {
        "source_match_id": source_id,
        "date": played.isoformat(),
        "division": division,
        "home_team": our_team,
        "away_team": opponent,
        "venue": "Davilak Oval",
        "result": "Won",
        "winning_team": our_team,
        "innings": [{
            "innings_number": 1,
            "batting_team": our_team,
            "bowling_team": opponent,
            # The shape cricketstatz_parse actually produces — the person is a
            # nested `batter` dict, not a flat name. A harness card that merely
            # looks right writes no innings at all and the whole suite measures
            # nothing; found by probing what the import stored.
            "batters": [{
                "batter": {"source_player_id": batter.lower().replace(" ", "-"),
                           "name": batter},
                "dismissal_type": None if not_out else "bowled",
                "not_out": not_out, "did_not_bat": False,
                "bowler": None, "fielder": None,
                "is_captain": False, "is_keeper": False,
                "batting_position": 3, "runs": runs,
                "minutes": None, "balls": None, "strike_rate": None,
                "fours": None, "sixes": None,
            }],
            "bowlers": [], "fall_of_wickets": [],
        }],
    }


def row(source_id: str, *, played: date, opponent: str, division: str) -> dict:
    return {"source_match_id": source_id, "date": played.isoformat(),
            "division": division, "opposition": opponent, "round": "Round 10"}


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        for stmt in CS_STATEMENTS:
            await conn.execute(text(stmt))
        # create_all types `raw_payload` as json where the migrations use jsonb,
        # and a UNION cannot coerce between them — the same fix the neighbouring
        # suites make.
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::jsonb'))
        for _name, sql in view_statements():
            await conn.execute(text(sql))


async def seed() -> None:
    async with Session() as s:
        await s.execute(text("""
            INSERT INTO organisations (id, name, slug, is_active)
            VALUES (:id, :name, 'cockburn', true)
        """), {"id": str(ORG), "name": CLUB_NAME})
        for sid, name, year in ((S_MODERN, "Summer 2002/03", 2002),
                                (S_OLD, "Summer 1969/70", 1969)):
            await s.execute(text("""
                INSERT INTO seasons (id, organisation_id, name, year)
                VALUES (:id, :org, :name, :year)
            """), {"id": str(sid), "org": str(ORG), "name": name, "year": year})
        for gid, name in ((G_FIRSTS, "1st Grade"), (G_SECONDS, "2nd Grade")):
            await s.execute(text("""
                INSERT INTO grades (id, season_id, name) VALUES (:id, :s, :n)
            """), {"id": str(gid), "s": str(S_MODERN), "n": name})
        for pid, name in ((SHEPHARD, "Heath Shephard"), (LYNCH, "Bob Lynch")):
            await s.execute(text("""
                INSERT INTO players (id, organisation_id, name, is_player, status)
                VALUES (:id, :org, :n, true, 'active')
            """), {"id": str(pid), "org": str(ORG), "n": name})

        # THE SYNCED HALF — what Cricket Australia already gave the club. Two
        # sides out that afternoon against the same opposition, which is the
        # case the guard must not collapse into one.
        for gid, grade, team in ((SYNCED_1ST, G_FIRSTS, "Cockburn CC 1st Grade"),
                                 (SYNCED_2ND, G_SECONDS, "Cockburn CC 2nd Grade")):
            await s.execute(text("""
                INSERT INTO games (id, grade_id, played_at, home_team, away_team,
                                   opp_club_name, result, winning_team, status)
                VALUES (:id, :g, :d, :home, 'Melville Cricket Club',
                        'Melville Cricket Club', 'Won', :home, 'COMPLETED')
            """), {"id": str(gid), "g": str(grade), "d": MATCH_DAY, "home": team})
        await s.execute(text("""
            INSERT INTO batting_innings (game_id, player_id, runs, not_out,
                                         batting_position, did_not_bat)
            VALUES (:g, :p, 270, false, 3, false)
        """), {"g": str(SYNCED_1ST), "p": str(SHEPHARD)})
        await s.commit()


def is_ours(team: str) -> bool:
    return "cockburn" in (team or "").lower()


TALLY: dict = {}


async def run_import(cards: list[tuple[dict, dict, str, str]]) -> list[str]:
    """Import a list of (card, row, season_label, season_value) through the
    SHIPPED import_match, driven the way run_import drives it — one shared
    fixture index and one shared tally across every season, because the claim is
    greedy and a synced game claimed by one season must not be offered to
    another."""
    notes: list[str] = []
    TALLY.clear()
    TALLY.update({"skipped": 0, "removed": 0})
    async with Session() as s:
        index = await synced_fixture_index(s, ORG) if HAVE_GUARD else None
        for c, r, label, value in cards:
            caches = {
                "seasons": {}, "grades": {}, "players": {}, "roster": None,
                "near_matches": {}, "hand_edited": set(),
                "season_label": label, "season_value": value,
                "held_tally": TALLY,
            }
            if HAVE_GUARD:
                caches["synced_fixtures"] = index
            note = await csi.import_match(s, ORG, uuid.uuid4(), c, r, is_ours, caches)
            if note:
                notes.append(note)
            await s.commit()
    return notes


# The join the record boards use — v_effective_batting_innings against
# v_effective_games, which is where a second copy of a match doubles an innings.
_BOARD = text("""
    SELECT COALESCE(p.display_name_override, p.name) AS name, bi.runs, s.name AS season
    FROM players p
    JOIN v_effective_batting_innings bi ON bi.player_id = p.id
    JOIN v_effective_games g ON g.id = bi.game_id
    JOIN grades gr ON gr.id = g.grade_id
    JOIN seasons s ON s.id = gr.season_id
    WHERE p.organisation_id = :org
      AND NOT COALESCE(bi.did_not_bat, FALSE)
      AND bi.runs IS NOT NULL AND bi.runs > 0
    ORDER BY bi.runs DESC
""")


async def board() -> list[dict]:
    async with Session() as s:
        rows = (await s.execute(_BOARD, {"org": str(ORG)})).mappings().all()
    return [dict(r) for r in rows]


async def manual_game_count() -> int:
    async with Session() as s:
        return (await s.scalar(text(
            "SELECT COUNT(*) FROM manual_games WHERE organisation_id = :o"),
            {"o": str(ORG)})) or 0


async def reset_manual() -> None:
    async with Session() as s:
        await s.execute(text("DELETE FROM manual_games WHERE organisation_id = :o"),
                        {"o": str(ORG)})
        await s.commit()


# ─── The checks ──────────────────────────────────────────────────────────────

async def check_reported_case():
    print("\n── the reported case ───────────────────────────────────────────")
    await reset_manual()
    notes = await run_import([(
        card("m-1", played=MATCH_DAY, opponent="Melville CC", division="A Grade",
             our_team="Cockburn 1st XI", batter="Heath Shephard", runs=270),
        row("m-1", played=MATCH_DAY, opponent="Melville CC", division="A Grade"),
        "2002/03", "2002",
    )])
    rows = await board()
    two_seventies = [r for r in rows if r["runs"] == 270]
    check("the innings the club already had synced is listed exactly once",
          len(two_seventies) == 1, f"{len(two_seventies)} rows: {two_seventies}")
    check("no second copy of the match is created",
          await manual_game_count() == 0, str(await manual_game_count()))
    check("and the club is told how many were left as Cricket Australia has them",
          TALLY["skipped"] == 1, str(TALLY))
    check("counted rather than noted per match, so 200 of them cannot crowd "
          "out the notes that need reading", not notes, str(notes))


async def check_old_season_still_imports():
    print("\n── a season only CricketStatz has ──────────────────────────────")
    notes = await run_import([(
        card("m-old", played=OLD_DAY, opponent="Melville CC", division="A Grade",
             our_team="Cockburn 1st XI", batter="Bob Lynch", runs=196, not_out=True),
        row("m-old", played=OLD_DAY, opponent="Melville CC", division="A Grade"),
        "1969/70", "1969",
    )])
    rows = await board()
    check("a match from before the sync could reach is imported",
          any(r["runs"] == 196 for r in rows), str(rows))
    check("exactly once", len([r for r in rows if r["runs"] == 196]) == 1, str(rows))
    check("and nothing is skipped for it",
          TALLY["skipped"] == 0 and not notes, f"{TALLY} {notes}")


async def check_second_side_same_day():
    print("\n── two sides out against one club on one afternoon ─────────────")
    # The club fielded a 1sts AND a 2nds against Melville that day, and both are
    # synced. Both CricketStatz copies must be recognised — collapsing the day
    # into one fixture would leave the second one importing as a duplicate.
    await reset_manual()
    notes = await run_import([
        (card("m-1", played=MATCH_DAY, opponent="Melville CC", division="A Grade",
              our_team="Cockburn 1st XI", batter="Heath Shephard", runs=270),
         row("m-1", played=MATCH_DAY, opponent="Melville CC", division="A Grade"),
         "2002/03", "2002"),
        (card("m-2", played=MATCH_DAY, opponent="Melville CC", division="B Grade",
              our_team="Cockburn 2nd XI", batter="Heath Shephard", runs=44),
         row("m-2", played=MATCH_DAY, opponent="Melville CC", division="B Grade"),
         "2002/03", "2002"),
    ])
    check("neither copy is written — the club holds both fixtures already",
          await manual_game_count() == 0, str(await manual_game_count()))
    check("both are counted rather than silently dropped",
          TALLY["skipped"] == 2, str(TALLY))
    check("and each was matched to its OWN side, not claimed in whatever order "
          "they arrived — 'A Grade' and '1st Grade' are the same eleven",
          csi._side_key("A Grade") == csi._side_key("1st Grade") == "1"
          and csi._side_key("B Grade") == "2",
          f"{csi._side_key('A Grade')} {csi._side_key('1st Grade')} {csi._side_key('B Grade')}")

    # A THIRD side the sync does not hold still imports: the guard may never
    # skip more matches than there are synced games that day. Driven in ONE run
    # with the other two, because that is how run_import drives it — the index
    # and its claims are shared across the whole import.
    await reset_manual()
    notes = await run_import([
        (card("m-1", played=MATCH_DAY, opponent="Melville CC", division="A Grade",
              our_team="Cockburn 1st XI", batter="Heath Shephard", runs=270),
         row("m-1", played=MATCH_DAY, opponent="Melville CC", division="A Grade"),
         "2002/03", "2002"),
        (card("m-2", played=MATCH_DAY, opponent="Melville CC", division="B Grade",
              our_team="Cockburn 2nd XI", batter="Heath Shephard", runs=44),
         row("m-2", played=MATCH_DAY, opponent="Melville CC", division="B Grade"),
         "2002/03", "2002"),
        (card("m-3", played=MATCH_DAY, opponent="Melville CC", division="C Grade",
              our_team="Cockburn 3rd XI", batter="Bob Lynch", runs=61),
         row("m-3", played=MATCH_DAY, opponent="Melville CC", division="C Grade"),
         "2002/03", "2002"),
    ])
    check("a side the sync does NOT hold is still imported",
          await manual_game_count() == 1, str(await manual_game_count()))
    check("only the two the club already had are skipped",
          TALLY["skipped"] == 2, str(TALLY))
    rows = await board()
    day = sorted(r["runs"] for r in rows if r["season"] == "Summer 2002/03")
    # The synced 1sts innings (270) and the imported 3rds innings (61). The
    # imported 1sts copy of the 270 and the imported 2nds 44 are both matches
    # the club already holds, so neither is written — the seeded 2nds game
    # carries no batting card of its own, which is why 44 is absent rather than
    # present once.
    check("that day reads as the synced innings plus the one only "
          "CricketStatz has — no second copy of either", day == [61, 270], str(day))


async def check_different_opponent_and_date():
    print("\n── a fixture the club genuinely does not hold ──────────────────")
    await reset_manual()
    notes = await run_import([
        (card("m-x", played=MATCH_DAY, opponent="Fremantle CC", division="A Grade",
              our_team="Cockburn 1st XI", batter="Heath Shephard", runs=88),
         row("m-x", played=MATCH_DAY, opponent="Fremantle CC", division="A Grade"),
         "2002/03", "2002"),
        (card("m-y", played=date(2003, 1, 25), opponent="Melville CC", division="A Grade",
              our_team="Cockburn 1st XI", batter="Heath Shephard", runs=99),
         row("m-y", played=date(2003, 1, 25), opponent="Melville CC", division="A Grade"),
         "2002/03", "2002"),
    ])
    check("a different opponent on the same day is imported",
          await manual_game_count() == 2, str(await manual_game_count()))
    check("as is the same opponent on a different day",
          TALLY["skipped"] == 0 and not notes, f"{TALLY} {notes}")


async def check_reimport_repairs():
    print("\n── a re-import repairs a club already in this state ────────────")
    await reset_manual()
    # Write the duplicate the way the buggy import did — no guard, straight in.
    async with Session() as s:
        caches = {"seasons": {}, "grades": {}, "players": {}, "roster": None,
                  "near_matches": {}, "hand_edited": set(),
                  "season_label": "2002/03", "season_value": "2002"}
        await csi.import_match(
            s, ORG, uuid.uuid4(),
            card("m-1", played=MATCH_DAY, opponent="Melville CC", division="A Grade",
                 our_team="Cockburn 1st XI", batter="Heath Shephard", runs=270),
            row("m-1", played=MATCH_DAY, opponent="Melville CC", division="A Grade"),
            is_ours, caches)
        await s.commit()
    rows = await board()
    check("the reported bug is reproduced — the innings is listed twice",
          len([r for r in rows if r["runs"] == 270]) == 2, str(rows))

    notes = await run_import([(
        card("m-1", played=MATCH_DAY, opponent="Melville CC", division="A Grade",
             our_team="Cockburn 1st XI", batter="Heath Shephard", runs=270),
        row("m-1", played=MATCH_DAY, opponent="Melville CC", division="A Grade"),
        "2002/03", "2002",
    )])
    rows = await board()
    check("re-running the import clears the duplicate it created",
          len([r for r in rows if r["runs"] == 270]) == 1, str(rows))
    check("the duplicate match row is gone with it",
          await manual_game_count() == 0, str(await manual_game_count()))
    check("and the club is told one was removed", TALLY["removed"] == 1, str(TALLY))


async def check_hand_edited_is_never_removed():
    print("\n── a scorecard somebody has worked on is never removed ─────────")
    await reset_manual()
    async with Session() as s:
        caches = {"seasons": {}, "grades": {}, "players": {}, "roster": None,
                  "near_matches": {}, "hand_edited": set(),
                  "season_label": "2002/03", "season_value": "2002"}
        await csi.import_match(
            s, ORG, uuid.uuid4(),
            card("m-1", played=MATCH_DAY, opponent="Melville CC", division="A Grade",
                 our_team="Cockburn 1st XI", batter="Heath Shephard", runs=270),
            row("m-1", played=MATCH_DAY, opponent="Melville CC", division="A Grade"),
            is_ours, caches)
        await s.commit()
        game_id = (await s.scalar(text(
            "SELECT id FROM manual_games WHERE organisation_id = :o"), {"o": str(ORG)}))

    notes = []
    async with Session() as s:
        index = await synced_fixture_index(s, ORG) if HAVE_GUARD else None
        caches = {"seasons": {}, "grades": {}, "players": {}, "roster": None,
                  "near_matches": {}, "hand_edited": {str(game_id)},
                  "season_label": "2002/03", "season_value": "2002"}
        if HAVE_GUARD:
            caches["synced_fixtures"] = index
        note = await csi.import_match(
            s, ORG, uuid.uuid4(),
            card("m-1", played=MATCH_DAY, opponent="Melville CC", division="A Grade",
                 our_team="Cockburn 1st XI", batter="Heath Shephard", runs=270),
            row("m-1", played=MATCH_DAY, opponent="Melville CC", division="A Grade"),
            is_ours, caches)
        if note:
            notes.append(note)
        await s.commit()
    check("a hand-edited game is left standing even though it duplicates",
          await manual_game_count() == 1, str(await manual_game_count()))
    check("and the club is told why, rather than it being removed silently",
          any("hand" in n.lower() for n in notes), str(notes))


async def check_repair_script():
    print("\n── the repair for a club already carrying duplicates ───────────")
    from app.services.cricketstatz_import import remove_duplicate_imported_games
    await reset_manual()
    async with Session() as s:
        for sid, opp, runs in (("m-1", "Melville CC", 270), ("m-old", "Melville CC", 196)):
            caches = {"seasons": {}, "grades": {}, "players": {}, "roster": None,
                      "near_matches": {}, "hand_edited": set(),
                      "season_label": "2002/03" if sid == "m-1" else "1969/70",
                      "season_value": "2002" if sid == "m-1" else "1969"}
            await csi.import_match(
                s, ORG, uuid.uuid4(),
                card(sid, played=MATCH_DAY if sid == "m-1" else OLD_DAY,
                     opponent=opp, division="A Grade", our_team="Cockburn 1st XI",
                     batter="Heath Shephard", runs=runs),
                row(sid, played=MATCH_DAY if sid == "m-1" else OLD_DAY,
                    opponent=opp, division="A Grade"),
                is_ours, caches)
        await s.commit()
    check("two imported matches to start", await manual_game_count() == 2)

    async with Session() as s:
        plan = await remove_duplicate_imported_games(s, ORG, apply=False)
        await s.commit()
    check("a dry run reports the one duplicate", plan["duplicates"] == 1, str(plan))
    check("and writes nothing", await manual_game_count() == 2, str(await manual_game_count()))

    async with Session() as s:
        done = await remove_duplicate_imported_games(s, ORG, apply=True)
        await s.commit()
    check("applying it removes exactly the duplicate", done["removed"] == 1, str(done))
    check("leaving the match only CricketStatz has",
          await manual_game_count() == 1, str(await manual_game_count()))
    rows = await board()
    check("the board reads each innings once",
          len(rows) == 2 and sorted(r["runs"] for r in rows) == [196, 270], str(rows))

    async with Session() as s:
        again = await remove_duplicate_imported_games(s, ORG, apply=True)
        await s.commit()
    check("a second run removes nothing", again["removed"] == 0, str(again))


async def main() -> int:
    if not HAVE_GUARD:
        print("The already-synced guard is not present in this build:")
        for m in MISSING:
            print(f"  - {m}")
        print("Running the reproduction anyway, so the bug itself is on record.\n")

    await build_schema()
    await seed()
    if HAVE_GUARD:
        await check_reported_case()
        await check_old_season_still_imports()
        await check_second_side_same_day()
        await check_different_opponent_and_date()
        await check_reimport_repairs()
        await check_hand_edited_is_never_removed()
        await check_repair_script()
    else:
        # CONTROL RUN: prove the bug is real against the previous behaviour.
        await reset_manual()
        async with Session() as s:
            caches = {"seasons": {}, "grades": {}, "players": {}, "roster": None,
                      "near_matches": {}, "hand_edited": set(),
                      "season_label": "2002/03", "season_value": "2002"}
            await csi.import_match(
                s, ORG, uuid.uuid4(),
                card("m-1", played=MATCH_DAY, opponent="Melville CC", division="A Grade",
                     our_team="Cockburn 1st XI", batter="Heath Shephard", runs=270),
                row("m-1", played=MATCH_DAY, opponent="Melville CC", division="A Grade"),
                is_ours, caches)
            await s.commit()
        rows = await board()
        check("REPRODUCTION: the innings the club already had is listed twice",
              len([r for r in rows if r["runs"] == 270]) == 2, str(rows))
        check("the already-synced guard is present", False, "; ".join(MISSING))

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print(f"  - {f}")
    await engine.dispose()
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
