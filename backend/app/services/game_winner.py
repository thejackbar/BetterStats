"""A decisive result with no winner named on the row.

`games.result` is WIN / LOSS from the point of view of whichever club's sync wrote it, so a fixture
between two synced clubs reads backwards to the other club. `games.winning_team` is the winning
side's NAME and is neutral: every page works out WIN or LOSS for its own club from it. A row that
holds a WIN or LOSS and no winner leaves every reader with only the one club's verdict and no way
to tell whose. Reported off Shoalwater Bay's Ladies B Grade Grand Final (2025/26): Secret Harbour's
sync stored LOSS and no winner, Shoalwater is recorded as the home side, and both the Games list
and the scorecard showed Shoalwater's premiership as a loss.

The sync only fills a missing winner on a game it reads, and an incremental run reads only the
fixtures newer than its window, so such a row was never visited again. ``games_missing_winner``
lists the club's finished games in that state, whatever their age, so the run reads them again and
the existing backfill in ``sync`` (``existing_winner is None``) names the winner from the card.
"""
from __future__ import annotations

from sqlalchemy import text

# Most games one run reads again for this. The state is rare (31 games platform-wide when it was
# found) and each read is one scorecard request.
MAX_REREAD = 50


async def games_missing_winner(db, org_id, cap: int = MAX_REREAD) -> set:
    """Match ids of the club's COMPLETED games that hold a WIN or LOSS and no winning team.

    Games the club played (a recorded side, or its own season), newest first, no age limit.
    A game CA has since marked something other than COMPLETED is left to the other re-read rules.
    """
    res = await db.execute(text("""
        SELECT g.id::text
          FROM games g
          LEFT JOIN grades gr ON gr.id = g.grade_id
          LEFT JOIN seasons s ON s.id = gr.season_id
         WHERE g.result IN ('WIN', 'LOSS')
           AND g.status = 'COMPLETED'
           AND nullif(btrim(g.winning_team), '') IS NULL
           AND (g.home_org_id = CAST(:org AS UUID) OR g.away_org_id = CAST(:org AS UUID)
                OR s.organisation_id = CAST(:org AS UUID))
         ORDER BY g.played_at DESC NULLS LAST
         LIMIT :cap
    """), {"org": str(org_id), "cap": cap})
    return {r[0] for r in res.all()}
