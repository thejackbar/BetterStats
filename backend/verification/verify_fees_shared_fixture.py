"""A game belongs to no club, so a fixture two synced clubs played is on BOTH fee lists.

``games.grade_id`` points at the grade row of whichever club's sync created the
game first, so the season that row hangs off says nothing about who played.
``recompute_fee_match_days`` used to read only games under the club's own season
row, so a club's half of every fixture another BetterCricket club had synced first
was left off its fee list. Reported case: Angus Castley (Applecross) played two
games in Summer 2026/27, 17 Oct under Applecross's season row and 24 Oct under
North Perth's, and the member page showed one match day while his profile held both.

Checks, against a real Postgres through ``recompute_fee_match_days``:

  * our own fixture is charged (unchanged),
  * a fixture under the other club's season row is charged to our player, with
    NO ``home_org_id``/``away_org_id`` set on it (a game is not read through who synced it),
  * the opposition's player in that fixture is NOT enrolled in our club,
  * a game none of our players is in is not read at all,
  * another club's season of a different year is not read,
  * a game lands in exactly ONE of the club's fee seasons: with two seasons in one
    year, the CA season GUID decides; a season that fits both is left out, never
    charged twice,
  * the club's own ``fee_format`` decides a foreign grade by name: our "Exclude"
    holds, and the other club's "Exclude" does not apply to us,
  * a rerun adds and removes nothing, a paid row survives, and the other club's own
    fee list is built the same way and never enrols our player.

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
        "a", "b",
        "sa", "sa_m", "sb", "sb_m", "sb_x", "sb_old",
        "ga4", "ga_jun", "ga_m", "gb4", "gb_jun", "gb_wom", "gb_sen", "gb_m", "gb_x", "gb_old",
        "own", "shared", "jun", "wom", "sen", "old", "masters", "ambiguous", "unrelated",
        "p_a", "p_b")}
    async with async_session_maker() as db:
        db.add_all([
            Organisation(id=ids["a"], name="Applecross", slug="apple-sf", is_active=True),
            Organisation(id=ids["b"], name="North Perth", slug="np-sf", is_active=True),
        ])
        await db.flush()
        db.add_all([
            # Applecross holds TWO seasons in 2026: the main one and a masters competition.
            Season(id=ids["sa"], organisation_id=ids["a"], name="Summer 2026/27", year=2026,
                   grassroots_id="CA-MAIN"),
            Season(id=ids["sa_m"], organisation_id=ids["a"], name="Over 60s 2026", year=2026,
                   grassroots_id="CA-MASTERS"),
            # North Perth's rows of the same real-world seasons (its own per-club ids).
            Season(id=ids["sb"], organisation_id=ids["b"], name="Summer 2026/27", year=2026,
                   grassroots_id="CA-MAIN"),
            Season(id=ids["sb_m"], organisation_id=ids["b"], name="Masters Summer", year=2026,
                   grassroots_id="CA-MASTERS"),
            # Matches neither by GUID nor name; only the year, which fits BOTH of ours.
            Season(id=ids["sb_x"], organisation_id=ids["b"], name="Club Cup", year=2026,
                   grassroots_id="CA-OTHER"),
            Season(id=ids["sb_old"], organisation_id=ids["b"], name="Summer 2025/26", year=2025,
                   grassroots_id="CA-OLD"),
        ])
        await db.flush()
        db.add_all([
            Grade(id=ids["ga4"], season_id=ids["sa"], name="One Day Grade 4"),
            Grade(id=ids["ga_jun"], season_id=ids["sa"], name="Juniors", fee_format="exclude"),
            Grade(id=ids["ga_m"], season_id=ids["sa_m"], name="Over 60s"),
            Grade(id=ids["gb4"], season_id=ids["sb"], name="One Day Grade 4"),
            Grade(id=ids["gb_jun"], season_id=ids["sb"], name="Juniors"),
            Grade(id=ids["gb_wom"], season_id=ids["sb"], name="Womens"),
            # North Perth excludes this one; Applecross has no grade of that name.
            Grade(id=ids["gb_sen"], season_id=ids["sb"], name="Seniors B", fee_format="exclude"),
            Grade(id=ids["gb_m"], season_id=ids["sb_m"], name="Over 60s"),
            Grade(id=ids["gb_x"], season_id=ids["sb_x"], name="Cup"),
            Grade(id=ids["gb_old"], season_id=ids["sb_old"], name="One Day Grade 4"),
            Player(id=ids["p_a"], organisation_id=ids["a"], name="Castley, Angus"),
            Player(id=ids["p_b"], organisation_id=ids["b"], name="Opposition, Olly"),
        ])
        await db.flush()

        def game(key, grade, when, sides=True):
            # `sides=False` leaves home_org_id/away_org_id unset, as a row is until a club's
            # own sync has touched it: the fee read must not depend on them.
            db.add(Game(id=ids[key], grade_id=ids[grade], played_at=when, home_team="H",
                        away_team="A", status="COMPLETED",
                        home_org_id=ids["b"] if sides else None,
                        away_org_id=ids["a"] if sides else None))

        game("own", "ga4", d(14))                       # under our season row
        game("shared", "gb4", d(7), sides=False)        # under North Perth's row, no side ids
        game("jun", "gb_jun", d(6))                     # our own grade of that name is Exclude
        game("wom", "gb_wom", d(5))                     # no grade of ours: match format default
        game("sen", "gb_sen", d(4))                     # THEIR Exclude is not ours
        game("old", "gb_old", d(400))                   # a different year
        game("masters", "gb_m", d(3))                   # the masters season, by CA GUID
        game("ambiguous", "gb_x", d(2))                 # fits both of our 2026 seasons
        game("unrelated", "gb4", d(8))                  # none of our players is in it
        await db.flush()
        await db.execute(text("UPDATE games SET innings_totals = CAST(:t AS JSONB)"), {"t": PLAYED})
        for g in ("own", "shared", "jun", "wom", "sen", "old", "masters", "ambiguous"):
            db.add(GameAppearance(game_id=ids[g], player_id=ids["p_a"]))
            db.add(GameAppearance(game_id=ids[g], player_id=ids["p_b"]))
        db.add(GameAppearance(game_id=ids["unrelated"], player_id=ids["p_b"]))
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
    await recompute_fee_match_days(str(ids["a"]), str(ids["sa_m"]))
    got = await charged(ids["a"], ids["sa"])
    got_m = await charged(ids["a"], ids["sa_m"])
    angus = {g for g, p in got if p == ids["p_a"]}
    angus_m = {g for g, p in got_m if p == ids["p_a"]}

    check("our own fixture is charged", ids["own"] in angus)
    check("a fixture under the other club's season row is charged to our player, no side ids set",
          ids["shared"] in angus)
    check("a foreign grade that OUR grade of that name excludes is not charged",
          ids["jun"] in angus, False)
    check("a foreign grade with no grade of ours falls back to the match format", ids["wom"] in angus)
    check("the other club's Exclude does not apply to us", ids["sen"] in angus)
    check("another club's season of a different year is not read", ids["old"] in angus, False)
    check("the opposition's player is not enrolled in our club",
          any(p == ids["p_b"] for g, p in got | got_m), False)
    check("our main season holds exactly Angus's four charged games", len(angus), 4)

    # One game, one fee season.
    check("the masters fixture is charged under the masters season", ids["masters"] in angus_m)
    check("the masters fixture is NOT also charged under the main season", ids["masters"] in angus, False)
    check("the main fixture is NOT also charged under the masters season",
          bool({ids["shared"], ids["own"]} & angus_m), False)
    check("a season that fits both of ours is charged under neither, never twice",
          ids["ambiguous"] in angus or ids["ambiguous"] in angus_m, False)

    # What the read returns: a game none of our players is in is not read at all.
    async with async_session_maker() as db:
        from app.models.db import Grade as G
        grades = {g.id: g for g in (await db.execute(
            select(G).where(G.season_id == ids["sa"]))).scalars().all()}
        games, _ = await fees._season_games(db, ids["a"], ids["sa"], grades)
    read = {g.id for g in games}
    check("a game none of our players is in is not read", ids["unrelated"] in read, False)
    check("(and the read does return the games we are in)", ids["own"] in read)

    # The grade settings screen counts the same games the charge reads.
    async with async_session_maker() as db:
        from app.routers.fees import list_grades
        club = await db.get(Organisation, ids["a"])
        listed = await list_grades(season_id=str(ids["sa"]), _=None, club=club, db=db)
    g4 = next(g for g in listed if g["name"] == "One Day Grade 4")
    check("the grade screen counts our game and the one under the other club's row",
          g4["games"], 2 if not CONTROL else 1)
    # Shown under our own grades only: our game, the shared game and the Juniors game (our Juniors
    # grade). Womens and Seniors B have no grade of ours to sit under; the unrelated game is not read.
    check("(and it is exactly those: not the game none of ours is in)",
          sum(g["games"] for g in listed), 3 if not CONTROL else 1)

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
    check("a paid shared-game row survives a rebuild",
          ids["shared"] in {g for g, p in await charged(ids["a"], ids["sa"]) if p == ids["p_a"]})

    # The other club, from its own side: charges ITS player, never ours.
    await recompute_fee_match_days(str(ids["b"]), str(ids["sb"]))
    gotb = await charged(ids["b"], ids["sb"])
    check("the other club charges its own player for the same game",
          (ids["shared"], ids["p_b"]) in gotb)
    check("the other club never enrols our player", any(p == ids["p_a"] for g, p in gotb), False)

    print(f"\n{PASS} passed, {FAIL} failed" + (" (control run)" if CONTROL else ""))
    sys.exit(0 if (FAIL == 0 or CONTROL) else 1)


if __name__ == "__main__":
    asyncio.run(main())
