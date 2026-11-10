"""A fixture between two synced clubs is on BOTH clubs' fee lists.

A game between two clubs that both sync BetterCricket is ONE ``games`` row owned
by whichever club synced it first, so its grade, and the grade's season, are the
other club's rows. ``recompute_fee_match_days`` read only games under the club's
own season, so a club's half of every such fixture was left off its fee list.
Reported case: Angus Castley (Applecross) played two games in Summer 2026/27,
the 17 Oct one owned by Applecross and the 24 Oct one owned by North Perth, and
the member page showed one match day while his profile held both.

Checks, against a real Postgres through ``recompute_fee_match_days``:

  * our own fixture is charged (unchanged),
  * the other club's fixture that we played in is charged to our player,
  * the opposition's player in a shared fixture is NOT enrolled in our club,
  * a fixture we are not a side to is not charged even with our player named,
  * another club's season of a different year is not read,
  * the club's own ``fee_format`` decides a foreign grade by name: our "Exclude"
    holds, and the other club's "Exclude" does not apply to us,
  * a rerun adds nothing, and the OTHER club's own fee list is built the same way.

The control run (``--control``) puts the old own-season-only read back, so the
checks that describe the fix must fail while the unchanged-behaviour checks pass.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/fees_verify?host=/tmp/pgsock&port=5544 \
      python verification/verify_fees_shared_fixture.py [--control]
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import select, text  # noqa: E402

PASS = FAIL = 0
PLAYED = '[{"runs_scored": 120, "wickets": 5}]'
CONTROL = "--control" in sys.argv


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


async def main():
    from app.models.db import (
        Game, GameAppearance, Grade, Organisation, Player, Season, Base,
        engine, async_session_maker,
    )
    from app.services import fees
    from app.services.fees import recompute_fee_match_days

    if CONTROL:
        async def own_season_only(session, org_id, sid, grades):
            rows = (await session.execute(
                select(Game).join(Grade, Game.grade_id == Grade.id).where(Grade.season_id == sid)
            )).scalars().all()
            return list(rows), {}
        fees._season_games = own_season_only

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        for tbl, col in (await conn.execute(text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND data_type = 'json'"))).all():
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        # Raw-SQL lifespan tables `create_all` cannot see (main.py lifespan, copied).
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
                alias_season_id    UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)"""))
        from app.services import superseded_ddl
        for stmt in superseded_ddl.STATEMENTS:
            await conn.execute(text(stmt))

    today = fees.datetime.now(fees.FEE_TZ).date()
    d = lambda n: today - timedelta(days=n)  # noqa: E731

    ids = {k: uuid.uuid4() for k in (
        "a", "b", "c", "sa", "sb", "sb_old", "sc",
        "ga4", "gb4", "ga_jun", "gb_jun", "gb_wom", "gb_sen", "gb_old", "gc",
        "own", "shared", "stranger_game", "jun", "wom", "sen", "old",
        "p_a", "p_b", "p_a_stranger")}
    async with async_session_maker() as db:
        db.add_all([
            Organisation(id=ids["a"], name="Applecross", slug="apple-sf", is_active=True),
            Organisation(id=ids["b"], name="North Perth", slug="np-sf", is_active=True),
            Organisation(id=ids["c"], name="Somewhere Else", slug="else-sf", is_active=True),
        ])
        await db.flush()
        db.add_all([
            Season(id=ids["sa"], organisation_id=ids["a"], name="Summer 2026/27", year=2026),
            Season(id=ids["sb"], organisation_id=ids["b"], name="Summer 2026/27", year=2026),
            Season(id=ids["sb_old"], organisation_id=ids["b"], name="Summer 2025/26", year=2025),
            Season(id=ids["sc"], organisation_id=ids["c"], name="Summer 2026/27", year=2026),
        ])
        await db.flush()
        db.add_all([
            # Applecross's own grades: Juniors is set to Exclude.
            Grade(id=ids["ga4"], season_id=ids["sa"], name="One Day Grade 4"),
            Grade(id=ids["ga_jun"], season_id=ids["sa"], name="Juniors", fee_format="exclude"),
            # North Perth's rows of the same real-world season.
            Grade(id=ids["gb4"], season_id=ids["sb"], name="One Day Grade 4"),
            Grade(id=ids["gb_jun"], season_id=ids["sb"], name="Juniors"),
            Grade(id=ids["gb_wom"], season_id=ids["sb"], name="Womens"),
            # North Perth excludes this one; Applecross has no grade of that name.
            Grade(id=ids["gb_sen"], season_id=ids["sb"], name="Seniors B", fee_format="exclude"),
            Grade(id=ids["gb_old"], season_id=ids["sb_old"], name="One Day Grade 4"),
            Grade(id=ids["gc"], season_id=ids["sc"], name="One Day Grade 4"),
            Player(id=ids["p_a"], organisation_id=ids["a"], name="Castley, Angus"),
            Player(id=ids["p_b"], organisation_id=ids["b"], name="Opposition, Olly"),
            Player(id=ids["p_a_stranger"], organisation_id=ids["a"], name="Misfiled, Max"),
        ])
        await db.flush()

        def game(key, grade, home, away, when):
            db.add(Game(id=ids[key], grade_id=ids[grade], played_at=when, home_team="H",
                        away_team="A", status="COMPLETED",
                        home_org_id=ids[home], away_org_id=ids[away]))

        game("own", "ga4", "a", "b", d(14))             # ours, we synced first
        game("shared", "gb4", "b", "a", d(7))           # North Perth synced first
        game("jun", "gb_jun", "b", "a", d(6))           # our own grade of that name is Exclude
        game("wom", "gb_wom", "b", "a", d(5))           # no grade of ours: match format default
        game("sen", "gb_sen", "b", "a", d(4))           # THEIR Exclude is not ours
        game("old", "gb_old", "b", "a", d(400))         # a different year
        game("stranger_game", "gc", "c", "b", d(3))     # we are not a side
        await db.flush()
        await db.execute(text("UPDATE games SET innings_totals = CAST(:t AS JSONB)"), {"t": PLAYED})
        for g in ("own", "shared", "jun", "wom", "sen", "old"):
            db.add(GameAppearance(game_id=ids[g], player_id=ids["p_a"]))
            db.add(GameAppearance(game_id=ids[g], player_id=ids["p_b"]))
        # Our player named in a game our club was not part of (bad data): never charged to us.
        db.add(GameAppearance(game_id=ids["stranger_game"], player_id=ids["p_a_stranger"]))
        await db.commit()

    async def charged(org, season):
        async with async_session_maker() as db:
            rows = (await db.execute(text("""
                SELECT md.game_id, m.player_id FROM fee_match_days md
                  JOIN fee_member_seasons ms ON ms.id = md.member_season_id
                  JOIN fee_members m ON m.id = ms.member_id
                 WHERE ms.season_id = :s AND ms.organisation_id = :o
            """), {"s": season, "o": org})).all()
        return {(r[0], r[1]) for r in rows}

    await recompute_fee_match_days(str(ids["a"]), str(ids["sa"]))
    got = await charged(ids["a"], ids["sa"])
    games_for_angus = {g for g, p in got if p == ids["p_a"]}
    check("our own fixture is charged", ids["own"] in games_for_angus)
    check("the fixture North Perth owns is charged to our player", ids["shared"] in games_for_angus)
    check("a foreign grade that OUR grade of that name excludes is not charged",
          ids["jun"] in games_for_angus, False)
    check("a foreign grade with no grade of ours falls back to the match format",
          ids["wom"] in games_for_angus)
    check("the other club's Exclude does not apply to us", ids["sen"] in games_for_angus)
    check("another club's season of a different year is not read", ids["old"] in games_for_angus, False)
    check("a fixture we are not a side to is not charged",
          any(g == ids["stranger_game"] for g, p in got), False)
    check("the opposition's player is not enrolled in our club",
          any(p == ids["p_b"] for g, p in got), False)
    check("our fee list holds exactly Angus's four charged games (not Juniors, not 2025)",
          len(games_for_angus), 4)

    # A rerun adds nothing and removes nothing.
    again = await recompute_fee_match_days(str(ids["a"]), str(ids["sa"]))
    check("a rerun upserts nothing", again["entries_upserted"], 0)
    check("a rerun removes nothing", again["entries_deleted"], 0)
    check("a rerun leaves the same rows", await charged(ids["a"], ids["sa"]), got)

    # A paid row for the shared game is left alone by the next rebuild.
    paid_id = uuid.uuid4()
    async with async_session_maker() as db:
        await db.execute(text("""
            INSERT INTO fee_payments (id, organisation_id, member_season_id, amount, paid_at, kind)
            SELECT :pid, ms.organisation_id, ms.id, 20, CURRENT_DATE, 'match_day'
              FROM fee_member_seasons ms JOIN fee_members m ON m.id = ms.member_id
             WHERE ms.season_id = :s AND m.player_id = :p LIMIT 1
        """), {"pid": paid_id, "s": ids["sa"], "p": ids["p_a"]})
        await db.execute(text("UPDATE fee_match_days SET paid_payment_id = :pid WHERE game_id = :g"),
                         {"pid": paid_id, "g": ids["shared"]})
        await db.commit()
    await recompute_fee_match_days(str(ids["a"]), str(ids["sa"]))
    check("a paid shared-game row survives a rebuild", ids["shared"] in
          {g for g, p in await charged(ids["a"], ids["sa"]) if p == ids["p_a"]})

    # The same fixture, from the owner's side: North Perth charges ITS player, not ours.
    await recompute_fee_match_days(str(ids["b"]), str(ids["sb"]))
    gotb = await charged(ids["b"], ids["sb"])
    check("the owner still charges its own player for the shared game",
          (ids["shared"], ids["p_b"]) in gotb)
    check("the owner never enrolls our player", any(p == ids["p_a"] for g, p in gotb), False)

    print(f"\n{PASS} passed, {FAIL} failed" + (" (control run)" if CONTROL else ""))
    sys.exit(0 if (FAIL == 0 or CONTROL) else 1)


if __name__ == "__main__":
    asyncio.run(main())
