"""How much of a player's career can be broken down at all.

THE PROBLEM THIS EXISTS TO STATE OUT LOUD. A career carries two match counts
and a filter switches between them:

  no filter  -> ``SUM(player_season_stats.matches)``, Cricket Australia's own
                season totals, which carry no grade at all
  any filter -> ``COUNT(DISTINCT game)`` over the scorecards we hold, because
                a grade is only recorded on a match

So picking a competition, a grade type or a format can move the matches figure
in either direction, and the per-competition figures do not sum to the career
total. Measured across the platform (95,151 players): the two sources agree
for 41%, we hold more than CA counts for 20% (worst +221) and CA counts more
than we hold for 39% (worst -484). Neither is wrong and neither can be made to
follow the other without renumbering tens of thousands of careers, so the
figures stay as they are and the page says why they differ.

**A MATCH WITH NO SCORECARD IS NOT AN UNASSIGNED MATCH.** The obvious reading
is that the shortfall is games sitting in a grade nobody grouped, which an
admin could go and fix. Checked against three clubs and it is not: Applecross
(22 grades), Payneham (112) and Hamilton Veterans (4) each have ZERO grades
outside a competition, and their per-competition figures sum exactly to their
club totals. The shortfall is matches CA credits a player with that we hold no
game row for at all — there is nothing to assign, because the match is not in
the database in any form. A grade genuinely outside a competition is a real and
separate thing, and is already reported as its own "Other grades" row.
"""
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.game_status import appearance_counts_as_match

_APPEARANCE_PLAYED = appearance_counts_as_match("ga")

# A game is this club's when it owns the fixture or is one of the two sides —
# the same predicate every other per-game read uses, so this count cannot
# disagree with the boards about which matches are ours.
_OURS = (
    " AND (g.organisation_id = CAST(:org AS UUID)"
    " OR g.home_org_id = CAST(:org AS UUID)"
    " OR g.away_org_id = CAST(:org AS UUID))"
)


async def scorecard_matches(
    session: AsyncSession, player_id: str, org_id, season_id: Optional[str] = None
) -> int:
    """Distinct matches we hold a game row for, however the player featured.

    The same four sources `_scoped_games_played` unions — a batting innings, a
    bowling spell, a fielding row, or a bare appearance in a fixture that was
    actually played — so this is exactly what a filtered figure is counted
    from, and the difference against the career total is exactly what a filter
    can never reach.

    A GRADE-LESS GAME STILL COUNTS HERE. An uploaded scorecard with no grade
    picked belongs to no competition, but we do hold the match — so filing it
    under "we have no scorecard for this" would blame the wrong thing and send
    an admin looking for a game that is right there. It is a real and separate
    state, already reported on its own by `competition_stats.unattributed`.

    Season comes from the view's own column, never from a join through the
    grade: a manual game legitimately has no grade and always has a season.
    """
    params: dict = {"pid": str(player_id), "org": str(org_id)}
    season_clause = ""
    if season_id:
        from app.services.season_aliases import resolve_season_filter
        ids = await resolve_season_filter(session, str(org_id), str(season_id),
                                          include_shared=True)
        if ids:
            params["sids"] = ids
            season_clause = " AND g.season_id = ANY(:sids)"
    res = await session.execute(
        text(f"""
            SELECT COUNT(DISTINCT g.id)
              FROM v_effective_games g
             WHERE g.id IN (
                    SELECT bi.game_id FROM v_effective_batting_innings bi
                     WHERE bi.player_id = CAST(:pid AS UUID)
                    UNION
                    SELECT bs.game_id FROM v_effective_bowling_spells bs
                     WHERE bs.player_id = CAST(:pid AS UUID)
                    UNION
                    SELECT fs.game_id FROM v_effective_fielding_stats fs
                     WHERE fs.player_id = CAST(:pid AS UUID)
                    UNION
                    SELECT ga.game_id FROM game_appearances ga
                     WHERE ga.player_id = CAST(:pid AS UUID) AND {_APPEARANCE_PLAYED}
             ){_OURS}{season_clause}
        """),
        params,
    )
    return int(res.scalar() or 0)


async def aggregate_matches(
    session: AsyncSession, player_id: str, season_id: Optional[str] = None
) -> Optional[int]:
    """Cricket Australia's own matches-played total, whatever filter is on.

    The same `SUM(pss.matches)` over `v_effective_player_season_stats` that
    `get_career_batting`'s unfiltered branch reads, so the note quotes exactly
    the number the headline shows when nothing is picked. Deliberately NOT the
    career figure the caller already has: with a filter on, that figure has
    already switched source to the scorecards, and comparing the scorecards
    against themselves would draw no note at the very moment somebody is
    looking at a filtered figure and wondering why it moved.

    The view is org-scoped internally (migration 060), so a season row
    belonging to another club cannot reach this sum.
    """
    from app.services.season_aliases import resolve_season_filter_no_org

    season_ids = await resolve_season_filter_no_org(session, season_id)
    params: dict = {"pid": str(player_id)}
    season_clause = ""
    if season_ids:
        params["sids"] = season_ids
        season_clause = " AND pss.season_id = ANY(:sids)"
    res = await session.execute(
        text(f"""
            SELECT COALESCE(SUM(pss.matches), 0)
              FROM v_effective_player_season_stats pss
             WHERE pss.player_id = CAST(:pid AS UUID){season_clause}
        """),
        params,
    )
    val = res.scalar()
    return int(val) if val is not None else None


async def career_coverage(
    session: AsyncSession,
    player_id: str,
    org_id,
    season_id: Optional[str] = None,
) -> Optional[dict]:
    """What a breakdown of this career can and cannot reach.

    Deliberately reads BOTH figures itself rather than taking the caller's
    current one, so it says the same thing whether or not a filter is on. The
    difference is a fact about the career, not about the view — and with a
    filter on the caller's figure has already switched to the scorecards, so
    passing it in would compare them against themselves and draw no note at the
    very moment somebody is looking at a moved number.

    Returns None when there is nothing to say — the two agree, or neither
    source has anything — so a profile that needs no note draws none. A note on
    every player is noise that teaches people to stop reading notes, the same
    rule `rate_coverage` keeps for a strike rate.

    `breakdown_matches` is what any filter counts from, so the per-competition
    rows sum to it by construction. `without_scorecard` is the rest: matches
    Cricket Australia's season totals credit this player with and we hold no
    game row for. It runs the other way too — we hold more scorecards than CA
    counts — which is why the caller gets both figures rather than one
    "missing" number.
    """
    claimed = await aggregate_matches(session, player_id, season_id)
    held = await scorecard_matches(session, player_id, org_id, season_id)
    if claimed is None or claimed == held:
        return None
    if not claimed and not held:
        return None
    return {
        "career_matches": claimed,
        "breakdown_matches": held,
        "without_scorecard": max(claimed - held, 0),
        "extra_scorecards": max(held - claimed, 0),
    }
