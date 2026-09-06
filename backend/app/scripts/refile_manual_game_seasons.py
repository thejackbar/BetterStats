"""Re-file manually created games whose season disagrees with their date.

WHY THIS EXISTS
---------------
Reported off a live club: a scorecard uploaded from a 1974 PDF sat under
Summer 1999/00. The season dropdown only ever offered seasons the club
already had, its own list started at 1996/97, and the form required a
season — so the game went in under whatever was on the list and could not
be found by any season filter afterwards.

The upload path resolves and creates the right season itself now, but a
game already filed wrongly stays wrong until something moves it. This is
that something.

WHAT IT DOES
------------
For every manual game whose `played_at` falls outside the season it is
filed under, moves it to that club's season for the right year — creating
the season when the club has none, and re-creating the game's grade by name
inside it so the game keeps its grade rather than losing it in the move.

WHAT IT WILL NOT TOUCH
----------------------
- A game with no date. There is nothing to check it against.
- A game whose season carries no readable year (no "1974/75" token and no
  `year` column). "We cannot tell" is not "it is wrong".
- Synced games. `games` rows come from Cricket Australia's own season and
  grade ids; this is only ever about manually created ones.

A game an admin deliberately filed against a season its date falls outside
is indistinguishable from a mistake by the data alone, so this is dry-run by
default, prints every move it would make, and takes one club at a time — a
person reads the list before anything moves. Same posture as
`purge_import_only_players`.

    python -m app.scripts.refile_manual_game_seasons <org-id-or-slug|all>
    python -m app.scripts.refile_manual_game_seasons applecross --apply
"""

from __future__ import annotations

import asyncio
import sys
import uuid

from sqlalchemy import select

from app.models.db import Grade, ManualGame, Organisation, Season, async_session_maker
from app.services.season_resolve import (
    canonical_name,
    ensure_grade,
    ensure_season_for_year,
    season_matches_date,
    season_year_for_date,
)


async def _orgs(session, ref: str) -> list[Organisation]:
    if ref == "all":
        return list((await session.execute(select(Organisation))).scalars().all())
    try:
        org = await session.get(Organisation, uuid.UUID(ref))
    except ValueError:
        org = (await session.execute(
            select(Organisation).where(Organisation.slug == ref)
        )).scalar_one_or_none()
    return [org] if org else []


async def run(ref: str, apply: bool) -> int:
    moved = skipped = 0
    async with async_session_maker() as session:
        orgs = await _orgs(session, ref)
        if not orgs:
            print(f"No club matched '{ref}'.")
            return 1

        for org in orgs:
            games = list((await session.execute(
                select(ManualGame).where(ManualGame.organisation_id == org.id)
            )).scalars().all())
            if not games:
                continue

            header_shown = False
            for game in games:
                if game.played_at is None:
                    continue
                season = await session.get(Season, game.season_id)
                if season is None or season_matches_date(season, game.played_at):
                    continue

                year = season_year_for_date(game.played_at)
                grade = await session.get(Grade, game.grade_id) if game.grade_id else None
                label = (
                    f"{game.played_at}  {game.home_team or '?'} v {game.away_team or '?'}"
                    f"  [{season.name}"
                    + (f" / {grade.name}" if grade else "")
                    + "]"
                )

                if not header_shown:
                    print(f"\n{org.name} ({org.slug})")
                    header_shown = True

                if not apply:
                    print(f"  WOULD MOVE  {label}  ->  {canonical_name(year)}")
                    moved += 1
                    continue

                new_season, season_created = await ensure_season_for_year(
                    session, org.id, year
                )
                note = f"  MOVED  {label}  ->  {new_season.name}"
                if season_created:
                    note += "  (season created)"

                # Carry the grade across by NAME. The game's own grade row
                # belongs to the wrong season, so pointing at it would leave
                # the game's grade and season contradicting each other.
                if grade is not None:
                    new_grade, grade_created = await ensure_grade(
                        session, new_season, grade.name
                    )
                    if new_grade is not None:
                        game.grade_id = new_grade.id
                        if grade_created:
                            note += f"  (grade '{new_grade.name}' created)"

                game.season_id = new_season.id
                print(note)
                moved += 1

            skipped += len(games)

        if apply:
            await session.commit()

    print(
        f"\n{moved} game(s) {'moved' if apply else 'would move'}"
        f" out of {skipped} manual game(s) checked."
    )
    if moved and not apply:
        print("Re-run with --apply to move them.")
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv[1:]
    if len(args) != 1:
        print(__doc__)
        return 2
    return asyncio.run(run(args[0], apply))


if __name__ == "__main__":
    raise SystemExit(main())
