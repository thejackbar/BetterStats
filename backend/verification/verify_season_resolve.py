"""A game brings its own season with it.

Reported off a live club: a scorecard uploaded from a 1974 PDF was filed
under Summer 1999/00. The season dropdown only offers seasons the club
already has, the club's list starts at 1996/97, and the form requires one —
so the game went in under whatever was on the list and could then be found
by no season filter at all.

This runs the SHIPPED route bodies and services (imported, nothing retyped)
against a real Postgres. Run it against the previous commit and checks fail
on exactly the reported behaviour.

    python -m verification.verify_season_resolve
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base, Grade, ManualGame, Organisation, Player, Season, User
from app.routers.manual_entries import (
    ManualGameIn,
    create_manual_game,
    season_for_date,
    update_manual_game,
)
from app.services import season_resolve as sr

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres@localhost:55432/verify_season_resolve",
)

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


async def main() -> int:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        org = Organisation(id=uuid.uuid4(), name="Collegians Cricket Club", slug="collegians-sr")
        other = Organisation(id=uuid.uuid4(), name="Newry", slug="newry-sr")
        user = User(id=uuid.uuid4(), username="admin-sr", email="a@b.c", password_hash="x")
        db.add_all([org, other, user])
        await db.flush()

        # The club's own list, matching the reported one: nothing before 1996/97.
        seasons = {}
        for y in (1996, 1999, 2025):
            s = Season(id=uuid.uuid4(), organisation_id=org.id, grassroots_id=f"ca-{y}",
                       name=f"Summer {y}/{(y + 1) % 100:02d}", year=y)
            db.add(s)
            seasons[y] = s
        await db.flush()
        g99 = Grade(id=uuid.uuid4(), season_id=seasons[1999].id, name="2nd Grade")
        db.add(g99)
        player = Player(id=uuid.uuid4(), organisation_id=org.id, name="Smith, John")
        db.add(player)
        await db.flush()
        await db.commit()

        print("\nWhich season a date belongs to")
        check("a November game is that year's season",
              sr.season_year_for_date(dt.date(1974, 11, 30)) == 1974)
        check("a February game belongs to the year before",
              sr.season_year_for_date(dt.date(1975, 2, 8)) == 1974)
        check("July is the boundary the rest of the app already uses",
              sr.season_year_for_date(dt.date(1975, 7, 1)) == 1975
              and sr.season_year_for_date(dt.date(1975, 6, 30)) == 1974)
        check("no date, no answer", sr.season_year_for_date(None) is None)
        check("the year is named the way the club's list names one",
              sr.canonical_name(1974) == "Summer 1974/75"
              and sr.canonical_name(1999) == "Summer 1999/00")
        check("a season name parses back to its year",
              sr.season_start_year("Summer 1968/69") == 1968
              and sr.season_start_year("1968-69") == 1968)
        check("a name that is not a consecutive pair is not a season token",
              sr.season_start_year("1968/72") is None)

        print("\nThe reported case, replayed through the shipped route")
        # Exactly what the upload page sends once it stops being able to
        # pick a wrong season: no season_id, just the card's own date.
        body = ManualGameIn(
            played_at="1974-11-30", home_team="Newry", away_team="Collegians 2nd XI",
            opposition="Newry", grade_name="2nd Grade",
            winning_team="Collegians 2nd XI", result="WIN",
        )
        made = await create_manual_game(body, user, org, db)
        game = await db.get(ManualGame, uuid.UUID(made["id"]))
        season = await db.get(Season, game.season_id)
        check("the game is filed under its own year, not 1999/00",
              season.name == "Summer 1974/75", season.name)
        check("that season now exists on the club's list", season.year == 1974, str(season.year))
        check("it is marked as not from a sync", season.grassroots_id is None)
        check("the season belongs to this club", season.organisation_id == org.id)

        grade = await db.get(Grade, game.grade_id) if game.grade_id else None
        check("the game keeps a grade", grade is not None)
        check("that grade sits in the NEW season, not the old one",
              grade is not None and grade.season_id == season.id)
        check("the grade is named off the card", grade is not None and grade.name == "2nd Grade")
        check("a created grade carries its category AND categories",
              grade is not None and grade.category and grade.categories,
              f"{getattr(grade, 'category', None)} / {getattr(grade, 'categories', None)}")

        print("\nThe club's existing seasons are reused, never duplicated")
        body2 = ManualGameIn(played_at="1999-11-06", home_team="A", away_team="B",
                             grade_name="2nd Grade")
        made2 = await create_manual_game(body2, user, org, db)
        g2 = await db.get(ManualGame, uuid.UUID(made2["id"]))
        check("a 1999 game lands on the club's own 1999/00 season",
              g2.season_id == seasons[1999].id)
        check("its existing grade is reused rather than a second one made",
              g2.grade_id == g99.id)

        body3 = ManualGameIn(played_at="1974-12-14", home_team="A", away_team="B")
        made3 = await create_manual_game(body3, user, org, db)
        g3 = await db.get(ManualGame, uuid.UUID(made3["id"]))
        check("a second 1974 game reuses the season just created",
              g3.season_id == season.id)
        count = len((await db.execute(
            select(Season).where(Season.organisation_id == org.id, Season.year == 1974)
        )).scalars().all())
        check("so the club has exactly one 1974/75 season", count == 1, f"{count} rows")

        print("\nAn explicit choice still wins")
        body4 = ManualGameIn(season_id=str(seasons[2025].id), played_at="1974-11-30",
                             home_team="A", away_team="B")
        made4 = await create_manual_game(body4, user, org, db)
        g4 = await db.get(ManualGame, uuid.UUID(made4["id"]))
        check("a season the admin picked is honoured, date or no date",
              g4.season_id == seasons[2025].id)

        print("\nRefusals")
        try:
            await create_manual_game(
                ManualGameIn(home_team="A", away_team="B"), user, org, db)
            refused = None
        except Exception as exc:  # noqa: BLE001
            refused = str(exc)
        check("a game with neither a season nor a date is refused",
              refused is not None and "date" in refused.lower(),
              refused or "accepted")

        try:
            await create_manual_game(
                ManualGameIn(season_id=str(uuid.uuid4()), played_at="1974-11-30",
                             home_team="A", away_team="B"), user, org, db)
            foreign = None
        except Exception as exc:  # noqa: BLE001
            foreign = str(exc)
        check("a season that is not this club's is refused", foreign is not None,
              foreign or "accepted")

        print("\nWhat the upload screen is told before it imports anything")
        told = await season_for_date("1974-11-30", user, org, db)
        check("it reports the year and its name",
              told["year"] == 1974 and told["expected_name"] == "Summer 1974/75", str(told))
        check("it names the club's season now that one exists",
              told["season"] and told["season"]["id"] == str(season.id))

        # A year the club still has no row for — the state the report was about.
        told2 = await season_for_date("1961-01-14", user, org, db)
        check("a year the club has no row for reports none",
              told2["season"] is None and told2["expected_name"] == "Summer 1960/61", str(told2))
        check("asking never creates anything",
              (await db.execute(select(Season).where(
                  Season.organisation_id == org.id, Season.year == 1960))).scalar_one_or_none() is None)

        try:
            await season_for_date("not-a-date", user, org, db)
            bad = None
        except Exception as exc:  # noqa: BLE001
            bad = str(exc)
        check("an unreadable date is refused", bad is not None, bad or "accepted")

        print("\nCorrecting a misread date moves the game with it")
        patch = ManualGameIn(played_at="1975-11-30", home_team="Newry",
                             away_team="Collegians 2nd XI", grade_name="2nd Grade")
        await update_manual_game(str(game.id), patch, user, org, db)
        moved = await db.get(ManualGame, game.id)
        await db.refresh(moved)
        s_moved = await db.get(Season, moved.season_id)
        check("the game follows its corrected date to 1975/76",
              s_moved.name == "Summer 1975/76", s_moved.name)

        print("\nA season is never taken from another club")
        s_other = Season(id=uuid.uuid4(), organisation_id=other.id, grassroots_id=None,
                         name="Summer 1974/75", year=1974)
        db.add(s_other)
        await db.flush()
        found = await sr.find_season_for_year(db, org.id, 1974)
        check("the other club's 1974/75 is not offered to us",
              found is not None and found.organisation_id == org.id)

        print("\nA season whose year is only in its name still counts")
        bare = Season(id=uuid.uuid4(), organisation_id=org.id, grassroots_id=None,
                      name="1980/81", year=None)
        db.add(bare)
        await db.flush()
        hit = await sr.find_season_for_year(db, org.id, 1980)
        check("a NULL year column is read off the name instead",
              hit is not None and hit.id == bare.id)
        made5 = await create_manual_game(
            ManualGameIn(played_at="1980-12-06", home_team="A", away_team="B"), user, org, db)
        g5 = await db.get(ManualGame, uuid.UUID(made5["id"]))
        check("so a game joins it rather than minting a duplicate",
              g5.season_id == bare.id)

        print("\nWhen a year holds several seasons")
        winter = Season(id=uuid.uuid4(), organisation_id=org.id, grassroots_id="ca-w1999",
                        name="Winter 1999/00", year=1999)
        db.add(winter)
        await db.flush()
        pick = await sr.find_season_for_year(db, org.id, 1999)
        check("the canonically named one is preferred over a sibling",
              pick is not None and pick.id == seasons[1999].id,
              pick.name if pick else "none")

        print("\nTelling a misfiled game from a correctly filed one")
        check("a 1974 game in 1999/00 reads as misfiled",
              not sr.season_matches_date(seasons[1999], dt.date(1974, 11, 30)))
        check("a 1999 game in 1999/00 reads as fine",
              sr.season_matches_date(seasons[1999], dt.date(1999, 11, 6)))
        check("a season with no readable year says nothing rather than guessing",
              sr.season_matches_date(
                  Season(id=uuid.uuid4(), organisation_id=org.id, name="Centenary", year=None),
                  dt.date(1974, 11, 30)))

        # A game already filed wrongly — exactly the shape the live report
        # described, and what the repair script exists to move.
        misfiled = ManualGame(
            id=uuid.uuid4(), organisation_id=org.id, season_id=seasons[1999].id,
            grade_id=g99.id, played_at=dt.date(1961, 1, 14),
            home_team="Newry", away_team="Collegians 2nd XI",
        )
        # One that is filed correctly, as the control for the script's own scope.
        fine = ManualGame(
            id=uuid.uuid4(), organisation_id=org.id, season_id=seasons[1999].id,
            grade_id=g99.id, played_at=dt.date(1999, 12, 4),
            home_team="A", away_team="B",
        )
        # And one with no date at all, which there is nothing to judge.
        undated = ManualGame(
            id=uuid.uuid4(), organisation_id=org.id, season_id=seasons[1999].id,
            played_at=None, home_team="A", away_team="B",
        )
        db.add_all([misfiled, fine, undated])
        await db.commit()

    print("\nRepairing a game that is already filed wrongly")
    from app.scripts.refile_manual_game_seasons import run as refile_run

    await refile_run(str(org.id), apply=False)
    async with Session() as db:
        still = await db.get(ManualGame, misfiled.id)
        check("a dry run moves nothing", still.season_id == seasons[1999].id)

    await refile_run(str(org.id), apply=True)
    async with Session() as db:
        fixed = await db.get(ManualGame, misfiled.id)
        s_fixed = await db.get(Season, fixed.season_id)
        check("the misfiled game is moved to its own season",
              s_fixed.name == "Summer 1960/61", s_fixed.name)
        g_fixed = await db.get(Grade, fixed.grade_id)
        check("its grade is carried across by name into that season",
              g_fixed is not None and g_fixed.name == "2nd Grade"
              and g_fixed.season_id == fixed.season_id,
              f"{getattr(g_fixed, 'name', None)} in {getattr(g_fixed, 'season_id', None)}")
        check("a correctly filed game is left alone",
              (await db.get(ManualGame, fine.id)).season_id == seasons[1999].id)
        check("a game with no date is left alone",
              (await db.get(ManualGame, undated.id)).season_id == seasons[1999].id)

        await refile_run(str(org.id), apply=True)
        again = await db.get(ManualGame, misfiled.id)
        await db.refresh(again)
        check("re-running moves nothing further", again.season_id == fixed.season_id)
        n60 = len((await db.execute(select(Season).where(
            Season.organisation_id == org.id, Season.year == 1960))).scalars().all())
        check("and mints no second 1960/61 season", n60 == 1, f"{n60} rows")

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
