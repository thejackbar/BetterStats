"""Upcoming fixtures sourced from the Grassroots /scores/* API.

Replaces the retired PlayHQ Partner ``get_org_games`` path. The org's grades are
read from our own DB (DB-first); only the not-yet-played fixtures — which we
don't persist until a match is synced — are fetched live from Grassroots via
``/scores/grades/{id}/matches`` (status 0=UPCOMING / 2=LIVE).
"""
from typing import NamedTuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import grassroots_scores_client as gr
from app.services.club_match import club_match_keys
from app.services.grade_labels import category_for_name, category_label, org_grade_categories


class GradeRow(NamedTuple):
    """One of the org's current-season grades, as ``_current_grade_rows`` returns it.

    A NamedTuple rather than a bare tuple ON PURPOSE. This started life as a
    3-tuple; ``our_grade_id`` was added for a caller that needed to stamp a real
    ``grades.id`` FK, and the other caller's ``for guid, gname, _ in rows`` kept
    compiling and kept passing ``py_compile`` while raising "too many values to
    unpack (expected 3)" on every request — which took the whole BetterPosts
    Results tab down for every club until it was reported from the wild. Read the
    fields by NAME, and a fifth column can be added here without silently
    breaking a caller that doesn't want it.
    """

    guid: str
    """The RAW Cricket Australia grade GUID. What ``/scores/grades/{id}/matches``
    is keyed on, and what a discovered match carries as its ``grade_id`` — so
    it's also the right key for a lookup built off upstream match payloads."""

    our_grade_id: object
    """Our own ``grades.id`` PK. NOT always the same as ``guid`` (a per-club
    ``uuid5`` on a cross-club collision, see the grade-collision note in
    CLAUDE.md), so a caller stamping a real FK must use this, never the guid."""

    grade_name: str | None
    season_name: str | None


async def _current_grade_rows(db: AsyncSession, org_id) -> list[GradeRow]:
    """The org's latest season's grades as :class:`GradeRow`.

    Restricting to the org's most-recent season year keeps this to ~one season of
    grades rather than fanning out across all of history.
    """
    res = await db.execute(
        text(
            """
            SELECT DISTINCT COALESCE(g.grassroots_id, g.id::text) AS guid,
                   g.id AS grade_id,
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
    return [GradeRow(r.guid, r.grade_id, r.grade_name, r.season_name) for r in res]


async def org_grassroots_fixtures(db: AsyncSession, org) -> list[dict]:
    """Upcoming/live fixtures for the org, filtered to its own games.

    Each fixture carries ``grade_name``/``season_name`` (resolved from the DB
    grade it came from) on top of the normalised
    ``grassroots_scores_client.get_grade_fixtures`` shape, plus ``category``/
    ``category_label`` (the grade's Senior/Junior/Women's/... classification —
    confirmed via `grades.category`, else the name-based suggestion),
    ``is_final`` (round name contains "final" — the same heuristic
    `sync.py` uses to set `games.is_final` once a match is played), and
    ``db_grade_id`` — our own ``grades.id`` for the fixture's grade (distinct
    from the raw CA grade guid returned under ``grade_id``), for a caller that
    needs to stamp a real FK (e.g. persisting a Fixture row).
    """
    rows = await _current_grade_rows(db, org.id)
    if not rows:
        return []
    meta = {r.guid: (r.our_grade_id, r.grade_name, r.season_name) for r in rows}
    categories = await org_grade_categories(db, org.id)
    fixtures = await gr.get_grades_fixtures(
        [r.guid for r in rows], club_match_keys(org)
    )
    for fx in fixtures:
        db_grade_id, gname, sname = meta.get(fx.get("grade_id"), (None, None, None))
        fx["db_grade_id"] = str(db_grade_id) if db_grade_id else None
        fx["grade_name"] = gname
        fx["season_name"] = sname
        cat = category_for_name(categories, gname) if gname else None
        fx["category"] = cat
        fx["category_label"] = category_label(cat) if cat else None
        fx["is_final"] = "final" in (fx.get("round") or "").lower()
    return fixtures
