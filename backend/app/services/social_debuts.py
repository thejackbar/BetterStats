"""Which of the players on a BetterSocials lineup are making their debut.

A debut is the club's first game, so the answer is "this player has nothing on
record before the match date". Three sources are read, because a club's history
reaches us three ways and any one of them is enough to rule a debut out:

* a named appearance in a game that was played (synced scorecards),
* a batting or bowling line in the effective views (this is how an imported or
  hand-typed game shows up, which has no `game_appearances` row),
* a season summary from an EARLIER season with matches in it (the years before
  the club's scorecards go back).

The season summary is deliberately limited to earlier seasons. The current
season's own aggregate already contains the match once it has been played, so
counting it would stop a lineup for a game that has been synced from ever
showing a debut.

Abandoned and cancelled fixtures do not count: a player named in a washout never
took the field. Players are scoped by `players.organisation_id`, so a name in a
shared fixture that belongs to another club's register is never read as ours.

The answer is a suggestion. The editor lets the admin switch any player's debut
tag on or off by hand, because a club's own records can be wrong either way (a
player who played for the club under another name, a match nobody scored).
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

MAX_PLAYERS = 40


def season_start_year(on: date) -> int:
    """The calendar year the season containing `on` began in.

    Seasons are stored by the year they START (`seasons.year` is the first four
    characters of CA's start date), and a cricket summer starts in the second
    half of the year, so January to June belongs to the season that began the
    year before.
    """
    return on.year if on.month >= 7 else on.year - 1


def parse_ids(raw: str | None) -> list[str]:
    """Comma separated player ids to a de-duplicated list of valid UUIDs, in order."""
    out: list[str] = []
    seen: set[str] = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            u = str(uuid.UUID(part))
        except ValueError:
            continue
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:MAX_PLAYERS]


_HISTORY_SQL = text("""
    SELECT
        p.id::text AS player_id,
        (
            EXISTS (
                SELECT 1
                FROM game_appearances ga
                JOIN v_effective_games g ON g.id = ga.game_id
                WHERE ga.player_id = p.id
                  AND g.played_at < :before
                  AND COALESCE(g.status, '') NOT IN ('ABANDONED', 'CANCELLED')
            )
            OR EXISTS (
                SELECT 1
                FROM v_effective_batting_innings bi
                JOIN v_effective_games g ON g.id = bi.game_id
                WHERE bi.player_id = p.id
                  AND g.played_at < :before
                  AND COALESCE(g.status, '') NOT IN ('ABANDONED', 'CANCELLED')
            )
            OR EXISTS (
                SELECT 1
                FROM v_effective_bowling_spells bs
                JOIN v_effective_games g ON g.id = bs.game_id
                WHERE bs.player_id = p.id
                  AND g.played_at < :before
                  AND COALESCE(g.status, '') NOT IN ('ABANDONED', 'CANCELLED')
            )
            OR EXISTS (
                SELECT 1
                FROM v_effective_player_season_stats pss
                JOIN seasons s ON s.id = pss.season_id
                WHERE pss.player_id = p.id
                  AND COALESCE(pss.matches, 0) > 0
                  AND s.year IS NOT NULL
                  AND s.year < :season_year
            )
        ) AS has_history
    FROM players p
    WHERE p.organisation_id = :org
      AND p.id = ANY(CAST(:ids AS uuid[]))
""")


async def social_debuts(
    db: AsyncSession, org, player_ids: list[str], before: date | None = None,
) -> dict:
    """`{debuts: [ids], known: [ids], before: iso}` for the given players.

    `known` is every id that is one of this club's players and could be
    answered. An id missing from it (a fill-in with no record, a redacted
    junior) is neither a debut nor a veteran: the editor leaves its tag alone
    rather than guessing.
    """
    on = before or date.today()
    if not player_ids:
        return {"debuts": [], "known": [], "before": on.isoformat()}
    result = await db.execute(
        _HISTORY_SQL,
        {
            "org": org.id,
            "ids": player_ids,
            "before": on,
            "season_year": season_start_year(on),
        },
    )
    rows = result.mappings().all()
    known = [r["player_id"] for r in rows]
    debuts = [r["player_id"] for r in rows if not r["has_history"]]
    return {"debuts": debuts, "known": known, "before": on.isoformat()}
