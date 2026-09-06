"""One club's view of every grade its own games were played in.

A CA fixture between two clubs that BOTH sync BetterCricket is a single
``games`` row, and its ``grade_id`` — and so its ``season_id`` — points at
whichever club synced it first. **The fixture is not that club's property.**
Both sides played it, both sides' scorecards hang off it, and both sides'
statistics have to count it.

Everything that goes wrong when a read forgets that comes back to one of two
shapes:

* **The read scopes by the grade's owner** (``seasons.organisation_id``), so
  the other club's own matches silently vanish from its own leaderboard. Use
  :func:`club_game_clause` / :data:`CLUB_GAME_SQL` instead: a game is ours when
  it is our own fixture (``organisation_id``, migration 169) **or when we are
  one of the two sides** (``home_org_id``/``away_org_id``, migration 167).
* **The read classifies by the grade ROW** and finds a row it does not own, so
  it cannot say what the grade is. ``grade_scope``'s category filter is an
  exclusion, so an unclassifiable grade is KEPT — and a senior fixture then
  turns up under Juniors as well as under Men's, counted twice over. That is
  the reported Shoalwater Bay case: 28 senior Peel Cricket Association matches
  reading as junior cricket because the grade row belonged to the other club.

:func:`club_grade_rows` is the fix for the second shape. It enumerates the
club's OWN grades plus every grade row its games actually sit in, and resolves
each one to the club's own answer:

* the effective **name key**, folded through the club's own grade merges, so
  the other club's "A Grade" reads as our "A Grade Wyllie Cup";
* the **competition** it belongs to, taken from our own grade of that name, and
  failing that from our competition running the same association. A foreign
  grade's own ``competition_id`` is never read — it belongs to another club's
  competition list and naming our figures after it would be that club's label
  on our page.

Nothing here reads another club's PLAYERS, stats or contact data. It reads the
name and the association of a grade our own club played in, which is on the
fixture card either way.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.grade_labels import grade_alias_map, grade_key


def club_game_sql(alias: str = "g", param: str = "club_org") -> str:
    """The predicate for "this game is our club's", as a bare condition.

    Written as a CAST rather than a bare ``:param IS NULL`` — asyncpg cannot
    infer a bound parameter's type from that and raises at execute time.
    A NULL org matches everything, which is the answer the query gave before
    any club scoping existed.
    """
    o = f"CAST(:{param} AS UUID)"
    return (f"({o} IS NULL"
            f" OR {alias}.organisation_id = {o}"
            f" OR {alias}.home_org_id = {o}"
            f" OR {alias}.away_org_id = {o})")


def club_game_clause(alias: str = "g", param: str = "club_org") -> str:
    """:func:`club_game_sql` with a leading ``AND``, for pasting into a WHERE."""
    return " AND " + club_game_sql(alias, param)


class ClubGrade:
    """One grade row as this club sees it."""

    __slots__ = ("id", "name", "key", "is_own", "competition_id", "association_id")

    def __init__(self, id, name, key, is_own, competition_id, association_id):
        self.id = id
        self.name = name
        self.key = key
        self.is_own = is_own
        self.competition_id = competition_id
        self.association_id = association_id


async def club_grade_rows(session: AsyncSession, org_id) -> list[ClubGrade]:
    """Every grade this club's stats can land in, resolved to the club's answer.

    Two sources unioned:

    1. the club's own grades (``grades`` under its own seasons), and
    2. every grade row its own GAMES sit in, which for a shared fixture is the
       other club's row.

    The second arm is what closes the leak. It reads
    ``idx_games_home_org_id``/``idx_games_away_org_id`` (migration 167), so it
    costs two index scans rather than a table scan.
    """
    if not org_id:
        return []
    res = await session.execute(
        text(
            """
            SELECT gr.id, gr.name, gr.competition_id, gr.association_id,
                   (s.organisation_id = CAST(:org AS UUID)) AS is_own
            FROM grades gr
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = CAST(:org AS UUID)
               OR gr.id IN (
                    SELECT DISTINCT g.grade_id FROM games g
                    WHERE g.grade_id IS NOT NULL
                      AND (g.home_org_id = CAST(:org AS UUID)
                           OR g.away_org_id = CAST(:org AS UUID))
               )
            """
        ),
        {"org": str(org_id)},
    )
    raw = res.fetchall()
    aliases = await grade_alias_map(session, org_id)

    # The club's own answer per name key: which competition that name belongs
    # to, taken from a row that actually carries one so an unassigned sibling
    # season's row cannot blank it.
    own_comp_by_key: dict[str, object] = {}
    own_keys: set[str] = set()
    comp_by_association: dict[str, object] = {}
    for gid, name, comp_id, assoc_id, is_own in raw:
        if not is_own:
            continue
        key = aliases.get(grade_key(name), grade_key(name))
        own_keys.add(key)
        if comp_id is not None:
            own_comp_by_key.setdefault(key, comp_id)
            if assoc_id:
                comp_by_association.setdefault(str(assoc_id), comp_id)

    out: list[ClubGrade] = []
    for gid, name, comp_id, assoc_id, is_own in raw:
        key = aliases.get(grade_key(name), grade_key(name))
        if is_own:
            resolved = comp_id
        else:
            # NEVER the foreign row's own competition_id — that is another
            # club's competition, and its name has no business labelling our
            # figures. Our own grade of the same name first, then whichever of
            # our competitions runs the same association.
            if key in own_keys:
                # We hold this grade under this name. Whatever answer we gave
                # it — including "not grouped yet" — is the answer here too,
                # or the same grade would read one way on our own fixture and
                # another on the shared one.
                resolved = own_comp_by_key.get(key)
            elif assoc_id:
                # A name we have never held. The association CA records on the
                # grade is the only thing left that is ours to match on, and it
                # is exact: `club_competitions.association_id` is the same CA
                # org GUID.
                resolved = comp_by_association.get(str(assoc_id))
            else:
                resolved = None
        out.append(ClubGrade(gid, name, key, bool(is_own), resolved, assoc_id))
    return out


async def club_grade_competitions(session: AsyncSession, org_id) -> dict:
    """``{grade_id: competition_id or None}`` for every grade in scope.

    What a breakdown grouped BY competition needs: it replaces reading
    ``grades.competition_id`` directly, which is NULL for a shared fixture's
    grade (so the match falls into "Other grades") or, once the other club has
    grouped its own grades, is that club's competition row.
    """
    return {str(r.id): r.competition_id for r in await club_grade_rows(session, org_id)}
