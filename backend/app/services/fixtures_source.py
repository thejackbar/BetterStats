"""Upcoming fixtures sourced from the Grassroots /scores/* API.

Replaces the retired PlayHQ Partner ``get_org_games`` path. The org's grades are
read from our own DB (DB-first); only the not-yet-played fixtures — which we
don't persist until a match is synced — are fetched live from Grassroots via
``/scores/grades/{id}/matches`` (status 0=UPCOMING / 2=LIVE).
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import grassroots_scores_client as gr
from app.services.club_match import club_match_keys


async def _current_grade_rows(db: AsyncSession, org_id) -> list[tuple]:
    """``[(grade_guid, grade_name, season_name)]`` for the org's latest season.

    The raw CA grade GUID (``grassroots_id``, COALESCE'd with ``id`` for legacy
    rows) is what ``/scores/grades/{id}/matches`` is keyed on. Restricting to the
    org's most-recent season year keeps this to ~one season of grades rather than
    fanning out across all of history.
    """
    res = await db.execute(
        text(
            """
            SELECT DISTINCT COALESCE(g.grassroots_id, g.id::text) AS guid,
                   COALESCE(g.display_name_override, g.name) AS grade_name,
                   s.name AS season_name
            FROM grades g
            JOIN seasons s ON s.id = g.season_id
            WHERE s.organisation_id = CAST(:org AS UUID)
              AND s.year = (
                  SELECT MAX(year) FROM seasons
                  WHERE organisation_id = CAST(:org AS UUID) AND year IS NOT NULL
              )
            """
        ),
        {"org": str(org_id)},
    )
    return [(r.guid, r.grade_name, r.season_name) for r in res]


async def org_grassroots_fixtures(db: AsyncSession, org) -> list[dict]:
    """Upcoming/live fixtures for the org, filtered to its own games.

    Each fixture carries ``grade_name``/``season_name`` (resolved from the DB
    grade it came from) on top of the normalised
    ``grassroots_scores_client.get_grade_fixtures`` shape.
    """
    rows = await _current_grade_rows(db, org.id)
    if not rows:
        return []
    meta = {guid: (gname, sname) for guid, gname, sname in rows}
    fixtures = await gr.get_grades_fixtures(
        [guid for guid, _, _ in rows], club_match_keys(org)
    )
    for fx in fixtures:
        gname, sname = meta.get(fx.get("grade_id"), (None, None))
        fx["grade_name"] = gname
        fx["season_name"] = sname
    return fixtures
